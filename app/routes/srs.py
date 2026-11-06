"""Active SRS workflows. Email OTP is the agreed authentication amendment."""
import csv
import io
import secrets
from collections import Counter,defaultdict
from decimal import Decimal
from datetime import datetime
from statistics import mean
from flask import Blueprint,abort,flash,redirect,render_template,request,session,url_for,Response
from ..auth import login_required
from ..db import query_all,query_one,execute,execute_returning_id
from .. import gradebook as gb,srs_grading as sg
from ..security import store_preview,load_preview,rate_limit
from ..notifications import notify,notify_many
from ..grading import letter_grade,component_type
from .admin import active_term,log_activity
from .workspace import write_scores

srs_bp=Blueprint('srs',__name__,url_prefix='/app')


def teacher_class(aid,write=False):
    row=gb.classroom(aid,write)
    if row['teacher_id']!=session.get('teacher_id'):abort(404)
    if write:
        if not row['is_active']:abort(409,description='Only classes in the active term can be changed.')
        if request.form.get('revision',type=int)!=row['revision']:abort(409,description='This class changed. Reload and review before saving.')
        if row['status']=='PUBLISHED' and request.form.get('action')!='reopen':abort(409,description='Reopen the published class before making changes. Students will not see draft grades.')
    return row


def bump(row,message,status='IN_PROGRESS'):
    execute('UPDATE teacher_subjects SET status=:state,revision=revision+1 WHERE assignment_id=:id',{'state':status,'id':row['assignment_id']})
    log_activity(f"Class {row['assignment_id']}: {message}");flash(message,'success')


def model(aid):
    row=gb.classroom(aid);cats,components,students,scores=gb.content(aid)
    results={s['enrollment_id']:sg.calculate(cats,components,scores.get(s['enrollment_id'],{}),row.get('grading_model')=='FLEXIBLE',row.get('aggregation','LEGACY')) for s in students}
    return row,cats,components,students,scores,results


def activity_batch(aid, category, name, weight, maximum, components):
    count=request.form.get('activity_count',type=int) if 'activity_count' in request.form else 1
    if count is None or not 1<=count<=50:abort(400,description='Choose between 1 and 50 activities.')
    names=[name if count==1 else f'{name} {i+1}' for i in range(count)]
    existing={c['component_name'].strip().casefold() for c in components}
    if any(len(n.encode())>50 or n.casefold() in existing for n in names):
        abort(400,description='Use unique activity titles of at most 50 bytes, including their numbers.')
    share=(weight/ count).quantize(Decimal('.01'))
    for i,title in enumerate(names):
        allocated=weight-share*(count-1) if i==count-1 else share
        execute('INSERT INTO grade_components(assignment_id,component_name,weight_percent,category_id,maximum_score) VALUES(:aid,:name,:weight,:category,:maximum)',
                dict(aid=aid,name=title,weight=allocated,category=category,maximum=maximum))


@srs_bp.route('/teacher')
@login_required('faculty')
def teacher_home():
    term=active_term();classes=sg.load_classes(term['term_id'] if term else 0,session['teacher_id'])
    return render_template('srs/teacher_home.html',term=term,classes=classes,
        total_students=sum(len(c['students']) for c in classes),recorded=sum(c['recorded'] for c in classes),
        expected=sum(c['expected'] for c in classes))


@srs_bp.route('/teacher/classes')
@login_required('faculty')
def teacher_classes():
    from ..academic import active
    term=active_term()
    if not term or term.get('is_all'):
        current=active()
        if current:return redirect(url_for('srs.teacher_classes',term_filter=current['term_id']))
    classes=sg.load_classes(term['term_id'] if term else 0,session['teacher_id'])
    return render_template('srs/teacher_classes.html',term=term,classes=classes)


@srs_bp.route('/teacher/class/<int:aid>')
@login_required('faculty')
def classroom(aid):
    if request.args.get('tab') in ('settings','weighting'):
        return redirect(url_for('srs.classroom',aid=aid))
    row=teacher_class(aid);_,cats,components,students,scores,results=model(aid)
    q=request.args.get('q','').strip().casefold()
    shown=[s for s in students if not q or q in s['full_name'].casefold() or q in s['id_number'].casefold()]
    check=sg.calculate(cats,components,{},row.get('grading_model')=='FLEXIBLE',row.get('aggregation','LEGACY'))
    groups=[dict(category=c,activities=[a for a in components if a.get('category_id')==c['category_id']],has_scores=any(a['component_id'] in marks for a in components if a.get('category_id')==c['category_id'] for marks in scores.values())) for c in cats]
    return render_template('srs/classroom.html',groups=groups,a=row,term=active_term(),categories=cats if row.get('grading_model')=='FLEXIBLE' else [c for c in cats if c['category_name'].casefold() in ('lecture','laboratory')],components=components,
        students=shown,roster=students,scores=scores,results=results,check=check,q=request.args.get('q',''),
        legacy_components=[c for c in components if c.get('category_id') not in {cat['category_id'] for cat in cats}],
        tab=request.args.get('tab','grades'),locked=row['status']=='PUBLISHED' or not row['is_active'])


