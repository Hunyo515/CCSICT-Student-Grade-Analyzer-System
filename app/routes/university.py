"""University account delivery and selected current-term self-enlistment."""
import re
from flask import Blueprint,abort,flash,redirect,render_template,request,session,url_for
from ..auth import login_required,hash_password
from ..db import query_all,query_one,execute,execute_returning_id
from .. import academic
from ..curriculum import canonical_program,PROGRAM_NAMES
from .admin import log_activity

university_bp=Blueprint('university',__name__,url_prefix='/university')


@university_bp.route('/credentials')
@login_required('admin')
def credentials():
    from ..university_accounts import reveal
    return render_template('admin/credentials.html',credential=reveal(),term=academic.selected())


@university_bp.route('/credentials/<role>/<int:profile_id>/reset',methods=['POST'])
@login_required('admin')
def reset_credentials(role,profile_id):
    from ..university_accounts import temporary_password,issue
    if role not in ('student','faculty'):abort(404)
    table,key=('students','student_id') if role=='student' else ('teachers','teacher_id')
    row=query_one(f'SELECT u.user_id,u.username FROM {table} p JOIN users u ON u.user_id=p.user_id WHERE p.{key}=:id FOR UPDATE OF u.password_hash WAIT 5',{'id':profile_id})
    if not row:abort(404)
    password=temporary_password();hashed=hash_password(password)
    execute('UPDATE users SET password_hash=:pw,must_change_password=:required,updated_at=SYSTIMESTAMP WHERE user_id=:id',{'pw':hashed,'required':0 if role=='faculty' else 1,'id':row['user_id']})
    issue(row['user_id'],row['username'],password,hashed)
    log_activity(f'Admin generated replacement credentials for user {row["user_id"]}')
    return redirect(url_for('university.credentials'))


@university_bp.route('/terms/<int:term_id>/enlistment',methods=['POST'])
@login_required('admin')
def open_enlistment(term_id):
    # All term-state mutations take the same locks in the same order.
    terms=query_all('SELECT * FROM school_terms ORDER BY term_id FOR UPDATE WAIT 5')
    term=next((t for t in terms if t['term_id']==term_id),None)
    current=next((t for t in terms if t['is_active']),None)
    if not term:abort(404)
    if term['enlistment_open']:
        execute('UPDATE school_terms SET enlistment_open=0 WHERE term_id=:id',{'id':term_id})
        flash('Future class preparation closed. Existing classes and enrollments are preserved.','success')
    else:
        if not current or academic.order(term)<=academic.order(current):abort(409,description='Enlistment can open only for a term after the active term.')
        execute('UPDATE school_terms SET enlistment_open=0 WHERE enlistment_open=1')
        execute('UPDATE school_terms SET enlistment_open=1 WHERE term_id=:id',{'id':term_id})
        flash('Future class preparation opened. Students can enlist in these classes once the term is active.','success')
    log_activity(f'Admin changed enlistment availability for term {term_id}')
    return redirect(url_for('admin.settings'))


def offerings(term,program,year_level,section):
    return query_all("""SELECT ts.assignment_id,s.subject_id,:section AS section,
        COALESCE(ts.status,'DRAFT') AS status,s.subject_code,s.subject_name,
        s.units,s.year_level,s.prerequisite_text,s.prerequisite_subject_id,
        COALESCE(u.full_name,'Faculty not yet assigned') AS teacher_name
        FROM subjects s
        LEFT JOIN teacher_subjects ts ON ts.subject_id=s.subject_id AND ts.term_id=:term
            AND UPPER(TRIM(ts.section))=UPPER(TRIM(:section))
        LEFT JOIN teachers t ON t.teacher_id=ts.teacher_id LEFT JOIN users u ON u.user_id=t.user_id
        WHERE s.program=:program AND s.year_level=:year_level
        AND s.semester_offered=:semester AND s.is_archived=0
        ORDER BY s.subject_code,s.subject_id""",dict(term=term['term_id'],program=program,
            semester=term['semester'],year_level=year_level,section=section))


def current_enrollments(student_id,term_id):
    return query_all("""SELECT e.enrollment_id,e.assignment_id,ts.subject_id
        FROM enrollments e JOIN teacher_subjects ts ON ts.assignment_id=e.assignment_id
        WHERE e.student_id=:sid AND ts.term_id=:term""",dict(sid=student_id,term=term_id))


