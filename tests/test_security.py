import argparse
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from flask import Flask, session
from werkzeug.exceptions import TooManyRequests, BadRequest
from app import create_app
from app.auth import hash_password, verify_password
from app.security import init_security, connect, rate_limit, store_preview, load_preview
from app.validation import field_error, password_error, LIMITS, CHOICES, REQUIRED, validate_request
from scripts.backup_recovery import build_command, dump_name, identifier


class ValidationTests(unittest.TestCase):
    def test_every_text_limit(self):
        for field, limit in LIMITS.items():
            with self.subTest(field=field):
                self.assertIsNotNone(field_error(field, 'x'*(limit+1)))
                self.assertIsNotNone(field_error(field, 'x\n'))

    def test_choices(self):
        for key, choices in CHOICES.items():
            for value in choices:
                self.assertIsNone(field_error(key, value), (key, value))
            self.assertIsNotNone(field_error(key, 'INVALID'))

    def test_valid_and_invalid_fields(self):
        cases = {
            'username': ('j.dela-cruz', 'has space'), 'email': ('test@example.com', 'bad@'),
            'first_name': ('José', '\n'), 'last_name': ("Dela Cruz", '\n'), 'full_name': ('Ana Cruz', '\n'),
            'subject_code': ('DSA 111', '<script>'), 'subject_name': ('Computer Science', '\n'),
            'faculty_code': ('FAC-1', 'bad!'), 'id_number': ('23-2762', 'bad!'),
            'section': ('BSCS 1-1', '\n'), 'program': ('BS Computer Science', '\n'),
            'contact_number': ('09999999999', 'abcdefg'),
            'component_name': ('Quiz 1', '\n'), 'category_name': ('Lecture', '\n'),
            'q': ('Dela Cruz', '\n'), 'code': ('AB1234', 'bad!'),
            'school_year': ('2026-2027', '2026-2029'), 'link': ('/student/grades', '\n'),
            'units': ('3', '2.5'), 'weight_percent': ('25.5', 'NaN'),
            'score__1__2': ('90', '101'),
            'status': ('ACTIVE', 'UNKNOWN'), 'page': ('1', '0'),
            'password': ('StrongPassword1!', 'weak'), 'new_password': ('StrongPassword1!', 'weak'),
            'confirm_password': ('StrongPassword1!', 'x'*73),
        }
        for field in ('assignment_id','teacher_id','student_id','subject_id','category_id','prerequisite_subject_id'):
            cases[field] = ('1', '-1')
        for key, (valid, invalid) in cases.items():
            with self.subTest(key=key):
                self.assertIsNone(field_error(key, valid))
                self.assertIsNotNone(field_error(key, invalid))
        for value in ('nan','inf','-1','101','abc'):
            self.assertIsNotNone(field_error('score__1__2', value))
        for value in ('0','100','99.5'):
            self.assertIsNone(field_error('score__1__2', value))

    def test_required_field_contracts(self):
        app = Flask(__name__)
        for endpoint in REQUIRED:
            with app.test_request_context('/', method='POST'):
                from flask import request
                request.url_rule = MagicMock(endpoint=endpoint)
                with self.assertRaises(BadRequest):
                    validate_request()

    def test_password_hash_policy(self):
        value = 'StrongPassword1!'
        hashed = hash_password(value)
        self.assertTrue(verify_password(value, hashed))
        min_length_password = 'Aa1!bcde'
        self.assertIsNone(password_error(min_length_password))
        self.assertTrue(verify_password(min_length_password, hash_password(min_length_password)))
        self.assertFalse(verify_password('wrong', hashed))
        self.assertFalse(verify_password('x'*73, hashed))
        for weak in ('Aa1!bcd', 'password123', 'é'*40+'Aa1!'):
            self.assertIsNotNone(password_error(weak))
        self.assertIsNotNone(password_error('a long memorable phrase'))


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path("tests").resolve())
        self.app = Flask(__name__)
        self.app.config.update(SECRET_KEY='s'*48, SECURITY_DB=str(Path(self.tmp.name)/'security.db'))
        init_security(self.app)
        self.ctx = self.app.test_request_context('/')
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()
        self.tmp.cleanup()

    def test_rate_limit_persists_and_expires(self):
        for _ in range(5):
            rate_limit('account')
        with self.assertRaises(TooManyRequests):
            rate_limit('account')
        with connect() as db:
            db.execute('UPDATE attempts SET expires=0')
        rate_limit('account')

    def test_preview_owner_and_consumption(self):
        session['user_id']=1
        store_preview({'rows':[1,2]})
        session['user_id']=2
        self.assertIsNone(load_preview())
        session['user_id']=1
        self.assertEqual(load_preview(consume=True), {'rows':[1,2]})
        self.assertIsNone(load_preview())


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path("tests").resolve())
        class TestConfig:
            TESTING=True
            SECRET_KEY='k'*48
            SECURITY_DB=str(Path(self.tmp.name)/'security.db')
            SESSION_COOKIE_SECURE=False
        with patch('app.init_pool'):
            self.app=create_app(TestConfig)
        self.client=self.app.test_client()
        self.user=dict(user_id=1,username='admin',role='admin',full_name='Admin',status='ACTIVE',password_hash='hash',email='a@example.com')

    def tearDown(self):
        self.tmp.cleanup()

    def token(self):
        self.client.get('/login/admin')
        with self.client.session_transaction() as s:
            return s['csrf']

    def test_password_login_requires_email_verification_before_session(self):
        csrf=self.token()
        with patch('app.routes.auth.query_one', return_value=self.user), patch('app.routes.auth.verify_password',return_value=True),patch('app.email_otp.send_code'):
            result=self.client.post('/login/admin',data=dict(csrf_token=csrf,username='admin',password='pass'))
        self.assertEqual(result.status_code,302)
        self.assertTrue(result.location.endswith('/verify-email'))
        with self.client.session_transaction() as s:
            self.assertNotIn('user_id',s)
            self.assertNotIn('auth_token',s)
            self.assertTrue(s['otp_token'])
        self.assertIn('auth.otp', self.app.view_functions)

    def test_csrf_and_invalid_input(self):
        self.assertEqual(self.client.post('/login/admin',data={'username':'admin','password':'x'}).status_code,400)
        csrf=self.token()
        with patch('app.routes.auth.query_one') as query:
            response=self.client.post('/register',data=dict(csrf_token=csrf,email='not-email',password='weak'))
            self.assertEqual(response.status_code,400)
            query.assert_not_called()
        self.assertEqual(self.client.get('/admin/students?page=NaN').status_code,400)

    def test_invalid_credentials_do_not_create_a_session(self):
        csrf=self.token()
        with patch('app.routes.auth.query_one',return_value=self.user),patch('app.routes.auth.verify_password',return_value=False):
            result=self.client.post('/login/admin',data=dict(csrf_token=csrf,username='admin',password='pass'))
        self.assertEqual(result.status_code,200)
        with self.client.session_transaction() as s:
            self.assertNotIn('user_id',s)

    def test_foreign_class_score_denied(self):
        csrf=self.token()
        with self.client.session_transaction() as s:
            s.update(user_id=1,role='faculty',teacher_id=1)
            with self.app.test_request_context('/'):
                from app.security import create_session
                create_session(self.user)
                s['auth_token']=session['auth_token']
        with patch('app.db.query_one',side_effect=[{**self.user,'role':'faculty'},{'teacher_id':1,'status':'ACTIVE'}]), patch('app.routes.faculty.get_assignment_or_404'),patch('app.routes.faculty.assignment_enrollments',return_value=[{'enrollment_id':1}]),patch('app.routes.faculty.assignment_components',return_value=[{'component_id':2}]),patch('app.routes.faculty.execute') as execute,patch('app.notifications.recent',return_value=[]),patch('app.notifications.unread_count',return_value=0),patch('app.db.query_all',return_value=[]):
            result=self.client.post('/faculty/grade-entry/scores/save',data={'csrf_token':csrf,'assignment_id':'1','revision':'0','score__99__2':'90'})
        self.assertEqual(result.status_code,409)
        execute.assert_not_called()

    def test_templates_compile_and_forms_have_csrf(self):
        for name in self.app.jinja_env.list_templates():
            self.app.jinja_env.get_template(name)
        for path in Path('app/templates').rglob('*.html'):
            source=path.read_text(encoding='utf-8')
            for match in re.finditer(r'<form\b[^>]*method=["\']post["\'][^>]*>(.*?)</form>',source,re.I|re.S):
                self.assertTrue('csrf_token' in match[1] or ('hidden()' in match[1] and 'csrf_token' in source),str(path))


    def test_dashboard_chart_rendering(self):
        from app.routes import admin, faculty, student
        from insight_fixture import sample_sections
        with self.app.test_request_context('/'):
            session.update(user_id=1, role='admin')
            with patch('app.insights.load_sections',side_effect=sample_sections) as load, patch.object(admin, 'active_term',return_value={'term_id':1}), patch.object(admin,'query_all',return_value=[]), patch.object(admin,'render_template') as render:
                admin.dashboard()
                self.assertEqual(render.call_args.kwargs['report']['sections'],4)
                load.assert_called_once_with(1)
            session['role']='faculty'
            with patch('app.insights.load_sections',side_effect=sample_sections) as load, patch.object(faculty,'active_term',return_value={'term_id':1}), patch.object(faculty,'current_teacher_id',return_value=2), patch.object(faculty,'render_template') as render:
                faculty.dashboard()
                self.assertEqual(render.call_args.kwargs['report']['students'],12)
                load.assert_called_once_with(1,teacher_id=2)
            session['role']='student'
            with patch('app.insights.load_sections',side_effect=sample_sections) as load, patch.object(student,'active_term',return_value={'term_id':1}), patch.object(student,'get_student',return_value={'student_id':3}), patch.object(student,'my_enrollments',return_value=[]), patch.object(student,'render_template') as render:
                student.dashboard()
                self.assertEqual(render.call_args.kwargs['report']['complete'],2)
                load.assert_called_once_with(student_id=3)
            self.app.template_context_processors[None] = []
            from flask import render_template_string
            html=render_template_string("{% from '_insight_ui.html' import bar %}{{ bar('Assessment', 80, target=true) }}")
            self.assertIn('80%',html)
            self.assertIn('width:80.0%',html)
            self.assertIn('insight-target',html)

    def test_request_transaction_commit_and_rollback(self):
        from flask import g
        conn=MagicMock()
        @self.app.route('/test-transaction/<int:code>')
        def transaction(code):
            g.db_conn=conn
            return 'result',code
        with patch('app.db._pool'):
            self.client.get('/test-transaction/200')
            conn.commit.assert_called_once()
            conn.reset_mock()
            self.client.get('/test-transaction/400')
            conn.commit.assert_not_called()
            self.assertTrue(conn.rollback.called)


class RecoveryTests(unittest.TestCase):
    def args(self, **kwargs):
        values=dict(action='recover',service='CCTDB',directory='CCT_BACKUP_DIR',schema='STUDENT',dump='backup.dmp',target='RESTORED')
        values.update(kwargs)
        return argparse.Namespace(**values)

    def test_backup_and_isolated_recovery(self):
        self.assertIn('flashback_time=systimestamp',build_command(self.args(action='backup')))
        self.assertIn('remap_schema=STUDENT:RESTORED',build_command(self.args()))
        self.assertIn('table_exists_action=SKIP',build_command(self.args()))
        for target in ('STUDENT',None):
            with self.assertRaises(ValueError):
                build_command(self.args(target=target))
        for value in ('../backup.dmp','a.dmp;drop','bad name.dmp'):
            with self.assertRaises(argparse.ArgumentTypeError):
                dump_name(value)
        with self.assertRaises(argparse.ArgumentTypeError):
            identifier('bad;drop')


if __name__=='__main__':
    unittest.main()