@srs_bp.route('/teacher/class/<int:aid>/setup',methods=['POST'])
@login_required('faculty')
def setup(aid):
    row=teacher_class(aid,True);cats,components,students,scores=gb.content(aid);action=request.form.get('action')
    if action in ('category','edit_category','delete_category'):
        cid=request.form.get('category_id',type=int)
        if action=='category':cid=None
        old=next((c for c in cats if c['category_id']==cid),None)
        if action!='category' and not old:abort(404)
        if action=='delete_category':
            if any(c.get('category_id')==cid for c in components):abort(409,description='Remove or move the activities before deleting this grading component.')
            execute('DELETE FROM grade_categories WHERE category_id=:cid AND assignment_id=:aid',dict(cid=cid,aid=aid))
        else:
            name=request.form.get('category_name','').strip()
            if not name or len(name.encode())>50:abort(400,description='Enter a component name of at most 50 bytes.')
            if any(c['category_name'].strip().casefold()==name.casefold() and c['category_id']!=cid for c in cats):abort(400,description='Grading component names must be unique.')
            try:weight=gb.decimal(request.form.get('weight_percent'),0,100)
            except ValueError as error:abort(400,description=str(error))
            if sum(Decimal(str(c['weight_percent'])) for c in cats if c['category_id']!=cid)+weight>100:abort(400,description='Component percentages cannot exceed 100% in total.')
            if action=='category':
                # Validate the entire batch before the first database write.
                if request.form.get('activity_count'):
                    count=request.form.get('activity_count',type=int)
                    title=request.form.get('component_name','').strip() or name
                    if count is None or not 1<=count<=50 or not title:abort(400,description='Enter an activity title and a count from 1 to 50.')
                    titles=[title if count==1 else f'{title} {i+1}' for i in range(count)]
                    if any(len(n.encode())>50 or any(c['component_name'].casefold()==n.casefold() for c in components) for n in titles):abort(400,description='Activity titles must be unique and at most 50 bytes.')
                cid=execute_returning_id('INSERT INTO grade_categories(assignment_id,category_name,weight_percent) VALUES(:aid,:name,:weight) RETURNING category_id INTO :out_id',dict(aid=aid,name=name,weight=weight))
                if request.form.get('activity_count'):activity_batch(aid,cid,title,Decimal(100),None,components)
            else:execute('UPDATE grade_categories SET category_name=:name,weight_percent=:weight WHERE category_id=:cid AND assignment_id=:aid',dict(aid=aid,cid=cid,name=name,weight=weight))
        execute("UPDATE teacher_subjects SET grading_model='FLEXIBLE' WHERE assignment_id=:id",{'id':aid})
    elif action=='split':
        try:lecture=gb.decimal(request.form.get('lecture'),0,100);laboratory=gb.decimal(request.form.get('laboratory'),0,100)
        except ValueError as error:abort(400,description=str(error))
        if lecture+laboratory+sum(Decimal(str(c['weight_percent'])) for c in cats if c['category_name'].strip().casefold() not in ('lecture','laboratory'))>100:abort(400,description='Component percentages cannot exceed 100% in total.')
        # Unfinished allocations may be saved as draft; publication is the validation boundary.
        for name,weight in [('Lecture',lecture),('Laboratory',laboratory)]:
            match=next((c for c in cats if c['category_name'].casefold()==name.casefold()),None)
            if match:execute('UPDATE grade_categories SET weight_percent=:weight WHERE category_id=:id',{'weight':weight,'id':match['category_id']})
            else:execute('INSERT INTO grade_categories(assignment_id,category_name,weight_percent) VALUES(:aid,:name,:weight)',{'aid':aid,'name':name,'weight':weight})
        execute("UPDATE teacher_subjects SET aggregation='LEGACY' WHERE assignment_id=:id",{'id':aid})
    elif action in ('component','edit_component'):
        name=request.form.get('component_name','').strip();cid=request.form.get('category_id',type=int);component=request.form.get('component_id',type=int)
        if not name or len(name.encode())>50:abort(400,description='Enter a component name of at most 50 bytes.')
        if not any(c['category_id']==cid for c in cats):abort(400,description='Choose a grading component in this class.')
        if any(c['component_name'].casefold()==name.casefold() and c['component_id']!=component for c in components):abort(400,description='Component names must be unique within the class.')
        try:weight=gb.decimal(request.form.get('weight_percent'),0,100);maximum=gb.decimal(request.form['maximum_score'],.01,9999) if request.form.get('maximum_score','').strip() else None
        except ValueError as error:abort(400,description=str(error))
        if action=='component':
            activity_batch(aid,cid,name,weight,maximum,components)
        else:
            old=next((c for c in components if c['component_id']==component),None)
            if not old:abort(404)
            if old['maximum_score']!=maximum and any(component in s for s in scores.values()):abort(409,description='Change highest possible scores in the grading sheet together with any affected scores.')
            execute('UPDATE grade_components SET component_name=:name,weight_percent=:weight,category_id=:category,maximum_score=:maximum WHERE component_id=:component AND assignment_id=:aid',{'aid':aid,'name':name,'weight':weight,'category':cid,'maximum':maximum,'component':component})
    elif action=='delete_component':
        component=request.form.get('component_id',type=int)
        if any(component in s for s in scores.values()):abort(409,description='This component has scores. Keep it for academic history or correct its configuration.')
        execute('DELETE FROM grade_components WHERE component_id=:id AND assignment_id=:aid',{'id':component,'aid':aid})
    else:abort(400)
    bump(row,'Grading configuration saved.','DRAFT' if row['status']=='DRAFT' else 'IN_PROGRESS')
    return redirect(url_for('srs.classroom',aid=aid))


