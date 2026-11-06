import unittest
from unittest.mock import patch
from app.routes import admin
from srs_fixture import SrsFixture


class AdminCleanupTests(unittest.TestCase):
    def test_dashboard_removes_activity_and_classes_but_keeps_metrics(self):
        with SrsFixture() as fixture:
            response=fixture.client('admin').get('/app/admin')
            self.assertEqual(response.status_code,200)
            self.assertNotIn(b'Recent activity',response.data)
            self.assertNotIn(b'Classes this term',response.data)
            self.assertIn(b'Enrollment by program',response.data)
            self.assertIn(b'Active students',response.data)
            analytics=fixture.client('admin').get('/app/admin/analytics')
            self.assertIn(b'Published class averages',analytics.data)

    def test_deleting_faculty_detaches_classes_and_preserves_academic_records(self):
        with SrsFixture() as fixture:
            client=fixture.client('admin');client.get('/admin/teachers')
            with client.session_transaction() as state:csrf=state['csrf']
            with patch.object(admin,'query_one',return_value={'user_id':2,'full_name':'Test Faculty'}), patch.object(admin,'query_all',return_value=[{'assignment_id':10}]), patch.object(admin,'execute') as write,patch.object(admin,'log_activity'):
                response=client.post('/admin/teachers/2/delete',data={'csrf_token':csrf})
            self.assertEqual(response.status_code,302)
            calls=[c.args[0] for c in write.call_args_list]
            self.assertTrue(calls[0].startswith('UPDATE grade_versions SET actor_name'))
            self.assertTrue(calls[1].startswith('UPDATE teacher_subjects SET teacher_id=NULL'))
            self.assertTrue(calls[2].startswith('DELETE FROM users'))
            self.assertFalse(any(sql.startswith('DELETE FROM '+table) for sql in calls for table in ('grades','grade_versions','enrollments','teacher_subjects')))


if __name__=='__main__':unittest.main()
