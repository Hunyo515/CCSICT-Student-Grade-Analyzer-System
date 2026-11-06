import unittest
from unittest.mock import patch
from app.routes import auth
from audit_fixture import AuditFixture, USERS, one


class RegistrationLoginTests(unittest.TestCase):
    def test_student_email_id_and_case_variants_sign_in(self):
        with AuditFixture() as fixture:
            user = dict(USERS['student'], username='26-9999', email='new.student@isu.edu.ph')
            for identifier in ('26-9999', 'new.student@isu.edu.ph', 'NEW.STUDENT@ISU.EDU.PH'):
                client = fixture.app.test_client()
                client.get('/login/student')
                with client.session_transaction() as state:
                    csrf = state['csrf']
                def find(sql, params=None):
                    return user if 'FROM users' in sql else one(sql, params)
                with patch.object(auth, 'query_one', side_effect=find) as lookup:
                    response = client.post('/login/student', data=dict(username=identifier, password='AuditPassword123!', csrf_token=csrf))
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.location.endswith('/student/dashboard'))
                self.assertIn('LOWER(email)', lookup.call_args_list[0].args[0])
                with client.session_transaction() as state:
                    self.assertEqual(state['student_id'], 3)
                    self.assertEqual(state['role'], 'student')

    def test_wrong_password_and_inactive_account_are_rejected(self):
        with AuditFixture() as fixture:
            for password, status, message in [('wrong', 'ACTIVE', b'Invalid username or password'), ('AuditPassword123!', 'INACTIVE', b'This account is inactive')]:
                client = fixture.app.test_client(); client.get('/login/student')
                with client.session_transaction() as state:
                    csrf = state['csrf']
                with patch.object(auth, 'query_one', return_value=dict(USERS['student'], status=status)):
                    response = client.post('/login/student', data=dict(username='26-9999', password=password, csrf_token=csrf))
                self.assertIn(message, response.data)
                with client.session_transaction() as state:
                    self.assertNotIn('user_id', state)

    def test_duplicate_registration_email_does_not_create_account(self):
        with AuditFixture() as fixture:
            client = fixture.app.test_client(); client.get('/register')
            with client.session_transaction() as state:
                csrf = state['csrf']
            data = dict(age=19, csrf_token=csrf, first_name='New', last_name='Student', id_number='26-9999', year_level='1st Year', section='BSCS 1-1', program='BSCS', email='new.student@isu.edu.ph', contact_number='09999999999', password='NewPassword123!', confirm_password='NewPassword123!')
            with patch.object(auth, 'query_one', side_effect=[None, {'user_id':3}]), patch.object(auth, 'execute_returning_id') as write:
                response = client.post('/register', data=data)
            self.assertIn(b'An account with this email address already exists', response.data)
            write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
