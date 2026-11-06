import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from app.curriculum import DATA_DIR, source_curriculum,curriculum_rows
from audit_fixture import AuditFixture


class CurriculumTests(unittest.TestCase):
    def test_import_matches_every_source_cell(self):
        curriculum = source_curriculum('BSDSA')
        semesters = [s for y in curriculum['years'] for s in y['semesters']]
        self.assertEqual(len(semesters), 8)
        self.assertEqual(sum(len(s['courses']) for s in semesters), 52)
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        with ZipFile(DATA_DIR / 'bsdsa-2023-2024.docx') as doc:
            root = ET.fromstring(doc.read('word/document.xml'))
        tables = root.findall('.//w:body/w:tbl', ns)
        self.assertEqual(len(tables), len(semesters))
        for table, semester in zip(tables, semesters):
            rows = [['\n'.join(''.join(t.text or '' for t in p.findall('.//w:t', ns))
                               for p in cell.findall('w:p', ns))
                     for cell in row.findall('w:tc', ns)] for row in table.findall('w:tr', ns)]
            courses = [[c[k] for k in ('code','title','units','lecture','laboratory','prerequisite')]
                       for c in semester['courses']]
            self.assertEqual(courses, rows[1:-1])
            self.assertEqual([semester['totals'][k] for k in ('units','lecture','laboratory')], rows[-1][2:5])

    def test_source_ambiguities_are_preserved(self):
        curriculum = source_curriculum('BSDSA')
        courses = [c for y in curriculum['years'] for s in y['semesters'] for c in s['courses']]
        self.assertEqual(sum(c['code'] == 'DSA 315' for c in courses), 2)
        self.assertEqual(sum(c['units'] == '(3)' for c in courses), 2)
        self.assertTrue(any('DSA 412' in note and 'DSA 421' in note for note in curriculum['notes']))

    def test_legacy_subject_bookmarks_open_srs_catalog(self):
        with AuditFixture() as fixture:
            client = fixture.client('admin')
            response = client.get('/admin/subjects',follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'curriculum-folder',response.data)
            for program in ('BSCS','BSIT','BSIS','BLIS','BSDSA'):
                response = client.get('/admin/subjects?program='+program,follow_redirects=True)
                self.assertEqual(response.status_code, 200)
            self.assertIn(b'Add subject', response.data)
            self.assertEqual(client.get('/admin/subjects?program=UNKNOWN',follow_redirects=True).status_code, 404)
            self.assertEqual(client.get('/admin/subjects/curriculum').status_code,302)
            download = client.get('/admin/subjects/curriculum/bsdsa/source')
            self.assertEqual(download.status_code, 200)
            self.assertTrue(download.data.startswith(b'PK'))
            download.close()

    def test_subject_catalog_groups_curriculum_by_year_and_semester_with_crud(self):
        from scripts.migrate_curriculum_workflow import import_rows
        rows=[dict(subject_id=i,subject_code=r['code'],subject_name=r['name'],units=r['units'],
              year_level=r['year_level'],semester_offered=r['semester'],program='BSDSA',
              lecture_units=r['lecture'],lab_units=r['lab'],prerequisite_text=r['prerequisite'],
              units_note=r['note'],is_archived=0,prerequisite_code=None) for i,r in enumerate(import_rows(),1)]
        with AuditFixture() as fixture:
            client=fixture.client('admin')
            with patch('app.routes.admin.query_all',return_value=rows):
                response=client.get('/app/admin/subjects?program=BSDSA')
            self.assertEqual(response.status_code,200)
            self.assertIn(b'Fundamentals of Programming',response.data)
            self.assertIn(b'1st Year',response.data)
            self.assertIn(b'4th Year',response.data)
            self.assertIn(b'2nd Semester',response.data)
            self.assertEqual(response.data.count(b'>Edit</a>'),52)

    def test_source_is_admin_only(self):
        with AuditFixture() as fixture:
            for role in ('faculty','student'):
                self.assertEqual(fixture.client(role).get('/admin/subjects/curriculum/bsdsa/source').status_code,302)

    def test_all_four_curricula_include_every_term_and_source_specific_fields(self):
        for program,count,terms in [('BSCS',57,9),('BSIT',56,9),('BSIS',54,8),('BLIS',57,8)]:
            source=source_curriculum(program);rows=curriculum_rows(program)
            self.assertEqual(len(rows),count)
            self.assertEqual(sum(len(y['semesters']) for y in source['years']),terms)
            self.assertTrue((DATA_DIR/source['source_file']).is_file())
            self.assertEqual({r['year_level'] for r in rows},{'1st Year','2nd Year','3rd Year','4th Year'})
        self.assertEqual(sum(r['semester']=='Summer' for r in curriculum_rows('BSCS')),3)
        self.assertEqual(sum(r['semester']=='Summer' for r in curriculum_rows('BSIT')),2)
        courses={r['code']:r for r in curriculum_rows('BLIS')}
        self.assertEqual(courses['LIS ICT 221']['prerequisite'],'LIS ICT 211')
        self.assertEqual(courses['LIS ICT 221']['semester'],'1st Semester')
        self.assertIsNone(courses['LIS Inst 1']['lecture'])
        self.assertEqual(courses['LIS 412']['lab'],3)
        self.assertEqual(courses['NSTP 1']['note'],'(3)')
        self.assertEqual(sum(r['units'] for r in curriculum_rows('BSCS')),168)
        self.assertEqual(sum(r['units'] for r in curriculum_rows('BSIT')),167)

    def test_import_is_idempotent_and_keeps_cross_program_codes(self):
        from scripts.import_program_curricula import plan,PROGRAMS
        rows=[r for program in PROGRAMS for r in curriculum_rows(program)]
        self.assertEqual(len(plan([])[0]),224)
        existing=[dict(program=r['program'],subject_code=r['code'],subject_name=r['name'],units=r['units'],year_level=r['year_level'],semester_offered=r['semester'],lecture_units=r['lecture'],lab_units=r['lab'],prerequisite_text=r['prerequisite'],units_note=r['note']) for r in rows]
        self.assertEqual(plan(existing),([],[]))
        self.assertEqual(sum(r['subject_code']=='GEC 4' for r in existing),4)
        changed=[dict(existing[0],units=99),*existing[1:]]
        pending,conflicts=plan(changed)
        self.assertFalse(pending);self.assertEqual(conflicts[0]['field'],'units')

    def test_imported_program_pages_and_pdf_sources(self):
        with AuditFixture() as fixture:
            client=fixture.client('admin')
            for program in ('BSCS','BSIT','BSIS','BLIS'):
                rows=[dict(subject_id=i,subject_code=r['code'],subject_name=r['name'],units=r['units'],year_level=r['year_level'],semester_offered=r['semester'],program=program,lecture_units=r['lecture'],lab_units=r['lab'],prerequisite_text=r['prerequisite'],units_note=r['note'],is_archived=0,prerequisite_code=None) for i,r in enumerate(curriculum_rows(program),1)]
                with patch('app.routes.admin.query_all',return_value=rows):response=client.get('/app/admin/subjects?program='+program)
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.data.count(b'>Edit</a>'),len(rows))
                self.assertIn(b'2021-2022',response.data)
                self.assertIn(b'Curriculum source notes',response.data)
                download=client.get('/admin/subjects/curriculum/'+program.lower()+'/source')
                self.assertEqual(download.status_code,200);self.assertTrue(download.data.startswith(b'%PDF'));download.close()
            for role in ('faculty','student'):
                self.assertEqual(fixture.client(role).get('/admin/subjects/curriculum/bscs/source').status_code,302)


if __name__ == '__main__':
    unittest.main()
