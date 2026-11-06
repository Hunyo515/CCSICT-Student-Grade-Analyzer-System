"""Scoped, bulk-loaded reporting with explicit grade completeness denominators."""
from collections import defaultdict
from statistics import mean, median
from math import isfinite

from .db import query_all
from .grading import compute_weighted_total

TARGET = 75


def percent(numerator, denominator):
    return round(numerator * 100 / denominator, 1) if denominator else None


def valid_score(score, maximum):
    return (score is not None and maximum is not None
            and isfinite(float(score)) and isfinite(float(maximum))
            and float(maximum) > 0 and 0 <= float(score) <= float(maximum))


def effective_weights(components, categories):
    """Require complete, consistent weighting before reporting final outcomes."""
    weights = {}
    groups = defaultdict(float)
    for c in components:
        weight = float(c['weight_percent'])
        if not isfinite(weight) or not 0 <= weight <= 100:
            return {}, False
        cid = c.get('category_id')
        if (categories and cid not in categories) or (cid is not None and cid not in categories):
            return {}, False
        groups[cid] += weight
        weights[c['component_id']] = weight * float(categories[cid]) / 100 if categories else weight
    if categories:
        valid = (all(isfinite(float(w)) and 0 <= float(w) <= 100 for w in categories.values())
                 and abs(sum(float(w) for w in categories.values()) - 100) < .01
                 and all(abs(groups[cid] - 100) < .01 for cid, w in categories.items() if float(w) > 0))
    else:
        valid = abs(sum(weights.values()) - 100) < .01
    return weights, bool(components) and valid


def load_sections(term_id=None, *, teacher_id=None, student_id=None):
    """Five bounded bulk queries; student score reads are published-only in SQL."""
    conditions, params = [], {}
    if term_id is not None:
        conditions.append('ts.term_id=:term_id')
        params['term_id'] = term_id
    if teacher_id is not None:
        conditions.append('ts.teacher_id=:teacher_id')
        params['teacher_id'] = teacher_id
    if student_id is not None:
        conditions.append('EXISTS (SELECT 1 FROM enrollments mine WHERE mine.assignment_id=ts.assignment_id AND mine.student_id=:student_id)')
        params['student_id'] = student_id
    where = ' AND '.join(conditions) or '1=1'
    sections = query_all(f"""SELECT ts.assignment_id, ts.term_id, ts.section, ts.status,
        s.subject_code, s.subject_name, s.units, t.school_year, t.semester
        FROM teacher_subjects ts JOIN subjects s ON s.subject_id=ts.subject_id
        JOIN school_terms t ON t.term_id=ts.term_id WHERE {where}
        ORDER BY ts.term_id, s.subject_code, ts.section""", params)
    if not sections:
        return []
    own = ' AND e.student_id=:student_id' if student_id is not None else ''
    published = " AND ts.status='PUBLISHED'" if student_id is not None else ''
    enrollments = query_all(f"""SELECT e.assignment_id, e.enrollment_id, e.student_id,
        st.program, u.full_name FROM enrollments e
        JOIN teacher_subjects ts ON ts.assignment_id=e.assignment_id
        JOIN students st ON st.student_id=e.student_id JOIN users u ON u.user_id=st.user_id
        WHERE {where}{own}""", params)
    components = query_all(f"""SELECT gc.assignment_id, gc.component_id, gc.component_name,
        gc.weight_percent, gc.category_id FROM grade_components gc
        JOIN teacher_subjects ts ON ts.assignment_id=gc.assignment_id
        WHERE {where}{published} ORDER BY gc.component_id""", params)
    categories = query_all(f"""SELECT cat.assignment_id, cat.category_id, cat.weight_percent
        FROM grade_categories cat JOIN teacher_subjects ts ON ts.assignment_id=cat.assignment_id
        WHERE {where}{published}""", params)
    scores = query_all(f"""SELECT e.assignment_id, g.enrollment_id, g.component_id, g.score, g.max_score
        FROM grades g JOIN enrollments e ON e.enrollment_id=g.enrollment_id
        JOIN teacher_subjects ts ON ts.assignment_id=e.assignment_id
        WHERE {where}{own}{published}""", params)
    return build_sections(sections, enrollments, components, categories, scores)


