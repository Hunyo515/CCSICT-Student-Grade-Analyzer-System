import unittest
from audit_fixture import AuditFixture
from srs_fixture import SrsFixture


class StudentGradesTests(unittest.TestCase):
    def test_unpublished_selection_is_retained_and_explained(self):
        with SrsFixture() as fixture:
            response=fixture.client('student').get('/app/student/grades?assignment_id=10')
            self.assertEqual(response.status_code,200)
            self.assertIn(b'Back to My Subjects',response.data)
            self.assertIn(b'No published grade yet',response.data)
            self.assertIn(b'Awaiting publication',response.data)
            self.assertNotIn(b'class="final-result"',response.data)
            self.assertIn(b'id="total-enrolled-units">6 units',response.data)

    def test_published_selection_displays_result_and_total_units(self):
        with SrsFixture() as fixture:
            response=fixture.client('student').get('/app/student/grades?assignment_id=20')
            self.assertEqual(response.status_code,200)
            self.assertNotIn(b'id="subject"',response.data)
            self.assertIn(b'Grade A',response.data)
            self.assertIn(b'COMPONENT BREAKDOWN',response.data)
            self.assertIn(b'id="total-enrolled-units">6 units',response.data)

    def test_all_term_filter_is_preserved_in_subject_form(self):
        with SrsFixture() as fixture:
            response=fixture.client('student').get('/app/student/grades?term_filter=all&assignment_id=10')
            self.assertIn(b'/app/student/grades?term_filter=all',response.data)
            self.assertIn(b'Back to My Subjects',response.data)

    def test_unenrolled_subject_cannot_be_viewed(self):
        with SrsFixture() as fixture:
            self.assertEqual(fixture.client('student').get('/app/student/grades?assignment_id=999').status_code,404)

    def test_no_enrollments_has_zero_total_and_clear_state(self):
        with AuditFixture() as fixture:
            response=fixture.client('student').get('/app/student/grades')
            self.assertEqual(response.status_code,200)
            self.assertIn(b'No enrolled subjects',response.data)
            self.assertIn(b'id="total-enrolled-units">0 units',response.data)


if __name__=='__main__':unittest.main()
