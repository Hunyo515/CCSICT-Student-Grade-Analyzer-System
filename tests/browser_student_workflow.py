"""Desktop/mobile checks using isolated accounts and curriculum fixtures."""
import sys,threading,logging
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright
from srs_fixture import SrsFixture
from audit_fixture import PROFILE

def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    output=Path('audit/student-workflow');output.mkdir(parents=True,exist_ok=True)
    with SrsFixture() as f:
        person=dict(PROFILE,program='BSCS',year_level='2nd Year',section='BSCS 2-1')
        f.stack.enter_context(patch('app.routes.student.get_student',return_value=person))
        def offerings(term,program,year,section):
            return [dict(assignment_id=i,subject_id=i,subject_code='CS '+str(i),subject_name=name,units=3,year_level=year,section=section,teacher_name='Test faculty',prerequisite_text=prerequisite,status='DRAFT') for i,name,prerequisite in [(111,'Completed subject',''),(211,'Restricted subject','CS 112'),(212,'Available subject','')]]
        catalog=[dict(subject_id=i,subject_code='CS '+str(i),subject_name=name,program='BSCS',year_level='1st Year',semester_offered='1st Semester') for i,name in [(111,'Completed subject'),(112,'Prerequisite subject')]]
        f.stack.enter_context(patch('app.routes.university.offerings',side_effect=offerings))
        f.stack.enter_context(patch('app.routes.university.current_enrollments',return_value=[]))
        f.stack.enter_context(patch('app.student_progress.curriculum',return_value=catalog))
        f.stack.enter_context(patch('app.student_progress.passed_subjects',return_value={('BSCS','CS111','completed subject')}))
        server=make_server('127.0.0.1',0,f.app,threaded=True);threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='msedge',headless=True)
                errors=[]
                for width in (1440,375):
                    context=browser.new_context(viewport=dict(width=width,height=1000));page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                    base=f'http://127.0.0.1:{server.server_port}'
                    for path in ('/register','/register/faculty'):
                        page.goto(base+path);assert page.locator('form.login-form').is_visible()
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                        page.screenshot(path=str(output/(path.replace('/','-')+f'-{width}.png')),full_page=True)
                    page.goto(base+'/__audit/login/student');page.goto(base+'/app/student/grades')
                    assert page.get_by_role('heading',name='Enrolled subjects').is_visible()
                    assert page.get_by_role('heading',name='COMPONENT BREAKDOWN').count()==0
                    page.locator('a[href*="assignment_id=20"]').click()
                    assert page.get_by_role('heading',name='COMPONENT BREAKDOWN').is_visible()
                    page.goto(base+'/student/profile')
                    assert page.get_by_role('heading',name='Enrolled subjects').count()==0
                    assert page.get_by_text('IRREGULAR',exact=True).is_visible()
                    page.goto(base+'/university/enlistme')
                    assert page.locator('#enlist-class-111').is_disabled()
                    assert page.locator('#enlist-class-211').is_disabled()
                    assert page.locator('#enlist-class-212').is_enabled()
                    page.select_option('#enlist-year',label='1st Year');page.wait_for_load_state();page.select_option('#enlist-section',label='BSCS 1-1');page.wait_for_load_state()
                    assert page.locator('legend').inner_text()=='1st Year subjects'
                    page.locator('#enlist-class-212').check();assert page.locator('#enlist-save').is_enabled()
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    page.screenshot(path=str(output/f'enlist-{width}.png'),full_page=True)
                    context.close()
                browser.close();assert not errors,errors
                print('PASS: desktop/mobile registration, subject navigation, read-only profile status, year filter, passed/prerequisite disabled checkboxes, selection, no JS errors or overflow.')
        finally:server.shutdown();server.server_close()
if __name__=='__main__':main()
