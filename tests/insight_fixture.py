"""Synthetic reporting data for deterministic UI checks; no production records."""
from app.insights import build_sections


def sample_sections(term_id=None, *, teacher_id=None, student_id=None):
    sections, enrollments, components, grades = [], [], [], []
    definitions = [(10, 'CS101', 'Introduction to Computing', 'PUBLISHED', 1),
                   (20, 'CS202', 'Data Structures and Algorithms', 'PUBLISHED', 1),
                   (30, 'IT204', 'Database Management Systems', 'IN_PROGRESS', 1),
                   (40, 'CS103', 'Discrete Mathematics', 'DRAFT', 1),
                   (50, 'CS100', 'Programming Fundamentals', 'PUBLISHED', 0)]
    for aid, code, name, status, tid in definitions:
        if term_id is not None and tid != term_id:
            continue
        sections.append(dict(assignment_id=aid, subject_code=code, subject_name=name,
            section='BSCS 2A', status=status, term_id=tid, units=3,
            school_year='2026–2027' if tid else '2025–2026', semester='1st Semester'))
        if student_id is None or status == 'PUBLISHED':
            for offset, name, weight in [(1, 'Practical examinations', 40), (2, 'Projects and laboratory work', 35), (3, 'Quizzes and written exercises', 25)]:
                components.append(dict(assignment_id=aid, component_id=aid+offset,
                    component_name=name, weight_percent=weight, category_id=None))
        for sid in range(3, 15):
            if student_id is not None and sid != student_id:
                continue
            eid=aid*100+sid
            enrollments.append(dict(assignment_id=aid, enrollment_id=eid, student_id=sid,
                                    program='BSCS', full_name=f'Sample student {sid:02d}'))
            if student_id is not None and status != 'PUBLISHED':
                continue
            for offset in (1, 2, 3):
                if aid==40 or (aid==30 and (sid+offset)%3==0) or (aid==20 and sid==14):
                    continue
                value = (68 if aid==20 else 79) + (sid-3)*1.5 + (offset-2)*4
                grades.append(dict(assignment_id=aid, enrollment_id=eid, component_id=aid+offset,
                                   score=min(100,value), max_score=100))
    return build_sections(sections,enrollments,components,[],grades)
