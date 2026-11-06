"""Teacher-centered class workspaces and administrator grade review."""
import io
import json
import secrets
import zipfile
from statistics import mean,median
from decimal import Decimal
from flask import Blueprint,abort,flash,redirect,render_template,request,session,url_for,send_file
from ..auth import login_required
from ..db import query_all,query_one,execute
from .. import gradebook as gb
from ..security import store_preview,load_preview,rate_limit
from .admin import active_term,log_activity

workspace_bp=Blueprint('workspace',__name__,url_prefix='/workspace')


def admin_report():
    term=active_term();tid=term['term_id'] if term else 0
    classes=query_all('''SELECT ts.assignment_id,ts.section,ts.status,s.subject_name,s.subject_code,u.full_name,
        (SELECT COUNT(*) FROM enrollments e WHERE e.assignment_id=ts.assignment_id) AS students
        FROM teacher_subjects ts JOIN subjects s ON s.subject_id=ts.subject_id LEFT JOIN teachers t ON t.teacher_id=ts.teacher_id
        LEFT JOIN users u ON u.user_id=t.user_id WHERE ts.term_id=:term ORDER BY s.subject_name,ts.section''',{'term':tid})
    programs=query_all('''SELECT st.program,COUNT(DISTINCT st.student_id) AS students FROM enrollments e
        JOIN teacher_subjects ts ON ts.assignment_id=e.assignment_id JOIN students st ON st.student_id=e.student_id
        WHERE ts.term_id=:term GROUP BY st.program ORDER BY st.program''',{'term':tid})
    from ..curriculum import canonical_program
    normalized={}
    for item in programs:
        key=canonical_program(item['program']) or item['program']
        normalized[key]=normalized.get(key,0)+item['students']
    programs=[dict(program=key,students=value) for key,value in sorted(normalized.items())]
    versions=query_all('''SELECT v.* FROM grade_versions v JOIN teacher_subjects ts ON ts.assignment_id=v.assignment_id
        WHERE ts.term_id=:term AND v.kind='PUBLICATION' AND v.version_id=(SELECT MAX(x.version_id)
        FROM grade_versions x WHERE x.assignment_id=v.assignment_id AND x.kind='PUBLICATION')''',{'term':tid})
    published=[];totals=[]
    for version in versions:
        raw=version['payload'];data=json.loads(raw.read() if hasattr(raw,'read') else raw)
        values=[s['result']['total'] for s in data['students'] if s['result']['total'] is not None]
        totals.extend(values)
        published.append(dict(subject=data['subject'],count=len(values),mean=round(mean(values),2) if values else None,
            median=round(median(values),2) if values else None,legacy=data.get('legacy',False),date=version['created_at']))
    states=[dict(label=state.title(),count=sum(c['status']==state for c in classes)) for state in ('DRAFT','IN_PROGRESS','SUBMITTED','RETURNED','PUBLISHED')]
    bins=[dict(label=label,count=sum(lo<=v<hi for v in totals)) for label,lo,hi in [('Below 75%',0,75),('75–79.99%',75,80),('80–89.99%',80,90),('90–100%',90,101)]]
    return dict(term=term,classes=classes,programs=programs,published=published,states=states,bins=bins,
        pending=sum(c['status']=='SUBMITTED' for c in classes),enrollments=sum(c['students'] for c in classes),
        results=len(totals),report_only=request.endpoint=='workspace.reports')


@workspace_bp.route('/overview')
@login_required('admin')
def overview():
    return render_template('workspace/overview.html',**admin_report())


@workspace_bp.route('/reports')
@login_required('admin')
def reports():
    return render_template('workspace/overview.html',**admin_report())


def role_required(*roles):
    if session.get('role') not in roles:abort(403)


def teacher_class(aid,write=False):
    row=gb.classroom(aid,lock=write)
    if row['teacher_id']!=session.get('teacher_id'):abort(404)
    if write:
        if row['status'] in ('SUBMITTED','PUBLISHED'):abort(409,description='This gradebook is locked. An administrator must return it or open a correction.')
        if not row['is_active'] and row['status']!='RETURNED':abort(409,description='Only active-term classes or administrator-returned corrections can be edited.')
        if request.form.get('revision',type=int)!=row['revision']:abort(409,description='This class changed. Reload and review before saving.')
    return row


