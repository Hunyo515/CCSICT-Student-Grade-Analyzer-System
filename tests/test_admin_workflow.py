import unittest
from unittest.mock import patch
from flask import abort, session
from werkzeug.exceptions import BadRequest, Conflict
from app.curriculum import canonical_program, cohort_matches
from app.routes import admin
from app.validation import field_error
from audit_fixture import AuditFixture


CLASS=dict(assignment_id=10,subject_id=20,term_id=1,program='BSDSA',year_level='1st Year',section='1A',status='DRAFT')
STUDENT=dict(student_id=3,program='BS Data Science',year_level='1st Year',section='1A',status='ACTIVE')


class WorkflowTests(unittest.TestCase):
    def test_error_page_returns_only_to_same_origin_referrer(self):
        with AuditFixture() as f:
            f.app.add_url_rule(
                "/__audit/conflict",
                view_func=lambda: abort(409, description="Academic history must be preserved."),
            )
            client = f.client("admin")
            response = client.get(
                "/__audit/conflict",
                headers={"Referer": "http://localhost/admin/students"},
            )
            self.assertIn(b'href="http://localhost/admin/students"', response.data)
            self.assertIn(b"Return to previous page", response.data)

            response = client.get(
                "/__audit/conflict",
                headers={"Referer": "https://example.com/"},
            )
            self.assertNotIn(b"href=\"https://example.com/\"", response.data)
            self.assertNotIn(b"Return to previous page", response.data)

    def test_program_aliases_and_cohort_identity(self):
        self.assertEqual(canonical_program(' BS Data Science '),'BSDSA')
        self.assertTrue(cohort_matches(STUDENT,CLASS,'1A'))
        for field,value in [('program','BSCS'),('year_level','2nd Year'),('section','1B')]:
            self.assertFalse(cohort_matches({**STUDENT,field:value},CLASS,'1A'))
        self.assertFalse(cohort_matches(STUDENT,{**CLASS,'program':None},'1A'))

    def test_bulk_preview_excludes_duplicates_and_other_classes(self):
        people=[{**STUDENT,'student_id':sid} for sid in range(1,5)]+[{**STUDENT,'student_id':5,'program':'BSCS'}]
        cohort,eligible=admin._bulk_preview(CLASS,people,[{'student_id':1}],{2},'1A')
        self.assertEqual(len(cohort),4)
        self.assertEqual([p['student_id'] for p in eligible],[3,4])

    def test_course_codes_and_unit_validation(self):
        for code in ('DSA 111','NSTP/ROTC 1','DSA Inst 1'):
            self.assertIsNone(field_error('subject_code',code))
        for value in ('NaN','-1','1.5','10'):
            self.assertIsNotNone(field_error('lecture_units',value))
        self.assertIsNone(field_error('units','9'))
        self.assertIsNone(field_error('lecture_units','9'))
        self.assertIsNotNone(field_error('units','10'))

    def test_roster_guards_before_writes(self):
        with AuditFixture() as f:
            cases=[('individual',{},BadRequest),('bulk',{'source_section':'1A','preview_token':'stale'},Conflict)]
            for mode,extra,error in cases:
                with f.app.test_request_context('/students/assign',method='POST',data={'assignment_id':10,'mode':mode,**extra}):
                    session.update(user_id=1,role='admin')
                    with patch.object(admin,'_offered_classes',return_value=[CLASS]),patch.object(admin,'_enrollment_data',return_value=([STUDENT],[],set())),patch.object(admin,'query_one',return_value={'assignment_id':10,'status':'DRAFT','term_id':1}),patch.object(admin,'execute') as write:
                        with self.assertRaises(error):admin.assign_student_to_section()
                        write.assert_not_called()

    def test_published_roster_cannot_change(self):
        with AuditFixture() as f, f.app.test_request_context('/',method='POST',data={'assignment_id':10,'mode':'individual','student_id':3}):
            session.update(user_id=1,role='admin')
            with patch.object(admin,'_offered_classes',return_value=[CLASS]),patch.object(admin,'_enrollment_data',return_value=([STUDENT],[],set())),patch.object(admin,'query_one',return_value={'assignment_id':10,'status':'PUBLISHED','term_id':1}),patch.object(admin,'execute') as write:
                with self.assertRaises(Conflict):admin.assign_student_to_section()
                write.assert_not_called()

    def test_used_subject_cannot_change_units_or_be_deleted(self):
        subject=dict(subject_id=20,subject_code='DSA 111',program='BSDSA',units=3)
        with AuditFixture() as f, f.app.test_request_context('/',method='POST',data=dict(program='BSDSA',subject_code='DSA 111',subject_name='Programming',units='4',year_level='1st Year',semester_offered='1st Semester')):
            session.update(user_id=1,role='admin')
            with patch.object(admin,'query_one',side_effect=[subject,{'assignment_id':10}]),patch.object(admin,'execute') as write:
                with self.assertRaises(Conflict):admin._save_curriculum_subject(20)
                write.assert_not_called()
            with patch.object(admin,'query_one',side_effect=[subject,{'assignment_id':10}]),patch.object(admin,'execute') as write:
                with self.assertRaises(Conflict):admin.delete_subject(20)
                write.assert_not_called()

    def test_inactive_or_out_of_term_subject_is_rejected(self):
        with AuditFixture() as f, f.app.test_request_context('/',method='POST',data=dict(teacher_id=2,subject_id=20,section='1A')):
            session.update(user_id=1,role='admin')
            for archived,program,semester in ((1,'BSDSA','1st Semester'),(0,None,'1st Semester'),(0,'BSDSA','2nd Semester')):
                with patch.object(admin,'query_one',side_effect=[{'term_id':1,'semester':'1st Semester'},dict(is_archived=archived,program=program,semester_offered=semester)]),patch.object(admin,'execute_returning_id') as insert:
                    with self.assertRaises(Conflict):admin.assign_subject()
                    insert.assert_not_called()


if __name__=='__main__':unittest.main()
