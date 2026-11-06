"""One calculation and immutable revision service for the rebuilt gradebook."""
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_FLOOR
from statistics import mean, median
from flask import abort, session
from .db import query_all, query_one, execute, execute_returning_id


def decimal(value, low=0, high=999999):
    try:
        result=Decimal(str(value))
        if not result.is_finite() or not Decimal(str(low))<=result<=Decimal(str(high)):raise ValueError()
        if result!=result.quantize(Decimal('.01')):raise ValueError()
        return result
    except (InvalidOperation,ValueError,TypeError):
        raise ValueError(f'Enter a number between {low} and {high}, with at most two decimal places.')


def equivalent(value, rounding):
    if value is None or rounding=='UNSET':return None
    n=Decimal(str(value)).quantize(Decimal('1'),rounding=ROUND_HALF_UP if rounding=='HALF_UP' else ROUND_FLOOR)
    for threshold,grade in [(98,'1.00'),(95,'1.25'),(92,'1.50'),(89,'1.75'),(86,'2.00'),(83,'2.25'),(80,'2.50'),(77,'2.75'),(75,'3.00')]:
        if n>=threshold:return grade
    return '5.00'


def calculate(categories, assessments, scores, aggregation, rounding='UNSET'):
    """No partial totals or implicit zeros. Return explicit coverage and problems."""
    problems=[];parts=[];contributions=[]
    if not categories:problems.append('Add grading categories.')
    if sum((decimal(c['weight_percent'],0,100) for c in categories),Decimal(0))!=100:problems.append('Category weights must total 100%.')
    if aggregation not in ('EQUAL','POINTS'):problems.append('Choose how assessments are averaged.')
    if any(a.get('category_id') not in {c['category_id'] for c in categories} for a in assessments):problems.append('Assign every assessment to a category.')
    recorded=0
    for cat in categories:
        items=[a for a in assessments if a.get('category_id')==cat['category_id']]
        values=[]
        for a in items:
            pair=scores.get(a['component_id'])
            if pair and pair[0] is not None:
                try:
                    maximum=decimal(pair[1],.01);score=decimal(pair[0],0,maximum)
                    values.append((score,maximum));recorded+=1
                except ValueError:problems.append('A score or maximum is invalid.')
        complete=bool(items) and len(values)==len(items)
        result=None
        if complete and aggregation in ('EQUAL','POINTS'):
            result=(sum((s/m*100 for s,m in values),Decimal(0))/len(values) if aggregation=='EQUAL'
                    else sum((s for s,m in values),Decimal(0))/sum((m for s,m in values),Decimal(0))*100)
        if result is not None:contributions.append(result*decimal(cat['weight_percent'],0,100)/100)
        parts.append(dict(name=cat['category_name'],weight=float(cat['weight_percent']),
            result=float(result) if result is not None else None,
            contribution=float(result*decimal(cat['weight_percent'],0,100)/100) if result is not None else None,
            recorded=len(values),expected=len(items)))
    complete=bool(parts) and all(p['result'] is not None for p in parts) and not problems
    total=sum(contributions,Decimal(0)) if complete else None
    return dict(parts=parts,total=float(total) if total is not None else None,
        equivalent=equivalent(total,rounding),recorded=recorded,expected=len(assessments),problems=problems,complete=complete)


def classroom(aid, lock=False):
    if lock:
        if not query_one('SELECT assignment_id FROM teacher_subjects WHERE assignment_id=:id FOR UPDATE WAIT 5',{'id':aid}):abort(404)
    row=query_one('''SELECT ts.*,s.subject_code,s.subject_name,s.units,s.program,s.prerequisite_text,
        COALESCE(u.full_name,'Faculty not yet assigned') AS teacher_name,t.user_id AS teacher_user_id,term.school_year,term.semester,term.is_active
        FROM teacher_subjects ts JOIN subjects s ON s.subject_id=ts.subject_id
        LEFT JOIN teachers t ON t.teacher_id=ts.teacher_id LEFT JOIN users u ON u.user_id=t.user_id
        JOIN school_terms term ON term.term_id=ts.term_id WHERE ts.assignment_id=:id''',{'id':aid})
    if not row:abort(404)
    return row


def content(aid):
    cats=query_all('SELECT * FROM grade_categories WHERE assignment_id=:id ORDER BY display_order,category_id',{'id':aid})
    assessments=query_all('SELECT * FROM grade_components WHERE assignment_id=:id ORDER BY component_id',{'id':aid})
    roster=query_all('''SELECT e.enrollment_id,s.student_id,s.id_number,s.program,s.section,u.full_name
        FROM enrollments e JOIN students s ON s.student_id=e.student_id JOIN users u ON u.user_id=s.user_id
        WHERE e.assignment_id=:id ORDER BY u.full_name''',{'id':aid})
    rows=query_all('''SELECT g.* FROM grades g JOIN enrollments e ON e.enrollment_id=g.enrollment_id
        WHERE e.assignment_id=:id''',{'id':aid})
    scores={}
    for r in rows:scores.setdefault(r['enrollment_id'],{})[r['component_id']]=(r['score'],r['max_score'])
    return cats,assessments,roster,scores


def snapshot(row):
    cats,assessments,roster,scores=content(row['assignment_id'])
    students=[]
    for s in roster:
        pairs=scores.get(s['enrollment_id'],{})
        result=calculate(cats,assessments,pairs,row['aggregation'],row['rounding_rule'])
        students.append(dict(**s,result=result,scores={str(k):[float(x) if x is not None else None for x in v] for k,v in pairs.items()}))
    return dict(subject={k:row[k] for k in ('subject_code','subject_name','units','section','school_year','semester','aggregation','rounding_rule')},
        categories=cats,assessments=assessments,students=students)


def save_version(row, kind, payload, source=None, reason=None):
    return execute_returning_id('''INSERT INTO grade_versions(assignment_id,kind,actor_user_id,actor_name,source_version_id,revision,payload,reason)
        VALUES(:aid,:kind,:actor,:actor_name,:source,:revision,:payload,:reason) RETURNING version_id INTO :out_id''',
        dict(aid=row['assignment_id'],kind=kind,actor=session['user_id'],actor_name=session.get('full_name'),source=source,revision=row['revision'],payload=json.dumps(payload,default=str),reason=reason))


def latest(aid,kind):
    row=query_one('''SELECT * FROM grade_versions WHERE assignment_id=:id AND kind=:kind
        ORDER BY version_id DESC FETCH FIRST 1 ROWS ONLY''',{'id':aid,'kind':kind})
    if row:
        raw=row['payload'];row['data']=json.loads(raw.read() if hasattr(raw,'read') else raw)
    return row


def analysis(assessments,roster,scores):
    result=[]
    for a in assessments:
        values=[]
        for student in roster:
            pair=scores.get(student['enrollment_id'],{}).get(a['component_id'])
            if pair and pair[0] is not None and pair[1] and 0<=pair[0]<=pair[1]:values.append(float(pair[0])/float(pair[1])*100)
        bins=[sum(1 for v in values if lo<=v<(hi if hi<101 else 101)) for lo,hi in [(0,25),(25,50),(50,75),(75,90),(90,101)]]
        result.append(dict(name=a['component_name'],recorded=len(values),missing=len(roster)-len(values),
            mean=round(mean(values),2) if values else None,median=round(median(values),2) if values else None,
            bins=bins,maximum=max(bins,default=1) or 1))
    return result