def changed(row,message):
    execute("UPDATE teacher_subjects SET revision=revision+1,status=CASE WHEN status='RETURNED' THEN 'RETURNED' ELSE 'IN_PROGRESS' END WHERE assignment_id=:id",{'id':row['assignment_id']})
    log_activity(f"Class {row['assignment_id']}: {message}")
    flash(message,'success')


@workspace_bp.route('/classes')
@login_required('faculty')
def classes():
    term=active_term()
    rows=query_all('''SELECT ts.*,s.subject_name,s.subject_code,s.program,
        (SELECT COUNT(*) FROM enrollments e WHERE e.assignment_id=ts.assignment_id) AS student_count
        FROM teacher_subjects ts JOIN subjects s ON s.subject_id=ts.subject_id
        WHERE ts.teacher_id=:tid AND ts.term_id=:term ORDER BY s.subject_name,ts.section''',
        {'tid':session['teacher_id'],'term':term['term_id'] if term else 0})
    return render_template('workspace/classes.html',rows=rows,term=term,submissions=request.args.get('view')=='submissions')


@workspace_bp.route('/class/<int:aid>')
@login_required('faculty')
def classroom(aid):
    row=teacher_class(aid);cats,assessments,roster,scores=gb.content(aid)
    reports={s['enrollment_id']:gb.calculate(cats,assessments,scores.get(s['enrollment_id'],{}),row['aggregation'],row['rounding_rule']) for s in roster}
    return render_template('workspace/classroom.html',a=row,categories=cats,assessments=assessments,roster=roster,
        scores=scores,reports=reports,charts=gb.analysis(assessments,roster,scores),tab=request.args.get('tab','gradebook'),
        allocation=sum(float(c['weight_percent']) for c in cats),review=gb.latest(aid,'RETURN'),
        released=gb.latest(aid,'RELEASE'),locked=row['status'] in ('SUBMITTED','PUBLISHED') or (not row['is_active'] and row['status']!='RETURNED'))


