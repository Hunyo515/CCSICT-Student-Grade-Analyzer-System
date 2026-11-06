import unittest
from unittest.mock import patch
from audit_fixture import AuditFixture,USERS
from app.routes import auth,admin


class FacultyEmailLoginTests(unittest.TestCase):
    def test_existing_faculty_can_log_in_with_email_and_case_variants(self):
        with AuditFixture() as fixture:
            for email in ('faculty@example.invalid','FACULTY@EXAMPLE.INVALID','  faculty@example.invalid  '):
                client=fixture.app.test_client();client.get('/login/faculty')
                with client.session_transaction() as state:csrf=state['csrf']
                response=client.post('/login/faculty',data=dict(username=email,password='AuditPassword123!',csrf_token=csrf))
                self.assertEqual(response.status_code,302)
                with client.session_transaction() as state:
                    self.assertEqual(state['role'],'faculty');self.assertEqual(state['teacher_id'],2)

    def test_existing_faculty_with_legacy_password_flag_goes_directly_to_dashboard(self):
        with AuditFixture() as fixture:
            from audit_fixture import one
            client=fixture.app.test_client();client.get('/login/faculty')
            with client.session_transaction() as state:csrf=state['csrf']
            def user(sql,params=None):
                row=one(sql,params)
                return dict(row,must_change_password=1) if row and 'from users' in sql.lower() else row
            with patch.object(auth,'query_one',side_effect=user),patch('app.db.query_one',side_effect=user):
                response=client.post('/login/faculty',data=dict(username='faculty@example.invalid',password='AuditPassword123!',csrf_token=csrf))
                self.assertTrue(response.location.endswith('/faculty/dashboard'))
                page=client.get('/app/teacher')
                self.assertEqual(page.status_code,200)
                self.assertNotIn(b'Set your own password',page.data)
                self.assertTrue(client.get('/change-password').location.endswith('/faculty/dashboard'))

    def test_faculty_id_other_role_email_and_wrong_password_are_rejected(self):
        with AuditFixture() as fixture:
            for identifier,password in [('faculty','AuditPassword123!'),('FAC-1234ABCD','AuditPassword123!'),('student@example.invalid','AuditPassword123!'),('faculty@example.invalid','wrong')]:
                client=fixture.app.test_client();client.get('/login/faculty')
                with client.session_transaction() as state:csrf=state['csrf']
                response=client.post('/login/faculty',data=dict(username=identifier,password=password,csrf_token=csrf))
                self.assertIn(b'Invalid email address or password.',response.data)
                with client.session_transaction() as state:self.assertNotIn('user_id',state)

    def test_forgot_password_looks_up_faculty_email(self):
        with AuditFixture() as fixture:
            client=fixture.app.test_client();client.get('/forgot-password/faculty')
            with client.session_transaction() as state:csrf=state['csrf']
            with patch.object(auth,'query_one',return_value=USERS['faculty']) as lookup:
                response=client.post('/forgot-password/faculty',data=dict(username='faculty@example.invalid',csrf_token=csrf))
            self.assertEqual(response.status_code,302)
            self.assertIn('LOWER(email) = LOWER(:u)',lookup.call_args.args[0])
            self.assertEqual(lookup.call_args.args[1]['r'],'faculty')

    def test_duplicate_faculty_email_is_rejected_before_account_creation(self):
        with AuditFixture() as fixture:
            client=fixture.client('admin');client.get('/admin/teachers')
            with client.session_transaction() as state:csrf=state['csrf']
            with patch.object(admin,'query_one',return_value={'user_id':2}),patch.object(admin,'execute_returning_id') as create:
                response=client.post('/admin/teachers/add',data=dict(csrf_token=csrf,program='BSCS',first_name='Test',last_name='Faculty',email='test.faculty@isu.edu.ph',password='AuditPassword123!',confirm_password='AuditPassword123!'))
            self.assertEqual(response.status_code,409)
            self.assertIn(b'email address already exists',response.data)
            create.assert_not_called()


if __name__=='__main__':unittest.main()
