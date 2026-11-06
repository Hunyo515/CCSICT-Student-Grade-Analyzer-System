"""Isolated audit fixtures. Never imported by the production application."""
import tempfile
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from flask import session, request, redirect
from app import create_app
from config import Config
from app.security import create_session
from app.auth import hash_password
FIXTURE_HASH = hash_password("AuditPassword123!")

USERS = {
 role:dict(user_id=i, username=role, role=role, status='ACTIVE', full_name='Audit '+role, email=role+'@example.invalid', password_hash=FIXTURE_HASH)
 for i,role in enumerate(('admin','faculty','student'),1)
}
TERM = dict(term_id=1,school_year='2026-2027',semester='1st Semester',is_active=1,enlistment_open=0)
PROFILE = dict(student_id=3,user_id=3,id_number='TEST-003',full_name='Audit student',program='BSCS',year_level='1st Year',section='A',contact_number='',status='ACTIVE',email='student@example.invalid',sex='FEMALE',enrollment_type='REGULAR')


def one(sql, params=None):
    sql=' '.join(sql.lower().split());params=params or {}
    if 'count(' in sql: return {'n':0,'c':0,'total':0}
    if 'from users' in sql:
        if 'username' in params:
            if 'lower(email) = lower(:username)' in sql and "role" in params and params['role']=='faculty':
                return next((u for u in USERS.values() if u['email'].lower()==params['username'].lower() and u['role']=='faculty'),None)
            return USERS.get(params['username'])
        uid=params.get('id',params.get('user_id',session.get('user_id',1)))
        return next((u for u in USERS.values() if u['user_id']==uid),None)
    if 'from school_terms' in sql: return None if 'where enlistment_open=1' in sql else dict(TERM)
    if 'from students' in sql: return dict(PROFILE)
    if 'from teachers' in sql: return dict(teacher_id=2,user_id=2,status='ACTIVE')
    return None


def all_rows(sql, params=None):
    sql=' '.join(sql.lower().split())
    params=params or {}
    if 'from subjects s' in sql and params.get('program')=='BSDSA':
        from scripts.migrate_curriculum_workflow import import_rows
        return [dict(subject_id=i,subject_code=r['code'],subject_name=r['name'],units=r['units'],
                     year_level=r['year_level'],semester_offered=r['semester'],program='BSDSA',
                     lecture_units=r['lecture'],lab_units=r['lab'],prerequisite_text=r['prerequisite'],
                     units_note=r['note'],is_archived=0,prerequisite_code=None)
                for i,r in enumerate(import_rows(),1001)]
    if 'from school_terms' in sql: return [dict(TERM)]
    return []


class AuditFixture:
    def __enter__(self):
        self.stack=ExitStack()
        self.tmp=self.stack.enter_context(tempfile.TemporaryDirectory(dir=Path('tests').resolve()))
        class TestConfig(Config):
            TESTING=True
            SECRET_KEY='audit-only-random-length-secret-not-for-production-123456'
            SECURITY_DB=str(Path(self.tmp)/'security.db')
            SESSION_COOKIE_SECURE=False
        with patch('app.init_pool'):
            self.app=create_app(TestConfig)
        from app.routes import auth,admin,faculty,student
        from app import db,notifications,gradebook,srs_grading,academic,university_accounts,student_progress
        from app.routes import workspace,srs,university
        for module in (auth,admin,faculty,student,db,notifications,gradebook,workspace,srs,srs_grading,academic,university,university_accounts,student_progress):
            for name,impl in (('query_one',one),('query_all',all_rows)):
                if hasattr(module,name): self.stack.enter_context(patch.object(module,name,side_effect=impl))
        self.stack.enter_context(patch('app.db._pool'))
        self.stack.enter_context(patch('app.insights.load_sections', return_value=[]))
        # Deliberately test-only authentication fixture. Not registered in production.
        @self.app.route('/__audit/login/<role>')
        def fixture_login(role):
            user=USERS[role]
            session.clear(); session.update({k:user[k] for k in ('user_id','username','role','full_name')})
            session.permanent=True
            if role=='faculty': session['teacher_id']=2
            if role=='student': session['student_id']=3
            create_session(user)
            return redirect('/'+role+'/dashboard')
        return self

    def __exit__(self,*args):
        self.stack.close()

    def client(self,role):
        client=self.app.test_client()
        client.get('/__audit/login/'+role)
        return client

ASSIGNMENT=dict(assignment_id=10,teacher_id=2,subject_id=20,subject_code='CS101',subject_name='Programming',section='A',status='PUBLISHED',revision=1,student_count=1,term_id=1,join_code='TEST1234',enrollment_open='Y',units=3)
ENROLLMENT={**PROFILE,**ASSIGNMENT,'enrollment_id':30,'teacher_name':'Audit faculty','component_count':1}
COMPONENT=dict(component_id=40,component_name='Exam',weight_percent=100,category_id=None)
GRADE=dict(component_id=40,enrollment_id=30,score=80,max_score=100)

class PopulatedAuditFixture(AuditFixture):
    def __enter__(self):
        super().__enter__()
        from insight_fixture import sample_sections
        self.stack.enter_context(patch('app.insights.load_sections', side_effect=sample_sections))
        from app.routes import auth,admin,faculty,student
        from app import db,notifications
        def populated_one(sql,params=None):
            text=' '.join(sql.lower().split())
            if 'count(' in text:return {'n':1,'c':1,'total':1}
            if 'from teacher_subjects' in text:return dict(ASSIGNMENT)
            return one(sql,params)
        def populated_all(sql,params=None):
            from datetime import datetime
            text=' '.join(sql.lower().split())
            if 'from grades g' in text and 'updated_at' in text:return [{**GRADE,'subject_name':'Programming','component_name':'Exam','updated_at':datetime(2026,10,24)}]
            if 'from grade_components' in text and 'from enrollments e' not in text:return [dict(COMPONENT)]
            if 'from grade_categories' in text:return []
            if 'from enrollments e' in text and 'join grades' in text:return [dict(GRADE)]
            if 'from enrollments e' in text:return [{**ENROLLMENT,'created_at':datetime(2026,10,24)}]
            if 'from teacher_subjects ts' in text:return [dict(ASSIGNMENT)]
            if 'from grades' in text:return [dict(GRADE)]
            if 'from students s' in text and 'join enrollments' in text:return [{**PROFILE,**GRADE,**COMPONENT,'units':3,'category_weight':None}]
            if 'from students s' in text:return [dict(PROFILE)]
            return all_rows(sql,params)
        for module in (auth,admin,faculty,student,db,notifications):
            if hasattr(module,'query_one'):self.stack.enter_context(patch.object(module,'query_one',side_effect=populated_one))
            if hasattr(module,'query_all'):self.stack.enter_context(patch.object(module,'query_all',side_effect=populated_all))
        return self
