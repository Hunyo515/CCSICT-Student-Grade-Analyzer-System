import unittest
from unittest.mock import patch
from flask import session
from werkzeug.exceptions import BadRequest,Conflict
from app import srs_grading as sg
from app.routes import srs
from srs_fixture import SrsFixture

CATEGORIES=[dict(category_id=1,category_name='Examinations',weight_percent=80),dict(category_id=2,category_name='Laboratory',weight_percent=20)]
ACTIVITIES=[dict(component_id=1,component_name='Final Exam',category_id=1,weight_percent=100,maximum_score=100),dict(component_id=2,component_name='Lab 1',category_id=2,weight_percent=40,maximum_score=50),dict(component_id=3,component_name='Lab 2',category_id=2,weight_percent=60,maximum_score=100)]

class FlexibleFixture(SrsFixture):
    def __enter__(self):
        super().__enter__()
        for item in self.records:
            if item['row']['assignment_id']==10:
                item['row']['grading_model']='FLEXIBLE'
                item['categories']=[dict(c,assignment_id=10,display_order=i) for i,c in enumerate(CATEGORIES)]
                item['components']=[dict(c,assignment_id=10) for c in ACTIVITIES]
                item['scores'][1]={1:(80,100),2:(40,50),3:(60,100)}
                item['scores'][2]={1:(90,100),2:(45,50),3:(90,100)}
                item['scores'][3]={1:(70,100),2:(35,50)}
        return self

