import unittest
from unittest.mock import patch
from app import student_progress as progress
from app.routes import auth,university
from audit_fixture import AuditFixture,TERM
from srs_fixture import SrsFixture

class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.student=dict(student_id=3,program='BSCS',year_level='2nd Year')
        self.catalog=[dict(subject_id=i,subject_code='CS '+str(i),year_level='1st Year',semester_offered='1st Semester',prerequisite_text='') for i in (111,112,113)]
        self.subject=dict(subject_id=211,subject_code='CS 211',prerequisite_text='CS 111, 112')
    def test_prerequisites_shorthand_passed_and_incomplete(self):
        passed={('BSCS','CS111','')}
        self.assertEqual(progress.eligibility(self.subject,self.student,self.catalog,passed),'PREREQUISITE NOT COMPLETED')
        passed.add(('BSCS','CS112',''))
        self.assertEqual(progress.eligibility(self.subject,self.student,self.catalog,passed),'')
        passed.add(('BSCS','CS211',''))
        self.assertEqual(progress.eligibility(self.subject,self.student,self.catalog,passed),'PASSED')
    def test_standing_unknown_and_corequisite(self):
        for text,expected in [('3rd year Standing','YEAR STANDING REQUIRED'),('Unknown 123','PREREQUISITE REVIEW REQUIRED')]:
            self.assertEqual(progress.eligibility(dict(self.subject,prerequisite_text=text),self.student,self.catalog,set()),expected)
        subject=dict(self.subject,prerequisite_text='Co-requisite with CS 111')
        self.assertEqual(progress.eligibility(subject,self.student,self.catalog,set()),'CO-REQUISITE REQUIRED')
        self.assertEqual(progress.eligibility(subject,self.student,self.catalog,set(),{111}),'')
    def test_only_complete_published_passes_count(self):
        def classroom(status,total,missing,student_id=3):
            return dict(status=status,program='BSCS',subject_code='CS 111',students=[dict(student_id=student_id,result=dict(total=total,missing=missing))])
        for c in [classroom('DRAFT',90,0),classroom('PUBLISHED',74,0),classroom('PUBLISHED',90,1),classroom('PUBLISHED',90,0,4)]:
            self.assertEqual(progress.passed_subjects(3,[c]),set())
        self.assertEqual(progress.passed_subjects(3,[classroom('PUBLISHED',75,0)]),{('BSCS','CS111','')})
    def test_regular_status_tracks_prior_semesters_only(self):
        student=dict(self.student,year_level='1st Year')
        self.assertEqual(progress.academic_status(student,TERM,self.catalog,set()),'REGULAR')
        term=dict(TERM,semester='2nd Semester')
        self.assertEqual(progress.academic_status(student,term,self.catalog,set()),'IRREGULAR')
        self.assertEqual(progress.academic_status(student,term,self.catalog,{('BSCS','CS'+str(i),'') for i in (111,112,113)}),'REGULAR')
    def test_progression_is_once_per_year_capped_and_never_reversed(self):
        student=dict(student_id=3,year_level='2nd Year',section='BSCS 2-1',progress_school_year=2026)
        with patch.object(progress,'query_all',return_value=[student]),patch.object(progress,'execute') as write:
            progress.advance_years(dict(TERM,semester='2nd Semester'));write.assert_not_called()
            progress.advance_years(dict(TERM,school_year='2027-2028'))
            self.assertEqual(write.call_args.args[1]['level'],'3rd Year');self.assertEqual(write.call_args.args[1]['section'],'BSCS 3-1')
            write.reset_mock();progress.advance_years(dict(TERM,school_year='2025-2026'));write.assert_not_called()
            progress.advance_years(dict(TERM,school_year='2030-2031'));self.assertEqual(write.call_args.args[1]['level'],'4th Year')
    def test_subject_list_requires_click_and_profile_has_no_enrollments(self):
        with SrsFixture() as fixture:
            client=fixture.client('student');page=client.get('/app/student/grades').data
            self.assertIn(b'Enrolled subjects',page);self.assertIn(b'assignment_id=20',page);self.assertNotIn(b'COMPONENT BREAKDOWN',page)
            self.assertIn(b'COMPONENT BREAKDOWN',client.get('/app/student/grades?assignment_id=20').data)
            self.assertNotIn(b'Enrolled subjects',client.get('/student/profile').data)
    def test_faculty_self_registration_validates_and_saves_program(self):
        with AuditFixture() as fixture:
            client=fixture.app.test_client();self.assertIn(b'/register/faculty',client.get('/login/faculty').data)
            client.get('/register/faculty')
            with client.session_transaction() as state:csrf=state['csrf']
            data=dict(csrf_token=csrf,first_name='New',last_name='Faculty',program='BSIT',email='new.faculty@isu.edu.ph',password='NewPassword123!',confirm_password='NewPassword123!')
            with patch.object(auth,'query_one',return_value=None),patch.object(auth,'execute_returning_id',return_value=123) as create,patch.object(auth,'execute') as save,patch('app.university_accounts.faculty_id',return_value='FAC-TEST1234'):
                self.assertEqual(client.post('/register/faculty',data=dict(data,program='BAD')).status_code,400);create.assert_not_called()
                self.assertEqual(client.post('/register/faculty',data=dict(data,email='not@isu.edu.ph')).status_code,400);create.assert_not_called()
                self.assertEqual(client.post('/register/faculty',data=data).status_code,302)
                self.assertEqual(save.call_args.args[1]['program'],'BSIT')
    def test_age_validation(self):
        from app.validation import field_error
        for value in ('0','121','19.5','abc'):self.assertIsNotNone(field_error('age',value))
        self.assertIsNone(field_error('age','19'))

if __name__=='__main__':unittest.main()
