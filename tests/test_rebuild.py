import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from flask import Flask,session
from werkzeug.exceptions import Conflict,NotFound
from app.gradebook import calculate,decimal,equivalent,analysis
from app.security import init_security,connect
from app.email_otp import init_otp,begin,consume,pending
from audit_fixture import AuditFixture,USERS


class CalculationTests(unittest.TestCase):
    def setUp(self):
        self.cats=[dict(category_id=1,category_name='Laboratory',weight_percent=100)]
        self.items=[dict(component_id=i,category_id=1) for i in (1,2,3)]
        self.scores={1:(18,20),2:(40,50),3:(30,30)}

    def test_equal_and_points_have_different_correct_results(self):
        self.assertEqual(calculate(self.cats,self.items,self.scores,'EQUAL')['total'],90)
        self.assertEqual(calculate(self.cats,self.items,self.scores,'POINTS')['total'],88)

    def test_weighted_categories_match_professor_example(self):
        cats=[dict(category_id=i,category_name=str(i),weight_percent=w) for i,w in enumerate((30,30,20,10,10),1)]
        items=[dict(component_id=i,category_id=i) for i in range(1,6)]
        scores={i:(s,100) for i,s in enumerate((90,80,85,95,100),1)}
        result=calculate(cats,items,scores,'EQUAL','HALF_UP')
        self.assertEqual(result['total'],87.5);self.assertEqual(result['parts'][0]['contribution'],27)

    def test_missing_is_not_zero_or_renormalized(self):
        result=calculate(self.cats,self.items,{1:(0,20),2:(40,50)},'EQUAL')
        self.assertIsNone(result['total']);self.assertEqual(result['recorded'],2)
        result=calculate(self.cats,self.items,{1:(0,20),2:(0,50),3:(0,30)},'EQUAL')
        self.assertEqual(result['total'],0);self.assertTrue(result['complete'])

    def test_invalid_configuration_is_explicit(self):
        for cats,mode in (([{**self.cats[0],'weight_percent':99}],'EQUAL'),(self.cats,'LEGACY'),([], 'EQUAL')):
            result=calculate(cats,self.items,self.scores,mode)
            self.assertFalse(result['complete']);self.assertTrue(result['problems']);self.assertIsNone(result['total'])

    def test_grade_conversion_boundaries_and_no_hidden_rounding(self):
        self.assertIsNone(equivalent(94.5,'UNSET'))
        self.assertEqual(equivalent(94.5,'HALF_UP'),'1.25')
        self.assertEqual(equivalent(94.5,'FLOOR'),'1.50')
        for score,grade in [(100,'1.00'),(98,'1.00'),(95,'1.25'),(92,'1.50'),(89,'1.75'),(86,'2.00'),(83,'2.25'),(80,'2.50'),(77,'2.75'),(75,'3.00'),(74,'5.00'),(0,'5.00')]:
            self.assertEqual(equivalent(score,'HALF_UP'),grade)

    def test_finite_precision_and_bounds(self):
        for value in ('NaN','Infinity','-1','100.001','101'):
            with self.assertRaises(ValueError):decimal(value,0,100)

    def test_analytics_zero_and_missing_denominators(self):
        items=[dict(component_id=1,component_name='Lab')]
        roster=[dict(enrollment_id=1),dict(enrollment_id=2),dict(enrollment_id=3)]
        result=analysis(items,roster,{1:{1:(0,20)},2:{1:(10,20)}})[0]
        self.assertEqual((result['recorded'],result['missing'],result['mean'],result['median']),(2,1,25,25))
        self.assertEqual(sum(result['bins']),2)


class OtpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path('tests').resolve())
        self.app=Flask(__name__);self.app.config.update(SECRET_KEY='s'*48,SECURITY_DB=str(Path(self.tmp.name)/'auth.db'))
        init_security(self.app);self.ctx=self.app.test_request_context('/');self.ctx.push();init_otp()
        self.user=dict(user_id=1,role='faculty',email='teacher@example.invalid',status='ACTIVE',password_hash='hash')
        self.mail=patch('app.email_otp.send_code');self.send=self.mail.start()
    def tearDown(self):
        self.mail.stop();self.ctx.pop();self.tmp.cleanup()
    def start(self):
        begin(self.user);return self.send.call_args.args[1]
    def test_no_session_before_otp_and_single_use(self):
        code=self.start();self.assertNotIn('user_id',session)
        self.assertTrue(consume(code,self.user));self.assertFalse(consume(code,self.user))
    def test_wrong_expired_and_changed_credentials_fail(self):
        code=self.start();self.assertFalse(consume('incorrect',self.user))
        self.assertFalse(consume(code,{**self.user,'password_hash':'changed'}))
        self.assertFalse(consume(code,{**self.user,'email':'changed@example.invalid'}))
        with connect() as db:db.execute('UPDATE email_challenges SET expires=0')
        self.assertFalse(consume(code,self.user))
    def test_attempt_limit_and_no_plaintext_codes(self):
        code=self.start()
        self.assertNotEqual(pending()['digest'],code)
        for i in range(5):self.assertFalse(consume('xxxxxx',self.user))
        self.assertFalse(consume(code,self.user))
    def test_resend_cooldown_and_replacement(self):
        code=self.start()
        with self.assertRaises(RuntimeError):begin(self.user)
        with connect() as db:db.execute('UPDATE email_challenges SET created=0')
        new=self.start();self.assertFalse(consume(code,self.user));self.assertTrue(consume(new,self.user))
    def test_delivery_failure_does_not_create_pending_login(self):
        self.send.side_effect=OSError('offline')
        with self.assertRaises(OSError):begin(self.user)
        self.assertIsNone(pending());self.assertNotIn('user_id',session)


class RebuildAccessTests(unittest.TestCase):
    def test_admin_otp_and_direct_faculty_student_login(self):
        with AuditFixture() as fixture:
            for role in ('admin','faculty','student'):
                client=fixture.app.test_client();client.get('/login/'+role)
                with client.session_transaction() as s:csrf=s['csrf']
                with patch('app.email_otp.send_code') as mail:
                    response=client.post('/login/'+role,data=dict(username=USERS[role]['email'] if role=='faculty' else role,password='AuditPassword123!',csrf_token=csrf))
                self.assertEqual(response.status_code,302)
                if role!='admin':
                    mail.assert_not_called()
                    with client.session_transaction() as s:self.assertEqual(s['role'],role)
                    self.assertEqual(client.get('/'+role+'/dashboard',follow_redirects=True).status_code,200)
                    continue
                with client.session_transaction() as s:self.assertNotIn('user_id',s)
                code=mail.call_args.args[1];client.get('/verify-email')
                with client.session_transaction() as s:csrf=s['csrf']
                response=client.post('/verify-email',data=dict(otp=code,csrf_token=csrf))
                self.assertEqual(response.status_code,302)
                with client.session_transaction() as s:self.assertEqual(s['role'],role);self.assertTrue(s['auth_token'])
                self.assertEqual(client.get('/'+role+'/dashboard',follow_redirects=True).status_code,200)

    def test_workspace_role_boundaries(self):
        with AuditFixture() as fixture:
            for role,path in [('student','/workspace/review'),('faculty','/workspace/reports'),('admin','/workspace/classes'),('student','/workspace/class/10')]:
                client=fixture.client(role)
                self.assertEqual(client.get(path).status_code,302)
            client=fixture.app.test_client()
            for path in ('/workspace/review','/workspace/classes','/workspace/subjects'):
                self.assertEqual(client.get(path).status_code,302)


if __name__=='__main__':unittest.main()
