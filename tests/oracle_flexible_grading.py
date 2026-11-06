"""Rollback-only acceptance of custom semester component and activity weights."""
import sys,tempfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flask import request,session
from werkzeug.datastructures import ImmutableMultiDict
from werkzeug.exceptions import BadRequest,Conflict,NotFound
from app import create_app,gradebook as gb,srs_grading as sg
from app.db import query_one,query_all,execute,execute_returning_id,get_connection
from app.routes import srs
from config import Config

def main():
    with tempfile.TemporaryDirectory(dir=Path('tests').resolve()) as directory:
        class TestConfig(Config):SECURITY_DB=str(Path(directory)/'security.sqlite3')
        app=create_app(TestConfig)
        with app.test_request_context('/',method='POST'):
            conn=get_connection()
            try:
                teacher=query_one("SELECT teacher_id,user_id FROM teachers WHERE status='ACTIVE' FETCH FIRST 1 ROWS ONLY")
                term=query_one('SELECT term_id,semester FROM school_terms WHERE is_active=1');assert teacher and term
                code='FLEX'+uuid4().hex[:7]
                subject=execute_returning_id("INSERT INTO subjects(subject_code,subject_name,units,program,year_level,semester_offered) VALUES(:code,'Flexible semester test',3,'BSCS','4th Year',:semester) RETURNING subject_id INTO :out_id",dict(code=code,semester=term['semester']))
                aid=execute_returning_id("INSERT INTO teacher_subjects(teacher_id,subject_id,term_id,section,aggregation) VALUES(:teacher,:subject,:term,'BSCS 4-99','LEGACY') RETURNING assignment_id INTO :out_id",dict(teacher=teacher['teacher_id'],subject=subject,term=term['term_id']))
                uid=execute_returning_id("INSERT INTO users(username,password_hash,role,full_name,status) VALUES(:code,'not-a-login-hash','student','Flexible Test Student','ACTIVE') RETURNING user_id INTO :out_id",dict(code=code))
                student=execute_returning_id("INSERT INTO students(user_id,id_number,program,year_level,section,status) VALUES(:user_key,:code,'BSCS','4th Year','BSCS 4-99','ACTIVE') RETURNING student_id INTO :out_id",dict(user_key=uid,code=code))
                eid=execute_returning_id('INSERT INTO enrollments(student_id,assignment_id) VALUES(:sid,:aid) RETURNING enrollment_id INTO :out_id',dict(sid=student,aid=aid))
                session.update(user_id=teacher['user_id'],teacher_id=teacher['teacher_id'],role='faculty',full_name='Acceptance Faculty')
                def post(fn,data):
                    request.method='POST';request.args=ImmutableMultiDict();request.url_rule=SimpleNamespace(endpoint='srs.'+fn.__name__)
                    request.form=ImmutableMultiDict({k:str(v) for k,v in dict(revision=gb.classroom(aid)['revision'],**data).items()})
                    return fn(aid)
                assert gb.classroom(aid)['grading_model']=='FLEXIBLE'
                for name,weight in [('Examinations',70),('Laboratory',20),('Assignments',10)]:post(srs.setup,dict(action='category',category_name=name,weight_percent=weight))
                categories={c['category_name']:c['category_id'] for c in gb.content(aid)[0]}
                for name,category,weight,maximum in [('Final Exam','Examinations',100,100),('Lab 1','Laboratory',40,50),('Lab 2','Laboratory',60,100),('Assignment 1','Assignments',100,25)]:
                    post(srs.setup,dict(action='component',component_name=name,category_id=categories[category],weight_percent=weight,maximum_score=maximum))
                activities={c['component_name']:c['component_id'] for c in gb.content(aid)[1]}
                post(srs.save_scores,{f'mark__{eid}__{activities[name]}':score for name,score in [('Final Exam',80),('Lab 1',40),('Lab 2',60),('Assignment 1',25)]})
                row,cats,comps,students,scores,results=srs.model(aid)
                assert results[eid]['total']==79.6 and results[eid]['equivalent']=='2.75'
                # Invalid outer allocation cannot be published.
                try:post(srs.setup,dict(action='edit_category',category_id=categories['Laboratory'],category_name='Laboratory',weight_percent=21));raise AssertionError('Accepted over 100%')
                except BadRequest:pass
                post(srs.setup,dict(action='edit_category',category_id=categories['Laboratory'],category_name='Laboratory',weight_percent=19))
                try:post(srs.status,dict(action='publish'));raise AssertionError('Invalid component total published')
                except BadRequest:pass
                post(srs.setup,dict(action='edit_category',category_id=categories['Laboratory'],category_name='Laboratory',weight_percent=20))
                # Other semester workspaces are read-only and keep their own setup.
                year=next(y for y in range(2300,2400) if not query_one('SELECT term_id FROM school_terms WHERE school_year=:year',{'year':f'{y}-{y+1}'}))
                other_term=execute_returning_id("INSERT INTO school_terms(school_year,semester,is_active) VALUES(:year,'2nd Semester',0) RETURNING term_id INTO :out_id",{'year':f'{year}-{year+1}'})
                other=execute_returning_id("INSERT INTO teacher_subjects(teacher_id,subject_id,term_id,section,aggregation) VALUES(:teacher,:subject,:term,'BSCS 4-99','LEGACY') RETURNING assignment_id INTO :out_id",dict(teacher=teacher['teacher_id'],subject=subject,term=other_term))
                assert not gb.content(other)[0] and not gb.content(other)[1]
                try:srs.setup(other);raise AssertionError('Historical/future semester changed')
                except Conflict:pass
                post(srs.status,dict(action='publish'))
                assert gb.classroom(aid)['status']=='PUBLISHED'
                published=next(c for c in sg.load_classes(term['term_id'],published_only=True) if c['assignment_id']==aid)
                assert published['students'][0]['result']['total']==79.6
                request.method='GET';request.args=ImmutableMultiDict()
                assert '79.6' in srs.export(aid).get_data(as_text=True)
                post(srs.status,dict(action='reopen'))
                post(srs.setup,dict(action='category',category_name='Practical Examination',weight_percent=0,activity_count=3,return_to='grades'))
                cats,comps,_,_=gb.content(aid)
                added=[c for c in comps if c['component_name'].startswith('Practical Examination')]
                assert len(added)==3 and all(c['maximum_score'] is None for c in added)
                assert sum(c['weight_percent'] for c in added)==100
                assert not sg.calculate(cats,comps,{},True)['valid']
                maxima={f"activity__{c['component_id']}__maximum":10 for c in added}
                exam=activities['Final Exam']
                post(srs.save_scores,dict(maxima,**{f'activity__{exam}__maximum':120,f'activity__{exam}__name':'Semester Exam',f'mark__{eid}__{exam}':100}))
                _,cats,comps,_,marks,results=srs.model(aid)
                assert marks[eid][exam]==(100,120)
                assert results[eid]['total']==81.93,results[eid]
                assert next(c for c in comps if c['component_id']==exam)['component_name']=='Semester Exam'
                try:
                    post(srs.save_scores,{f'activity__{exam}__maximum':50})
                    raise AssertionError('Accepted HPS below a recorded score')
                except BadRequest:pass
                assert gb.content(aid)[3][eid][exam]==(100,120)
                lab=categories['Laboratory']
                post(srs.save_scores,{'grading_basis':'POINTS',f'cat__{lab}__count':3,'new_category_name':'Oral Examination','new_category_weight':0,'new_category_count':2})
                row,cats,comps,_,marks,results=srs.model(aid)
                assert row['aggregation']=='POINTS'
                assert len([c for c in comps if c['category_id']==lab])==3
                oral=next(c for c in cats if c['category_name']=='Oral Examination')
                oral_items=[c for c in comps if c['category_id']==oral['category_id']]
                assert len(oral_items)==2 and all(c['maximum_score'] is None for c in oral_items)
                self_preview=results[eid]
                assert self_preview['total'] is None
                assert self_preview['preview_total']==81.66,self_preview
                assert marks[eid][exam]==(100,120)
                lab_items=[c for c in comps if c['category_id']==lab]
                new_lab=lab_items[-1]
                post(srs.save_scores,{'grading_basis':'POINTS',f"activity__{new_lab['component_id']}__maximum":50,**{f"activity__{c['component_id']}__maximum":20 for c in oral_items}})
                assert srs.model(aid)[-1][eid]['total']==78.33
                try:
                    post(srs.save_scores,{'grading_basis':'POINTS',f'cat__{lab}__count':1})
                    raise AssertionError('Removed an activity with recorded scores')
                except BadRequest:pass
                post(srs.save_scores,{f'activity__{exam}__date':'10/25/26'})
                assert next(c for c in gb.content(aid)[1] if c['component_id']==exam)['activity_date'].strftime('%Y-%m-%d')=='2026-10-25'
                try:
                    post(srs.save_scores,{'delete_category_id':lab,'confirm_delete':'yes'})
                    raise AssertionError('Deleted scores without explicit acknowledgement')
                except Conflict:pass
                post(srs.save_scores,{'delete_category_id':oral['category_id'],'confirm_delete':'yes'})
                assert not any(c['category_id']==oral['category_id'] for c in gb.content(aid)[0])
                post(srs.save_scores,{'delete_category_id':lab,'confirm_delete':'yes','confirm_delete_scores':'yes'})
                assert not any(c['category_id']==lab for c in gb.content(aid)[0])
                assert gb.content(aid)[3][eid][exam]==(100,120)
                print('PASS: 100% allocation cap, dates, confirmed component deletion, explicit scored-deletion consent, and preservation of other scores. All data rolled back.')
                print('PASS: inline activity counts, new component creation, blank HPS, raw-total/HPS calculation, and scored-column deletion guard. All data rolled back.')
                print('PASS: batch creation with blank HPS, inline setup and score persistence, denominator updates, and atomic invalid-HPS rejection. All data rolled back.')
                print('PASS: three custom components, nested activity weights, unequal HPS, score persistence, invalid-weight publication guard, numeric grade, semester isolation, published reporting, and CSV export. All data rolled back.')
            finally:conn.rollback()

if __name__=='__main__':main()