class FlexibleGradingTests(unittest.TestCase):
    def test_nested_weights_and_unequal_highest_scores(self):
        result=sg.calculate(CATEGORIES,ACTIVITIES,{1:(80,100),2:(40,50),3:(60,100)},True)
        self.assertTrue(result['valid']);self.assertEqual(result['total'],77.6)
        self.assertEqual(result['parts'][1]['result'],68)
        self.assertEqual(result['parts'][1]['contribution'],13.6)
        self.assertEqual(result['weights'],{1:80,2:8,3:12})
        self.assertEqual(result['equivalent'],'2.75')

    def test_record_points_use_total_score_over_total_hps(self):
        result=sg.calculate(CATEGORIES,ACTIVITIES,{1:(80,100),2:(40,50),3:(60,100)},True,'POINTS')
        self.assertTrue(result['valid'])
        self.assertEqual(result['parts'][1]['result'],66.67)
        self.assertEqual(result['parts'][1]['contribution'],13.33)
        self.assertEqual(result['total'],77.33)
        self.assertTrue(sg.calculate(CATEGORIES,[dict(c,weight_percent=0) for c in ACTIVITIES],{},True,'POINTS')['valid'])

    def test_single_exam_component_can_be_100_percent(self):
        result=sg.calculate([dict(CATEGORIES[0],weight_percent=100)],ACTIVITIES[:1],{1:(91,100)},True)
        self.assertEqual(result['total'],91);self.assertEqual(result['equivalent'],'1.75')

    def test_invalid_parent_or_activity_totals_block_result(self):
        for categories,activities in [(CATEGORIES[:1],ACTIVITIES[:1]),(CATEGORIES,ACTIVITIES[:2]),(CATEGORIES,[dict(ACTIVITIES[0],category_id=99)]),([],[])]:
            self.assertFalse(sg.calculate(categories,activities,{},True)['valid'])

    def test_missing_is_distinct_from_recorded_zero(self):
        blank=sg.calculate(CATEGORIES,ACTIVITIES,{1:(0,100)},True)
        self.assertEqual(blank['missing'],2);self.assertEqual(blank['recorded'],1)
        self.assertEqual(blank['total'],0)

    def test_partial_scores_and_unconfigured_columns_have_provisional_grades(self):
        marks={1:(80,100),2:(40,50)}
        partial=sg.calculate(CATEGORIES,ACTIVITIES,marks,True,'POINTS')
        self.assertEqual(partial['total'],69.33)
        pending=[dict(c,maximum_score=None) if c['component_id']==3 else c for c in ACTIVITIES]
        preview=sg.calculate(CATEGORIES,pending,marks,True,'POINTS')
        self.assertFalse(preview['valid']);self.assertIsNone(preview['total'])
        self.assertEqual(preview['preview_total'],80)
        self.assertEqual(preview['preview_equivalent'],'2.50')
        bad=sg.calculate([dict(CATEGORIES[0],weight_percent=90),CATEGORIES[1]],ACTIVITIES,marks,True,'POINTS')
        self.assertIsNone(bad['preview_total'])

    def test_faculty_sheet_renders_partial_grade_without_publication(self):
        with FlexibleFixture() as fixture:
            record=fixture.records[0];record['row']['aggregation']='POINTS'
            record['components'][2]['maximum_score']=None
            for marks in record['scores'].values():marks.pop(3,None)
            html=fixture.client('faculty').get('/app/teacher/class/10').data
            self.assertIn(b'data-semester-total>80',html)
            self.assertIn(b'In progress',html)
            self.assertIn(b'data-insert-activity="2"',html)
            self.assertNotIn(b'data-editor-count type=',html)

    def test_isu_numeric_grade_boundaries(self):
        for score,value in [(100,'1.00'),(98,'1.00'),(97.99,'1.25'),(95,'1.25'),(75,'3.00'),(74.99,'5.00'),(None,None)]:
            self.assertEqual(sg.university_grade(score),value)

    def test_sheet_and_settings_render_custom_components(self):
        with FlexibleFixture() as fixture:
            client=fixture.client('faculty')
            html=client.get('/app/teacher/class/10').data
            self.assertIn(b'Semester Class Record',html);self.assertIn(b'data-semester-total>78<',html)
            self.assertNotIn('← Dashboard'.encode(),html)
            self.assertNotIn(b'Add grading section',html)
            self.assertNotIn(b'NEW COMPONENT',html)
            self.assertNotIn(b'Assessment key',html)
            self.assertIn(b'data-component-add',html)
            self.assertNotIn(b'data-component-edit',html)
            self.assertNotIn(b'Add activities',html)
            self.assertIn(b'data-count-edit',html)
            self.assertIn(b'Examinations',html)
            self.assertIn(b'class="sheet-id">TEST-001</th>',html)
            self.assertNotIn(b'<small>TEST-001</small>',html)
            self.assertNotIn(b'Grading settings',html)
            self.assertNotIn(b'Analytics',html.split(b'aria-label="Class pages"')[1].split(b'</nav>')[0])
            self.assertEqual(client.get('/app/teacher/class/10?tab=settings').status_code,302)

    def test_foreign_category_and_scored_activity_changes_reject(self):
        with FlexibleFixture() as fixture,fixture.app.test_request_context('/',method='POST',data=dict(action='component',category_id=999,component_name='Other',weight_percent=100,maximum_score=100,revision=4)):
            session.update(user_id=2,role='faculty',teacher_id=2)
            with patch.object(srs,'teacher_class',return_value=fixture.records[0]['row']),self.assertRaises(BadRequest):srs.setup(10)
        with FlexibleFixture() as fixture,fixture.app.test_request_context('/',method='POST',data=dict(action='edit_component',component_id=1,category_id=1,component_name='Final Exam',weight_percent=100,maximum_score=50,revision=4)):
            session.update(user_id=2,role='faculty',teacher_id=2)
            with patch.object(srs,'teacher_class',return_value=fixture.records[0]['row']),self.assertRaises(Conflict):srs.setup(10)

    def test_dashboard_moves_class_cards_to_my_classes(self):
        with FlexibleFixture() as fixture:
            client=fixture.client('faculty')
            self.assertNotIn(b'Open gradebook',client.get('/app/teacher').data)
            self.assertNotIn(b'Semester gradebooks',client.get('/app/teacher').data)
            self.assertIn(b'class-folder',client.get('/app/teacher/classes?term_filter=1').data)

    def test_blank_hps_blocks_final_grade_and_renders_empty(self):
        activities=[dict(c,maximum_score=None) for c in ACTIVITIES]
        self.assertFalse(sg.calculate(CATEGORIES,activities,{},True)['valid'])
        with FlexibleFixture() as fixture:
            fixture.records[0]['components'][1]['maximum_score']=None
            fixture.records[0]['scores']={}
            html=fixture.client('faculty').get('/app/teacher/class/10').data
            self.assertIn(b'placeholder="Set HPS"',html)
            self.assertNotIn(b'value="None"',html)

    def test_sheet_rejects_invalid_maximum_without_writes(self):
        for data in [{'activity__1__maximum':'50'}, {'activity__1__maximum':'','mark__1__1':'0'}, {'activity__999__name':'Foreign'}]:
            with FlexibleFixture() as fixture,fixture.app.test_request_context('/',method='POST',data=dict(revision=4,**data)):
                session.update(user_id=2,role='faculty',teacher_id=2)
                with patch.object(srs,'execute') as write,patch.object(srs,'teacher_class',return_value=fixture.records[0]['row']),self.assertRaises(BadRequest):srs.save_scores(10)
                write.assert_not_called()

    def test_sheet_updates_hidden_student_denominators(self):
        with FlexibleFixture() as fixture,fixture.app.test_request_context('/',method='POST',data={'revision':'4','activity__1__maximum':'120','activity__1__name':'Updated exam','mark__1__1':'100'}):
            session.update(user_id=2,role='faculty',teacher_id=2)
            with patch.object(srs,'execute'),patch.object(srs,'bump'),patch.object(srs,'write_scores') as write,patch.object(srs,'teacher_class',return_value=fixture.records[0]['row']):
                srs.save_scores(10)
                updates=write.call_args.args[1]
                self.assertIn((2,1,90,120),updates)
                self.assertIn((3,1,70,120),updates)
                self.assertIn((1,1,100,120),updates)

    def test_batch_activities_have_blank_maxima_and_exact_weight_total(self):
        with FlexibleFixture() as fixture,fixture.app.test_request_context('/',method='POST',data=dict(action='component',category_id=2,component_name='Practical',weight_percent=100,activity_count=3,revision=4)):
            session.update(user_id=2,role='faculty',teacher_id=2)
            with patch.object(srs,'execute') as write,patch.object(srs,'bump'),patch.object(srs,'teacher_class',return_value=fixture.records[0]['row']):
                srs.setup(10)
                entries=[call.args[1] for call in write.call_args_list if call.args[0].startswith('INSERT INTO grade_components')]
                self.assertEqual(len(entries),3)
                self.assertEqual(sum(e['weight'] for e in entries),100)
                self.assertTrue(all(e['maximum'] is None for e in entries))
                self.assertEqual(entries[2]['name'],'Practical 3')

    def test_allocation_cap_and_dates_validate_before_writes(self):
        for data in [{'cat__2__weight':'21'},{'new_category_name':'Extra','new_category_weight':'1'},{'activity__1__date':'02/30/26'}]:
            with FlexibleFixture() as fixture,fixture.app.test_request_context('/',method='POST',data=dict(revision=4,**data)):
                session.update(user_id=2,role='faculty',teacher_id=2)
                with patch.object(srs,'execute') as write,patch.object(srs,'teacher_class',return_value=fixture.records[0]['row']),self.assertRaises(BadRequest):srs.save_scores(10)
                write.assert_not_called()

    def test_inline_date_is_saved_and_new_dates_render_blank(self):
        with FlexibleFixture() as fixture:
            html=fixture.client('faculty').get('/app/teacher/class/10').data
            self.assertIn(b'placeholder="mm/dd/yy"',html)
            self.assertIn(b'data-component-remove',html)
        with FlexibleFixture() as fixture,fixture.app.test_request_context('/',method='POST',data={'revision':'4','activity__1__date':'10/25/26'}):
            session.update(user_id=2,role='faculty',teacher_id=2)
            with patch.object(srs,'execute') as write,patch.object(srs,'bump'),patch.object(srs,'write_scores'),patch.object(srs,'teacher_class',return_value=fixture.records[0]['row']):
                srs.save_scores(10)
                saved=next(c.args[1] for c in write.call_args_list if 'activity_date=:activity_date' in c.args[0] and c.args[1]['cid']==1)
                self.assertEqual(saved['activity_date'].isoformat(),'2026-10-25T00:00:00')

    def test_component_deletion_requires_explicit_scored_consent(self):
        for data,error in [({'delete_category_id':'2'},BadRequest),({'delete_category_id':'999','confirm_delete':'yes'},BadRequest),({'delete_category_id':'2','confirm_delete':'yes'},Conflict)]:
            with FlexibleFixture() as fixture,fixture.app.test_request_context('/',method='POST',data=dict(revision=4,**data)):
                session.update(user_id=2,role='faculty',teacher_id=2)
                with patch.object(srs,'execute') as write,patch.object(srs,'teacher_class',return_value=fixture.records[0]['row']),self.assertRaises(error):srs.save_scores(10)
                write.assert_not_called()
        with FlexibleFixture() as fixture,fixture.app.test_request_context('/',method='POST',data=dict(revision=4,delete_category_id=2,confirm_delete='yes',confirm_delete_scores='yes')):
            session.update(user_id=2,role='faculty',teacher_id=2)
            with patch.object(srs,'execute') as write,patch.object(srs,'bump'),patch.object(srs,'write_scores'),patch.object(srs,'teacher_class',return_value=fixture.records[0]['row']):
                srs.save_scores(10)
                deleted=[c.args[1]['cid'] for c in write.call_args_list if c.args[0].startswith('DELETE FROM grade_components')]
                self.assertEqual(set(deleted),{2,3})

    def test_scored_activity_delete_requires_confirmation_and_keeps_other_columns(self):
        with FlexibleFixture() as fixture,fixture.app.test_request_context('/',method='POST',data=dict(revision=4,delete_activity_id=2)):
            session.update(user_id=2,role='faculty',teacher_id=2)
            with patch.object(srs,'execute') as write,patch.object(srs,'teacher_class',return_value=fixture.records[0]['row']),self.assertRaises(BadRequest):srs.save_scores(10)
            write.assert_not_called()
        with FlexibleFixture() as fixture,fixture.app.test_request_context('/',method='POST',data=dict(revision=4,delete_activity_id=2,confirm_delete_activity='yes',mark__1__2=40,mark__1__1=80)):
            session.update(user_id=2,role='faculty',teacher_id=2)
            with patch.object(srs,'execute') as write,patch.object(srs,'write_scores') as marks,patch.object(srs,'bump'),patch.object(srs,'teacher_class',return_value=fixture.records[0]['row']):
                srs.save_scores(10)
                deleted=[c.args[1]['cid'] for c in write.call_args_list if c.args[0].startswith('DELETE FROM grade_components')]
                self.assertEqual(deleted,[2])
                self.assertEqual([u[1] for u in marks.call_args.args[1]],[1])

if __name__=='__main__':unittest.main()
