import io
import unittest
from unittest.mock import patch
from flask import session
from werkzeug.exceptions import BadRequest,NotFound,Conflict
from app import srs_grading as sg
from app.routes import srs
from audit_fixture import AuditFixture

CATS=[dict(category_id=1,category_name='Lecture',weight_percent=60),dict(category_id=2,category_name='Laboratory',weight_percent=40)]
COMP=[dict(component_id=1,component_name='Quiz',category_id=1,weight_percent=50,maximum_score=100),dict(component_id=2,component_name='Exam',category_id=1,weight_percent=50,maximum_score=100),dict(component_id=3,component_name='Lab',category_id=2,weight_percent=100,maximum_score=20)]


class SrsCalculationTests(unittest.TestCase):
    def test_two_tier_contributions_and_letters(self):
        result=sg.calculate(CATS,COMP,{1:(80,100),2:(100,100),3:(18,20)})
        self.assertEqual(result['total'],90)
        self.assertEqual(result['letter'],'Grade A')
        self.assertEqual(result['weights'],{1:30,2:30,3:40})
    def test_missing_contributes_zero_but_stays_missing(self):
        result=sg.calculate(CATS,COMP,{1:(80,100),3:(18,20)})
        self.assertTrue(result['valid']);self.assertEqual(result['total'],60)
        self.assertEqual(result['missing'],1)
        recorded=sg.calculate(CATS,COMP,{1:(80,100),2:(0,100),3:(18,20)})
        self.assertEqual(recorded['total'],60);self.assertEqual(recorded['missing'],0)
    def test_invalid_splits_components_and_orphans(self):
        for cats,components in [(CATS[:1],COMP),([dict(CATS[0],weight_percent=50),CATS[1]],COMP),(CATS,COMP[:1]),(CATS,[dict(COMP[0],category_id=9)])]:
            result=sg.calculate(cats,components,{})
            self.assertFalse(result['valid']);self.assertIsNone(result['total'])
    def test_zero_weight_portion_can_have_no_components(self):
        result=sg.calculate([dict(CATS[0],weight_percent=100),dict(CATS[1],weight_percent=0)],COMP[:2],{})
        self.assertTrue(result['valid']);self.assertEqual(result['total'],0)
    def test_unused_previous_categories_do_not_change_srs_split(self):
        previous=dict(category_id=9,category_name='Previous scheme',weight_percent=70)
        result=sg.calculate(CATS+[previous],COMP,{})
        self.assertTrue(result['valid']);self.assertEqual(len(result['parts']),2)
        duplicate=dict(CATS[0],category_id=4)
        self.assertFalse(sg.calculate(CATS+[duplicate],COMP,{})['valid'])
    def test_rank_ties_are_stable_competition_ranks(self):
        rows=[dict(student_id=2,total=90),dict(student_id=1,total=90),dict(student_id=3,total=80)]
        ranked=sg.rank(rows)
        self.assertEqual([r['rank'] for r in ranked],[1,1,3]);self.assertEqual(ranked[0]['student_id'],1)
    def test_student_average_is_credit_weighted_and_published_only(self):
        def course(aid,status,units,value):
            return dict(assignment_id=aid,status=status,units=units,students=[dict(student_id=3,program='BSCS',main_section='A',result=dict(total=value))])
        student=dict(student_id=3,program='BSCS',section='A')
        report=sg.student_summary(student,[course(1,'PUBLISHED',3,80),course(2,'PUBLISHED',1,100),course(3,'IN_PROGRESS',5,0)])
        self.assertEqual(report['average'],85);self.assertEqual(report['published'],2);self.assertEqual(report['rank'],1)
    def test_reporting_uses_five_bulk_queries(self):
        with patch.object(sg,'query_all',side_effect=[[dict(assignment_id=1,units=3)],[],[],[],[]]) as query:
            rows=sg.load_classes(1,teacher_id=2)
        self.assertEqual(len(rows),1);self.assertEqual(query.call_count,5)
        for call in query.call_args_list:self.assertIn('ts.teacher_id=:teacher',call.args[0])
    def test_published_queries_explicitly_exclude_drafts(self):
        with patch.object(sg,'query_all',side_effect=[[dict(assignment_id=1,units=3)],[],[],[],[]]) as query:sg.load_classes(1,published_only=True)
        for call in query.call_args_list:self.assertIn("ts.status='PUBLISHED'",call.args[0])
    def test_existing_publication_value_is_preserved_across_srs_alignment(self):
        import json
        published=dict(assignment_id=1,payload=json.dumps(dict(students=[dict(student_id=3,result=dict(total=85,parts=[]))])))
        with patch.object(sg,'query_all',side_effect=[[dict(assignment_id=1,units=3,status='PUBLISHED')],[],[],[dict(assignment_id=1,student_id=3,enrollment_id=1)],[],[published]]):
            result=sg.load_classes(1,published_only=True)
        self.assertEqual(result[0]['students'][0]['result']['total'],85)
        self.assertTrue(result[0]['students'][0]['result']['legacy'])


class SrsAccessTests(unittest.TestCase):
    def test_roles_cannot_access_each_others_srs_routes(self):
        with AuditFixture() as fixture:
            for role,path in [('student','/app/admin'),('student','/app/teacher/class/1'),('faculty','/app/student/grades'),('admin','/app/teacher')]:
                self.assertEqual(fixture.client(role).get(path).status_code,302)
            self.assertEqual(fixture.app.test_client().get('/app/teacher').status_code,302)
    def test_teacher_cannot_write_foreign_or_stale_class(self):
        with AuditFixture() as fixture,fixture.app.test_request_context('/',method='POST',data={'revision':'2'}):
            session.update(user_id=2,role='faculty',teacher_id=2)
            with patch.object(srs.gb,'classroom',return_value=dict(teacher_id=99)):
                with self.assertRaises(NotFound):srs.teacher_class(1,True)
            with patch.object(srs.gb,'classroom',return_value=dict(teacher_id=2,is_active=1,revision=3,status='DRAFT')):
                with self.assertRaises(Conflict):srs.teacher_class(1,True)
    def test_export_text_sanitization(self):
        for text in ('=1+1',' +cmd','-formula','@SUM(A1)','\tcmd'):
            self.assertTrue(str(srs.csv_safe(text)).startswith("'"))
        self.assertEqual(srs.csv_safe(0),0)


if __name__=='__main__':unittest.main()
