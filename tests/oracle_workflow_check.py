"""Opt-in Oracle integration checks. All test writes run in one rolled-back request."""
import sys
from pathlib import Path
import tempfile
from uuid import uuid4
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flask import request, session
from werkzeug.datastructures import ImmutableMultiDict
from werkzeug.exceptions import Conflict, BadRequest
from app import create_app
from app.db import query_one, query_all, execute, execute_returning_id
from app.routes import admin
from app.validation import validate_request
from config import Config


def main():
    if '--database' not in sys.argv:raise SystemExit('Pass --database to run explicit rollback-only Oracle checks.')
    checks=[]
    with tempfile.TemporaryDirectory(dir='tests') as tmp:
        class TestConfig(Config):
            TESTING=True
            SECURITY_DB=str(Path(tmp).resolve()/'security.db')
        app=create_app(TestConfig)
        with app.test_request_context('/',method='POST'):
            actor=query_one("SELECT user_id FROM users WHERE role='admin' AND status='ACTIVE' FETCH FIRST 1 ROWS ONLY")
            session.update(user_id=actor['user_id'],role='admin',full_name='Workflow test')
            term=query_one('SELECT term_id,semester FROM school_terms WHERE is_active=1')
            teacher=query_one("SELECT teacher_id FROM teachers WHERE status='ACTIVE' FETCH FIRST 1 ROWS ONLY")
            assert term and teacher,'An active term and teacher are required.'
            nonce=uuid4().hex[:10]
            code='TEST-'+nonce
            def post(endpoint,data,fn):
                request.url_rule=SimpleNamespace(endpoint=endpoint)
                request.form=ImmutableMultiDict({key:str(value) for key,value in data.items()})
                validate_request()
                return fn()
            subject_data=dict(program='BSDSA',subject_code=code,subject_name='Rollback-only test subject',units='3',
                              year_level='1st Year',semester_offered=term['semester'],lecture_units='2',lab_units='1',prerequisite_text='None')
            assert post('admin.add_subject',subject_data,admin.add_subject).status_code==302
            subject=query_one('SELECT * FROM subjects WHERE subject_code=:code',{'code':code});sid=subject['subject_id']
            checks.append('create curriculum subject')
            assert post('admin.edit_subject',{**subject_data,'subject_name':'Updated test subject'},lambda:admin.edit_subject(sid)).status_code==302
            assert query_one('SELECT subject_name FROM subjects WHERE subject_id=:id',{'id':sid})['subject_name']=='Updated test subject'
            checks.append('edit curriculum subject')
            assert post('admin.archive_subject',{'archived':'1'},lambda:admin.archive_subject(sid)).status_code==302
            assert query_one('SELECT is_archived FROM subjects WHERE subject_id=:id',{'id':sid})['is_archived']==1
            assert post('admin.archive_subject',{'archived':'0'},lambda:admin.archive_subject(sid)).status_code==302
            checks.append('archive and restore subject')
            class_data=dict(teacher_id=str(teacher['teacher_id']),subject_id=str(sid),section='TEST-'+nonce)
            assert post('admin.assign_subject',class_data,admin.assign_subject).status_code==302
            a=query_one('SELECT assignment_id FROM teacher_subjects WHERE subject_id=:id',{'id':sid});aid=a['assignment_id']
            checks.append('create class from curriculum')
            try:post('admin.assign_subject',class_data,admin.assign_subject);raise AssertionError('Duplicate class accepted')
            except Conflict:checks.append('reject duplicate class')
            try:post('admin.edit_subject',{**subject_data,'units':'4','lecture_units':'3'},lambda:admin.edit_subject(sid));raise AssertionError('Used subject units changed')
            except Conflict:checks.append('protect used subject units')
            try:post('admin.delete_subject',{},lambda:admin.delete_subject(sid));raise AssertionError('Used subject deleted')
            except Conflict:checks.append('protect used subject deletion')
            student_ids=[]
            for i,program in enumerate(('BS Data Science','BSDSA','BSCS'),1):
                user_key=execute_returning_id("""INSERT INTO users(username,password_hash,role,full_name,status)
                    VALUES(:name,'not-a-login-hash','student',:full_name,'ACTIVE') RETURNING user_id INTO :out_id""",
                    {'name':nonce+str(i),'full_name':'Rollback student '+str(i)})
                student_id=execute_returning_id("""INSERT INTO students(user_id,id_number,program,year_level,section,status)
                    VALUES(:user_key,:idnum,:program,'1st Year',:section,'ACTIVE') RETURNING student_id INTO :out_id""",
                    {'user_key':user_key,'idnum':'T'+nonce+str(i),'program':program,'section':class_data['section']})
                student_ids.append(student_id)
            request.args=ImmutableMultiDict({'assignment_id':aid,'source_section':class_data['section']})
            request.method='GET'
            html=admin.assign_student_to_section()
            assert '2 students to add' in html
            import re
            token=re.search(r'name="preview_token" value="([a-f0-9]+)"',html).group(1)
            request.method='POST'
            bulk=dict(assignment_id=aid,mode='bulk',source_section=class_data['section'],preview_token=token)
            assert post('admin.assign_student_to_section',bulk,admin.assign_student_to_section).status_code==302
            assert query_one('SELECT COUNT(*) AS n FROM enrollments WHERE assignment_id=:id',{'id':aid})['n']==2
            checks.append('bulk enroll correct program/year/section')
            try:post('admin.assign_student_to_section',bulk,admin.assign_student_to_section);raise AssertionError('Stale bulk confirmation accepted')
            except Conflict:checks.append('reject stale bulk confirmation')
            individual=dict(assignment_id=aid,mode='individual',student_id=student_ids[2])
            try:post('admin.assign_student_to_section',individual,admin.assign_student_to_section);raise AssertionError('Exception without reason accepted')
            except BadRequest:checks.append('require exception reason')
            assert post('admin.assign_student_to_section',{**individual,'exception_reason':'Approved cross-program elective'},admin.assign_student_to_section).status_code==302
            checks.append('enroll individual exception')
            eid=query_one('SELECT enrollment_id FROM enrollments WHERE student_id=:sid AND assignment_id=:aid',{'sid':student_ids[2],'aid':aid})['enrollment_id']
            component=execute_returning_id("INSERT INTO grade_components(assignment_id,component_name,weight_percent) VALUES(:aid,'Test',100) RETURNING component_id INTO :out_id",{'aid':aid})
            execute('INSERT INTO grades(enrollment_id,component_id,score,max_score) VALUES(:eid,:cid,80,100)',{'eid':eid,'cid':component})
            removal=dict(assignment_id=aid,mode='remove',enrollment_id=eid)
            try:post('admin.assign_student_to_section',removal,admin.assign_student_to_section);raise AssertionError('Graded enrollment removed')
            except Conflict:checks.append('protect enrollment with grades')
            eid2=query_one('SELECT enrollment_id FROM enrollments WHERE student_id=:sid AND assignment_id=:aid',{'sid':student_ids[1],'aid':aid})['enrollment_id']
            assert post('admin.assign_student_to_section',{**removal,'enrollment_id':eid2},admin.assign_student_to_section).status_code==302
            checks.append('remove ungraded enrollment')
            execute("UPDATE teacher_subjects SET status='PUBLISHED' WHERE assignment_id=:id",{'id':aid})
            try:post('admin.assign_student_to_section',{**individual,'student_id':student_ids[1]},admin.assign_student_to_section);raise AssertionError('Published roster changed')
            except Conflict:checks.append('protect published roster')
            # Add an unused subject and exercise permanent deletion.
            unused={**subject_data,'subject_code':'DEL-'+nonce}
            post('admin.add_subject',unused,admin.add_subject)
            delete_id=query_one('SELECT subject_id FROM subjects WHERE subject_code=:code',{'code':unused['subject_code']})['subject_id']
            post('admin.delete_subject',{},lambda:admin.delete_subject(delete_id))
            assert query_one('SELECT subject_id FROM subjects WHERE subject_id=:id',{'id':delete_id}) is None
            checks.append('delete unused subject')
        # Teardown rolled the entire request back; no after_request commit was run.
        with app.app_context():
            assert query_one('SELECT subject_id FROM subjects WHERE subject_code=:code',{'code':code}) is None
            assert query_one('SELECT user_id FROM users WHERE username=:name',{'name':nonce+'1'}) is None
        print('PASS',len(checks),'Oracle workflow checks; all test records rolled back.')
        for check in checks:print('PASS',check)


if __name__=='__main__':main()


