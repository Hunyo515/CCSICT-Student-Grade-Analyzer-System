import unittest
from unittest.mock import patch
from app import academic
from app.routes import university
from audit_fixture import AuditFixture, PROFILE, TERM

PERSON = dict(PROFILE, program='BSCS', year_level='4th Year', section='BSCS 4-1')
CLASSES = [dict(assignment_id=i, subject_id=i+100, subject_code=f'CS{i}', subject_name='Current subject', units=3, year_level='4th Year', section='BSCS 4-1', teacher_name='Faculty', prerequisite_text='', status='DRAFT') for i in (10,20)]


class CurrentEnlistmentTests(unittest.TestCase):
    def run_enlistment(self, existing=(), classes=None, term=TERM, posted=None, changed=False, passed=(), catalog=()):
        with AuditFixture() as fixture:
            client=fixture.client('student'); client.get('/university/enlistme')
            with client.session_transaction() as state: csrf=state['csrf']
            def find(sql, params=None):
                if 'FROM subjects' in sql:return {'subject_id':params['id']}
                if 'FROM teacher_subjects' in sql:
                    return {'status':next(c['status'] for c in (classes or CLASSES) if c['assignment_id']==params['id'])}
                if 'FROM students' in sql:
                    return dict(PERSON, year_level='3rd Year') if changed else PERSON
                if 'FROM academic_sections' in sql:return {'section_id':5}
            with patch('app.student_progress.passed_subjects',return_value=set(passed)), patch('app.student_progress.curriculum',return_value=list(catalog)), patch('app.routes.student.get_student',return_value=PERSON), patch.object(academic,'active',return_value=term), patch.object(university,'offerings',return_value=CLASSES if classes is None else classes) as offered, patch.object(university,'current_enrollments',return_value=list(existing)), patch.object(university,'query_one',side_effect=find), patch.object(university,'query_all',return_value=[]), patch.object(university,'execute') as write, patch.object(university,'execute_returning_id',return_value=999) as create, patch.object(university,'log_activity'):
                response=client.post('/university/enlistme',data={'csrf_token':csrf,'enlistment_term_id':1,'subject_ids':['110','120'],**(posted or {})})
            self.created_class=create
            return response,write,offered

    def test_enrolls_only_checked_subjects(self):
        response,write,offered=self.run_enlistment(posted={'subject_ids':['110']})
        self.assertEqual(response.status_code,302)
        self.assertTrue(all(call.args==(TERM,'BSCS','4th Year','BSCS 4-1') for call in offered.call_args_list))
        inserts=[c.args[1]['aid'] for c in write.call_args_list if 'INSERT INTO enrollments' in c.args[0]]
        self.assertEqual(inserts,[10])
        self.assertFalse(any('DELETE' in c.args[0] for c in write.call_args_list))

    def test_enrolls_catalog_subject_before_any_class_or_faculty_assignment(self):
        response,write,_=self.run_enlistment(classes=[dict(CLASSES[0],assignment_id=None)],posted={'subject_ids':['110']})
        self.assertEqual(response.status_code,302)
        self.created_class.assert_called_once()
        self.assertNotIn('teacher_id',self.created_class.call_args.args[0])
        self.assertEqual(self.created_class.call_args.args[1]['subject'],110)
        self.assertEqual([c.args[1]['aid'] for c in write.call_args_list if 'INSERT INTO enrollments' in c.args[0]],[999])

    def test_empty_duplicate_invalid_or_unlisted_selection_rejected(self):
        for selection in ([], ['110','110'], ['999'], ['-1'], ['x']):
            response,write,_=self.run_enlistment(posted={'subject_ids':selection})
            self.assertEqual(response.status_code,400)
            write.assert_not_called()

    def test_unselected_locked_subject_does_not_block_selection(self):
        response,write,_=self.run_enlistment(classes=[dict(CLASSES[0],status='PUBLISHED'),CLASSES[1]],posted={'subject_ids':['120']})
        self.assertEqual(response.status_code,302)
        self.assertEqual([c.args[1]['aid'] for c in write.call_args_list if 'INSERT INTO enrollments' in c.args[0]],[20])

    def test_repeat_is_idempotent_and_existing_other_subjects_are_preserved(self):
        existing=[dict(enrollment_id=i,assignment_id=i,subject_id=i+100) for i in (10,20,30)]
        response,write,_=self.run_enlistment(existing=existing)
        self.assertEqual(response.status_code,302)
        self.assertFalse(any('INSERT INTO enrollments' in c.args[0] or 'DELETE' in c.args[0] or 'revision=revision+1' in c.args[0] for c in write.call_args_list))

    def test_stale_missing_term_and_missing_classes_reject_before_writes(self):
        for kwargs in ({'posted':{'enlistment_term_id':2}}, {'term':None}, {'classes':[]}, {'changed':True}):
            response,write,_=self.run_enlistment(**kwargs)
            self.assertEqual(response.status_code,409)
            write.assert_not_called()

    def test_missing_locked_class_rejects_entire_enrollment(self):
        response,write,_=self.run_enlistment(classes=[dict(CLASSES[0],status='PUBLISHED'),CLASSES[1]])
        self.assertEqual(response.status_code,409);write.assert_not_called()

    def test_already_enrolled_locked_class_blocks_second_submission(self):
        response,write,_=self.run_enlistment(existing=[dict(enrollment_id=1,assignment_id=10,subject_id=110)],classes=[dict(CLASSES[0],status='PUBLISHED'),CLASSES[1]])
        self.assertEqual(response.status_code,302)
        write.assert_not_called()

    def test_duplicate_subject_in_another_section_is_blocked(self):
        response,write,_=self.run_enlistment(existing=[dict(enrollment_id=1,assignment_id=99,subject_id=110)])
        self.assertEqual(response.status_code,302);write.assert_not_called()

    def test_passed_subject_rejected_even_if_checkbox_is_forged(self):
        response,write,_=self.run_enlistment(posted={'subject_ids':['110']},passed={('BSCS','CS10','current subject')})
        self.assertEqual(response.status_code,409);write.assert_not_called()
        self.assertIn(b'PASSED',response.data)

    def test_unmet_prerequisite_rejected_server_side(self):
        classes=[dict(CLASSES[0],prerequisite_text='CS 111')]
        catalog=[dict(subject_id=111,subject_code='CS 111')]
        response,write,_=self.run_enlistment(classes=classes,catalog=catalog,posted={'subject_ids':['110']})
        self.assertEqual(response.status_code,409);write.assert_not_called()
        response,write,_=self.run_enlistment(classes=classes,catalog=catalog,posted={'subject_ids':['110']},passed={('BSCS','CS111','programming')})
        self.assertEqual(response.status_code,302)

    def test_year_filter_changes_offerings_without_changing_profile(self):
        response,write,offered=self.run_enlistment(posted={'year_level':'2nd Year','subject_ids':['110']})
        self.assertEqual(response.status_code,302)
        self.assertTrue(all(call.args==(TERM,'BSCS','2nd Year','BSCS 2-1') for call in offered.call_args_list))
        self.assertFalse(any('UPDATE students' in call.args[0] for call in write.call_args_list))


if __name__=='__main__':unittest.main()