@university_bp.route('/enlistme',methods=['GET','POST'])
@login_required('student')
def enlistme():
    from .student import get_student
    student=get_student()
    if not student or student['status']!='ACTIVE':abort(403)
    from ..student_progress import YEARS,curriculum,passed_subjects,eligibility,residency
    program=canonical_program(student['program']);stored_year=student['year_level'];section=student['section']
    if request.method=='POST':query_all('SELECT term_id FROM school_terms ORDER BY term_id FOR UPDATE WAIT 5')
    target=academic.active()
    existing=current_enrollments(student['student_id'],target['term_id']) if target else []
    if existing:
        if request.method=='POST':
            flash('You have already enlisted for this semester.', 'info')
            return redirect(url_for('university.enlistme'))
        return render_template('srs/enlistme.html',target=target,term=target,enlistment_complete=True)
    student.update(residency(student,target))
    year=student['curriculum_year'];allowed_years=YEARS[:min(student['residency_year'],4)]
    selected_year=request.values.get('year_level',year)
    if selected_year not in allowed_years:abort(403,description='You may access only your residency year and previous year levels.')
    known=query_all("""SELECT section_name AS section FROM academic_sections WHERE term_id=:term AND program=:program AND year_level=:year
        UNION SELECT ts.section FROM teacher_subjects ts JOIN subjects s ON s.subject_id=ts.subject_id
        WHERE ts.term_id=:term AND s.program=:program AND s.year_level=:year ORDER BY section""",dict(term=target['term_id'] if target else 0,program=program,year=selected_year))
    section_pattern=re.escape(program or '')+' '+selected_year[0]+r'-[1-9][0-9]?'
    section_options=sorted({r['section'] for r in known if re.fullmatch(section_pattern,r['section'])})
    previous_section=re.sub(r' [1-4]-',' '+selected_year[0]+'-',section)
    if re.fullmatch(section_pattern,previous_section):section_options=sorted(set(section_options)|{previous_section})
    if not section_options:section_options=[f'{program} {selected_year[0]}-1']
    offering_section=request.values.get('section',previous_section if previous_section in section_options else '')
    if offering_section and offering_section not in section_options:abort(400,description='Choose one of the available sections.')
    valid_profile=bool(program and offering_section)
    if request.method=='POST':
        if not target:abort(409,description='There is no active school term. Contact your administrator.')
        if request.form.get('enlistment_term_id',type=int)!=target['term_id']:
            abort(409,description='The current term changed. Reload EnlistMe before continuing.')
        if not valid_profile:abort(400,description='Choose a section before selecting subjects.')
    available=offerings(target,program,selected_year,offering_section) if target and valid_profile else []
    catalog=curriculum(program);passed=passed_subjects(student['student_id'])
    potential={r['subject_id'] for r in available}|{r['subject_id'] for r in existing}
    available=[dict(r,eligibility=eligibility(r,dict(student,year_level=year),catalog,passed,potential)) for r in available]
    if request.method=='POST':
        if not available:abort(409,description='No curriculum subjects match your program, year level, and current semester. Contact your administrator.')
        ids=request.form.getlist('subject_ids')
        if not ids:abort(400,description='Select at least one subject to enroll.')
        if len(ids)!=len(set(ids)) or any(not re.fullmatch(r'[1-9][0-9]*',v) for v in ids):
            abort(400,description='Invalid subject selection.')
        chosen={int(v) for v in ids}
        if not chosen.issubset({r['subject_id'] for r in available}):
            abort(400,description='Select only subjects listed for your current term, program, and year level.')
        # Same lock order as class creation: term, curriculum subject, class, student.
        for sid in sorted(chosen):
            if not query_one('SELECT subject_id FROM subjects WHERE subject_id=:id FOR UPDATE WAIT 5',{'id':sid}):
                abort(409,description='The curriculum changed. Reload EnlistMe.')
        scope={r['subject_id']:r for r in offerings(target,program,selected_year,offering_section)}
        if not chosen.issubset(scope):abort(409,description='The curriculum changed. Reload EnlistMe.')
        locked={}
        for aid in sorted({scope[sid]['assignment_id'] for sid in chosen if scope[sid]['assignment_id'] is not None}):
            row=query_one('SELECT status FROM teacher_subjects WHERE assignment_id=:id FOR UPDATE WAIT 5',{'id':aid})
            if not row:abort(409,description='A class changed. Reload EnlistMe before continuing.')
            locked[aid]=row['status']
        person=query_one('SELECT student_id,id_number,status,program,year_level,section FROM students WHERE student_id=:id FOR UPDATE WAIT 5',{'id':student['student_id']})
        if not person or person['status']!='ACTIVE':abort(403)
        if person.get('id_number')!=student.get('id_number') or (canonical_program(person['program']),person['year_level'],person['section'])!=(program,stored_year,section):
            abort(409,description='Your student profile changed. Reload EnlistMe before continuing.')
        existing=current_enrollments(student['student_id'],target['term_id'])
        if existing:
            abort(409,description='You have already enlisted for this semester.')
        old={e['assignment_id'] for e in existing}
        for sid in chosen:
            aid=scope[sid]['assignment_id']
            if aid not in old and locked.get(aid) in ('PUBLISHED','SUBMITTED'):
                abort(409,description='A selected class roster is locked. Contact your administrator to complete enrollment.')
            if any(e['subject_id']==sid and e['assignment_id']!=aid for e in existing):
                abort(409,description='You are already enrolled in another section of a selected subject. Contact your administrator.')
        # Re-evaluate on the server after roster/student locks, before any writes.
        passed=passed_subjects(student['student_id'])
        concurrent=chosen|{r['subject_id'] for r in existing}
        for sid in chosen:
            reason=eligibility(scope[sid],dict(student,year_level=year),catalog,passed,concurrent)
            if reason:abort(409,description=scope[sid]['subject_code']+': '+reason+'.')
        added=0
        for sid in sorted(chosen):
            aid=scope[sid]['assignment_id']
            if aid in old:continue
            if aid is None:
                aid=execute_returning_id('INSERT INTO teacher_subjects(subject_id,term_id,section) VALUES(:subject,:term,:section) RETURNING assignment_id INTO :out_id',dict(subject=sid,term=target['term_id'],section=offering_section))
            execute('INSERT INTO enrollments(student_id,assignment_id) VALUES(:sid,:aid)',dict(sid=student['student_id'],aid=aid))
            execute('UPDATE teacher_subjects SET revision=revision+1 WHERE assignment_id=:id',{'id':aid})
            added+=1
        if not re.fullmatch(re.escape(program)+r' [1-4]-[1-9][0-9]?',section):
            section=offering_section
            execute('UPDATE students SET section=:section,year_level=:year WHERE student_id=:sid',dict(section=section,year=year,sid=student['student_id']))
        membership_year=YEARS[int(section.split(' ')[-1][0])-1]
        execute('''MERGE INTO academic_sections dst USING (SELECT :term AS term_id,:program AS program,:year_level AS year_level,:section AS section_name FROM dual) src
            ON (dst.term_id=src.term_id AND dst.program=src.program AND dst.section_name=src.section_name)
            WHEN NOT MATCHED THEN INSERT(term_id,program,year_level,section_name) VALUES(src.term_id,src.program,src.year_level,src.section_name)''',dict(term=target['term_id'],program=program,year_level=membership_year,section=section))
        sec=query_one('SELECT section_id FROM academic_sections WHERE term_id=:term AND program=:program AND section_name=:section',dict(term=target['term_id'],program=program,section=section))
        execute('''MERGE INTO student_term_memberships dst USING (SELECT :sid AS student_id,:term AS term_id,:section AS section_id FROM dual) src
            ON (dst.student_id=src.student_id AND dst.term_id=src.term_id)
            WHEN MATCHED THEN UPDATE SET dst.section_id=src.section_id
            WHEN NOT MATCHED THEN INSERT(student_id,term_id,section_id) VALUES(src.student_id,src.term_id,src.section_id)''',dict(sid=student['student_id'],term=target['term_id'],section=sec['section_id']))
        log_activity(f"Student {student['student_id']} selected {len(chosen)} current-term subjects; {added} added")
        flash(f'Enrolled in {len(chosen)} subjects for {target["school_year"]} · {target["semester"]}. {added} new enrollment(s) added.','success')
        return redirect(url_for('university.enlistme'))
    enrolled={e['subject_id'] for e in existing}
    return render_template('srs/enlistme.html',term=target,target=target,student=student,program=program,
        program_name=PROGRAM_NAMES.get(program,student['program']),offerings=available,enrolled=enrolled,
        valid_profile=valid_profile,selected_year=selected_year,year_levels=allowed_years,section_options=section_options,selected_section=offering_section)
