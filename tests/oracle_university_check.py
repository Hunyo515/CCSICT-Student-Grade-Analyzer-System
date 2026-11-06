"""University acceptance against Oracle. Every academic write is rolled back."""
import sys,tempfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flask import request,session
from werkzeug.datastructures import ImmutableMultiDict
from werkzeug.exceptions import BadRequest,Conflict,Gone
from app import create_app,academic,srs_grading
from app.db import query_all,query_one,execute,execute_returning_id,get_connection
from app.routes import admin,srs,university,auth
from app.university_accounts import reveal
from app.auth import verify_password
from app.validation import validate_request,password_error
from config import Config

def main():
    if '--database' not in sys.argv:raise SystemExit('Use --database for rollback-only Oracle acceptance.')
    checks=[]
    with tempfile.TemporaryDirectory(dir=Path('tests').resolve()) as tmp:
        class TestConfig(Config):
            TESTING=True
            SECURITY_DB=str(Path(tmp)/'security.db')
        app=create_app(TestConfig)
        with app.test_request_context('/',method='POST'):
            conn=get_connection()
            try:
                owner=query_one("SELECT user_id FROM users WHERE role='admin' AND status='ACTIVE' FETCH FIRST 1 ROWS ONLY")
                original=academic.active();assert owner and original
                def identity(role,uid=None,sid=None):
                    session.clear();session.update(role=role,user_id=uid or owner['user_id'],student_id=sid,full_name='Acceptance Tester')
                def post(fn,data,*args):
                    request.method='POST';request.args=ImmutableMultiDict();request.form=ImmutableMultiDict(data)
                    request.url_rule=SimpleNamespace(endpoint=('srs' if fn in (srs.create_class,srs.assign_faculty) else 'university' if fn in (university.enlistme,university.open_enlistment) else 'admin')+'.'+fn.__name__)
                    
                    if fn==university.enlistme:request.form=ImmutableMultiDict(list(request.form.items(multi=True))+[('enlistment_term_id',str(tid))])
                    validate_request();return fn(*args)
                identity('admin');suffix=uuid4().hex[:8]
                post(admin.add_teacher,dict(first_name='Acceptance',middle_name='',last_name='Faculty',email=f'faculty.{suffix}@isu.edu.ph',password='AcceptanceFaculty123!',confirm_password='AcceptanceFaculty123!'))
                assert reveal() is None
                teacher=query_one('SELECT t.teacher_id,u.* FROM teachers t JOIN users u ON u.user_id=t.user_id WHERE u.email=:email',{'email':f'faculty.{suffix}@isu.edu.ph'})
                credential=dict(user_id=teacher['user_id'],username=teacher['username'],password='AcceptanceFaculty123!')
                assert credential['username'].startswith('FAC-')
                assert teacher['must_change_password']==0 and verify_password(credential['password'],teacher['password_hash'])
                checks.append('Faculty ID generated and chosen password stored without credential display; direct dashboard access')
                # Choose a valid unused ID without changing any existing student identity.
                number=next(f'99-{i:04}' for i in range(9999,9000,-1) if not query_one('SELECT student_id FROM students WHERE id_number=:n',{'n':f'99-{i:04}'}))
                fields=dict(first_name='Acceptance',middle_name='Test',last_name='Student',email=f'student.{suffix}@isu.edu.ph',id_number=number,program='BSDSA',year_level='1st Year',section='BSDSA 1-1',contact_number='09999999999')
                post(admin.add_student,fields);student_credential=reveal()
                person=query_one('SELECT * FROM students WHERE user_id=:id',{'id':student_credential['user_id']})
                assert person['middle_name']=='Test' and student_credential['username']==number
                university.reset_credentials('student',person['student_id'])
                replacement=reveal();assert replacement['password']!=student_credential['password'] and replacement['username']==number
                checks.append('Student names/contact stored separately and login username equals unique university ID')
                try:post(admin.add_student,fields);raise AssertionError('Duplicate student ID accepted')
                except Conflict:pass
                for key,value in [('id_number','CCT-001'),('contact_number','12345678901'),('section','BSCS 1A'),('email','test@gmail.com')]:
                    request.form=ImmutableMultiDict({**fields,key:value});request.url_rule=SimpleNamespace(endpoint='admin.add_student')
                    try:validate_request();raise AssertionError('Invalid '+key+' accepted')
                    except BadRequest:pass
                checks.append('Duplicate identity, old ID/section formats, invalid phone and non-institutional email rejected')
                year=next(y for y in range(2090,2200) if not query_one('SELECT term_id FROM school_terms WHERE school_year=:y',{'y':f'{y}-{y+1}'}))
                tid=execute_returning_id("INSERT INTO school_terms(school_year,semester,is_active) VALUES(:y,'2nd Semester',0) RETURNING term_id INTO :out_id",{'y':f'{year}-{year+1}'})
                university.open_enlistment(tid)
                assert academic.enlistment()['term_id']==tid and academic.active()['term_id']==original['term_id']
                subjects_to_enroll=[]
                for i in range(2):
                    sid=execute_returning_id("INSERT INTO subjects(subject_code,subject_name,units,program,year_level,semester_offered) VALUES(:code,'Acceptance curriculum subject',3,'BSDSA','1st Year','2nd Semester') RETURNING subject_id INTO :out_id",{'code':f'U{suffix}{i}'})
                    subjects_to_enroll.append(sid)
                    if i==1:execute("INSERT INTO teacher_subjects(subject_id,term_id,section) VALUES(:subject,:term,'BSDSA 1-1')",{'subject':sid,'term':tid})
                checks.append('Admin opens separate future term and prepares curriculum-matched classes without activating it')
                # Prepare classes that must not be auto-selected for this student.
                for i,(other_program,other_year,other_section,other_semester) in enumerate([
                    ('BSDSA','4th Year','BSDSA 4-1','2nd Semester'),
                    ('BSCS','1st Year','BSCS 1-1','2nd Semester'),
                    ('BSDSA','1st Year','BSDSA 1-2','2nd Semester'),
                    ('BSDSA','1st Year','BSDSA 1-1','1st Semester')],10):
                    other=execute_returning_id("INSERT INTO subjects(subject_code,subject_name,units,program,year_level,semester_offered) VALUES(:code,'Excluded curriculum subject',3,:p,:y,:s) RETURNING subject_id INTO :out_id",{'code':f'U{suffix}{i}','p':other_program,'y':other_year,'s':other_semester})
                    execute('INSERT INTO teacher_subjects(teacher_id,subject_id,term_id,section) VALUES(:t,:s,:term,:section)',{'t':teacher['teacher_id'],'s':other,'term':tid,'section':other_section})
                admin.activate_term(tid)
                identity('student',person['user_id'],person['student_id'])
                post(university.enlistme,{'subject_ids':str(subjects_to_enroll[0])})
                assert query_one('SELECT COUNT(*) AS n FROM enrollments WHERE student_id=:id',{'id':person['student_id']})['n']==1
                assert not query_one('SELECT e.enrollment_id FROM enrollments e JOIN teacher_subjects ts ON ts.assignment_id=e.assignment_id WHERE e.student_id=:id AND ts.subject_id=:subject',{'id':person['student_id'],'subject':subjects_to_enroll[1]})
                post(university.enlistme,{'subject_ids':str(subjects_to_enroll[0])})
                assert query_one('SELECT COUNT(*) AS n FROM enrollments WHERE student_id=:id',{'id':person['student_id']})['n']==1
                post(university.enlistme,{'subject_ids':str(subjects_to_enroll[1])})
                assert query_one('SELECT COUNT(*) AS n FROM enrollments WHERE student_id=:id',{'id':person['student_id']})['n']==2
                aids=[query_one('SELECT assignment_id FROM teacher_subjects WHERE subject_id=:id AND term_id=:tid',{'id':sid,'tid':tid})['assignment_id'] for sid in subjects_to_enroll]
                from app.routes.student import my_enrollments
                assert len(my_enrollments(person['student_id'],tid))==2
                assert all(query_one('SELECT teacher_id FROM teacher_subjects WHERE assignment_id=:id',{'id':aid})['teacher_id'] is None for aid in aids)
                checks.append('Only checked current-term subjects enrolled; other program/year/section/semester classes excluded; repeat idempotent')
                eid=query_one('SELECT enrollment_id FROM enrollments WHERE student_id=:id AND assignment_id=:aid',{'id':person['student_id'],'aid':aids[0]})['enrollment_id']
                cid=execute_returning_id("INSERT INTO grade_components(assignment_id,component_name,weight_percent,maximum_score) VALUES(:a,'Acceptance exam',100,100) RETURNING component_id INTO :out_id",{'a':aids[0]})
                execute('INSERT INTO grades(enrollment_id,component_id,score,max_score) VALUES(:e,:c,80,100)',{'e':eid,'c':cid})
                # Neither omitted IDs nor forged profile inputs can remove/switch classes.
                post(university.enlistme,dict(program='BSCS',section='BSCS 1-1',subject_ids=str(subjects_to_enroll[0])))
                assert query_one('SELECT COUNT(*) AS n FROM enrollments WHERE student_id=:id',{'id':person['student_id']})['n']==2
                assert query_one('SELECT score FROM grades WHERE enrollment_id=:id',{'id':eid})['score']==80
                request.method='POST';request.form=ImmutableMultiDict()
                try:srs.join();raise AssertionError('Legacy code join accepted')
                except Gone:pass
                membership=query_one('SELECT * FROM student_term_memberships WHERE student_id=:id AND term_id=:tid',{'id':person['student_id'],'tid':tid})
                assert membership and query_one('SELECT section FROM students WHERE student_id=:id',{'id':person['student_id']})['section']=='BSDSA 1-1'
                checks.append('Existing grades/enrollments preserved, forged profile ignored, legacy join blocked, and term membership saved')
                request.method='GET';request.args=ImmutableMultiDict({'term_filter':'all'})
                assert academic.selected()['term_id'] is None
                assert any(c['assignment_id']==aids[0] for c in srs_grading.load_classes(None))
                assert academic.active()['term_id']==tid
                checks.append('All-term reads do not change current-term enrollment target')
                identity('admin')
                for index,(sid,aid) in enumerate(zip(subjects_to_enroll,aids)):
                    if index==0:post(srs.create_class,dict(class_term_id=str(tid),subject_id=str(sid),teacher_id=str(teacher['teacher_id']),section='BSDSA 1-1'))
                    else:post(srs.assign_faculty,dict(teacher_id=str(teacher['teacher_id'])),aid)
                    row=query_one('SELECT assignment_id,teacher_id FROM teacher_subjects WHERE subject_id=:sid AND term_id=:tid',{'sid':sid,'tid':tid})
                    assert row['assignment_id']==aid and row['teacher_id']==teacher['teacher_id']
                assert query_one('SELECT COUNT(*) AS n FROM enrollments WHERE student_id=:id',{'id':person['student_id']})['n']==2
                assert any(c['assignment_id']==aids[0] for c in srs_grading.load_classes(tid,teacher['teacher_id']))
                checks.append('Subjects enroll before faculty assignment; assigning faculty later preserves class IDs, enrollments, and grades')
                # Password-only faculty login creates a restricted session; no email request.
                request.method='POST';request.form=ImmutableMultiDict(dict(username=teacher['email'].upper(),password=credential['password']))
                with patch('app.email_otp.begin') as mail:
                    response=auth.login('faculty');assert response.location.endswith('/faculty/dashboard');mail.assert_not_called()
                request.form=ImmutableMultiDict(dict(current_password=credential['password'],new_password='Acceptance123!Changed',confirm_password='Acceptance123!Changed'))
                request.url_rule=SimpleNamespace(endpoint='auth.change_password');validate_request();assert auth.change_password().status_code==302
                updated=query_one('SELECT password_hash,must_change_password FROM users WHERE user_id=:id',{'id':teacher['user_id']})
                assert updated['must_change_password']==0 and verify_password('Acceptance123!Changed',updated['password_hash'])
                checks.append('Faculty logs in with email directly; voluntary password change still works')
                identity('admin');admin.activate_term(tid)
                assert academic.active()['term_id']==tid and academic.enlistment() is None
                checks.append('Activating the upcoming term automatically closes its enlistment')
            finally:conn.rollback()
    for check in checks:print('PASS:',check)
    print(f'Oracle university acceptance: {len(checks)} groups passed; academic writes rolled back.')

if __name__=='__main__':main()
