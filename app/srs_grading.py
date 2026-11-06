"""SRS grading: category/component weights, missing=zero, published-only averages."""
from collections import Counter,defaultdict
from decimal import Decimal,ROUND_HALF_UP
from statistics import mean
import json
from .db import query_all
from .gradebook import decimal
from .grading import letter_grade,component_type


def rounded(value):
    return float(Decimal(str(value)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))


def university_grade(value):
    if value is None:return None
    for threshold,grade in ((98,'1.00'),(95,'1.25'),(92,'1.50'),(89,'1.75'),(86,'2.00'),(83,'2.25'),(80,'2.50'),(77,'2.75'),(75,'3.00')):
        if value>=threshold:return grade
    return '5.00'


def calculate(categories,components,scores,flexible=False,aggregation='LEGACY'):
    issues=[];weights={};parts=[];recorded=0;total=Decimal(0)
    # Retain previous category rows for history, but only the SRS portions are active.
    categories=list(categories) if flexible else [c for c in categories if c['category_name'].strip().casefold() in ('lecture','laboratory')]
    if flexible and not categories:issues.append('Add at least one grading component.')
    if not flexible and (len(categories)!=2 or {c['category_name'].strip().casefold() for c in categories}!={'lecture','laboratory'}):
        issues.append('Set up the Lecture and Laboratory split.')
    if sum((Decimal(str(c['weight_percent'])) for c in categories),Decimal(0))!=100:
        issues.append('Grading component weights must total 100%.' if flexible else 'Lecture and Laboratory weights must total 100%.')
    ids={c['category_id'] for c in categories}
    if any(c.get('category_id') not in ids for c in components):issues.append('Assign every activity to a grading component.' if flexible else 'Assign every component to Lecture or Laboratory.')
    for category in categories:
        items=[c for c in components if c.get('category_id')==category['category_id']]
        weight=Decimal(str(category['weight_percent']))
        points=aggregation=='POINTS'
        if weight>0 and (not items or not points and sum((Decimal(str(c['weight_percent'])) for c in items),Decimal(0))!=100):
            issues.append(category['category_name']+' component weights must total 100%.')
        result=Decimal(0);count=0;raw=Decimal(0)
        maximum_total=sum((Decimal(str(c['maximum_score'])) for c in items if c.get('maximum_score') is not None),Decimal(0))
        for c in items:
            if c.get('maximum_score') is None:
                issues.append(c['component_name']+': set the highest possible score.')
            effective=(Decimal(str(c['maximum_score'] or 0))/maximum_total*weight if maximum_total else Decimal(0)) if points else Decimal(str(c['weight_percent']))*weight/100
            weights[c['component_id']]=float(effective)
            pair=scores.get(c['component_id'])
            if pair and pair[0] is not None:
                try:
                    maximum=decimal(pair[1],.01);value=decimal(pair[0],0,maximum)
                    result+=value/maximum*Decimal(str(c['weight_percent']))
                    raw+=value
                    count+=1;recorded+=1
                except ValueError:issues.append('A recorded score is invalid.')
        if points:result=Decimal(str(rounded(raw/maximum_total*100))) if maximum_total else Decimal(0)
        contribution=result*weight/100
        if points:contribution=Decimal(str(rounded(contribution)))
        total+=contribution
        parts.append(dict(category_id=category['category_id'],name=category['category_name'],weight=float(weight),result=rounded(result),
            contribution=rounded(contribution),recorded=count,expected=len(items)))
    valid=not issues
    value=rounded(total) if valid else None
    preview_safe=bool(categories) and bool(components) and ids.issuperset(c.get('category_id') for c in components)
    preview_safe=preview_safe and 0<=sum(Decimal(str(c['weight_percent'])) for c in categories)<=100
    preview_safe=preview_safe and any(c.get('maximum_score') is not None for c in components) and 'A recorded score is invalid.' not in issues
    preview_safe=preview_safe and not any(c.get('maximum_score') is None and scores.get(c['component_id'],(None,None))[0] is not None for c in components)
    if aggregation!='POINTS':preview_safe=preview_safe and all(sum(Decimal(str(c['weight_percent'])) for c in components if c.get('category_id')==cat['category_id'])<=100 for cat in categories)
    preview=rounded(total) if preview_safe and 0<=total<=100 else None
    return dict(total=value,letter=letter_grade(value),equivalent=university_grade(value),parts=parts,weights=weights,recorded=recorded,
        expected=len(components),missing=len(components)-recorded,problems=list(dict.fromkeys(issues)),valid=valid,
        preview_total=preview,preview_equivalent=university_grade(preview))


