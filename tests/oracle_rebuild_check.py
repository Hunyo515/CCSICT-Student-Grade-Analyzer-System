"""Real Oracle workflow checks in one rolled-back transaction; no emails sent."""
import io
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flask import request,session
from werkzeug.datastructures import ImmutableMultiDict,FileStorage
from werkzeug.exceptions import BadRequest,Conflict
from openpyxl import load_workbook
from app import create_app,gradebook as gb
from app.db import query_one,query_all,execute,execute_returning_id,get_connection
from app.routes import workspace as w
from config import Config


def main():
    if '--database' not in sys.argv:raise SystemExit('Pass --database for rollback-only checks.')
    checks=[]
    with tempfile.TemporaryDirectory(dir=Path('tests').resolve()) as tmp:
        class TestConfig(Config):
            TESTING=True
            SECURITY_DB=str(Path(tmp)/'security.db')
        app=create_app(TestConfig)
        with app.test_request_context('/',method='POST'):
            actor=query_one("SELECT user_id FROM users WHERE role='admin' AND status='ACTIVE' FETCH FIRST 1 ROWS ONLY")
            teacher=query_one("SELECT teacher_id,user_id FROM teachers WHERE status='ACTIVE' FETCH FIRST 1 ROWS ONLY")
            term=query_one('SELECT term_id FROM school_terms WHERE is_active=1')
            assert actor and teacher and term
            token=uuid4().hex[:9];code=('R'+token).upper()
            sid=execute_returning_id("INSERT INTO subjects(subject_code,subject_name,units,program,year_level,semester_offered) VALUES(:code,'Rebuild rollback test',3,'BSDSA','1st Year','1st Semester') RETURNING subject_id INTO :out_id",{'code':code})
            aid=execute_returning_id("INSERT INTO teacher_subjects(teacher_id,subject_id,term_id,section,join_code) VALUES(:teacher,:subject,:term,'TEST 1A',:code) RETURNING assignment_id INTO :out_id",{'teacher':teacher['teacher_id'],'subject':sid,'term':term['term_id'],'code':code})
            user=execute_returning_id("INSERT INTO users(username,password_hash,role,full_name,email,status) VALUES(:name,'not-a-real-hash','student','Rollback Student','test@example.invalid','ACTIVE') RETURNING user_id INTO :out_id",{'name':code})
            student=execute_returning_id("INSERT INTO students(user_id,id_number,program,year_level,section,status) VALUES(:user_key,:idnum,'BSCS','2nd Year','OTHER','ACTIVE') RETURNING student_id INTO :out_id",{'user_key':user,'idnum':code})
            def identity(role):
                session.clear();session.update(role=role,user_id=actor['user_id'] if role=='admin' else teacher['user_id'] if role=='faculty' else user,teacher_id=teacher['teacher_id'],student_id=student,full_name='Rollback test')
            def post(fn,data=None):
                request.method='POST';request.args=ImmutableMultiDict();request.files=ImmutableMultiDict()
                request.url_rule=SimpleNamespace(endpoint='workspace.'+fn.__name__)
                revision=gb.classroom(aid)['revision']
                request.form=ImmutableMultiDict({k:str(v) for k,v in dict(revision=revision,**(data or {})).items()})
                return fn(aid)
            identity('student')
            request.form=ImmutableMultiDict({'code':code});request.args=ImmutableMultiDict()
            assert w.join().status_code==302
            eid=query_one('SELECT enrollment_id FROM enrollments WHERE assignment_id=:id',{'id':aid})['enrollment_id']
            checks.append('Immediate cross-program/year/section code join')
            assert w.join().status_code==302
            assert query_one('SELECT COUNT(*) AS n FROM enrollments WHERE assignment_id=:id',{'id':aid})['n']==1
            checks.append('Repeated join cannot duplicate enrollment')
            identity('faculty')
            post(w.setup,dict(action='aggregation',aggregation='EQUAL'))
            post(w.setup,dict(action='category',category_name='Laboratory',weight_percent=100))
            cat=query_one('SELECT category_id FROM grade_categories WHERE assignment_id=:id',{'id':aid})['category_id']
            for i,maximum in enumerate((20,50,30),1):post(w.setup,dict(action='assessment',component_name=f'Lab {i}',category_id=cat,maximum_score=maximum))
            items=gb.content(aid)[1]
            checks.append('Flexible categories and assessment maxima')
            def marks(values,action='draft'):
                return {**{f'mark__{eid}__{a["component_id"]}':v for a,v in zip(items,values)},'action':action}
            post(w.scores,marks((18,40,30)))
            assert gb.snapshot(gb.classroom(aid))['students'][0]['result']['total']==90
            checks.append('Equal percentage calculation 90%')
            assert gb.latest(aid,'RELEASE') is None
            post(w.scores,marks((18,40,30),'release'))
            assert gb.latest(aid,'RELEASE')['data']['students'][0]['result']['total']==90
            checks.append('Explicit score release creates immutable student revision')
            post(w.scores,marks((10,40,30)))
            assert gb.latest(aid,'RELEASE')['data']['students'][0]['scores'][str(items[0]['component_id'])][0]==18
            checks.append('Unreleased draft changes remain private')
            html=post(w.setup,dict(action='category_edit',category_id=cat,category_name='Laboratory',weight_percent=90))
            assert 'Draft result preview' in html
            assert query_one('SELECT weight_percent FROM grade_categories WHERE category_id=:id',{'id':cat})['weight_percent']==100
            checks.append('Category edits preview impact before saving')
            try:post(w.scores,marks((21,40,30)));raise AssertionError('Out of bounds accepted')
            except BadRequest:checks.append('Out of bounds score rejected')
            try:post(w.submit);raise AssertionError('Unconfirmed conversion accepted')
            except BadRequest:checks.append('Unconfirmed rounding blocks final submission')
            response=w.template(aid);response.direct_passthrough=False
            book=load_workbook(io.BytesIO(response.get_data()));book['Scores'].cell(2,3,19)
            stream=io.BytesIO();book.save(stream);stream.seek(0)
            revision=gb.classroom(aid)['revision']
            request.form=ImmutableMultiDict({'revision':str(revision)});request.files=ImmutableMultiDict({'workbook':FileStorage(stream,filename='scores.xlsx')})
            html=w.import_excel(aid)
            assert '1 draft changes' in html
            assert post(w.confirm_import).status_code==302
            assert gb.content(aid)[3][eid][items[0]['component_id']][0]==19
            checks.append('Excel template, preview, and atomic import')
            try:post(w.confirm_import);raise AssertionError('Import replay accepted')
            except Conflict:checks.append('Stale Excel confirmation rejected')
            response=w.template(aid);response.direct_passthrough=False
            invalid_book=load_workbook(io.BytesIO(response.get_data()));invalid_book['Scores'].cell(2,3,'=1+1')
            invalid_stream=io.BytesIO();invalid_book.save(invalid_stream);invalid_stream.seek(0)
            request.form=ImmutableMultiDict({'revision':str(gb.classroom(aid)['revision'])})
            request.files=ImmutableMultiDict({'workbook':FileStorage(invalid_stream,filename='formula.xlsx')})
            assert 'Use numeric scores' in w.import_excel(aid)
            assert gb.content(aid)[3][eid][items[0]['component_id']][0]==19
            checks.append('Formula import rejected without grade changes')
            post(w.setup,dict(action='aggregation',aggregation='POINTS',confirmed='yes'))
            post(w.scores,marks((18,40,30)))
            assert gb.snapshot(gb.classroom(aid))['students'][0]['result']['total']==88
            checks.append('Points aggregation 88%')
            identity('admin');post(w.review,dict(action='policy',rounding_rule='HALF_UP',reason='Rollback-only approved policy fixture'))
            identity('faculty');post(w.submit)
            frozen=gb.latest(aid,'SUBMISSION')
            assert frozen['data']['students'][0]['result']['equivalent']=='2.00'
            checks.append('Frozen submission uses chosen conversion')
            try:post(w.scores,marks((0,0,0)));raise AssertionError('Locked score changed')
            except Conflict:checks.append('Submitted score writes blocked')
            identity('student');request.form=ImmutableMultiDict({'code':code})
            try:w.join();raise AssertionError('Submitted roster joined')
            except Conflict:checks.append('Submitted roster joining blocked')
            identity('admin');post(w.review,dict(action='return',reason='Verify the lab record',version_id=frozen['version_id']))
            assert gb.classroom(aid)['status']=='RETURNED'
            identity('faculty');post(w.submit)
            frozen=gb.latest(aid,'SUBMISSION')
            identity('admin');post(w.review,dict(action='publish',version_id=frozen['version_id']))
            assert gb.latest(aid,'PUBLICATION')['data']['students'][0]['result']['total']==88
            checks.append('Administrator return, resubmission, publication')
            identity('student');request.method='GET';request.args=ImmutableMultiDict()
            assert '2.00' in w.subjects()
            checks.append('Student sees own approved published result')
            identity('admin');post(w.review,dict(action='correction',reason='Approved test correction'))
            identity('faculty');post(w.scores,marks((0,0,0)))
            assert gb.latest(aid,'PUBLICATION')['data']['students'][0]['result']['total']==88
            assert gb.latest(aid,'SUBMISSION')['data']['students'][0]['result']['total']==88
            checks.append('Corrections preserve prior publication and submission')
            get_connection().rollback()
            assert query_one('SELECT subject_id FROM subjects WHERE subject_code=:code',{'code':code}) is None
            assert query_one('SELECT user_id FROM users WHERE username=:code',{'code':code}) is None
            checks.append('All integration fixture records rolled back')
    output=Path('audit/rebuild');output.mkdir(exist_ok=True)
    (output/'oracle-results.json').write_text(json.dumps(checks,indent=2))
    print(json.dumps(dict(checks=len(checks),results=checks)))


if __name__=='__main__':main()