@workspace_bp.route('/class/<int:aid>/setup',methods=['POST'])
@login_required('faculty')
def setup(aid):
    row=teacher_class(aid,True)
    action=request.form.get('action');cats,assessments,roster,scores=gb.content(aid)
    if action=='aggregation':
        mode=request.form.get('aggregation')
        if mode not in ('EQUAL','POINTS'):abort(400,description='Select an assessment averaging method.')
        if row['aggregation']!=mode and assessments and any(scores.values()) and not request.form.get('confirmed'):
            abort(400,description='Confirm that the calculation method changes existing draft results.')
        execute('UPDATE teacher_subjects SET aggregation=:method WHERE assignment_id=:id',{'method':mode,'id':aid})
    elif action in ('category','category_edit'):
        name=request.form.get('category_name','').strip()
        try:weight=gb.decimal(request.form.get('weight_percent'),.01,100)
        except ValueError as error:abort(400,description=str(error))
        if not name or len(name.encode())>50:abort(400,description='Enter a category name of at most 50 bytes.')
        cid=request.form.get('category_id',type=int)
        if any(c['category_name'].strip().casefold()==name.casefold() and c['category_id']!=cid for c in cats):abort(400,description='Category names must be unique.')
        if action=='category_edit':
            if not any(c['category_id']==cid for c in cats):abort(404)
            if any(scores.values()) and not request.form.get('confirmed'):
                proposed=[dict(c,category_name=name,weight_percent=weight) if c['category_id']==cid else c for c in cats]
                comparisons=[dict(name=s['full_name'],before=gb.calculate(cats,assessments,scores.get(s['enrollment_id'],{}),row['aggregation'])['total'],
                    after=gb.calculate(proposed,assessments,scores.get(s['enrollment_id'],{}),row['aggregation'])['total']) for s in roster]
                return render_template('workspace/setup_preview.html',a=row,comparisons=comparisons,fields=request.form)
            execute('UPDATE grade_categories SET category_name=:name,weight_percent=:weight WHERE category_id=:cid AND assignment_id=:aid',{'name':name,'weight':weight,'cid':cid,'aid':aid})
        else:execute('INSERT INTO grade_categories(assignment_id,category_name,weight_percent) VALUES(:aid,:name,:weight)',{'aid':aid,'name':name,'weight':weight})
    elif action=='assessment':
        name=request.form.get('component_name','').strip();cid=request.form.get('category_id',type=int)
        try:maximum=gb.decimal(request.form.get('maximum_score'),.01,9999)
        except ValueError as error:abort(400,description=str(error))
        if not name or len(name.encode())>50 or not any(c['category_id']==cid for c in cats):abort(400,description='Enter an assessment title and select its category.')
        if any(a['component_name'].casefold()==name.casefold() for a in assessments):abort(400,description='Assessment titles must be unique within the class.')
        execute('INSERT INTO grade_components(assignment_id,component_name,category_id,weight_percent,maximum_score) VALUES(:aid,:name,:cid,0,:maximum)',{'aid':aid,'name':name,'cid':cid,'maximum':maximum})
    elif action=='assessment_category':
        component=request.form.get('component_id',type=int);category=request.form.get('category_id',type=int)
        if not any(a['component_id']==component for a in assessments) or not any(c['category_id']==category for c in cats):abort(400,description='Choose an assessment and category belonging to this class.')
        execute('UPDATE grade_components SET category_id=:category WHERE component_id=:component AND assignment_id=:aid',{'category':category,'component':component,'aid':aid})
    elif action in ('delete_category','delete_assessment'):
        if action=='delete_category':
            cid=request.form.get('category_id',type=int)
            if any(a['category_id']==cid for a in assessments):abort(409,description='Remove unused assessments before deleting this category.')
            execute('DELETE FROM grade_categories WHERE category_id=:cid AND assignment_id=:aid',{'cid':cid,'aid':aid})
        else:
            cid=request.form.get('component_id',type=int)
            if not any(a['component_id']==cid for a in assessments):abort(404)
            if query_one('SELECT grade_id FROM grades WHERE component_id=:cid FETCH FIRST 1 ROWS ONLY',{'cid':cid}):abort(409,description='An assessment with scores must be retained for academic history.')
            execute('DELETE FROM grade_components WHERE component_id=:cid AND assignment_id=:aid',{'cid':cid,'aid':aid})
    else:abort(400)
    sync_weights(aid)
    changed(row,'Grading setup updated. Review the result preview before releasing scores.')
    return redirect(url_for('workspace.classroom',aid=aid,tab='setup'))


def sync_weights(aid):
    """Keep legacy reporting compatible with explicit averaging configuration."""
    row=gb.classroom(aid);cats,assessments,_,_=gb.content(aid)
    for cat in cats:
        items=[a for a in assessments if a['category_id']==cat['category_id']]
        denominator=sum(Decimal(str(a['maximum_score'])) for a in items) if row['aggregation']=='POINTS' else Decimal(len(items))
        remaining=Decimal('100')
        for index,a in enumerate(items):
            numerator=Decimal(str(a['maximum_score'])) if row['aggregation']=='POINTS' else Decimal(1)
            weight=(numerator/denominator*100).quantize(Decimal('.01')) if index<len(items)-1 else remaining
            remaining-=weight
            execute('UPDATE grade_components SET weight_percent=:weight WHERE component_id=:id',{'weight':weight,'id':a['component_id']})


def write_scores(row,updates):
    for eid,cid,score,maximum in updates:
        if score is None:
            execute('DELETE FROM grades WHERE enrollment_id=:eid AND component_id=:cid',{'eid':eid,'cid':cid})
        else:
            execute('''MERGE INTO grades g USING(SELECT :eid enrollment_id,:cid component_id FROM dual) src
                ON(g.enrollment_id=src.enrollment_id AND g.component_id=src.component_id)
                WHEN MATCHED THEN UPDATE SET score=:score,max_score=:maximum,updated_at=SYSTIMESTAMP
                WHEN NOT MATCHED THEN INSERT(enrollment_id,component_id,score,max_score) VALUES(:eid,:cid,:score,:maximum)''',
                {'eid':eid,'cid':cid,'score':score,'maximum':maximum})


