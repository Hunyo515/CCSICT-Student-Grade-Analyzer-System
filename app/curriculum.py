"""Program names, legacy aliases, and the retained original curriculum source."""
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / 'data' / 'curricula'
PROGRAM_NAMES = {
    'BSCS': 'Computer Science',
    'BSIT': 'Information Technology',
    'BSIS': 'Information Systems',
    'BSDSA': 'Data Science and Analytics',
    'BLIS': 'Library and Information Science',
}

PROGRAM_ALIASES = {
    'BSCS': ('BSCS','BS Computer Science','Bachelor of Science in Computer Science'),
    'BSIT': ('BSIT','BS Information Technology','Bachelor of Science in Information Technology'),
    'BSIS': ('BSIS','BS Information Systems','Bachelor of Science in Information Systems'),
    'BSDSA': ('BSDSA','BS Data Science','BS Data Science and Analytics','Bachelor of Science in Data Science and Analytics'),
    'BLIS': ('BLIS','Bachelor of Library and Information Science','BS Library and Information Science'),
}

SOURCE_FILES = {program: f'{program.lower()}-2021-2022.json' for program in ('BSCS','BSIT','BSIS','BLIS')}
SOURCE_FILES['BSDSA']='bsdsa-2023-2024.json'


def canonical_program(value):
    value=' '.join((value or '').split()).casefold()
    return next((code for code,aliases in PROGRAM_ALIASES.items()
                 if value in {alias.casefold() for alias in aliases}), None)


def cohort_matches(student, assignment, section):
    """A cohort is a program + year + section, never just a section name."""
    return (canonical_program(student.get('program')) == assignment.get('program')
            and assignment.get('program') in PROGRAM_NAMES
            and student.get('year_level') == assignment.get('year_level')
            and (student.get('section') or '').strip().casefold() == (section or '').strip().casefold())


def source_curriculum(program):
    filename=SOURCE_FILES.get(program)
    if not filename:return None
    return json.loads((DATA_DIR / filename).read_text(encoding='utf-8'))


def curriculum_rows(program):
    source=source_curriculum(program)
    if not source:return []
    rows=[]
    for year,data in enumerate(source['years'],1):
        for semester,term in enumerate(data['semesters'],1):
            for c in term['courses']:
                rows.append(dict(program=program,code=c['code'],name=c['title'],units=int(c['units'].strip('()')),
                    year_level=('1st','2nd','3rd','4th')[year-1]+' Year',
                    semester=term.get('semester',('1st' if semester==1 else '2nd')+' Semester'),
                    lecture=int(c['lecture']) if c['lecture'] else None,
                    lab=int(c['laboratory']) if c['laboratory'] else None,
                    prerequisite=c['prerequisite'] or None,note=c['units'] if c['units'].startswith('(') else None))
    return rows
