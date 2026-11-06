"""Synthetic records for read-only browser QA; never used in production."""
from datetime import datetime
from unittest.mock import patch
from audit_fixture import AuditFixture,all_rows,one,USERS
from app import gradebook as gb

A=dict(assignment_id=10,subject_id=20,teacher_id=2,teacher_user_id=2,term_id=1,
       subject_code='DSA 111',subject_name='Fundamentals of Programming',units=3,
       program='BSDSA',year_level='1st Year',section='BSDSA 1A',teacher_name='Audit faculty',
       full_name='Audit faculty',status='IN_PROGRESS',revision=4,aggregation='EQUAL',rounding_rule='HALF_UP',
       is_active=1,join_code='ABC1234567',enrollment_open='Y',school_year='2026-2027',semester='1st Semester',
       prerequisite_text='None',student_count=3,students=3)
CATS=[dict(category_id=1,category_name='Laboratory',weight_percent=30,display_order=0),dict(category_id=2,category_name='Examinations',weight_percent=70,display_order=1)]
ITEMS=[dict(component_id=1,component_name='Laboratory Activity 1',category_id=1,maximum_score=20,weight_percent=100),dict(component_id=2,component_name='Midterm Examination',category_id=2,maximum_score=50,weight_percent=100)]
ROSTER=[dict(enrollment_id=i,student_id=i+2,id_number=f'TEST-{i:03}',full_name=name,program='BSDSA',section='BSDSA 1A') for i,name in enumerate(('Ana Dela Cruz','José Santos','Maria Bautista'),1)]
SCORES={1:{1:(18,20),2:(40,50)},2:{1:(15,20),2:(45,50)},3:{1:(0,20)}}


def payload():
    return dict(subject={k:A[k] for k in ('subject_code','subject_name','units','section','school_year','semester','aggregation','rounding_rule')},
        categories=CATS,assessments=ITEMS,students=[dict(**s,scores={str(k):v for k,v in SCORES.get(s['enrollment_id'],{}).items()},result=gb.calculate(CATS,ITEMS,SCORES.get(s['enrollment_id'],{}),'EQUAL','HALF_UP')) for s in ROSTER])


class RebuildFixture(AuditFixture):
    def __enter__(self):
        super().__enter__()
        self.record=payload()
        def latest(aid,kind):
            if kind not in ('RELEASE','PUBLICATION','SUBMISSION'):return None
            return dict(version_id=12,actor_user_id=2,created_at=datetime(2026,10,27,10,0),data=self.record)
        def query_all(sql,params=None):
            compact=' '.join(sql.lower().split());params=params or {}
            if 'count(*) as n' in compact and 'from subjects' in compact:return [dict(program='BSDSA',n=52)]
            if 'from grade_versions v' in compact:
                import json
                return [dict(assignment_id=10,payload=json.dumps(self.record),created_at=datetime(2026,10,27,10,0))]
            if 'from grade_versions where' in compact:return [dict(version_id=12,kind='SUBMISSION',created_at=datetime(2026,10,27,10,0),reason=None)]
            if 'from grade_categories' in compact:return CATS
            if 'from grade_components' in compact:return ITEMS
            if 'from grades g join enrollments' in compact:
                return [dict(enrollment_id=eid,component_id=cid,score=pair[0],max_score=pair[1]) for eid,items in SCORES.items() for cid,pair in items.items()]
            if 'count(distinct st.student_id)' in compact:return [dict(program='BSDSA',students=3)]
            if 'from teacher_subjects ts' in compact:return [dict(A)]
            if 'from enrollments e join teacher_subjects' in compact:return [dict(A)]
            if 'from enrollments e join students' in compact:return ROSTER
            if 'from subjects where' in compact:return [dict(A,semester_offered='1st Semester')]
            if 'from teachers t' in compact:return [dict(teacher_id=2,full_name='Audit faculty',email='teacher@example.invalid',status='ACTIVE',faculty_code='TCH-001',subject_count=1)]
            return all_rows(sql,params)
        def query_one(sql,params=None):
            compact=' '.join(sql.lower().split())
            if 'from teacher_subjects ts' in compact:return dict(A)
            if 'from teacher_subjects where join_code' in compact:return dict(assignment_id=10)
            return one(sql,params)
        from app.routes import workspace,admin
        for module in (workspace,gb,admin):
            self.stack.enter_context(patch.object(module,'query_all',side_effect=query_all))
            self.stack.enter_context(patch.object(module,'query_one',side_effect=query_one))
        self.stack.enter_context(patch.object(gb,'latest',side_effect=latest))
        return self