@workspace_bp.route('/class/<int:aid>/scores',methods=['POST'])
@login_required('faculty')
def scores(aid):
    row=teacher_class(aid,True);cats,assessments,roster,old=gb.content(aid)
    allowed={str(s['enrollment_id']) for s in roster};components={str(a['component_id']):a for a in assessments};updates=[]
    for key,value in request.form.items():
        if not key.startswith('mark__'):continue
        parts=key.split('__')
        if len(parts)!=3 or parts[1] not in allowed or parts[2] not in components:abort(400,description='Invalid score field.')
        a=components[parts[2]];maximum=Decimal(str(a['maximum_score']))
        try:score=gb.decimal(value,0,maximum) if value.strip() else None
        except ValueError as error:abort(400,description=f"{a['component_name']}: {error}")
        updates.append((int(parts[1]),a['component_id'],score,maximum))
    write_scores(row,updates)
    if request.form.get('action')=='release':
        if row['aggregation']=='LEGACY':abort(400,description='Choose an averaging method before releasing results.')
        payload=gb.snapshot(row)
        if any(s['result']['problems'] for s in payload['students']):abort(400,description='Resolve grading setup problems before release.')
        gb.save_version(row,'RELEASE',payload)
    changed(row,'Scores saved and released to students.' if request.form.get('action')=='release' else 'Draft scores saved. Student results are unchanged.')
    return redirect(url_for('workspace.classroom',aid=aid))


@workspace_bp.route('/class/<int:aid>/submit',methods=['POST'])
@login_required('faculty')
def submit(aid):
    row=teacher_class(aid,True)
    if row['rounding_rule']=='UNSET':abort(400,description='An administrator must confirm the grade conversion rounding rule before submission.')
    payload=gb.snapshot(row)
    if not payload['students'] or any(not s['result']['complete'] for s in payload['students']):abort(400,description='Complete the grading setup and every required score before submission. Missing scores are not zero.')
    gb.save_version(row,'SUBMISSION',payload)
    execute("UPDATE teacher_subjects SET status='SUBMITTED',enrollment_open='N',revision=revision+1 WHERE assignment_id=:id",{'id':aid})
    log_activity(f'Teacher submitted class {aid} for review.')
    flash('Grades submitted for administrator review. This revision is locked.','success')
    return redirect(url_for('workspace.classroom',aid=aid))


@workspace_bp.route('/class/<int:aid>/joining',methods=['POST'])
@login_required('faculty')
def joining(aid):
    row=teacher_class(aid,True)
    if request.form.get('action')=='regenerate':
        execute('UPDATE teacher_subjects SET join_code=:code WHERE assignment_id=:id',{'code':secrets.token_hex(5).upper(),'id':aid})
    else:execute("UPDATE teacher_subjects SET enrollment_open=CASE enrollment_open WHEN 'Y' THEN 'N' ELSE 'Y' END WHERE assignment_id=:id",{'id':aid})
    changed(row,'Class joining settings updated.')
    return redirect(url_for('workspace.classroom',aid=aid,tab='details'))


@workspace_bp.route('/review')
@login_required('admin')
def reviews():
    rows=query_all('''SELECT ts.assignment_id,ts.section,ts.status,s.subject_name,s.subject_code,u.full_name,
        term.school_year,term.semester FROM teacher_subjects ts JOIN subjects s ON s.subject_id=ts.subject_id
        LEFT JOIN teachers t ON t.teacher_id=ts.teacher_id LEFT JOIN users u ON u.user_id=t.user_id
        JOIN school_terms term ON term.term_id=ts.term_id
        WHERE ts.status IN ('SUBMITTED','RETURNED','PUBLISHED') ORDER BY CASE ts.status WHEN 'SUBMITTED' THEN 0 ELSE 1 END,ts.assignment_id DESC''')
    return render_template('workspace/reviews.html',rows=rows,term=active_term())