def rank(rows,key='total'):
    """Competition ranking at displayed two-decimal precision: 1,1,3."""
    result=sorted((dict(r) for r in rows if r.get(key) is not None),key=lambda r:(-rounded(r[key]),r.get('student_id',0)))
    previous=None;position=0
    for index,row in enumerate(result,1):
        value=rounded(row[key])
        if value!=previous:position=index
        row['rank']=position;previous=value
    return result


def load_classes(term_id,teacher_id=None,published_only=False):
    clauses=['(:term IS NULL OR ts.term_id=:term)'];params={'term':term_id}
    if teacher_id is not None:clauses.append('ts.teacher_id=:teacher');params['teacher']=teacher_id
    if published_only:clauses.append("ts.status='PUBLISHED'")
    where=' AND '.join(clauses)
    classes=query_all(f'''SELECT ts.*,s.subject_code,s.subject_name,s.units,s.program,ac.school_year,ac.semester,
        COALESCE(u.full_name,'Faculty not yet assigned') AS teacher_name FROM teacher_subjects ts JOIN subjects s ON s.subject_id=ts.subject_id
        LEFT JOIN teachers t ON t.teacher_id=ts.teacher_id LEFT JOIN users u ON u.user_id=t.user_id
        JOIN school_terms ac ON ac.term_id=ts.term_id
        WHERE {where} ORDER BY s.subject_name,ts.section''',params)
    if not classes:return []
    categories=query_all(f'''SELECT cat.* FROM grade_categories cat JOIN teacher_subjects ts ON ts.assignment_id=cat.assignment_id
        WHERE {where} ORDER BY cat.display_order,cat.category_id''',params)
    components=query_all(f'''SELECT gc.* FROM grade_components gc JOIN teacher_subjects ts ON ts.assignment_id=gc.assignment_id
        WHERE {where} ORDER BY gc.component_id''',params)
    students=query_all(f'''SELECT e.assignment_id,e.enrollment_id,st.student_id,st.id_number,COALESCE(sec.program,st.program) AS program,COALESCE(sec.year_level,st.year_level) AS year_level,
        COALESCE(sec.section_name,st.section) AS main_section,st.sex,st.enrollment_type,st.status,u.full_name,st.user_id
        FROM enrollments e JOIN teacher_subjects ts ON ts.assignment_id=e.assignment_id
        JOIN students st ON st.student_id=e.student_id JOIN users u ON u.user_id=st.user_id
        LEFT JOIN student_term_memberships m ON m.student_id=st.student_id AND m.term_id=ts.term_id
        LEFT JOIN academic_sections sec ON sec.section_id=m.section_id
        WHERE {where} ORDER BY u.full_name''',params)
    scores=query_all(f'''SELECT e.assignment_id,g.enrollment_id,g.component_id,g.score,g.max_score,g.updated_at
        FROM grades g JOIN enrollments e ON e.enrollment_id=g.enrollment_id
        JOIN teacher_subjects ts ON ts.assignment_id=e.assignment_id WHERE {where}''',params)
    by_class={c['assignment_id']:dict(c,categories=[],components=[],students=[],scores={}) for c in classes}
    for c in categories:by_class[c['assignment_id']]['categories'].append(c)
    for c in components:by_class[c['assignment_id']]['components'].append(c)
    for s in students:by_class[s['assignment_id']]['students'].append(dict(s))
    for s in scores:by_class[s['assignment_id']]['scores'].setdefault(s['enrollment_id'],{})[s['component_id']]=(s['score'],s['max_score'])
    legacy={}
    if any(c.get('status')=='PUBLISHED' for c in classes):
        versions=query_all(f'''SELECT v.assignment_id,v.payload FROM grade_versions v
            JOIN teacher_subjects ts ON ts.assignment_id=v.assignment_id
            WHERE {where} AND ts.status='PUBLISHED' AND v.kind='PUBLICATION'
            AND v.version_id=(SELECT MAX(x.version_id) FROM grade_versions x WHERE x.assignment_id=v.assignment_id AND x.kind='PUBLICATION')''',params)
        for v in versions:
            raw=v['payload'];data=json.loads(raw.read() if hasattr(raw,'read') else raw)
            if data.get('model') not in ('SRS','FLEXIBLE'):legacy[v['assignment_id']]={s['student_id']:s['result'] for s in data.get('students',[])}
    for row in by_class.values():
        for s in row['students']:
            s['result']=calculate(row['categories'],row['components'],row['scores'].get(s['enrollment_id'],{}),row.get('grading_model')=='FLEXIBLE',row.get('aggregation','LEGACY'))
            preserved=legacy.get(row['assignment_id'],{}).get(s['student_id'])
            if preserved and preserved.get('total') is not None:
                s['result'].update(total=preserved['total'],letter=letter_grade(preserved['total']),
                    parts=preserved.get('parts',s['result']['parts']),valid=True,legacy=True)
                s['result']['equivalent']=university_grade(preserved['total'])
        totals=[s['result']['total'] for s in row['students'] if s['result']['total'] is not None]
        row['average']=rounded(mean(totals)) if totals else None
        row['ranked']=rank([dict(s,total=s['result']['total']) for s in row['students']])
        row['recorded']=sum(s['result']['recorded'] for s in row['students'])
        row['expected']=len(row['students'])*len(row['components'])
        row['missing']=row['expected']-row['recorded']
    return list(by_class.values())


