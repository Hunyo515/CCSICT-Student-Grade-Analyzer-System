import io
import json
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch, MagicMock
from flask import session
from werkzeug.exceptions import TooManyRequests, Conflict
from audit_fixture import AuditFixture, USERS
from app.security import connect, rate_limit, validate_session, create_session
from app.routes import student,faculty


class LaunchAuditTests(unittest.TestCase):
    def setUp(self):
        self.fixture=AuditFixture().__enter__()
        self.app=self.fixture.app

    def tearDown(self):
        self.fixture.__exit__(None,None,None)

    def test_all_static_get_pages_empty_data(self):
        results=[]
        for rule in self.app.url_map.iter_rules():
            if 'GET' not in rule.methods or rule.arguments or rule.endpoint.startswith('static') or rule.endpoint=='fixture_login': continue
            role=rule.endpoint.split('.')[0]
            client=self.fixture.client(role) if role in USERS else self.app.test_client()
            response=client.get(rule.rule)
            if role in USERS and response.status_code==302 and rule.endpoint not in ('faculty.csv_preview','admin.curriculum_guide'):
                response=client.get(rule.rule,follow_redirects=True)
            expected=302 if rule.endpoint in ('faculty.csv_preview','admin.curriculum_guide') else 404 if rule.endpoint=='faculty.grade_export' else 200 if role in USERS else (200,302)
            if rule.endpoint=='student.profile_photo':expected=(200,404)
            if isinstance(expected,tuple): self.assertIn(response.status_code,expected,rule.rule)
            else: self.assertEqual(response.status_code,expected,rule.rule)
            results.append({'path':rule.rule,'status':response.status_code})
            response.close()
        Path('audit/route-results.json').write_text(json.dumps(results,indent=2))

    def test_all_protected_routes_reject_anonymous_and_wrong_role(self):
        for rule in self.app.url_map.iter_rules():
            role=rule.endpoint.split('.')[0]
            if role not in USERS: continue
            path=rule.rule
            import re
            path=re.sub(r'<int:[^>]+>','1',path)
            for caller in (None, 'student' if role!='student' else 'faculty'):
                client=self.fixture.client(caller) if caller else self.app.test_client()
                if 'GET' in rule.methods:
                    self.assertIn(client.get(path).status_code,(302,401,403,404),path)
                if 'POST' in rule.methods:
                    self.assertIn(client.post(path,data={}).status_code,(302,400,401,403),path)

    def test_revoked_disabled_changed_credentials(self):
        client=self.fixture.client('admin')
        self.assertEqual(client.get('/admin/dashboard',follow_redirects=True).status_code,200)
        user=USERS['admin']
        with patch('app.db.query_one',return_value={**user,'status':'INACTIVE'}):
            self.assertEqual(client.get('/admin/dashboard').status_code,302)
        client=self.fixture.client('admin')
        with patch('app.db.query_one',return_value={**user,'password_hash':'changed'}):
            self.assertEqual(client.get('/admin/dashboard').status_code,302)
        client=self.fixture.client('admin')
        with client.session_transaction() as s: token=s['auth_token'];csrf=s.get('csrf')
        client.get('/admin/dashboard',follow_redirects=True)
        with client.session_transaction() as s: csrf=s['csrf']
        self.assertEqual(client.post('/logout',data={'csrf_token':csrf}).status_code,302)
        with client.session_transaction() as s: s.update(user_id=1,role='admin',auth_token=token)
        self.assertEqual(client.get('/admin/dashboard').status_code,302)
        self.assertEqual(client.get('/logout').status_code,405)

    def test_concurrent_rate_limit_no_bypass(self):
        def attempt(_):
            with self.app.app_context():
                try: rate_limit('race-account',5);return 1
                except TooManyRequests:return 0
        with ThreadPoolExecutor(max_workers=12) as executor:
            self.assertEqual(sum(executor.map(attempt,range(24))),5)

    def test_unpublished_scores_not_read(self):
        with self.app.test_request_context('/student/grades'):
            session.update(user_id=3,student_id=3,role='student')
            with patch.object(student,'my_enrollments',return_value=[{'assignment_id':1,'enrollment_id':1,'status':'DRAFT'}]),patch.object(student,'scores_for_enrollment') as scores,patch.object(student,'render_template') as render:
                student.grades()
                scores.assert_not_called()
                self.assertIsNone(render.call_args.kwargs['weighted_total'])
        with self.app.test_request_context('/student/analytics'):
            session.update(user_id=3,student_id=3,role='student')
            with patch.object(student,'my_enrollments',return_value=[{'assignment_id':1,'status':'DRAFT'}]),patch.object(student,'scores_for_enrollment') as scores,patch.object(student,'render_template') as render:
                student.analytics()
                scores.assert_not_called()
                self.assertEqual(render.call_args.kwargs['published'],[])
                self.assertIsNone(render.call_args.kwargs['report']['average'])

    def test_stale_grade_form_rejected_before_writes(self):
        with self.app.test_request_context('/faculty/grade-entry/scores/save',method='POST',data={'revision':'1'}):
            from flask import request
            request.url_rule=MagicMock(endpoint='faculty.save_scores')
            session.update(user_id=2,role='faculty',teacher_id=2)
            with patch.object(faculty,'query_one',side_effect=[{'assignment_id':1},{'assignment_id':1,'teacher_id':2,'revision':2}]),patch.object(faculty,'execute') as write:
                with self.assertRaises(Conflict): faculty.get_assignment_or_404(1)
                write.assert_not_called()

    def test_csv_formula_sanitization(self):
        for value in ('=1+1','+cmd','-cmd','@SUM(A1)','  =cmd','\tcmd'):
            self.assertTrue(str(faculty.csv_safe(value)).startswith("'"))
        self.assertEqual(faculty.csv_safe(95),95)
        self.assertEqual(faculty.csv_safe('Student Name'),'Student Name')

    def test_database_outage_error_does_not_query_context_again(self):
        import oracledb
        client=self.fixture.client('admin')
        with patch('app.db.query_one',side_effect=oracledb.DatabaseError('internal details')) as q:
            response=client.get('/admin/dashboard')
        self.assertEqual(response.status_code,503)
        self.assertNotIn(b'internal details',response.data)
        self.assertEqual(q.call_count,1)

    def test_unicode_csrf_and_oversized_upload(self):
        client=self.app.test_client();client.get('/login/admin')
        self.assertEqual(client.post('/login/admin',data={'csrf_token':'\u00e9'}).status_code,400)
        self.assertEqual(client.post('/register',data={'x':'x'*(2*1024*1024)}).status_code,413)

    def test_local_assets_and_template_endpoints_exist(self):
        import re
        endpoints={r.endpoint for r in self.app.url_map.iter_rules()}
        for path in Path('app/templates').rglob('*.html'):
            source=path.read_text(encoding='utf-8')
            for endpoint in re.findall(r"url_for\(['\"]([^'\"]+)",source):
                self.assertIn(endpoint,endpoints,str(path))
            for asset in re.findall(r"filename=['\"]([^'\"]+)",source):
                self.assertTrue((Path('app/static')/asset).is_file(),asset)


    def test_admin_otp_and_direct_faculty_student_login(self):
        for role in USERS:
            with self.subTest(role=role):
                client=self.app.test_client();client.get('/login/'+role)
                with client.session_transaction() as sess:csrf=sess['csrf']
                with patch('app.email_otp.send_code'):
                    response=client.post('/login/'+role,data={'username':USERS[role]['email'] if role=='faculty' else role,'password':'AuditPassword123!','csrf_token':csrf})
                self.assertEqual(response.status_code,302)
                if role!='admin':
                    with client.session_transaction() as sess:
                        self.assertEqual(sess['role'],role)
                        self.assertNotIn('otp_token',sess)
                    continue
                self.assertTrue(response.location.endswith('/verify-email'))
                with client.session_transaction() as sess:
                    self.assertNotIn('user_id',sess)
                    self.assertIn('otp_token',sess)
                self.assertEqual(client.get('/'+role+'/dashboard').status_code,302)

    def test_registration_allows_immediate_login(self):
        client=self.app.test_client();client.get('/register')
        with client.session_transaction() as sess:csrf=sess['csrf']
        fields=dict(age=19,first_name='New',middle_name='Test',last_name='Student',id_number='26-9999',year_level='1st Year',section='BSCS 1-1',program='BSCS',email='new.t.student@isu.edu.ph',contact_number='09999999999',password='NewPassword123!',confirm_password='NewPassword123!',csrf_token=csrf)
        with patch('app.routes.auth.query_one',return_value=None),patch('app.routes.auth.execute_returning_id',return_value=99) as create,patch('app.routes.auth.execute') as insert:
            response=client.post('/register',data=fields)
        self.assertEqual(response.status_code,302)
        self.assertIn("'ACTIVE'",create.call_args.args[0])
        self.assertIn("'ACTIVE'",insert.call_args.args[0])
        self.assertNotEqual(create.call_args.args[1]['pw'],fields['password'])

    def test_grade_revision_required_and_blank_score_clears_value(self):
        with self.app.test_request_context('/faculty/grade-entry/scores/save',method='POST',data={'assignment_id':'1','revision':'0','score__1__2':''}):
            session.update(user_id=2,role='faculty',teacher_id=2)
            with patch.object(faculty,'get_assignment_or_404'),patch.object(faculty,'assignment_enrollments',return_value=[{'enrollment_id':1}]),patch.object(faculty,'assignment_components',return_value=[{'component_id':2}]),patch.object(faculty,'execute') as write:
                self.assertEqual(faculty.save_scores().status_code,302)
                self.assertTrue(any('DELETE FROM grades' in call.args[0] for call in write.call_args_list))

    def test_each_post_role_guard_precedes_route_logic(self):
        for rule in self.app.url_map.iter_rules():
            role=rule.endpoint.split('.')[0]
            if role not in USERS or 'POST' not in rule.methods:continue
            with self.app.test_request_context(rule.rule,method='POST'):
                session.update(user_id=3,role='student' if role!='student' else 'faculty')
                response=self.app.view_functions[rule.endpoint](**{key:1 for key in rule.arguments})
                self.assertEqual(response.status_code,302,rule.endpoint)


    def test_bulk_ranking_credit_weights_and_ties(self):
        rows=[]
        for sid,units,score,eid in ((1,3,80,1),(1,1,100,2),(2,3,85,3)):
            rows.append(dict(student_id=sid,full_name='Student '+str(sid),enrollment_id=eid,units=units,component_id=1,weight_percent=100,category_id=None,category_weight=None,score=score,max_score=100))
        with patch.object(student,'query_all',return_value=rows) as query:
            ranked=student.class_leaderboard('A',1)
        self.assertEqual([row['average'] for row in ranked],[85,85])
        self.assertEqual([row['rank'] for row in ranked],[1,1])
        query.assert_called_once()

    def test_simultaneous_isolated_user_sessions(self):
        def visit(index):
            role=('admin','faculty','student')[index%3]
            client=self.fixture.client(role)
            start=time.perf_counter()
            response=client.get('/'+role+'/dashboard',follow_redirects=True)
            return response.status_code, time.perf_counter()-start
        with ThreadPoolExecutor(max_workers=12) as executor:
            results=list(executor.map(visit,range(36)))
        self.assertEqual({r[0] for r in results},{200})
        values=sorted(r[1] for r in results)
        Path('audit/concurrent-users.json').write_text(json.dumps({'fixture_only':True,'requests':36,'workers':12,'errors':0,'p50_seconds':round(values[len(values)//2],4),'p95_seconds':round(values[int(len(values)*.95)],4)},indent=2))

    def test_recovery_refuses_unverified_or_nonempty_target(self):
        from scripts.backup_recovery import ensure_empty_target
        from argparse import Namespace
        args=Namespace(target='RESTORED',service='CCTDB')
        for stdout,code in (('CCT_TARGET_NOT_EMPTY_OR_MISSING',0),('',1)):
            with patch('scripts.backup_recovery.subprocess.run',return_value=MagicMock(stdout=stdout,returncode=code)):
                with self.assertRaises(SystemExit):ensure_empty_target(args)
        with patch('scripts.backup_recovery.subprocess.run',return_value=MagicMock(stdout='CCT_TARGET_EMPTY',returncode=0)):
            ensure_empty_target(args)

    def test_confirmation_attributes_do_not_interpolate_javascript(self):
        import re
        for path in Path('app/templates').rglob('*.html'):
            source=path.read_text(encoding='utf-8')
            self.assertFalse(re.search(r'onsubmit="[^"\n]*confirm[^"\n]*\{\{',source),str(path))

    def test_notification_unicode_fits_database_byte_limit(self):
        from app import notifications
        with self.app.app_context(),patch.object(notifications,'execute') as write:
            notifications.notify(1,'界'*255)
        message=write.call_args.args[1]['msg']
        self.assertLessEqual(len(message.encode('utf-8')),255)

class PopulatedPageTests(unittest.TestCase):
    def test_faculty_and_student_pages_with_realistic_rows(self):
        from audit_fixture import PopulatedAuditFixture
        with PopulatedAuditFixture() as fixture:
            for role in ('faculty','student'):
                client=fixture.client(role)
                for rule in fixture.app.url_map.iter_rules():
                    if rule.endpoint.startswith(role+'.') and 'GET' in rule.methods and not rule.arguments and rule.endpoint not in ('faculty.csv_preview',):
                        path=rule.rule+('?assignment_id=10' if rule.endpoint=='faculty.grade_export' else '')
                        response=client.get(path)
                        self.assertIn(response.status_code,(200,404) if rule.endpoint=='student.profile_photo' else (200,302),path)
                        if rule.endpoint=='faculty.grade_export' and response.status_code==200:
                            self.assertIn(b'80',response.data)

if __name__=='__main__': unittest.main()