@srs_bp.route('/teacher/class/<int:aid>/scores',methods=['POST'])
@login_required('faculty')
def save_scores(aid):
    row=teacher_class(aid,True);cats,components,students,scores=gb.content(aid)
    # Validate all setup and score edits before writing any part of the sheet.
    category_edits=[];activity_edits=[]
    for prefix,rows,id_key,name_key in [('cat',cats,'category_id','category_name'),('activity',components,'component_id','component_name')]:
        known={str(c[id_key]) for c in rows}
        for key in request.form:
            if key.startswith(prefix+'__') and (len(key.split('__'))!=3 or key.split('__')[1] not in known or key.split('__')[2] not in ('name','weight','maximum','count','date')):abort(400,description='An edited column does not belong to this class.')
        names=set()
        for c in rows:
            ident=c[id_key];base=f'{prefix}__{ident}__'
            name=request.form.get(base+'name',c[name_key]).strip()
            if not name or len(name.encode())>50 or name.casefold() in names:abort(400,description='Use unique titles of at most 50 bytes.')
            names.add(name.casefold())
            try:
                weight=gb.decimal(request.form.get(base+'weight',c['weight_percent']),0,100)
                maximum=c.get('maximum_score')
                if prefix=='activity' and base+'maximum' in request.form:
                    raw=request.form[base+'maximum'].strip();maximum=gb.decimal(raw,1,9999) if raw else None
                    if maximum is not None and maximum!=maximum.to_integral_value():raise ValueError('Highest possible scores must be whole numbers.')
            except ValueError as error:abort(400,description=f'{name}: {error}')
            if prefix=='activity':
                activity_date=c.get('activity_date')
                if base+'date' in request.form:
                    raw_date=request.form[base+'date'].strip()
                    try:
                        activity_date=datetime.strptime(raw_date,'%m/%d/%y') if raw_date else None
                        if activity_date and activity_date.strftime('%m/%d/%y')!=raw_date:raise ValueError()
                    except ValueError:abort(400,description='Enter a valid activity date in mm/dd/yy format.')
                activity_edits.append(dict(c,component_name=name,weight_percent=weight,maximum_score=maximum,activity_date=activity_date))
            else:category_edits.append(dict(c,category_name=name,weight_percent=weight))
    components=activity_edits
    allowed={str(s['enrollment_id']) for s in students};items={str(c['component_id']):c for c in components};updates=[]
    for key,value in request.form.items():
        if not key.startswith('mark__'):continue
        parts=key.split('__')
        if len(parts)!=3 or parts[1] not in allowed or parts[2] not in items:abort(400,description='A score does not belong to this class.')
        c=items[parts[2]]
        if value.strip() and c['maximum_score'] is None:abort(400,description=f"{c['component_name']}: set the highest possible score first.")
        try:score=gb.decimal(value,0,c['maximum_score']) if value.strip() else None
        except ValueError as error:abort(400,description=f"{c['component_name']}: {error}")
        if score is not None and score!=score.to_integral_value():abort(400,description='Raw scores must be whole numbers.')
        updates.append((int(parts[1]),c['component_id'],score,c['maximum_score']))
    submitted={(eid,cid):value for eid,cid,value,maximum in updates}
    for c in components:
        for eid,marks in scores.items():
            pair=marks.get(c['component_id'])
            if not pair or (eid,c['component_id']) in submitted:continue
            if pair[0] is not None:
                if c['maximum_score'] is None or Decimal(str(pair[0]))>c['maximum_score']:abort(400,description=f"{c['component_name']}: highest possible score must cover all recorded scores, including students hidden by search.")
                if pair[1]!=c['maximum_score']:updates.append((eid,c['component_id'],pair[0],c['maximum_score']))
    additions=[];deletions=[];used={c['component_name'].casefold() for c in components}
    def count_value(key,default):
        try:value=int(request.form.get(key,default))
        except (TypeError,ValueError):abort(400,description='Activity counts must be whole numbers from 1 to 50.')
        if not 1<=value<=50:abort(400,description='Activity counts must be from 1 to 50.')
        return value
    def plan_activities(category,title,count,start=0):
        for index in range(start,count):
            number=index+1;name=f'{title} {number}'
            while name.casefold() in used:number+=1;name=f'{title} {number}'
            if len(name.encode())>50:abort(400,description='Shorten the component title to leave room for activity numbers.')
            used.add(name.casefold());additions.append(dict(category=category,name=name))
    for c in category_edits:
        existing=[a for a in components if a.get('category_id')==c['category_id']]
        key=f"cat__{c['category_id']}__count"
        if key not in request.form:continue
        count=count_value(key,len(existing))
        if count<len(existing):
            removed=existing[count:]
            if any(a['component_id'] in marks for a in removed for marks in scores.values()) or any(cid in {a['component_id'] for a in removed} and value is not None for eid,cid,value,maximum in updates):abort(400,description='Activities with scores cannot be removed. Clear their scores and save first.')
            deletions.extend(a['component_id'] for a in removed)
        else:plan_activities(c['category_id'],c['category_name'],count,len(existing))
    new_name=request.form.get('new_category_name','').strip();new_category=None
    if new_name:
        if len(new_name.encode())>45 or any(c['category_name'].casefold()==new_name.casefold() for c in category_edits):abort(400,description='Use a unique component title of at most 45 bytes.')
        try:new_weight=gb.decimal(request.form.get('new_category_weight'),0,100)
        except ValueError as error:abort(400,description=str(error))
        new_category=dict(name=new_name,weight=new_weight)
        plan_activities(None,new_name,count_value('new_category_count',1))
    elif request.form.get('new_category_weight','').strip():abort(400,description='Enter a title for the new component.')
    if 'delete_activity_id' in request.form:
        activity_id=request.form.get('delete_activity_id',type=int)
        target=next((c for c in components if c['component_id']==activity_id),None)
        if not target:abort(400,description='Choose an activity in this class.')
        if request.form.get('confirm_delete_activity')!='yes':abort(400,description='Confirm deletion of this activity and its scores first.')
        deletions.append(activity_id)
    delete_id=request.form.get('delete_category_id',type=int)
    if 'delete_category_id' in request.form:
        if not any(c['category_id']==delete_id for c in cats):abort(400,description='Choose a component in this class.')
        if request.form.get('confirm_delete')!='yes':abort(400,description='Confirm component deletion first.')
        removed={c['component_id'] for c in components if c.get('category_id')==delete_id}
        if (any(cid in marks for cid in removed for marks in scores.values()) or any(cid in removed and value is not None for eid,cid,value,maximum in updates)) and request.form.get('confirm_delete_scores')!='yes':abort(409,description='This component contains scores. Confirm that its activities and scores will be deleted.')
        deletions.extend(removed);additions=[a for a in additions if a['category']!=delete_id]
    total_weight=sum((c['weight_percent'] for c in category_edits if c['category_id']!=delete_id),Decimal(0))+(new_category['weight'] if new_category else 0)
    if total_weight>100:abort(400,description=f'Component percentages total {total_weight}%. Reduce the allocation to at most 100% before saving.')
    for c in category_edits:
        execute('UPDATE grade_categories SET category_name=:name,weight_percent=:weight WHERE category_id=:cid AND assignment_id=:aid',dict(name=c['category_name'],weight=c['weight_percent'],cid=c['category_id'],aid=aid))
    for c in components:
        execute('UPDATE grade_components SET component_name=:name,weight_percent=:weight,maximum_score=:maximum,activity_date=:activity_date WHERE component_id=:cid AND assignment_id=:aid',dict(name=c['component_name'],weight=c['weight_percent'],maximum=c['maximum_score'],activity_date=c['activity_date'],cid=c['component_id'],aid=aid))
    if any(c['category_name']!=old['category_name'] for c,old in zip(category_edits,cats)):
        execute("UPDATE teacher_subjects SET grading_model='FLEXIBLE' WHERE assignment_id=:id",{'id':aid})
    if new_category:
        new_id=execute_returning_id('INSERT INTO grade_categories(assignment_id,category_name,weight_percent) VALUES(:aid,:name,:weight) RETURNING category_id INTO :out_id',dict(aid=aid,**new_category))
        execute("UPDATE teacher_subjects SET grading_model='FLEXIBLE' WHERE assignment_id=:id",{'id':aid})
    for addition in additions:
        execute('INSERT INTO grade_components(assignment_id,component_name,weight_percent,category_id,maximum_score) VALUES(:aid,:name,0,:category,NULL)',dict(aid=aid,name=addition['name'],category=addition['category'] if addition['category'] is not None else new_id))
    for cid in deletions:execute('DELETE FROM grade_components WHERE component_id=:cid AND assignment_id=:aid',dict(cid=cid,aid=aid))
    if delete_id:execute('DELETE FROM grade_categories WHERE category_id=:cid AND assignment_id=:aid',dict(cid=delete_id,aid=aid))
    if request.form.get('grading_basis')=='POINTS':execute("UPDATE teacher_subjects SET aggregation='POINTS' WHERE assignment_id=:id",{'id':aid})
    write_scores(row,[u for u in updates if u[1] not in deletions]);bump(row,'Class record saved. Draft grades are private.')
    if total_weight<100:flash(f'{total_weight}% allocated. Complete exactly 100% before publishing.','warning')
    return redirect(url_for('srs.classroom',aid=aid))


