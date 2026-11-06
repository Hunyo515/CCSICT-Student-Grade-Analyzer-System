import unittest
from unittest.mock import patch
from decimal import Decimal
from flask import session
from werkzeug.exceptions import BadRequest
from app import student_progress as progress,academic
from app.routes import srs,auth,admin
from audit_fixture import AuditFixture,PROFILE,TERM
import test_current_enlistment as enlist_tests

class ResidencyWorkflowTests(unittest.TestCase):
    def test_residency_uses_id_and_shows_years_after_four(self):
        for identifier,number,label in [('26-1105',1,'1st Year'),('25-1105',2,'2nd Year'),('23-1105',4,'4th Year'),('22-1105',5,'5th Year'),('16-1105',11,'11th Year')]:
            result=progress.residency(dict(id_number=identifier,year_level='1st Year'),TERM)
            self.assertEqual(result['residency_year'],number);self.assertEqual(result['standing_year'],label)
            self.assertEqual(result['curriculum_year'],progress.YEARS[min(number,4)-1])
    def test_enlistment_denies_higher_year_even_with_forged_request(self):
        runner=enlist_tests.CurrentEnlistmentTests()
        with patch.dict(enlist_tests.PERSON,id_number='25-1105'):
            response,write,_=runner.run_enlistment(posted={'subject_ids':['110'],'year_level':'3rd Year'})
            self.assertEqual(response.status_code,403);write.assert_not_called()
            response,write,_=runner.run_enlistment(posted={'subject_ids':['110'],'year_level':'1st Year'})
            self.assertEqual(response.status_code,302)
    def test_new_student_registers_without_year_or_section(self):
        with AuditFixture() as f:
            client=f.app.test_client();page=client.get('/register')
            self.assertNotIn(b'name="year_level"',page.data);self.assertNotIn(b'name="section"',page.data)
            with client.session_transaction() as state:token=state['csrf']
            fields=dict(csrf_token=token,age=18,first_name='New',last_name='Student',id_number='26-1105',program='BSCS',email='new.student@isu.edu.ph',contact_number='09999999999',password='Password123!',confirm_password='Password123!')
            with patch.object(auth,'query_one',return_value=None),patch.object(auth,'execute_returning_id',return_value=900),patch.object(auth,'execute') as write:
                response=client.post('/register',data=fields)
                self.assertEqual(response.status_code,302)
                self.assertEqual(write.call_args.args[1]['section'],'UNASSIGNED')
    def test_unassigned_student_chooses_section_before_subjects(self):
        with AuditFixture() as f:
            client=f.client('student')
            with patch('app.routes.student.get_student',return_value=dict(PROFILE,id_number='26-1105',program='BSCS',section='UNASSIGNED')):
                page=client.get('/university/enlistme')
                self.assertIn(b'Choose your section above',page.data)
                self.assertNotIn(b'id="enlist-subjects"',page.data)
                self.assertNotIn(b'<option >2nd Year',page.data)
    def test_section_selected_in_enlistment_is_saved_on_first_enrollment(self):
        runner=enlist_tests.CurrentEnlistmentTests()
        with patch.dict(enlist_tests.PERSON,section='UNASSIGNED'):
            response,write,_=runner.run_enlistment(posted={'subject_ids':['110'],'section':'BSCS 4-1'})
            self.assertEqual(response.status_code,302)
            changes=[call.args[1] for call in write.call_args_list if 'UPDATE students SET section' in call.args[0]]
            self.assertEqual(changes[0]['section'],'BSCS 4-1')
            response,write,_=runner.run_enlistment(posted={'subject_ids':['110'],'section':'BSIT 4-1'})
            self.assertEqual(response.status_code,400);write.assert_not_called()
    def test_scholar_boundaries_missing_failures_and_unit_weighting(self):
        def check(grades,units=None,missing=False,status='PUBLISHED'):
            enrollments=[dict(assignment_id=i,status=status,units=(units or [3]*len(grades))[i]) for i in range(len(grades))]
            own=[dict(classroom=dict(assignment_id=i),student=dict(result=dict(total=90,missing=missing,equivalent=g))) for i,g in enumerate(grades)]
            return progress.scholarship(enrollments,own)
        for grade,label in [('1.00','University Scholar'),('1.49','University Scholar'),('1.50','College Scholar'),('1.75','College Scholar'),('1.76',None)]:self.assertEqual(check([grade])['label'],label)
        self.assertIsNone(check(['1.00'],missing=True)['label']);self.assertIsNone(check(['1.00'],status='DRAFT')['label'])
        self.assertIsNone(check(['1.00','5.00'],units=[9,1])['label'])
        self.assertEqual(check(['1.00','2.00'],units=[3,1])['gwa'],'1.25')
        self.assertFalse(check(['1.00'],missing=True)['complete'])
    def test_class_creation_rejects_wrong_program_before_writes(self):
        with AuditFixture() as f,f.app.test_request_context('/app/admin/classes/create',method='POST',data=dict(class_term_id=1,teacher_id=2,subject_id=10,section='BSCS 1-1')):
            session.update(user_id=1,role='admin')
            subject=dict(subject_id=10,program='BSCS',is_archived=0,year_level='1st Year',semester_offered='1st Semester')
            def one(sql,params=None):
                if 'FROM subjects' in sql:return subject
                if 'FROM teachers' in sql:return dict(teacher_id=2,user_id=2,program='BSIT')
                return dict(TERM)
            with patch.object(academic,'offering_terms',return_value=[TERM]),patch.object(srs,'query_one',side_effect=one),patch.object(srs,'execute_returning_id') as write,self.assertRaises(BadRequest):srs.create_class()
            write.assert_not_called()
    def test_admin_program_filters_and_protected_photos(self):
        with AuditFixture() as f:
            client=f.client('admin');page=client.get('/admin/students')
            for program in ('BSCS','BSIT','BSDSA','BSIS','BLIS'):self.assertIn(('value="'+program+'"').encode(),page.data)
            self.assertIn(b'BSIT 1-1',page.data)
            self.assertIn(f.client('student').get('/admin/students/3/photo').status_code,(302,403))
    def test_dashboard_panels_removed(self):
        with AuditFixture() as f:
            page=f.client('student').get('/app/student').data
            self.assertNotIn(b'<h2>Published subject results',page);self.assertNotIn(b'<h2>My classes',page)

if __name__=='__main__':unittest.main()