@workspace_bp.route('/sections',methods=['GET','POST'])
@login_required('admin')
def sections():
    from ..curriculum import PROGRAM_NAMES,canonical_program
    term=active_term()
    if request.method=='POST':
        if not term or not query_one('SELECT term_id FROM school_terms WHERE term_id=:id AND is_active=1',{'id':term['term_id']}):abort(409,description='Activate a term first.')
        action=request.form.get('action')
        if action=='create':
            program=canonical_program(request.form.get('program'));year=request.form.get('year_level');name=request.form.get('section','').strip()
            if not program or year not in ('1st Year','2nd Year','3rd Year','4th Year') or not name or len(name.encode())>20:abort(400,description='Choose a program, year, and section name of at most 20 bytes.')
            if query_one('SELECT section_id FROM academic_sections WHERE term_id=:term AND program=:program AND year_level=:year AND LOWER(section_name)=LOWER(:name)',{'term':term['term_id'],'program':program,'year':year,'name':name}):abort(409,description='This section already exists.')
            execute('INSERT INTO academic_sections(term_id,program,year_level,section_name) VALUES(:term,:program,:year,:name)',{'term':term['term_id'],'program':program,'year':year,'name':name})
        elif action=='member':
            section=query_one('SELECT * FROM academic_sections WHERE section_id=:id AND term_id=:term',{'id':request.form.get('section_id',type=int),'term':term['term_id']})
            student=query_one('SELECT student_id,program,year_level FROM students WHERE student_id=:id FOR UPDATE WAIT 5',{'id':request.form.get('student_id',type=int)})
            if not section or not student or canonical_program(student['program'])!=section['program'] or student['year_level']!=section['year_level']:abort(400,description="The student's program and year must match the main section.")
            execute('''MERGE INTO student_term_memberships m USING(SELECT :sid student_id,:term term_id FROM dual) src
                ON(m.student_id=src.student_id AND m.term_id=src.term_id)
                WHEN MATCHED THEN UPDATE SET section_id=:section
                WHEN NOT MATCHED THEN INSERT(student_id,term_id,section_id) VALUES(:sid,:term,:section)''',{'sid':student['student_id'],'term':term['term_id'],'section':section['section_id']})
            execute('UPDATE students SET section=:name WHERE student_id=:id',{'name':section['section_name'],'id':student['student_id']})
            log_activity(f"Student {student['student_id']} main section set for term {term['term_id']}; class enrollments unchanged.")
        else:abort(400)
        flash('Section setup saved. Existing class enrollments are unchanged.','success')
        return redirect(url_for('workspace.sections'))
    rows=query_all('''SELECT sec.*,(SELECT COUNT(*) FROM student_term_memberships m WHERE m.section_id=sec.section_id) AS member_count
        FROM academic_sections sec WHERE term_id=:term ORDER BY program,year_level,section_name''',{'term':term['term_id'] if term else 0})
    students=query_all("SELECT s.student_id,s.id_number,s.program,s.year_level,u.full_name FROM students s JOIN users u ON u.user_id=s.user_id WHERE s.status='ACTIVE' AND u.status='ACTIVE' ORDER BY u.full_name")
    return render_template('workspace/sections.html',rows=rows,students=students,programs=PROGRAM_NAMES,term=term)