@srs_bp.route('/teacher/class/<int:aid>/status',methods=['POST'])
@login_required('faculty')
def status(aid):
    row=teacher_class(aid,True);action=request.form.get('action')
    if action=='reopen':
        bump(row,'Class reopened for editing. Student grades are hidden until republished.')
    elif action=='draft':bump(row,'Draft saved. Grades remain private.')
    elif action=='publish':
        cats,components,students,scores=gb.content(aid);check=sg.calculate(cats,components,{},row.get('grading_model')=='FLEXIBLE',row.get('aggregation','LEGACY'))
        if check['problems']:abort(400,description=' '.join(check['problems']))
        if not students:abort(400,description='Enroll students before publishing.')
        payload=dict(aggregation=row.get('aggregation','LEGACY'),model='FLEXIBLE' if row.get('grading_model')=='FLEXIBLE' else 'SRS',subject={k:row[k] for k in ('subject_code','subject_name','units','section','school_year','semester')},
            categories=cats,assessments=components,students=[dict(**s,result=sg.calculate(cats,components,scores.get(s['enrollment_id'],{}),row.get('grading_model')=='FLEXIBLE',row.get('aggregation','LEGACY')),
                scores={str(cid):[float(v) if v is not None else None for v in pair] for cid,pair in scores.get(s['enrollment_id'],{}).items()}) for s in students])
        gb.save_version(row,'PUBLICATION',payload,reason='Teacher publication under SRS 3.3.6.')
        execute("UPDATE teacher_subjects SET enrollment_open='N' WHERE assignment_id=:id",{'id':aid})
        bump(row,'Grades published. Enrolled students can now view their results.','PUBLISHED')
        recipients=query_all('SELECT s.user_id FROM enrollments e JOIN students s ON s.student_id=e.student_id WHERE e.assignment_id=:id',{'id':aid})
        notify_many([s['user_id'] for s in recipients],f"Grades for {row['subject_code']} · {row['section']} are published.",url_for('srs.student_grades',assignment_id=aid))
    else:abort(400)
    return redirect(url_for('srs.classroom',aid=aid))