def build_sections(sections, enrollments, components, categories, scores):
    by_enrollment = defaultdict(dict)
    by_class, class_components, class_categories = defaultdict(list), defaultdict(list), defaultdict(dict)
    for row in enrollments:
        by_class[row['assignment_id']].append(row)
    for row in components:
        class_components[row['assignment_id']].append(row)
    for row in categories:
        class_categories[row['assignment_id']][row['category_id']] = row['weight_percent']
    for row in scores:
        by_enrollment[row['enrollment_id']][row['component_id']] = (row['score'], row['max_score'])
    result = []
    for original in sections:
        item = dict(original)
        aid = item['assignment_id']
        comps, cats = class_components[aid], class_categories[aid]
        weights, weighting_valid = effective_weights(comps, cats)
        required = [c for c in comps if weights.get(c['component_id'], 0) > 0]
        people, assessment_rows = [], []
        for enrollment in by_class[aid]:
            recorded = by_enrollment[enrollment['enrollment_id']]
            valid = {cid: pair for cid, pair in recorded.items() if valid_score(*pair)}
            missing = sum(c['component_id'] not in valid for c in required)
            complete = weighting_valid and missing == 0
            total = compute_weighted_total(valid, comps, cats) if complete else None
            people.append({**enrollment, 'total': total, 'missing': missing,
                           'recorded': sum(c['component_id'] in valid for c in required),
                           'complete': complete})
        for c in comps:
            values = [by_enrollment[e['enrollment_id']].get(c['component_id'], (None, None)) for e in by_class[aid]]
            valid = [float(s) / float(m) * 100 for s, m in values if valid_score(s, m)]
            assessment_rows.append({**c, 'mean': round(mean(valid), 1) if valid else None,
                'recorded': len(valid), 'expected': len(people), 'coverage': percent(len(valid), len(people)),
                'effective_weight': round(weights.get(c['component_id'], 0), 2),
                'contribution': round(mean(valid) * weights.get(c['component_id'], 0) / 100, 2) if valid and weighting_valid else None})
        totals = [p['total'] for p in people if p['complete']]
        expected = len(required) * len(people)
        recorded_count = sum(p['recorded'] for p in people)
        item.update(people=people, components=assessment_rows, weighting_valid=weighting_valid,
            students=len(people), expected=expected, recorded=recorded_count,
            missing=expected-recorded_count, coverage=percent(recorded_count, expected),
            complete=len(totals), mean=round(mean(totals), 2) if totals else None,
            median=round(median(totals), 2) if totals else None,
            below=sum(t < TARGET for t in totals), totals=totals)
        result.append(item)
    return result


def summarize(sections, published_only=False):
    eligible = [s for s in sections if not published_only or s['status'] == 'PUBLISHED']
    totals = [t for s in eligible for t in s['totals']]
    expected, recorded = sum(s['expected'] for s in sections), sum(s['recorded'] for s in sections)
    bins = [('Below 60', 0, 60), ('60–74.99', 60, 75), ('75–84.99', 75, 85), ('85–89.99', 85, 90), ('90–100', 90, 101)]
    return dict(sections=len(sections), students=len({p['student_id'] for s in sections for p in s['people']}),
        enrollments=sum(s['students'] for s in sections), published=sum(s['status']=='PUBLISHED' for s in sections),
        expected=expected, recorded=recorded, missing=expected-recorded, coverage=percent(recorded, expected),
        invalid=sum(not s['weighting_valid'] for s in sections), complete=len(totals),
        excluded=sum(s['students'] for s in eligible)-len(totals),
        mean=round(mean(totals), 1) if totals else None, median=round(median(totals), 1) if totals else None,
        below=sum(t < TARGET for t in totals), pass_rate=percent(sum(t >= TARGET for t in totals), len(totals)),
        distribution=[dict(label=label, value=sum(lo <= t < hi for t in totals)) for label, lo, hi in bins])


def student_summary(sections):
    published = [s for s in sections if s['status']=='PUBLISHED']
    eligible = [s for s in published if s['mean'] is not None and float(s['units'] or 0) > 0]
    units = sum(float(s['units']) for s in eligible)
    return dict(published=len(published), total=len(sections), complete=len(eligible),
        average=round(sum(s['totals'][0]*float(s['units']) for s in eligible)/units, 1) if units else None,
        units=units, below=sum(s['mean'] < TARGET for s in eligible),
        missing=sum(s['missing'] for s in published))


def enrollment_by_program(sections):
    programs = defaultdict(set)
    for section in sections:
        for person in section['people']:
            programs[person.get('program') or 'Unspecified'].add(person['student_id'])
    return sorted([dict(label=name, value=len(students)) for name, students in programs.items()],
                  key=lambda row: (-row['value'], row['label']))


def term_history(sections):
    history = []
    for tid in sorted({s['term_id'] for s in sections}):
        term = [s for s in sections if s['term_id'] == tid]
        history.append({**student_summary(term),
                        'label': f"{term[0]['semester']} · {term[0]['school_year']}"})
    return history
