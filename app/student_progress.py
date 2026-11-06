"""Curriculum completion and enrollment eligibility shared by student views."""
import re
from .db import query_all,execute
from . import srs_grading as sg
from .curriculum import canonical_program

YEARS=('1st Year','2nd Year','3rd Year','4th Year')
SEMESTERS={'1st Semester':1,'2nd Semester':2,'Summer':3}

def residency(student,term=None):
    from datetime import date
    reference=int(term['school_year'][:4]) if term and term.get('school_year') else date.today().year
    match=re.fullmatch(r'(\d{2})-\d{4}',student.get('id_number',''))
    if match:
        admission=2000+int(match[1])
        if admission>date.today().year+1:admission-=100
        count=max(1,reference-admission+1)
    else:
        count=int(student.get('year_level','1st Year')[0])
        admission=reference-count+1
    suffix='th' if 10<=count%100<=20 else {1:'st',2:'nd',3:'rd'}.get(count%10,'th')
    return dict(residency_year=count,standing_year=f'{count}{suffix} Year',admission_year=admission,curriculum_year=YEARS[min(count,4)-1])

def code(value):
    return re.sub(r'[^A-Z0-9]','',value.upper())

def identity(subject):
    return (canonical_program(subject.get('program')),code(subject['subject_code']),re.sub(r'\s+',' ',subject.get('subject_name','').strip()).casefold())

def passed_subjects(student_id,classes=None):
    passed=set()
    for classroom in classes if classes is not None else sg.load_classes(None,published_only=True):
        if classroom['status']!='PUBLISHED':continue
        for student in classroom['students']:
            result=student['result']
            if student['student_id']==student_id and result.get('total') is not None and result['total']>=75 and not result.get('missing'):
                passed.add(identity(classroom))
    return passed

def curriculum(program):
    return query_all('SELECT subject_id,subject_code,subject_name,program,year_level,semester_offered,prerequisite_text,prerequisite_subject_id FROM subjects WHERE program=:program AND is_archived=0',{'program':canonical_program(program)})

def eligibility(subject,student,catalog,passed,concurrent=()):
    program=canonical_program(student['program'])
    completed={c for p,c,name in passed if p==program}
    if identity(dict(subject,program=program)) in passed:return 'PASSED'
    text=(subject.get('prerequisite_text') or '').strip()
    direct=subject.get('prerequisite_subject_id')
    if direct:
        required=next((r for r in catalog if r['subject_id']==direct),None)
        if not required or code(required['subject_code']) not in completed:return 'PREREQUISITE NOT COMPLETED'
    if text.lower() in ('','none','n/a','-'):return ''
    standing=re.fullmatch(r'([1-4])(?:st|nd|rd|th) year standing',text,re.I)
    if standing:return '' if int(student['year_level'][0])>=int(standing[1]) else 'YEAR STANDING REQUIRED'
    coreq=bool(re.search(r'co[ -]?requisite',text,re.I))
    text=re.sub(r'co[ -]?requisite(?: with)?','',text,flags=re.I).strip()
    # Expand printed shorthand (DSA 112, 121; CS DM 3 & 4) and ranges.
    tokens=re.split(r'\s*[,;&]\s*|\s+and\s+',text,flags=re.I)
    required=set();prefix=''
    catalog_codes={code(r['subject_code']):r['subject_code'].upper() for r in catalog}
    for token in tokens:
        token=token.strip().upper()
        if token.isdigit() and prefix:token=prefix+token
        match=re.match(r'^(.*?)(\d+)$',token)
        if match:prefix=match[1]
        normalized=code(token)
        if normalized in catalog_codes:required.add(normalized);continue
        # Source BLIS prerequisites contain inclusive code ranges.
        ranges=re.findall(r'([A-Z]+(?: [A-Z]+)* \d+)\s*[–—-]\s*([A-Z]+(?: [A-Z]+)* \d+)',token)
        if ranges:
            remaining=token
            for start,end in ranges:
                left=re.match(r'(.*?)(\d+)$',start);right=re.match(r'(.*?)(\d+)$',end)
                if left[1]!=right[1]:return 'PREREQUISITE REVIEW REQUIRED'
                matches={k for k,v in catalog_codes.items() if (m:=re.fullmatch(re.escape(left[1])+r'(\d+)',v)) and int(left[2])<=int(m[1])<=int(right[2])}
                if not matches:return 'PREREQUISITE REVIEW REQUIRED'
                required.update(matches)
                remaining=remaining.replace(start,'').replace(end,'')
            if re.sub(r'[\s–—-]','',remaining):return 'PREREQUISITE REVIEW REQUIRED'
        else:return 'PREREQUISITE REVIEW REQUIRED'
    if coreq:
        completed=completed|{code(r['subject_code']) for r in catalog if r['subject_id'] in concurrent}
    return '' if required<=completed else ('CO-REQUISITE REQUIRED' if coreq else 'PREREQUISITE NOT COMPLETED')

def academic_status(student,term,catalog,passed):
    if not term:return student.get('enrollment_type') or 'REGULAR'
    current=(student.get('residency_year',int(student['year_level'][0])),SEMESTERS[term['semester']])
    completed=passed
    behind=any((int(r['year_level'][0]),SEMESTERS.get(r.get('semester_offered'),9))<current and identity(dict(r,program=student['program'])) not in completed for r in catalog)
    return 'IRREGULAR' if behind else 'REGULAR'

def advance_years(term):
    year=int(term['school_year'][:4])
    for student in query_all('SELECT student_id,id_number,year_level,section,progress_school_year FROM students ORDER BY student_id FOR UPDATE WAIT 5'):
        previous=student.get('progress_school_year')
        if previous is not None and year<=previous:continue
        level=min(4,residency(student,term)['residency_year']) if re.fullmatch(r'\d{2}-\d{4}',student.get('id_number','')) else min(4,int(student['year_level'][0])+max(0,year-int(previous or year)))
        section=re.sub(r' [1-4]-',f' {level}-',student['section'])
        execute('UPDATE students SET year_level=:level,section=:section,progress_school_year=:year WHERE student_id=:sid',dict(level=YEARS[level-1],section=section,year=year,sid=student['student_id']))


def scholarship(enrollments,own,all_terms=False):
    from decimal import Decimal,ROUND_HALF_UP
    incomplete=dict(gwa=None,label=None,complete=False)
    if all_terms or not enrollments:return incomplete
    results={r['classroom']['assignment_id']:r['student']['result'] for r in own}
    points=Decimal(0);units=Decimal(0);failed=False
    for enrollment in enrollments:
        result=results.get(enrollment['assignment_id'])
        if enrollment['status']!='PUBLISHED' or not result or result.get('total') is None or result.get('missing') or not result.get('equivalent'):
            return incomplete
        grade=Decimal(str(result['equivalent']));weight=Decimal(str(enrollment['units']))
        if weight<=0:return incomplete
        failed=failed or grade==Decimal('5.00')
        points+=grade*weight;units+=weight
    gwa=(points/units).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    label=None
    if not failed:
        if Decimal('1.00')<=gwa<=Decimal('1.49'):label='University Scholar'
        elif Decimal('1.50')<=gwa<=Decimal('1.75'):label='College Scholar'
    return dict(gwa=f'{gwa:.2f}',label=label,complete=True)
