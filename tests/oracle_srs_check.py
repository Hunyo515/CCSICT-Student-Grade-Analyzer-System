"""SRS acceptance on Oracle; all academic test writes are rolled back."""
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
from werkzeug.exceptions import BadRequest,Conflict,NotFound
from app import create_app,gradebook as gb,srs_grading as sg
from app.db import query_one,query_all,execute,execute_returning_id,get_connection
from app.routes import srs as w
from config import Config


def main():
    if '--database' not in sys.argv:raise SystemExit('Pass --database for rollback-only Oracle checks.')
    checks=[]
    with tempfile.TemporaryDirectory(dir=Path('tests').resolve()) as tmp:
        class TestConfig(Config):
            TESTING=True
            SECURITY_DB=str(Path(tmp)/'security.db')
        app=create_app(TestConfig)
        with app.test_request_context('/',method='POST'):
            teacher=query_one("SELECT teacher_id,user_id FROM teachers WHERE status='ACTIVE' FETCH FIRST 1 ROWS ONLY")
            administrator=query_one("SELECT user_id FROM users WHERE role='admin' AND status='ACTIVE' FETCH FIRST 1 ROWS ONLY")
            term=query_one('SELECT term_id FROM school_terms WHERE is_active=1')
            assert teacher and term
            code=('S'+uuid4().hex[:9]).upper()
            sid=execute_returning_id("INSERT INTO subjects(subject_code,subject_name,units,program,year_level,semester_offered) VALUES(:code,'SRS rollback subject',3,'BSDSA','1st Year','1st Semester') RETURNING subject_id INTO :out_id",{'code':code})
            aid=execute_returning_id("INSERT INTO teacher_subjects(teacher_id,subject_id,term_id,section,join_code) VALUES(:teacher,:subject,:term,'SRS-A',:code) RETURNING assignment_id INTO :out_id",{'teacher':teacher['teacher_id'],'subject':sid,'term':term['term_id'],'code':code})
            user=execute_returning_id("INSERT INTO users(username,password_hash,role,full_name,email,status) VALUES(:name,'not-a-login-hash','student','SRS Rollback Student','test@example.invalid','ACTIVE') RETURNING user_id INTO :out_id",{'name':code})
            student=execute_returning_id("INSERT INTO students(user_id,id_number,program,year_level,section,status,sex,enrollment_type) VALUES(:user_key,:idnum,'BSDSA','1st Year','SRS-A','ACTIVE','FEMALE','REGULAR') RETURNING student_id INTO :out_id",{'user_key':user,'idnum':code})
            def identity(role):
                session.clear();session.update(user_id=administrator['user_id'] if role=='admin' else teacher['user_id'] if role=='faculty' else user,role=role,teacher_id=teacher['teacher_id'],student_id=student,full_name='SRS Test')
            def post(fn,data=None):
                request.method='POST';request.args=ImmutableMultiDict();request.files=ImmutableMultiDict();request.__dict__.pop('values',None)
                request.url_rule=SimpleNamespace(endpoint='srs.'+fn.__name__)
                request.form=ImmutableMultiDict({k:str(v) for k,v in dict(revision=gb.classroom(aid)['revision'],**(data or {})).items()})
                return fn() if fn.__name__=='create_class' else fn(aid)
            execute('INSERT INTO enrollments(student_id,assignment_id) VALUES(:sid,:aid)',{'sid':student,'aid':aid})
            identity('faculty')
            post(w.setup,dict(action='split',lecture=60,laboratory=40))
            cats=gb.content(aid)[0];lecture=next(c['category_id'] for c in cats if c['category_name']=='Lecture');lab=next(c['category_id'] for c in cats if c['category_name']=='Laboratory')
            for name,weight,category,maximum in [('Quiz',50,lecture,100),('Exam',50,lecture,100),('Lab',100,lab,20)]:post(w.setup,dict(action='component',component_name=name,weight_percent=weight,category_id=category,maximum_score=maximum))
            checks.append('Lecture/Laboratory split and explicit component weights')
            assert gb.classroom(aid)['status']=='DRAFT'
            checks.append('Setup remains draft until score entry')
            components=gb.content(aid)[1];items={c['component_name']:c for c in components};eid=gb.content(aid)[2][0]['enrollment_id']
            marks={f'mark__{eid}__{items[name]["component_id"]}':score for name,score in [('Quiz',80),('Lab',18)]}
            post(w.save_scores,marks)
            record=sg.calculate(*gb.content(aid)[:2],gb.content(aid)[3][eid])
            assert record['total']==60 and record['missing']==1
            checks.append('Missing component contributes zero without creating a fake zero score')
            identity('student');request.method='GET';request.args=ImmutableMultiDict()
            assert 'SRS Rollback Student' not in w.student_grades() # no unpublished result detail
            assert not sg.load_classes(term['term_id'],published_only=True) or all(c['status']=='PUBLISHED' for c in sg.load_classes(term['term_id'],published_only=True))
            checks.append('Draft scores excluded from student results and rankings')
            identity('faculty');request.method='POST'
            csv_data=f'id_number,component_name,score\n{code},Exam,100\nUNKNOWN,Quiz,50\n{code},Quiz,999\n{code},Lab,18\n'.encode()
            request.form=ImmutableMultiDict({'revision':str(gb.classroom(aid)['revision'])});request.files=ImmutableMultiDict({'csv_file':FileStorage(io.BytesIO(csv_data),filename='scores.csv')})
            html=w.csv_upload(aid);assert 'Import 2 valid rows' in html
            post(w.csv_cancel)
            try:post(w.csv_confirm);raise AssertionError('Cancelled CSV preview accepted')
            except Conflict:checks.append('Cancelled CSV preview cannot be confirmed')
            request.form=ImmutableMultiDict({'revision':str(gb.classroom(aid)['revision'])})
            request.files=ImmutableMultiDict({'csv_file':FileStorage(io.BytesIO(csv_data),filename='scores.csv')})
            w.csv_upload(aid)
            assert post(w.csv_confirm).status_code==302
            try:post(w.csv_confirm);raise AssertionError('CSV replay accepted')
            except Conflict:checks.append('CSV preview imports valid rows, skips invalid rows, and rejects replay')
            record=sg.calculate(*gb.content(aid)[:2],gb.content(aid)[3][eid]);assert record['total']==90 and record['letter']=='Grade A'
            checks.append('Two-tier weighted total and letter grade')
            post(w.status,dict(action='publish'))
            assert gb.classroom(aid)['status']=='PUBLISHED'
            assert gb.latest(aid,'PUBLICATION')['actor_user_id']==teacher['user_id']
            assert query_one('SELECT notification_id FROM notifications WHERE user_id=:id AND link LIKE :link',{'id':user,'link':'%/app/student/grades%'})
            checks.append('Teacher directly publishes and enrolled students receive in-app notification')
            try:post(w.save_scores,marks);raise AssertionError('Published scores changed')
            except Conflict:checks.append('Published gradebook requires explicit reopen before editing')
            identity('student');request.method='GET';request.args=ImmutableMultiDict()
            html=w.student_grades();assert 'Grade 1.75' in html and '90.0' in html
            summary=sg.student_summary(dict(student_id=student,program='BSDSA',section='SRS-A'),sg.load_classes(term['term_id'],published_only=True))
            assert summary['average']==90 and summary['rank'] is not None
            checks.append('Student sees own published grade, unit-weighted average, and rank')
            identity('faculty');request.method='GET';output=w.export(aid).get_data(as_text=True)
            assert 'Weighted Total (%)' in output and 'University Grade' in output
            checks.append('CSV export includes calculated totals and letters')
            post(w.status,dict(action='reopen'));assert gb.classroom(aid)['status']=='IN_PROGRESS'
            identity('student');request.method='GET';request.args=ImmutableMultiDict()
            html=w.student_grades();assert 'No published grade yet' in html
            checks.append('Reopened draft results are hidden until teacher republication')
            assert gb.latest(aid,'PUBLICATION') is not None
            checks.append('Publication history preserved')
            identity('faculty');request.method='POST'
            post(w.setup,dict(action='split',lecture=50,laboratory=40))
            try:post(w.status,dict(action='publish'));raise AssertionError('Invalid split published')
            except BadRequest:checks.append('Invalid weighting cannot be published')
            post(w.setup,dict(action='split',lecture=60,laboratory=40))
            with patch('app.notifications.execute',side_effect=RuntimeError('Simulated notification failure')):
                post(w.status,dict(action='publish'))
            assert gb.classroom(aid)['status']=='PUBLISHED'
            checks.append('Notification failure does not block teacher publication')
            get_connection().rollback()
            assert query_one('SELECT subject_id FROM subjects WHERE subject_code=:code',{'code':code}) is None
            checks.append('All academic fixtures rolled back')
    output=Path('audit/srs-alignment');output.mkdir(exist_ok=True)
    (output/'oracle-results.json').write_text(json.dumps(checks,indent=2));print(json.dumps(dict(checks=len(checks),results=checks)))


if __name__=='__main__':main()
