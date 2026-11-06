import unittest
from unittest.mock import patch
from app.auth import verify_password
from app.routes import admin
from audit_fixture import AuditFixture


class TeacherRegistrationTests(unittest.TestCase):
    def test_teacher_uses_separate_names_and_selected_password(self):
        with AuditFixture() as fixture:
            for middle in ('', 'Santos'):
                client = fixture.client('admin')
                client.get('/admin/teachers')
                with client.session_transaction() as state:
                    csrf = state['csrf']
                fields = dict(program='BSDSA', first_name='Juan', middle_name=middle, last_name='Cruz', email='juan.cruz@isu.edu.ph', password='ChosenPassword123!', confirm_password='ChosenPassword123!', csrf_token=csrf)
                with patch.object(admin, 'query_one',return_value=None), patch.object(admin, 'execute_returning_id', return_value=99) as create, patch.object(admin, 'execute'), patch.object(admin, 'log_activity'), patch('app.university_accounts.faculty_id', return_value='FAC-1234ABCD'), patch('app.university_accounts.issue') as issue:
                    response = client.post('/admin/teachers/add', data=fields)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.location.endswith('/admin/teachers'))
                saved = create.call_args.args[1]
                self.assertEqual(saved['name'], 'Juan Santos Cruz' if middle else 'Juan Cruz')
                self.assertTrue(verify_password(fields['password'], saved['pw']))
                issue.assert_not_called()
                page = client.get(response.location)
                self.assertIn(b'Faculty registered successfully.', page.data)
                self.assertNotIn(b'Account ready', page.data)
                self.assertNotIn(fields['password'].encode(), page.data)

    def test_invalid_teacher_credentials_are_rejected_before_writes(self):
        with AuditFixture() as fixture:
            fields = dict(program='BSDSA', first_name='Juan', last_name='Cruz', email='juan.cruz@isu.edu.ph', password='ChosenPassword123!', confirm_password='ChosenPassword123!')
            for invalid in ({'first_name':''}, {'last_name':''}, {'password':'weak'}, {'confirm_password':'OtherPassword123!'}, {'email':'juan@gmail.com'}):
                client = fixture.client('admin')
                client.get('/admin/teachers')
                with client.session_transaction() as state:
                    csrf = state['csrf']
                with patch.object(admin, 'execute_returning_id') as create:
                    response = client.post('/admin/teachers/add', data={**fields, **invalid, 'csrf_token':csrf})
                self.assertEqual(response.status_code, 400)
                create.assert_not_called()


if __name__ == '__main__':
    unittest.main()
