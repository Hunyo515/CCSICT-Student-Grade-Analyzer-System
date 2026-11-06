"""Isolated UI checks for student/admin residency and class workflows."""
import logging,sys,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright
from PIL import Image
from audit_fixture import PROFILE,TERM,one,all_rows
from test_flexible_grading import FlexibleFixture

PERSON=dict(PROFILE,id_number='22-1105',year_level='4th Year',section='BSCS 4-1',first_name='Audit',middle_name='',last_name='Student',age=22)
TEACHERS=[dict(teacher_id=2,user_id=2,program='BSCS',full_name='CS faculty'),dict(teacher_id=3,user_id=4,program='BSIT',full_name='IT faculty')]
SUBJECT=dict(subject_id=101,subject_code='CS 111',subject_name='Programming',program='BSCS',year_level='1st Year',semester_offered='1st Semester',is_archived=0)

def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR);output=Path('audit/residency-workflow');output.mkdir(parents=True,exist_ok=True)
    with FlexibleFixture() as f:
        f.app.instance_path=f.tmp;photos=Path(f.tmp)/'profile-photos';photos.mkdir();Image.new('RGB',(100,100),'#658677').save(photos/'3.jpg')
        def rows(sql,params=None):
            if 'OFFSET' in sql and 'FROM students s' in sql:return [dict(PERSON)]
            if 'FROM teachers t' in sql:return TEACHERS
            if 'FROM subjects WHERE' in sql:return [SUBJECT]
            return all_rows(sql,params)
        def query(sql,params=None):
            if 'COUNT(*) AS n' in sql:return {'n':1}
            if 'FROM students' in sql:return dict(PERSON)
            return one(sql,params)
        f.stack.enter_context(patch('app.routes.admin.query_all',side_effect=rows));f.stack.enter_context(patch('app.routes.admin.query_one',side_effect=query))
        f.stack.enter_context(patch('app.routes.admin._offered_classes',return_value=[dict(SUBJECT,assignment_id=1,teacher_id=2,term_id=1,status='DRAFT',section='BSCS 1-1',teacher_name='CS faculty',student_count=0)]))
        server=make_server('127.0.0.1',0,f.app,threaded=True);threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='msedge',headless=True);errors=[]
                for width in (1440,375):
                    context=browser.new_context(viewport=dict(width=width,height=1000));page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));base=f'http://127.0.0.1:{server.server_port}'
                    page.goto(base+'/register/faculty');assert page.locator('.password-toggle').count()==2
                    page.locator('#password').fill('Password123!');page.get_by_role('button',name='Show password',exact=True).first.click();assert page.locator('#password').get_attribute('type')=='text'
                    page.screenshot(path=str(output/f'faculty-register-{width}.png'),full_page=True)
                    page.goto(base+'/__audit/login/admin');page.goto(base+'/admin/students')
                    assert page.locator('.data-table thead th').all_text_contents()==['','Student ID ↕','Name ↕','Program','Year level','Section','Status']
                    assert page.locator('.directory-name img').is_visible()
                    page.locator('.directory-name').click()
                    assert page.get_by_text('5th Year',exact=True).is_visible()
                    assert page.locator('.student-profile-photo').is_visible()
                    page.get_by_role('button',name='Edit record',exact=True).click();assert page.locator('#editStudentId').input_value()=='22-1105'
                    page.locator('#editStudentModal .modal-close').click()
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    page.screenshot(path=str(output/f'admin-profile-{width}.png'),full_page=True)
                    page.goto(base+'/admin/classes');page.select_option('#class-program','BSCS');page.select_option('#class-year','1')
                    assert page.locator('#class-teacher option[value="2"]').is_enabled()
                    assert page.locator('#class-teacher option[value="3"]').evaluate('(option)=>option.disabled && option.hidden')
                    assert page.get_by_role('cell',name='In process',exact=True).is_visible()
                    page.goto(base+'/__audit/login/faculty');page.goto(base+'/app/teacher/classes?term_filter=1')
                    assert page.locator('.class-folder').count()>0
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    page.screenshot(path=str(output/f'class-folders-{width}.png'),full_page=True)
                    context.close()
                browser.close();assert not errors,errors
                print('PASS: faculty eye toggles and responsive registration, admin photo/profile/edit flow, program-matched faculty, class status and folders at desktop/mobile widths.')
        finally:server.shutdown();server.server_close()
if __name__=='__main__':main()