@workspace_bp.route('/review/<int:aid>',methods=['GET','POST'])
@login_required('admin')
def review(aid):
    row=gb.classroom(aid,request.method=='POST');submission=gb.latest(aid,'SUBMISSION')
    if request.method=='POST':
        if row['revision']!=request.form.get('revision',type=int):abort(409,description='This class changed. Reload before deciding.')
        action=request.form.get('action');reason=request.form.get('reason','').strip()
        if len(reason)>500:abort(400,description='Use at most 500 characters for the reason.')
        if action=='policy':
            if row['status'] in ('SUBMITTED','PUBLISHED'):abort(409,description='Return the submission or open a correction before changing policy.')
            rule=request.form.get('rounding_rule')
            if rule not in ('HALF_UP','FLOOR'):abort(400,description='Choose an institution-approved rounding rule.')
            if not reason:abort(400,description='Record the approval reference for this conversion rule.')
            execute('UPDATE teacher_subjects SET rounding_rule=:rule,revision=revision+1 WHERE assignment_id=:id',{'rule':rule,'id':aid})
            log_activity(f'Class {aid} conversion rule {rule}: {reason}')
        elif action=='correction':
            if row['status']!='PUBLISHED' or not reason:abort(400,description='A published class and authorization reason are required.')
            gb.save_version(row,'RETURN',{'correction':True},reason=reason)
            execute("UPDATE teacher_subjects SET status='RETURNED',revision=revision+1 WHERE assignment_id=:id",{'id':aid})
        else:
            if not submission or row['status']!='SUBMITTED':abort(409,description='There is no pending submission for this class.')
            if submission['version_id']!=request.form.get('version_id',type=int):abort(409,description='Review the latest submission.')
            if submission['actor_user_id']==session['user_id']:abort(403,description='A different authorized administrator must review your submission.')
            if action=='publish':
                if any(not s['result']['complete'] for s in submission['data']['students']):abort(409,description='This submission is incomplete.')
                gb.save_version(row,'PUBLICATION',submission['data'],submission['version_id'])
                execute("UPDATE teacher_subjects SET status='PUBLISHED',revision=revision+1 WHERE assignment_id=:id",{'id':aid})
            elif action=='return' and reason:
                gb.save_version(row,'RETURN',{'submission':submission['version_id']},submission['version_id'],reason)
                execute("UPDATE teacher_subjects SET status='RETURNED',revision=revision+1 WHERE assignment_id=:id",{'id':aid})
            else:abort(400,description='Choose a decision and provide a reason when returning grades.')
            log_activity(f'Admin {action} class {aid}. {reason}')
        flash('Review action recorded.','success');return redirect(url_for('workspace.review',aid=aid))
    publication=gb.latest(aid,'PUBLICATION')
    history=query_all('SELECT version_id,kind,created_at,reason FROM grade_versions WHERE assignment_id=:id ORDER BY version_id DESC',{'id':aid})
    return render_template('workspace/review.html',a=row,submission=submission,publication=publication,history=history,term=active_term())


@workspace_bp.route('/subjects')
@login_required('student')
def subjects():
    term=active_term()
    rows=query_all('''SELECT ts.assignment_id,ts.status,ts.section,s.subject_name,s.subject_code,s.units,
        term.school_year,term.semester,COALESCE(u.full_name,'Faculty not yet assigned') AS teacher_name FROM enrollments e
        JOIN teacher_subjects ts ON ts.assignment_id=e.assignment_id JOIN subjects s ON s.subject_id=ts.subject_id
        JOIN school_terms term ON term.term_id=ts.term_id LEFT JOIN teachers t ON t.teacher_id=ts.teacher_id
        LEFT JOIN users u ON u.user_id=t.user_id WHERE e.student_id=:sid ORDER BY ts.term_id DESC,s.subject_name''',{'sid':session['student_id']})
    results=[]
    for row in rows:
        pub=gb.latest(row['assignment_id'],'PUBLICATION');release=gb.latest(row['assignment_id'],'RELEASE')
        item=dict(row,publication=None,released=None)
        for record,key in ((pub,'publication'),(release,'released')):
            if record:
                own=next((s for s in record['data']['students'] if s['student_id']==session['student_id']),None)
                if own:item[key]=dict(student=own,assessments=record['data']['assessments'],created_at=record['created_at'],version_id=record['version_id'])
        if item['publication'] and item['released'] and item['publication']['version_id']>item['released']['version_id']:
            item['released']=None
        results.append(item)
    return render_template('workspace/subjects.html',rows=results,term=term,history=request.args.get('view')=='history')


