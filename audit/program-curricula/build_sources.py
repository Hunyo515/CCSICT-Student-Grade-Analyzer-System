"""Build retained curriculum records from visually checked source tables."""
import json,shutil
from pathlib import Path
import pdfplumber

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'app/data/curricula'
YEAR=['First Year','Second Year','Third Year','Fourth Year']
TERMS={'1':'First Semester','2':'Second Semester','S':'Midyear'}
KEYS=['code','title','units','lecture','laboratory','prerequisite']

def base(program,title,track=''):
    return dict(program=program,title=title,school_year='2021-2022',institution='Isabela State University',college='College of Computing Studies, Information and Communication Technology',specialization=track,years=[dict(label=y,semesters=[]) for y in YEAR],notes=[],source_file='ccsict-2021-2022.pdf',source_pages=[])

data={
    'BSIS':base('BSIS','Bachelor of Science in Information Systems','Service Management for Business Process Outsourcing (BPO)'),
    'BSCS':base('BSCS','Bachelor of Science in Computer Science','Data Mining'),
    'BSIT':base('BSIT','Bachelor of Science in Information Technology','Web and Mobile Applications Development'),
    'BLIS':base('BLIS','Bachelor of Library and Information Science'),
}
for line in (Path(__file__).parent/'reviewed-courses.txt').read_text(encoding='utf-8').splitlines():
    if not line:continue
    if line.startswith('@'):
        program,year,semester,page,units,lecture,lab=line[1:].split('|')
        term=dict(label=TERMS[semester],semester='Summer' if semester=='S' else ('1st' if semester=='1' else '2nd')+' Semester',source_page=int(page),courses=[],totals=dict(units=units,lecture=lecture,laboratory=lab),notes=[])
        data[program]['years'][int(year)-1]['semesters'].append(term)
        if int(page) not in data[program]['source_pages']:data[program]['source_pages'].append(int(page))
    else:
        cells=line.split('|');assert len(cells)==6,line
        term['courses'].append(dict(zip(KEYS,cells)))

with pdfplumber.open(r'C:\Users\june\Downloads\BLIS.pdf') as pdf:
    for page_number,page in enumerate(pdf.pages,1):
        for row in page.extract_tables()[0]:
            first=row[0] or ''
            if first in ('FIRST SEMESTER','SECOND SEMESTER'):
                term=dict(label=first.title(),semester=('1st' if first=='FIRST SEMESTER' else '2nd')+' Semester',source_page=page_number,courses=[],notes=[])
                data['BLIS']['years'][page_number-1]['semesters'].append(term)
            elif row[1]=='Total Units':term['totals']=dict(zip(('units','lecture','laboratory'),row[2:5]))
            elif first and row[2] and row[2].strip('()').isdigit():
                term['courses'].append(dict(zip(KEYS,[' '.join((v or '').split()) for v in row])))
data['BLIS'].update(source_file='blis-2021-2022.pdf',source_pages=[1,2,3,4])
data['BSCS']['notes']=[
    'The source includes a third-year Midyear term; it is catalogued under Summer.',
    'The printed second-year first-semester header contains “CS Inst 3: 1 hour lecture; 3 hours lab 2 units” without a course title, row units or prerequisite. It is retained as a source note, not invented as a subject.',
    'NSTP units are printed as (3); the source totals include them. Parentheses are preserved as units notes.',
    'Prerequisites and year-standing requirements are retained as printed, including the fourth-year-standing requirement for third-year Midyear CS Elec 3.',
]
data['BSIS']['notes']=[
    'The source prints NSTP units as (3) and excludes them from semester totals. Parentheses are preserved as units notes.',
    'Similar GE/GEC elective codes with different titles are retained as separate subjects, as printed.',
]
data['BSIT']['notes']=[
    'The source includes a second-year Mid-Year term; it is catalogued under Summer.',
    'IT Inst 3 is titled “Data Science Analytics” in the course table; the summary page calls it “Fundamentals of Data Science Analytics”. The course-table title is retained.',
]
data['BLIS']['notes']=[
    'Blank lecture, laboratory and prerequisite cells are retained as unspecified, including LIS Inst 1.',
    'LIS ICT 221 (Programming Fundamentals 2) is printed in second-year first semester with prerequisite LIS ICT 211, which is printed in the following semester. The sequence is retained as printed.',
    'LIS 411 prerequisites refer to LIS Elec 1 through LIS Elec 7, which are not separate listed subjects in the supplied document. No additional courses are invented.',
    'Printed totals contain discrepancies: third-year second semester states 24 units although its seven listed courses sum to 21; fourth-year laboratory totals do not include all listed laboratory units. The supplied grand total is 165. Catalog totals are calculated from listed course rows.',
    'NSTP units are printed as (3); parentheses are preserved as units notes.',
]
for program,result in data.items():
    result['printed_grand_total']={'BSIS':'156','BSCS':'168','BSIT':'167','BLIS':'165'}[program]
    count=0
    for year in result['years']:
        for term in year['semesters']:
            count+=len(term['courses'])
            actual=sum(int(c['units'].strip('()')) for c in term['courses'])
            if float(term['totals']['units'])!=actual:
                term['notes'].append(f"Source total: {term['totals']['units']} units; listed course rows: {actual} units (including parenthesized NSTP). Source values are retained.")
    (OUT/f'{program.lower()}-2021-2022.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(program,count,'courses;',sum(len(y['semesters']) for y in result['years']),'terms')
shutil.copyfile(r'C:\Users\june\Downloads\BSCS-Curriculum-2021-2022-6.pdf',OUT/'ccsict-2021-2022.pdf')
shutil.copyfile(r'C:\Users\june\Downloads\BLIS.pdf',OUT/'blis-2021-2022.pdf')
