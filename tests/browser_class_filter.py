"""Read-only checks for Create Class program/year/semester filtering."""
import logging
from pathlib import Path
import sys
import threading
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_fixture import AuditFixture, all_rows
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server


def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    subjects = [dict(subject_id=i, subject_code=f'TEST{i}', subject_name=f'Year {year} subject', program=program, year_level=year, semester_offered=semester)
                for i, (program, year, semester) in enumerate([
                    ('BSCS', '1st Year', '1st Semester'),
                    ('BSCS', '4th Year', '1st Semester'),
                    ('BSCS', '4th Year', '2nd Semester'),
                    ('BSIT', '4th Year', '1st Semester'),
                    ('BSCS', '3rd Year', '1st Semester')], 101)]
    terms = [dict(term_id=i, school_year='2026-2027', semester=semester, is_active=i==1)
             for i, semester in ((1, '1st Semester'), (2, '2nd Semester'))]
    def rows(sql, params=None):
        if 'FROM teachers t' in sql:return [dict(teacher_id=7,full_name='Test Faculty')]
        return subjects if 'FROM subjects WHERE' in sql else all_rows(sql, params)
    output=Path('audit/class-filter');output.mkdir(exist_ok=True)
    errors=[]
    with AuditFixture() as fixture, patch('app.routes.admin.query_all', side_effect=rows), patch('app.academic.offering_terms', return_value=terms), patch('app.routes.admin._offered_classes',return_value=[dict(assignment_id=900,subject_id=102,term_id=1,teacher_id=None,teacher_name='Faculty not yet assigned',program='BSCS',subject_code='TEST102',subject_name='Year 4 subject',section='BSCS 4-1',student_count=2,status='DRAFT')]):
        server=make_server('127.0.0.1',0,fixture.app,threaded=True)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='msedge',headless=True)
                page=browser.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                base=f'http://127.0.0.1:{server.server_port}'
                page.goto(base+'/__audit/login/admin')
                for width in (1440,375,320):
                    page.set_viewport_size(dict(width=width,height=1000))
                    page.goto(base+'/admin/classes')
                    assert page.locator('td').filter(has_text='Faculty not yet assigned').count()==1
                    assignment=page.locator('form[action$="/900/faculty"]')
                    assert assignment.get_by_role('button',name='Assign faculty').is_visible()
                    assignment.locator('[name=teacher_id]').select_option('7')
                    page.select_option('#class-program','BSCS')
                    assert page.locator('#class-subject option[data-program]:enabled').count()==0
                    page.select_option('#class-year','4')
                    assert page.locator('#class-subject option[data-program]:enabled').evaluate_all('(items)=>items.map(e=>e.value)')==['102']
                    page.select_option('#class-subject','102')
                    assert page.locator('#class-section').get_attribute('placeholder')=='BSCS 4-1'
                    page.select_option('#class-year','1')
                    assert page.locator('#class-subject').input_value()==''
                    assert page.locator('#class-subject option[data-program]:enabled').evaluate_all('(items)=>items.map(e=>e.value)')==['101']
                    page.select_option('#class-year','4');page.select_option('#class-term','2')
                    assert page.locator('#class-subject option[data-program]:enabled').evaluate_all('(items)=>items.map(e=>e.value)')==['103']
                    page.select_option('#class-program','BSIT')
                    assert page.locator('#class-subject option[data-program]:enabled').count()==0
                    assert 'No subjects available' in page.locator('#class-subject option').first.inner_text()
                    page.select_option('#class-term','1')
                    assert page.locator('#class-subject option[data-program]:enabled').evaluate_all('(items)=>items.map(e=>e.value)')==['104']
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    page.screenshot(path=str(output/f'classes-{width}.png'),full_page=True)
                    page.goto(base+'/admin/classes?subject_id=102&program=BSCS')
                    assert page.locator('#class-year').input_value()=='4'
                    assert page.locator('#class-subject').input_value()=='102'
                browser.close()
                assert not errors,errors
                print('PASS: year/program/semester filters, selection clearing, empty results, curriculum links, and responsive layout at 1440/375/320px.')
        finally:
            server.shutdown();server.server_close()


if __name__=='__main__':main()