@srs_bp.route('/teacher/class/<int:aid>/joining',methods=['POST'])
@login_required('faculty')
def joining(aid):
    row=teacher_class(aid,True)
    if request.form.get('action')=='regenerate':
        code=secrets.token_hex(5).upper()
        execute('UPDATE teacher_subjects SET join_code=:code WHERE assignment_id=:id',{'code':code,'id':aid})
    else:execute("UPDATE teacher_subjects SET enrollment_open=CASE enrollment_open WHEN 'Y' THEN 'N' ELSE 'Y' END WHERE assignment_id=:id",{'id':aid})
    bump(row,'Class joining settings updated.',status='DRAFT' if row['status']=='DRAFT' else 'IN_PROGRESS')
    return redirect(url_for('srs.classroom',aid=aid,tab='class'))


@srs_bp.route('/teacher/class/<int:aid>/csv',methods=['GET','POST'])
@login_required('faculty')
def csv_upload(aid):
    row=teacher_class(aid,request.method=='POST');cats,components,students,scores=gb.content(aid)
    if request.method=='GET':
        stream=io.StringIO();writer=csv.writer(stream);writer.writerow(['id_number','component_name','score','max_score'])
        for s in students:
            for c in components:
                pair=scores.get(s['enrollment_id'],{}).get(c['component_id'])
                writer.writerow([csv_safe(s['id_number']),csv_safe(c['component_name']),pair[0] if pair else '',pair[1] if pair else c['maximum_score']])
        return Response('\ufeff'+stream.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename="class-{aid}-import-template.csv"'})
    load_preview(consume=True);file=request.files.get('csv_file')
    if not file or not file.filename.lower().endswith('.csv'):abort(400,description='Choose a UTF-8 CSV file.')
    try:reader=csv.DictReader(io.StringIO(file.read().decode('utf-8-sig')),strict=True)
    except UnicodeDecodeError:abort(400,description='Save the CSV as UTF-8 and upload it again.')
    headers=[(h or '').strip().lower() for h in (reader.fieldnames or [])]
    if len(headers)!=len(set(headers)) or not {'id_number','component_name','score'}.issubset(headers):abort(400,description='CSV requires unique id_number, component_name, and score columns.')
    reader.fieldnames=headers;people={s['id_number']:s for s in students};items={c['component_name'].casefold():c for c in components};valid=[];invalid=[];seen=set()
    for index,data in enumerate(reader,2):
        if index>10001:abort(400,description='Import at most 10,000 rows per file.')
        identifier=(data.get('id_number') or '').strip();name=(data.get('component_name') or '').strip();raw=(data.get('score') or '').strip()
        pair=(identifier,name.casefold());error=None;s=people.get(identifier);c=items.get(name.casefold())
        if None in data:error='Too many columns.'
        elif pair in seen:error='Duplicate student/component row.'
        elif not s:error='Unknown student ID.'
        elif not c:error='Unknown component.'
        elif not raw:error='Blank score: no value will be imported.'
        else:
            try:
                score=gb.decimal(raw,0,c['maximum_score'])
                if data.get('max_score') and gb.decimal(data['max_score'],.01)!=Decimal(str(c['maximum_score'])):raise ValueError('Maximum does not match this component.')
            except ValueError as failure:error=str(failure)
        seen.add(pair)
        record=dict(line=index,id_number=identifier,component_name=name,score=raw,error=error)
        if error:invalid.append(record)
        else:valid.append(dict(record,eid=s['enrollment_id'],cid=c['component_id'],maximum=str(c['maximum_score']),previous=scores.get(s['enrollment_id'],{}).get(c['component_id'],(None,None))[0]))
    store_preview(dict(type='srs_csv',aid=aid,revision=row['revision'],valid=valid,invalid=invalid))
    return render_template('srs/csv_preview.html',a=row,valid=valid,invalid=invalid)


@srs_bp.route('/teacher/class/<int:aid>/csv/confirm',methods=['POST'])
@login_required('faculty')
def csv_confirm(aid):
    row=teacher_class(aid,True);preview=load_preview()
    if not preview or preview.get('type')!='srs_csv' or preview['aid']!=aid or preview['revision']!=row['revision']:abort(409,description='This preview expired or the class changed. Upload the CSV again.')
    cats,components,students,scores=gb.content(aid);people={s['enrollment_id'] for s in students};items={c['component_id']:c for c in components};updates=[]
    for value in preview['valid']:
        if value['eid'] not in people or value['cid'] not in items:abort(409)
        maximum=items[value['cid']]['maximum_score'];updates.append((value['eid'],value['cid'],gb.decimal(value['score'],0,maximum),maximum))
    if not updates:abort(400,description='There are no valid rows to import.')
    write_scores(row,updates);bump(row,f"Imported {len(updates)} valid rows; skipped {len(preview['invalid'])} invalid rows.")
    return redirect(url_for('srs.classroom',aid=aid))


@srs_bp.route('/teacher/class/<int:aid>/csv/cancel',methods=['POST'])
@login_required('faculty')
def csv_cancel(aid):
    teacher_class(aid)
    preview=load_preview()
    if preview and preview.get('type')=='srs_csv' and preview.get('aid')==aid:load_preview(consume=True)
    flash('CSV import cancelled. No scores were changed.','info')
    return redirect(url_for('srs.classroom',aid=aid))


def csv_safe(value):
    text=str(value or '')
    return "'"+text if text.lstrip().startswith(('=','+','-','@')) or text.startswith(('\t','\r')) else value


@srs_bp.route('/teacher/class/<int:aid>/export')
@login_required('faculty')
def export(aid):
    row=teacher_class(aid);_,cats,components,students,scores,results=model(aid)
    stream=io.StringIO();writer=csv.writer(stream)
    flexible=row.get('grading_model')=='FLEXIBLE'
    writer.writerow(['School Year','Semester','Subject','Section','Student ID','Student Name']+[c['component_name']+' (%)' for c in components]+['Weighted Total (%)','University Grade']+([] if flexible else ['Letter Grade'])+['State'])
    for s in students:
        values=[]
        for c in components:
            pair=scores.get(s['enrollment_id'],{}).get(c['component_id'])
            values.append(sg.rounded(float(pair[0])/float(pair[1])*100) if pair and pair[0] is not None and pair[1] else '')
        writer.writerow([row['school_year'],row['semester'],row['subject_code'],row['section'],csv_safe(s['id_number']),csv_safe(s['full_name'])]+values+[results[s['enrollment_id']]['total'],results[s['enrollment_id']]['equivalent']]+([] if flexible else [results[s['enrollment_id']]['letter']])+[row['status']])
    # Protect component headers as well as student text.
    content=stream.getvalue();parsed=list(csv.reader(io.StringIO(content)));out=io.StringIO();csv.writer(out).writerows([[csv_safe(v) for v in r] for r in parsed])
    return Response('\ufeff'+out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename="class-{aid}-gradebook.csv"'})


@srs_bp.route('/teacher/analytics')
@srs_bp.route('/teacher/top-performers',endpoint='top_performers')
@login_required('faculty')
def teacher_analytics():
    term=active_term();classes=sg.load_classes(term['term_id'] if term else 0,session['teacher_id']);aid=request.args.get('assignment_id',type=int)
    selected=next((c for c in classes if c['assignment_id']==aid),classes[0] if classes else None)
    if aid and not any(c['assignment_id']==aid for c in classes):abort(404)
    charts=gb.analysis(selected['components'],selected['students'],selected['scores']) if selected else []
    return render_template('srs/teacher_analytics.html',term=term,classes=classes,selected=selected,charts=charts,
        top=request.path.endswith('top-performers'),bands=sg.distribution([s['total'] for s in selected['ranked']]) if selected else [])


def student_data(all_terms=False):
    from .student import get_student,my_enrollments
    term=active_term();student=get_student()
    if all_terms:term=dict(term_id=None,is_all=True,school_year='All school years',semester='All semesters')
    tid=term['term_id'] if term else 0
    if not student:abort(404)
    if tid is not None:
        membership=query_one('''SELECT sec.program,sec.year_level,sec.section_name AS section FROM student_term_memberships m
            JOIN academic_sections sec ON sec.section_id=m.section_id WHERE m.student_id=:sid AND m.term_id=:tid''',{'sid':student['student_id'],'tid':tid})
        if membership:student.update(membership)
    classes=sg.load_classes(tid,published_only=True)
    report=sg.student_summary(student,classes)
    if tid is None:report.update(rank=None,cohort=0)
    enrollments=my_enrollments(student['student_id'],tid)
    return dict(term=term,student=student,report=report,enrollments=enrollments)


@srs_bp.route('/student')
@login_required('student')
def student_home():
    context=student_data()
    trends=[]
    for item in context['report']['own']:
        classroom=item['classroom']
        student=item['student']
        scores=classroom['scores'].get(student['enrollment_id'],{})
        daily=defaultdict(lambda: [0.0,0.0])
        for activity in classroom['components']:
            date=activity.get('activity_date')
            score=scores.get(activity['component_id'])
            if date and score and score[0] is not None and score[1] and score[1]>0:
                day=daily[date.strftime('%Y-%m-%d')]
                day[0]+=float(score[0])
                day[1]+=float(score[1])
        if daily:
            points=[dict(date=date,value=round(100*earned/possible,2)) for date,(earned,possible) in sorted(daily.items())]
            trends.append(dict(label=f"{classroom['subject_code']} · {classroom['subject_name']}",points=points))
    return render_template('srs/student_home.html',**context,trends=trends)


@srs_bp.route('/student/grades')
@login_required('student')
def student_grades():
    context=student_data();aid=request.args.get('assignment_id',type=int)
    selected=next((r for r in context['report']['own'] if r['classroom']['assignment_id']==aid),None)
    enrollment=next((e for e in context['enrollments'] if e['assignment_id']==aid),None)
    if aid and not enrollment:abort(404)
    if not aid:
        return render_template('srs/student_subjects.html',**context)
    return render_template('srs/student_grades.html',**context,selected=selected,selected_enrollment=enrollment)


@srs_bp.route('/student/view-grade')
@login_required('student')
def student_view_grade():
    context=student_data(all_terms=not request.args.get('term_filter'));groups={}
    published={item['classroom']['assignment_id']:item['student']['result'] for item in context['report']['own']}
    for enrollment in context['enrollments']:
        key=(enrollment.get('school_year',''),enrollment.get('semester',''))
        groups.setdefault(key,[]).append(dict(enrollment,result=published.get(enrollment['assignment_id']) if enrollment['status']=='PUBLISHED' else None))
    groups=dict(sorted(groups.items(),key=lambda item:(item[0][0],{'1st Semester':1,'2nd Semester':2,'Summer':3}.get(item[0][1],0)),reverse=True))
    return render_template('srs/student_view_grade.html',**context,grade_groups=groups)


@srs_bp.route('/student/analytics')
@srs_bp.route('/student/rank',endpoint='student_rank')
@login_required('student')
def student_analytics():
    context=student_data();grouped=defaultdict(list)
    for item in context['report']['own']:
        c=item['classroom'];s=item['student'];scores=c['scores'].get(s['enrollment_id'],{})
        for component in c['components']:
            pair=scores.get(component['component_id'])
            grouped[component_type(component['component_name'])].append(float(pair[0])/float(pair[1])*100 if pair and pair[0] is not None and pair[1] else 0)
    types=[dict(label=k,value=sg.rounded(mean(v)),count=len(v)) for k,v in sorted(grouped.items())]
    from ..student_progress import scholarship
    scholar=scholarship(context['enrollments'],context['report']['own'],bool(context['term'] and context['term'].get('is_all')))
    return render_template('srs/student_analytics.html',**context,types=types,scholar=scholar,rank_only=request.path.endswith('/rank'))


@srs_bp.route('/student/join',methods=['GET','POST'])
@login_required('student')
def join():
    if request.method=='POST':abort(410,description='Enrollment codes have been retired. Use EnlistMe.')
    return redirect(url_for('university.enlistme'))


def admin_data():
    from ..curriculum import canonical_program
    term=active_term();tid=term['term_id'] if term else 0;classes=sg.load_classes(tid)
    people={s['student_id']:s for c in classes for s in c['students']}
    program=Counter();years=Counter();sex=Counter();types=Counter();regular=defaultdict(Counter)
    for s in people.values():
        p=canonical_program(s['program']) or s['program'];program[p]+=1;years[s['year_level']]+=1
        sex[s.get('sex') or 'Not recorded']+=1;types[s.get('enrollment_type') or 'Not recorded']+=1
        regular[p][s.get('enrollment_type') or 'Not recorded']+=1
    def bars(counter):return [dict(label=k,value=v) for k,v in sorted(counter.items())]
    counts=query_one('''SELECT
        (SELECT COUNT(*) FROM students st JOIN users u ON u.user_id=st.user_id WHERE st.status='ACTIVE' AND u.status='ACTIVE') AS active_students,
        (SELECT COUNT(*) FROM teachers t JOIN users u ON u.user_id=t.user_id WHERE t.status='ACTIVE' AND u.status='ACTIVE') AS active_faculty,
        (SELECT COUNT(*) FROM subjects WHERE is_archived=0) AS subjects,
        (SELECT COUNT(*) FROM grades g JOIN enrollments e ON e.enrollment_id=g.enrollment_id
         JOIN teacher_subjects ts ON ts.assignment_id=e.assignment_id WHERE (:term IS NULL OR ts.term_id=:term) AND g.score IS NOT NULL) AS recorded FROM dual''',{'term':tid})
    return dict(term=term,classes=classes,counts=counts or {},programs=bars(program),years=bars(years),sex=bars(sex),types=bars(types),
        regular=[dict(program=k,regular=v['REGULAR'],irregular=v['IRREGULAR'],unknown=v['Not recorded']) for k,v in sorted(regular.items())],
        subject_counts=[dict(label=c['subject_code']+' · '+c['section'],value=len(c['students'])) for c in classes],
        unique=len(people),analytics=request.endpoint=='srs.admin_analytics')


@srs_bp.route('/admin')
@login_required('admin')
def admin_home():return render_template('srs/admin_home.html',**admin_data())


@srs_bp.route('/admin/analytics')
@login_required('admin')
def admin_analytics():return render_template('srs/admin_home.html',**admin_data())


@srs_bp.route('/admin/subjects')
@login_required('admin')
def subject_catalog():
    from .admin import subjects
    return subjects()


@srs_bp.route('/admin/classes/create',methods=['POST'])
@login_required('admin')
def create_class():
    from .. import academic
    from ..curriculum import PROGRAM_NAMES
    import re
    allowed=academic.offering_terms();tid=request.form.get('class_term_id',type=int)
    term=next((t for t in allowed if t['term_id']==tid),None)
    if not term:abort(409,description='Choose the active term or the upcoming term opened for enlistment.')
    query_one('SELECT term_id FROM school_terms WHERE term_id=:id FOR UPDATE WAIT 5',{'id':tid})
    term=query_one('SELECT * FROM school_terms WHERE term_id=:id',{'id':tid})
    if not (term['is_active'] or term['enlistment_open']):abort(409,description='This term is no longer open for class preparation.')
    subject=query_one('SELECT * FROM subjects WHERE subject_id=:id FOR UPDATE WAIT 5',{'id':request.form.get('subject_id',type=int)})
    teacher=query_one("SELECT t.teacher_id,t.user_id,t.program FROM teachers t JOIN users u ON u.user_id=t.user_id WHERE t.teacher_id=:id AND t.status='ACTIVE' AND u.status='ACTIVE'",{'id':request.form.get('teacher_id',type=int)})
    section=request.form.get('section','').strip();match=re.fullmatch(r'(BSCS|BSIT|BSIS|BSDSA|BLIS) ([1-4])-[1-9][0-9]?',section)
    if not subject or subject['is_archived'] or subject['program'] not in PROGRAM_NAMES or not teacher or not match:abort(400,description='Choose a curriculum subject, active faculty member, and valid section such as BSDSA 1-1.')
    if teacher.get('program')!=subject['program']:abort(400,description='Choose a faculty member belonging to the subject program.')
    if match[1]!=subject['program'] or match[2]!=subject['year_level'][:1] or subject['semester_offered']!=term['semester']:
        abort(400,description='The subject must match the section program, year level, and selected term semester.')
    existing=query_one('SELECT assignment_id,teacher_id,status FROM teacher_subjects WHERE subject_id=:subject AND term_id=:term AND UPPER(TRIM(section))=UPPER(:section) FOR UPDATE WAIT 5',{'subject':subject['subject_id'],'term':tid,'section':section})
    if existing:
        assign_class_faculty(dict(existing,subject_code=subject['subject_code'],section=section),teacher)
        return redirect(url_for('admin.classes'))
    aid=execute_returning_id('INSERT INTO teacher_subjects(teacher_id,subject_id,term_id,section) VALUES(:teacher,:subject,:term,:section) RETURNING assignment_id INTO :out_id',{'teacher':teacher['teacher_id'],'subject':subject['subject_id'],'term':tid,'section':section})
    notify(teacher['user_id'],f"You were assigned {subject['subject_code']} · {section}.",url_for('srs.classroom',aid=aid))
    log_activity(f"Administrator assigned class {aid} to faculty {teacher['teacher_id']}.")
    flash('Class created. Students can select matching subjects in EnlistMe when this term is active.','success')
    return redirect(url_for('admin.classes'))


def assign_class_faculty(row,teacher):
    if row.get('teacher_id') is not None:abort(409,description='This class already has an assigned faculty member.')
    execute('UPDATE teacher_subjects SET teacher_id=:teacher,revision=revision+1 WHERE assignment_id=:id',dict(teacher=teacher['teacher_id'],id=row['assignment_id']))
    notify(teacher['user_id'],f"You were assigned {row['subject_code']} · {row['section']}.",url_for('srs.classroom',aid=row['assignment_id']))
    log_activity(f"Administrator assigned faculty {teacher['teacher_id']} to existing class {row['assignment_id']}; enrollments preserved.")
    flash('Faculty assigned. Existing student enrollments are preserved.','success')


@srs_bp.route('/admin/classes/<int:aid>/faculty',methods=['POST'])
@login_required('admin')
def assign_faculty(aid):
    from .. import academic
    query_all('SELECT term_id FROM school_terms ORDER BY term_id FOR UPDATE WAIT 5')
    row=query_one('''SELECT ts.assignment_id,ts.teacher_id,ts.term_id,ts.status,ts.section,s.subject_code,s.program
        FROM teacher_subjects ts JOIN subjects s ON s.subject_id=ts.subject_id
        WHERE ts.assignment_id=:id FOR UPDATE OF ts.teacher_id WAIT 5''',{'id':aid})
    if not row:abort(404)
    if row['term_id'] not in {t['term_id'] for t in academic.offering_terms()}:
        abort(409,description='Assign faculty in the current term or an opened future class term.')
    teacher=query_one("SELECT t.teacher_id,t.user_id,t.program FROM teachers t JOIN users u ON u.user_id=t.user_id WHERE t.teacher_id=:id AND t.status='ACTIVE' AND u.status='ACTIVE'",{'id':request.form.get('teacher_id',type=int)})
    if not teacher or teacher.get('program')!=row['program']:abort(400,description='Choose an active faculty member from the subject program.')
    assign_class_faculty(row,teacher)
    return redirect(url_for('admin.classes'))
