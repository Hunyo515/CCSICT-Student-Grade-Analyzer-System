"""Rollback-only verification of faculty deletion with published academic history."""
from pathlib import Path
import sys
import tempfile
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flask import session
from app import create_app
from app.auth import hash_password
from app.db import execute,execute_returning_id,query_one,get_connection
from app.gradebook import save_version
from app.routes import admin,srs
from config import Config


def main():
    with tempfile.TemporaryDirectory(dir=Path('tests').resolve()) as directory:
        class TestConfig(Config):
            SECURITY_DB=str(Path(directory)/'security.sqlite3')
        app=create_app(TestConfig)
        with app.test_request_context('/',method='POST'):
            conn=get_connection()
            try:
                owner=query_one("SELECT user_id,full_name FROM users WHERE role='admin' AND status='ACTIVE' FETCH FIRST 1 ROWS ONLY")
                term=query_one('SELECT term_id,semester FROM school_terms WHERE is_active=1')
                assert owner and term
                suffix=uuid4().hex[:8]
                password=hash_password('DeletionAcceptance123!')
                teacher_user=execute_returning_id("INSERT INTO users(username,password_hash,role,full_name,email,status) VALUES(:name,:pw,'faculty','Deletion Test Faculty',:email,'ACTIVE') RETURNING user_id INTO :out_id",dict(name='DEL-'+suffix,pw=password,email=f'deletion.{suffix}@isu.edu.ph'))
                tid=execute_returning_id("INSERT INTO teachers(user_id,faculty_code,status) VALUES(:user_key,:code,'ACTIVE') RETURNING teacher_id INTO :out_id",dict(user_key=teacher_user,code='DEL-'+suffix))
                student_user=execute_returning_id("INSERT INTO users(username,password_hash,role,full_name,email,status) VALUES(:name,:pw,'student','Deletion Test Student',:email,'ACTIVE') RETURNING user_id INTO :out_id",dict(name='STU-'+suffix,pw=password,email=f'student.{suffix}@isu.edu.ph'))
                sid=execute_returning_id("INSERT INTO students(user_id,id_number,program,year_level,section,status) VALUES(:user_key,:code,'BSCS','1st Year','BSCS 1-99','ACTIVE') RETURNING student_id INTO :out_id",dict(user_key=student_user,code='DEL-'+suffix))
                subject=execute_returning_id("INSERT INTO subjects(subject_code,subject_name,units,program,year_level,semester_offered) VALUES(:code,'Deletion Test Subject',3,'BSCS','1st Year',:semester) RETURNING subject_id INTO :out_id",dict(code='DEL-'+suffix,semester=term['semester']))
                aid=execute_returning_id("INSERT INTO teacher_subjects(teacher_id,subject_id,term_id,section,status) VALUES(:teacher,:subject,:term,'BSCS 1-99','PUBLISHED') RETURNING assignment_id INTO :out_id",dict(teacher=tid,subject=subject,term=term['term_id']))
                eid=execute_returning_id('INSERT INTO enrollments(student_id,assignment_id) VALUES(:sid,:aid) RETURNING enrollment_id INTO :out_id',dict(sid=sid,aid=aid))
                component=execute_returning_id("INSERT INTO grade_components(assignment_id,component_name,weight_percent,maximum_score) VALUES(:aid,'Deletion test score',100,100) RETURNING component_id INTO :out_id",dict(aid=aid))
                execute('INSERT INTO grades(enrollment_id,component_id,score,max_score) VALUES(:eid,:cid,85,100)',dict(eid=eid,cid=component))
                session.update(user_id=teacher_user,role='faculty',full_name='Deletion Test Faculty')
                version=save_version(dict(assignment_id=aid,revision=0),'PUBLICATION',{'model':'SRS','students':[]})
                session.update(user_id=owner['user_id'],role='admin',full_name=owner['full_name'])
                response=admin.delete_teacher(tid)
                assert response.status_code==302 and response.location.endswith('/admin/teachers')
                assert not query_one('SELECT user_id FROM users WHERE user_id=:id',{'id':teacher_user})
                assert not query_one('SELECT teacher_id FROM teachers WHERE teacher_id=:id',{'id':tid})
                assert query_one('SELECT teacher_id FROM teacher_subjects WHERE assignment_id=:id',{'id':aid})['teacher_id'] is None
                assert query_one('SELECT enrollment_id FROM enrollments WHERE enrollment_id=:id',{'id':eid})
                assert query_one('SELECT score FROM grades WHERE enrollment_id=:id',{'id':eid})['score']==85
                history=query_one('SELECT actor_user_id,actor_name FROM grade_versions WHERE version_id=:id',{'id':version})
                assert history==dict(actor_user_id=None,actor_name='Deletion Test Faculty')
                # A replacement can be assigned without reopening published grades.
                replacement=query_one("SELECT t.teacher_id,t.user_id FROM teachers t JOIN users u ON u.user_id=t.user_id WHERE t.status='ACTIVE' AND u.status='ACTIVE' FETCH FIRST 1 ROWS ONLY")
                if replacement:
                    srs.assign_class_faculty(dict(assignment_id=aid,teacher_id=None,status='PUBLISHED',subject_code='DEL-'+suffix,section='BSCS 1-99'),replacement)
                    row=query_one('SELECT teacher_id,status FROM teacher_subjects WHERE assignment_id=:id',{'id':aid})
                    assert row['teacher_id']==replacement['teacher_id'] and row['status']=='PUBLISHED'
                print('PASS: faculty account deleted; published class, enrollments, scores, publication record, and historical author name retained. All test changes rolled back.')
            finally:conn.rollback()


if __name__=='__main__':main()
