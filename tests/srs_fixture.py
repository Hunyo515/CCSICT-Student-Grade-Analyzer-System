"""Synthetic SRS records, isolated from production Oracle and email."""
from datetime import datetime
from unittest.mock import patch
from audit_fixture import AuditFixture,all_rows,one,PROFILE
from app import gradebook, srs_grading
from app.routes import srs,admin,student


def records():
    result=[]
    for aid,status,code,title in [(10,'IN_PROGRESS','DSA 111','Fundamentals of Programming'),(20,'PUBLISHED','DSA 112','Statistical Foundations')]:
        offset=0 if aid==10 else 10
        cats=[dict(assignment_id=aid,category_id=1+offset,category_name='Lecture',weight_percent=60,display_order=0),dict(assignment_id=aid,category_id=2+offset,category_name='Laboratory',weight_percent=40,display_order=1)]
        comps=[dict(assignment_id=aid,component_id=i+offset,component_name=name,category_id=cat+offset,weight_percent=weight,maximum_score=maximum) for i,name,cat,weight,maximum in [(1,'Quiz 1',1,50,100),(2,'Midterm Examination',1,50,100),(3,'Laboratory Activity 1',2,100,20)]]
        people=[dict(assignment_id=aid,enrollment_id=i+offset,student_id=i+2,id_number=f'TEST-{i:03}',full_name=name,program='BSDSA',year_level='1st Year',main_section='BSDSA 1A',section='BSDSA 1A',sex=sex,enrollment_type=kind,status='ACTIVE',user_id=i+2) for i,name,sex,kind in [(1,'Ana Dela Cruz','FEMALE','REGULAR'),(2,'José Santos','MALE','IRREGULAR'),(3,'Maria Bautista','FEMALE','REGULAR')]]
        scores={1+offset:{1+offset:(80,100),2+offset:(100,100),3+offset:(18,20)},2+offset:{1+offset:(90,100),2+offset:(90,100),3+offset:(18,20)},3+offset:{1+offset:(70,100),3+offset:(15,20)}}
        row=dict(assignment_id=aid,subject_id=aid+10,teacher_id=2,teacher_user_id=2,term_id=1,subject_code=code,subject_name=title,units=3,program='BSDSA',year_level='1st Year',section='BSDSA 1A',teacher_name='Audit faculty',full_name='Audit faculty',status=status,revision=4,aggregation='LEGACY',rounding_rule='UNSET',is_active=1,join_code='ABC1234567',enrollment_open='Y' if status!='PUBLISHED' else 'N',school_year='2026-2027',semester='1st Semester',prerequisite_text=None,student_count=3)
        result.append(dict(row=row,categories=cats,components=comps,students=people,scores=scores))
    return result


class SrsFixture(AuditFixture):
    def __enter__(self):
        super().__enter__();self.records=records()
        def filtered(sql,params):
            selected=self.records
            if params.get('id'):selected=[r for r in selected if r['row']['assignment_id']==params['id']]
            if "ts.status='published'" in sql:selected=[r for r in selected if r['row']['status']=='PUBLISHED']
            return selected
        def query_all(sql,params=None):
            sql=' '.join(sql.lower().split());params=params or {};selected=filtered(sql,params)
            if 'from grade_categories' in sql:return [c for r in selected for c in r['categories']]
            if 'from grade_components' in sql and 'from enrollments e' not in sql:return [c for r in selected for c in r['components']]
            if 'from grades g' in sql and 'gc.component_name' not in sql:
                return [dict(assignment_id=r['row']['assignment_id'],enrollment_id=eid,component_id=cid,score=p[0],max_score=p[1],updated_at=datetime(2026,10,27,10)) for r in selected for eid,items in r['scores'].items() for cid,p in items.items()]
            if 'from teacher_subjects ts' in sql:return [r['row'] for r in selected]
            if 'from enrollments e join teacher_subjects' in sql and 'join students st' in sql:return [s for r in selected for s in r['students']]
            if 'from enrollments e join students' in sql:return [s for r in selected for s in r['students']]
            if 'from enrollments e' in sql:
                return [dict(r['row'],enrollment_id=r['students'][0]['enrollment_id'],component_count=3) for r in selected]
            if 'from grades g' in sql:return [dict(subject_name='Statistical Foundations',component_name='Quiz 1',score=80,max_score=100,updated_at=datetime(2026,10,27,10))]
            if 'from activity_log' in sql:return [dict(message='Teacher published DSA 112 grades.',created_at=datetime(2026,10,27,10))]
            if 'count(*) as n' in sql and 'from subjects' in sql:return [dict(program='BSDSA',n=52)]
            if 'from subjects where' in sql:
                if params.get('q'):return [dict(self.records[0]['row'],semester_offered='1st Semester')]
                return [dict(r['row'],semester_offered='1st Semester') for r in self.records]
            if 'from teachers t' in sql:return [dict(teacher_id=2,user_id=2,faculty_code='TCH-001',full_name='Audit faculty',email='teacher@example.invalid',status='ACTIVE',subject_count=2)]
            return all_rows(sql,params)
        def query_one(sql,params=None):
            sql=' '.join(sql.lower().split());params=params or {}
            if 'from teacher_subjects ts' in sql:return next((r['row'] for r in self.records if r['row']['assignment_id']==params.get('id')),None)
            if 'where join_code=' in sql:return dict(assignment_id=10)
            if 'as active_students' in sql:return dict(active_students=3,active_faculty=1,subjects=52,recorded=16)
            if 'count(' in sql:return dict(n=2 if 'from subjects' in sql else 0,c=0,total=0)
            if 'from students s join users' in sql:return dict(PROFILE,program='BSDSA',section='BSDSA 1A',full_name='Ana Dela Cruz')
            return one(sql,params)
        for module in (srs,srs_grading,gradebook,admin,student):
            self.stack.enter_context(patch.object(module,'query_all',side_effect=query_all))
            if hasattr(module,'query_one'):self.stack.enter_context(patch.object(module,'query_one',side_effect=query_one))
        return self