@workspace_bp.route('/join',methods=['GET','POST'])
@login_required('student')
def join():
    row=None;code=request.values.get('code','').strip().upper()
    if code:
        rate_limit('join-preview:'+str(session['student_id']),30,900)
        match=query_one('SELECT assignment_id FROM teacher_subjects WHERE join_code=:code',{'code':code})
        if match:row=gb.classroom(match['assignment_id'],request.method=='POST')
        if not row:flash('Class code not found. Check the code with your teacher.','error')
    if request.method=='POST':
        rate_limit('join-write:'+str(session['student_id']),10,900)
        if not row or not row['is_active'] or row['enrollment_open']!='Y' or row['status'] in ('SUBMITTED','PUBLISHED'):abort(409,description='This class is not currently accepting students.')
        # Serialize across class sections for the same student.
        student=query_one("SELECT student_id,status FROM students WHERE student_id=:id FOR UPDATE WAIT 5",{'id':session['student_id']})
        if not student or student['status']!='ACTIVE':abort(403)
        if query_one('''SELECT e.enrollment_id FROM enrollments e JOIN teacher_subjects ts ON ts.assignment_id=e.assignment_id
            WHERE e.student_id=:sid AND ts.subject_id=:subject AND ts.term_id=:term FETCH FIRST 1 ROWS ONLY''',{'sid':session['student_id'],'subject':row['subject_id'],'term':row['term_id']}):
            flash('You are already enrolled in this subject for this term.','info')
        else:
            execute('INSERT INTO enrollments(student_id,assignment_id) VALUES(:sid,:aid)',{'sid':session['student_id'],'aid':row['assignment_id']})
            execute('UPDATE teacher_subjects SET revision=revision+1 WHERE assignment_id=:id',{'id':row['assignment_id']})
            log_activity(f"Student joined class {row['assignment_id']} by code; prerequisite warning acknowledged.")
            flash('You have joined the class. Your teacher can now see you in the roster.','success')
        return redirect(url_for('workspace.subjects'))
    return render_template('workspace/join.html',a=row,code=code,term=active_term())


def excel_text(value):
    text=str(value or '')
    return "'"+text if text.startswith(('=','+','-','@')) else text