def student_summary(student,classes):
    """Only published classes reach this function. Return own records and own rank."""
    from .curriculum import canonical_program
    totals={};own=[]
    for c in classes:
        if c['status']!='PUBLISHED':continue
        for s in c['students']:
            value=s['result']['total'];units=Decimal(str(c['units']))
            if value is None or units<=0:continue
            item=totals.setdefault(s['student_id'],dict(student_id=s['student_id'],program=s['program'],section=s['main_section'],points=0,units=0,count=0))
            item['points']+=Decimal(str(value))*units;item['units']+=units;item['count']+=1
            if s['student_id']==student['student_id']:
                private_class={key:value for key,value in c.items() if key not in ('students','scores','ranked')}
                private_class['scores']={s.get('enrollment_id'):c.get('scores',{}).get(s.get('enrollment_id'),{})}
                own.append(dict(classroom=private_class,student=s))
    cohort=[]
    for item in totals.values():
        program_key=canonical_program(item['program']) or item['program'].strip().casefold()
        own_program=canonical_program(student['program']) or student['program'].strip().casefold()
        if item['section'].strip().casefold()==student['section'].strip().casefold() and program_key==own_program:
            cohort.append(dict(item,total=rounded(item['points']/item['units'])))
    ranked=rank(cohort);mine=next((s for s in ranked if s['student_id']==student['student_id']),None)
    own_total=totals.get(student['student_id'])
    return dict(own=own,average=rounded(own_total['points']/own_total['units']) if own_total else None,
        rank=mine['rank'] if mine else None,cohort=len(ranked),published=len(own),
        units=own_total['units'] if own_total else 0)


def distribution(values):
    groups=[('90–100%',90,101),('85–89.99%',85,90),('80–84.99%',80,85),('75–79.99%',75,80),('Below 75%',0,75)]
    return [dict(label=label,value=sum(lo<=v<hi for v in values)) for label,lo,hi in groups]
