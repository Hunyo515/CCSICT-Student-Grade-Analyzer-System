import unittest
from unittest.mock import patch
from app.routes import admin
from audit_fixture import AuditFixture,TERM

TEACHER=dict(teacher_id=2,faculty_code='FAC-1234ABCD',full_name='Test Faculty',status='ACTIVE')
CLASS=dict(assignment_id=10,term_id=1,subject_code='CS401',subject_name='Advanced Computing',program='BSCS',year_level='4th Year',units=3,section='BSCS 4-1',status='DRAFT',school_year='2026-2027',semester='1st Semester',student_count=5)


class FacultyClassesTests(unittest.TestCase):
    def test_selected_term_panel_has_details_and_is_scoped_to_faculty(self):
        with AuditFixture() as fixture:
            client=fixture.client('admin')
            with patch.object(admin,'query_one',return_value=TEACHER),patch.object(admin,'query_all',return_value=[CLASS]) as rows:
                response=client.get('/admin/teachers/2/classes?panel=1&term_filter=1')
            self.assertEqual(response.status_code,200)
            self.assertIn(b'Advanced Computing',response.data)
            self.assertIn(b'4th Year',response.data)
            self.assertIn(b'Enrolled students',response.data)
            self.assertIn(b'View Class',response.data)
            self.assertNotIn(b'<!DOCTYPE',response.data)
            self.assertEqual(rows.call_args.args[1],{'teacher':2,'term_id':1})

    def test_all_terms_panel_and_full_page_fallback(self):
        with AuditFixture() as fixture:
            client=fixture.client('admin')
            with patch.object(admin,'query_one',return_value=TEACHER),patch.object(admin,'query_all',return_value=[CLASS]) as rows:
                response=client.get('/admin/teachers/2/classes?term_filter=all')
            self.assertEqual(response.status_code,200)
            self.assertIn(b'Back to Faculty',response.data)
            self.assertIn(b'All school terms',response.data)
            self.assertIsNone(rows.call_args.args[1]['term_id'])

    def test_empty_load_offers_assignment_for_this_faculty(self):
        with AuditFixture() as fixture:
            with patch.object(admin,'query_one',return_value=TEACHER),patch.object(admin,'query_all',return_value=[]):
                response=fixture.client('admin').get('/admin/teachers/2/classes?panel=1')
            self.assertIn(b'No assigned classes in this term.',response.data)
            self.assertIn(b'teacher_id=2',response.data)

    def test_missing_faculty_and_class_return_404(self):
        with AuditFixture() as fixture:
            client=fixture.client('admin')
            with patch.object(admin,'query_one',return_value=None):
                self.assertEqual(client.get('/admin/teachers/999/classes?panel=1').status_code,404)
                self.assertEqual(client.get('/admin/classes/999').status_code,404)

    def test_faculty_and_students_cannot_access_admin_load_or_roster(self):
        with AuditFixture() as fixture:
            for role in ('faculty','student'):
                client=fixture.client(role)
                with patch.object(admin,'query_one') as lookup:
                    for path in ('/admin/teachers/2/classes?panel=1','/admin/classes/10'):
                        self.assertEqual(client.get(path).status_code,302)
                    lookup.assert_not_called()

    def test_class_details_show_read_only_roster(self):
        with AuditFixture() as fixture:
            with patch.object(admin,'query_one',return_value=dict(CLASS,teacher_id=2,teacher_name='Test Faculty')),patch.object(admin,'query_all',return_value=[dict(id_number='26-0001',full_name='Test Student',program='BSCS',year_level='4th Year')]):
                response=fixture.client('admin').get('/admin/classes/10')
            self.assertEqual(response.status_code,200)
            self.assertIn(b'Test Student',response.data)
            self.assertIn(b'Advanced Computing',response.data)
            self.assertIn(b'Enrolled students',response.data)


if __name__=='__main__':unittest.main()