@workspace_bp.route('/class/<int:aid>/template')
@login_required('faculty')
def template(aid):
    from openpyxl import Workbook
    row=teacher_class(aid);cats,assessments,roster,scores=gb.content(aid)
    workbook=Workbook();sheet=workbook.active;sheet.title='Scores'
    sheet.append(['Student ID','Student Name']+[str(a['component_id'])+' · '+a['component_name'] for a in assessments])
    for student in roster:
        sheet.append([excel_text(student['id_number']),excel_text(student['full_name'])]+[scores.get(student['enrollment_id'],{}).get(a['component_id'],(None,None))[0] for a in assessments])
    meta=workbook.create_sheet('Metadata');meta.append(['Class ID',aid]);meta.append(['Revision',row['revision']]);meta.append(['Blank cells','Leave existing scores unchanged. Formulas are not supported.'])
    meta.append(['Assessment ID','Assessment','Maximum','Category ID'])
    for a in assessments:meta.append([a['component_id'],excel_text(a['component_name']),a['maximum_score'],a['category_id']])
    from openpyxl.styles import Font,PatternFill
    for ws in workbook:
        ws.freeze_panes='C2' if ws.title=='Scores' else 'A5'
        for cell in ws[1]:cell.font=Font(color='FFFFFF',bold=True);cell.fill=PatternFill('solid',fgColor='8A6D3B')
        for column in ws.columns:ws.column_dimensions[column[0].column_letter].width=24
    stream=io.BytesIO();workbook.save(stream);stream.seek(0)
    return send_file(stream,as_attachment=True,download_name=f'class-{aid}-scores.xlsx',mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@workspace_bp.route('/class/<int:aid>/import',methods=['POST'])
@login_required('faculty')
def import_excel(aid):
    from openpyxl import load_workbook
    from openpyxl.utils.exceptions import InvalidFileException
    from xml.etree.ElementTree import ParseError
    row=teacher_class(aid,True);cats,assessments,roster,scores=gb.content(aid)
    file=request.files.get('workbook')
    if not file or not file.filename.lower().endswith('.xlsx'):abort(400,description='Choose the class .xlsx template.')
    load_preview(consume=True)
    raw=file.read();errors=[];changes=[]
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if sum(i.file_size for i in archive.infolist())>20_000_000 or len(archive.infolist())>200:raise ValueError('Workbook is too large when expanded.')
        book=load_workbook(io.BytesIO(raw),read_only=True,data_only=False,keep_links=False)
        if set(book.sheetnames)!={'Scores','Metadata'}:raise ValueError('Use the unchanged class template.')
        metadata=list(book['Metadata'].values)
        if metadata[0][1]!=aid or metadata[1][1]!=row['revision']:raise ValueError('Template is stale or belongs to another class. Download a fresh template.')
        expected_meta=[(a['component_id'],excel_text(a['component_name']),a['maximum_score'],a['category_id']) for a in assessments]
        if [tuple(r[:4]) for r in metadata[4:]]!=expected_meta:raise ValueError('Assessment configuration changed. Download a new template.')
        sheet=book['Scores']
        if sheet.max_row>10001 or sheet.max_column>252:raise ValueError('Workbook exceeds the allowed dimensions.')
        iterator=sheet.iter_rows();header=next(iterator)
        expected=['Student ID','Student Name']+[str(a['component_id'])+' · '+a['component_name'] for a in assessments]
        if [c.value for c in header]!=expected:raise ValueError('Assessment columns were changed. Use the class template.')
        students={excel_text(s['id_number']):s for s in roster};seen=set()
        for index,cells in enumerate(iterator,2):
            if not any(c.value is not None for c in cells):continue
            key=str(cells[0].value or '').strip()
            if key not in students or key in seen:errors.append(f'Row {index}: unknown or duplicate student ID.');continue
            seen.add(key);student=students[key]
            for a,cell in zip(assessments,cells[2:]):
                if cell.value is None:continue
                try:
                    if cell.data_type=='f' or isinstance(cell.value,bool):raise ValueError('Use numeric scores, not formulas.')
                    score=gb.decimal(cell.value,0,a['maximum_score'])
                    previous=scores.get(student['enrollment_id'],{}).get(a['component_id'],(None,None))[0]
                    if previous is None or Decimal(str(previous))!=score:
                        changes.append(dict(eid=student['enrollment_id'],cid=a['component_id'],score=str(score),maximum=str(a['maximum_score']),student=student['full_name'],assessment=a['component_name'],previous=previous))
                except ValueError as error:errors.append(f'Row {index}, {a["component_name"]}: {error}')
        book.close()
    except (ValueError,KeyError,IndexError,zipfile.BadZipFile,StopIteration,InvalidFileException,ParseError,OSError) as error:errors.append('Invalid workbook: '+str(error))
    if len(errors)>100:errors=errors[:100]+['More errors omitted. Correct the template and try again.']
    if not errors:store_preview(dict(type='xlsx',aid=aid,revision=row['revision'],changes=changes))
    return render_template('workspace/import.html',a=row,changes=changes,errors=errors)


@workspace_bp.route('/class/<int:aid>/import/confirm',methods=['POST'])
@login_required('faculty')
def confirm_import(aid):
    row=teacher_class(aid,True);preview=load_preview()
    if not preview or preview.get('type')!='xlsx' or preview.get('aid')!=aid or preview['revision']!=row['revision']:abort(409,description='Import preview expired or class changed. Upload a fresh template.')
    cats,assessments,roster,_=gb.content(aid)
    allowed={s['enrollment_id'] for s in roster};components={a['component_id']:a for a in assessments};updates=[]
    for change in preview['changes']:
        if change['eid'] not in allowed or change['cid'] not in components:abort(409)
        maximum=components[change['cid']]['maximum_score']
        updates.append((change['eid'],change['cid'],gb.decimal(change['score'],0,maximum),maximum))
    write_scores(row,updates);changed(row,f'Excel import saved {len(updates)} draft score changes.')
    # Revision protects replay even if commit acknowledgment is interrupted.
    return redirect(url_for('workspace.classroom',aid=aid))
