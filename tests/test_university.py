import unittest,time
from unittest.mock import patch
from flask import session
from werkzeug.datastructures import MultiDict
from app import academic,university_accounts as accounts
from app.routes import university
from app.validation import password_error
from app.security import connect
from audit_fixture import AuditFixture,USERS,FIXTURE_HASH


class UniversityTests(unittest.TestCase):
    def test_issued_credentials_are_encrypted_actor_bound_expiring_and_single_use(self):
        with AuditFixture() as f,f.app.test_request_context('/'):
            session['user_id']=1
            accounts.issue(2,'faculty','GeneratedPassword1!',FIXTURE_HASH)
            token=session['issued_credential']
            with connect() as db:
                stored=db.execute('SELECT payload FROM issued_credentials').fetchone()['payload']
            self.assertNotIn('GeneratedPassword1!',stored)
            session['user_id']=3
            self.assertIsNone(accounts.reveal())
            session['user_id']=1
            self.assertEqual(accounts.reveal()['username'],'faculty')
            self.assertIsNone(accounts.reveal())
            accounts.issue(2,'faculty','GeneratedPassword1!',FIXTURE_HASH)
            with connect() as db:db.execute('UPDATE issued_credentials SET expires=?',(time.time()-1,))
            self.assertIsNone(accounts.reveal())

    def test_reset_rollback_or_changed_password_does_not_reveal_stale_credentials(self):
        with AuditFixture() as f,f.app.test_request_context('/'):
            session['user_id']=1;accounts.issue(2,'faculty','GeneratedPassword1!',FIXTURE_HASH)
            with patch.object(accounts,'query_one',return_value={**USERS['faculty'],'password_hash':'changed'}):
                self.assertIsNone(accounts.reveal())

    def test_generated_credentials_satisfy_policy_and_retry_duplicate_faculty_id(self):
        for i in range(20):self.assertIsNone(password_error(accounts.temporary_password()))
        with patch.object(accounts.secrets,'token_hex',side_effect=['12345678','abcdef12']),patch.object(accounts,'query_one',side_effect=[{'user_id':1},None,None]):
            self.assertEqual(accounts.faculty_id(),'FAC-ABCDEF12')

    def test_student_forced_password_change_cannot_be_bypassed_with_direct_url(self):
        with AuditFixture() as f:
            client=f.client('student')
            def user(sql,params=None):
                from audit_fixture import one
                row=one(sql,params)
                if row and 'from users' in sql.lower():return {**row,'must_change_password':1}
                return row
            with patch('app.db.query_one',side_effect=user):
                self.assertTrue(client.get('/app/student').location.endswith('/change-password'))
                response=client.get('/change-password')
                self.assertEqual(response.status_code,200)
                self.assertIn(b'Set your own password',response.data)

    def test_legacy_enrollment_writers_are_retired(self):
        with AuditFixture() as f:
            for role,path,data in [('student','/app/student/join',{}),('admin','/admin/students/assign',dict(assignment_id=10,mode='individual',student_id=3)),('faculty','/app/teacher/class/10/joining',{})]:
                client=f.client(role);client.get('/'+role+'/dashboard',follow_redirects=True)
                with client.session_transaction() as s:csrf=s['csrf']
                self.assertEqual(client.post(path,data=dict(data,csrf_token=csrf)).status_code,410,path)

    def test_term_filter_never_updates_academic_state(self):
        with AuditFixture() as f:
            client=f.client('admin')
            with patch('app.routes.admin.execute') as write:
                response=client.get('/app/admin?term_filter=all')
                self.assertEqual(response.status_code,200)
                self.assertIn(b'All school terms',response.data)
                self.assertNotIn(b'Set Active',response.data)
                write.assert_not_called()

if __name__=='__main__':unittest.main()
