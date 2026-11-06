import unittest
from unittest.mock import patch
from app.insights import build_sections, effective_weights, load_sections, summarize, student_summary, enrollment_by_program


class InsightTests(unittest.TestCase):
    def build(self, scores, weights=(40, 60), status='PUBLISHED'):
        sections=[dict(assignment_id=1, status=status, units=3)]
        people=[dict(assignment_id=1, enrollment_id=eid, student_id=eid) for eid in scores]
        components=[dict(assignment_id=1, component_id=i, weight_percent=w, category_id=None)
                    for i,w in enumerate(weights,1)]
        grades=[dict(enrollment_id=eid, component_id=cid, score=score, max_score=maximum)
                for eid, values in scores.items() for cid,(score,maximum) in values.items()]
        return build_sections(sections,people,components,[],grades)

    def test_zero_is_recorded_but_missing_is_not_failure(self):
        sections=self.build({1:{1:(0,100),2:(0,100)},2:{1:(90,100)}})
        report=summarize(sections)
        self.assertEqual((report['complete'], report['below'], report['excluded']),(1,1,1))
        self.assertEqual((report['recorded'],report['expected'],report['coverage']),(3,4,75))
        self.assertIsNone(sections[0]['people'][1]['total'])

    def test_invalid_and_out_of_range_scores_are_incomplete(self):
        for score,maximum in [(10,0),(-1,100),(101,100),(float('nan'),100),(1,float('inf'))]:
            with self.subTest(score=score,maximum=maximum):
                report=summarize(self.build({1:{1:(score,maximum),2:(80,100)}}))
                self.assertEqual(report['complete'],0)
                self.assertEqual(report['missing'],1)

    def test_category_weights_and_unused_component(self):
        components=[dict(component_id=1,category_id=10,weight_percent=100),
                    dict(component_id=2,category_id=20,weight_percent=100)]
        weights, valid=effective_weights(components,{10:60,20:40})
        self.assertTrue(valid)
        self.assertEqual(weights,{1:60,2:40})
        self.assertFalse(effective_weights(components,{10:60,20:30})[1])
        self.assertFalse(effective_weights(components,{})[1])
        self.assertFalse(effective_weights(components,{10:60,20:40,30:1})[1])
        sections=self.build({1:{1:(80,100)}},weights=(100,0))
        self.assertEqual(sections[0]['totals'],[80])
        self.assertEqual(sections[0]['expected'],1)

    def test_weight_configuration_prevents_false_final_grade(self):
        section=self.build({1:{1:(100,100),2:(100,100)}},weights=(20,30))[0]
        self.assertFalse(section['weighting_valid'])
        self.assertEqual(section['complete'],0)
        self.assertIsNone(section['mean'])

    def test_distribution_boundaries_and_denominator(self):
        sections=self.build({i:{1:(n,100)} for i,n in enumerate([0,59.99,60,74.99,75,84.99,85,89.99,90,100],1)},weights=(100,))
        report=summarize(sections)
        self.assertEqual([b['value'] for b in report['distribution']],[2,2,2,2,2])
        self.assertEqual(report['pass_rate'],60)
        self.assertEqual(report['median'],80.0)

    def test_published_only_reporting(self):
        sections=self.build({1:{1:(95,100)}},weights=(100,),status='DRAFT')
        self.assertEqual(summarize(sections,published_only=True)['complete'],0)
        self.assertIsNone(student_summary(sections)['average'])
        self.assertEqual(summarize(sections)['complete'],1)

    def test_credit_weighted_average_excludes_missing_and_zero_units(self):
        a=self.build({1:{1:(80,100)}},weights=(100,))[0]
        b=self.build({1:{1:(100,100)}},weights=(100,))[0];b['units']=1
        missing=self.build({1:{}},weights=(100,))[0]
        zero=dict(a, units=0)
        result=student_summary([a,b,missing,zero])
        self.assertEqual(result['average'],85)
        self.assertEqual((result['complete'],result['units']),(2,4))

    def test_empty_is_unknown_not_zero_percent(self):
        self.assertIsNone(summarize([])['coverage'])
        self.assertIsNone(summarize([])['pass_rate'])
        self.assertIsNone(student_summary([])['average'])

    def test_program_chart_counts_students_once_across_classes(self):
        sections = [dict(people=[dict(student_id=1,program='BSDSA'),dict(student_id=2,program='BSCS')]),
                    dict(people=[dict(student_id=1,program='BSDSA'),dict(student_id=3,program='BSDSA')])]
        self.assertEqual(enrollment_by_program(sections),[dict(label='BSDSA',value=2),dict(label='BSCS',value=1)])

    def test_student_sql_scopes_scores_to_owner_and_published_classes(self):
        section=dict(assignment_id=1,status='DRAFT',units=3)
        with patch('app.insights.query_all',side_effect=[[section],[],[],[],[]]) as query:
            load_sections(7,student_id=9)
        self.assertEqual(query.call_count,5)
        for call in query.call_args_list:
            self.assertIn('mine.student_id=:student_id',call.args[0])
            self.assertEqual(call.args[1],{'term_id':7,'student_id':9})
        score_sql=query.call_args_list[-1].args[0]
        self.assertIn("ts.status='PUBLISHED'",score_sql)
        self.assertIn('e.student_id=:student_id',score_sql)

    def test_faculty_sql_scopes_all_queries(self):
        with patch('app.insights.query_all',side_effect=[[dict(assignment_id=1,status='DRAFT')],[],[],[],[]]) as query:
            load_sections(7,teacher_id=2)
        for call in query.call_args_list:
            self.assertIn('ts.teacher_id=:teacher_id',call.args[0])
            self.assertEqual(call.args[1]['teacher_id'],2)


if __name__ == '__main__':
    unittest.main()
