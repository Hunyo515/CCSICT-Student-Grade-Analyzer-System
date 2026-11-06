"""Read-only responsive faculty teaching-load panel checks."""
import logging
import re
from pathlib import Path
import sys
import threading
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audit_fixture import AuditFixture,all_rows,one,TERM
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from test_faculty_classes import TEACHER,CLASS


def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    output=Path('audit/faculty-load');output.mkdir(exist_ok=True);errors=[]
    def lookup(sql,params=None):
        if 'FROM teachers t JOIN users' in sql:return TEACHER if (params or {}).get('id')==2 else None
        if 'WHERE ts.assignment_id=:id' in sql:return dict(CLASS,teacher_id=2,teacher_name=TEACHER['full_name'])
        return one(sql,params)
    def rows(sql,params=None):
        if 'AS class_count' in sql:return [dict(TEACHER,email='test.faculty@isu.edu.ph',class_count=2),dict(TEACHER,teacher_id=3,full_name='Unassigned Faculty',class_count=0,email='other.faculty@isu.edu.ph')]
        if 'WHERE ts.teacher_id=:teacher' in sql:return [CLASS,dict(CLASS,assignment_id=11,section='BSCS 4-2',student_count=2)]
        if 'FROM enrollments e JOIN students' in sql:return [dict(id_number='26-0001',full_name='Test Student',program='BSCS',year_level='4th Year')]
        if 'FROM teachers t' in sql:return [TEACHER]
        return all_rows(sql,params)
    with AuditFixture() as fixture,patch('app.routes.admin.query_one',side_effect=lookup),patch('app.routes.admin.query_all',side_effect=rows):
        server=make_server('127.0.0.1',0,fixture.app,threaded=True)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='msedge',headless=True)
                for width in (1440,768,375,320):
                    context=browser.new_context(viewport=dict(width=width,height=900))
                    page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                    base=f'http://127.0.0.1:{server.server_port}'
                    page.goto(base+'/__audit/login/admin');page.goto(base+'/admin/teachers?term_filter=1')
                    link=page.locator('[data-faculty-load]')
                    assert '2 classes' in link.inner_text()
                    assert page.get_by_text('Advanced Computing',exact=True).count()==0
                    assert page.get_by_text('No assigned classes',exact=True).is_visible()
                    before=page.url;link.click()
                    panel=page.locator('#faculty-load-panel')
                    panel.locator('.faculty-class-card').first.wait_for()
                    assert page.url==before
                    assert panel.locator('.faculty-class-card').count()==2
                    assert panel.get_by_text('4th Year',exact=True).count()==2
                    assert panel.get_by_text('5',exact=True).count()==1
                    assert page.evaluate('document.body.style.overflow')=='hidden'
                    rect=panel.bounding_box()
                    assert abs(rect['x']+rect['width']-width)<1 and rect['height']==900
                    if width<=600:assert rect['x']==0 and rect['width']==width
                    assert panel.evaluate('(e)=>e.scrollWidth<=e.clientWidth')
                    page.screenshot(path=str(output/f'panel-{width}.png'),full_page=True)
                    page.keyboard.press('Escape')
                    assert not panel.is_visible()
                    assert link.evaluate('(e)=>e===document.activeElement')
                    link.click();panel.locator('.faculty-class-card').first.wait_for()
                    panel.get_by_role('button',name='Close assigned classes').click()
                    assert not panel.is_visible()
                    if width==1440:
                        page.route(re.compile(r'/admin/teachers/2/classes.*panel=1'),lambda route:route.fulfill(status=503,body='Unavailable'),times=1)
                        link.click()
                        panel.get_by_role('alert').wait_for()
                        assert panel.get_by_role('link',name='Open full page').is_visible()
                        panel.get_by_role('button',name='Try again').click()
                        panel.locator('.faculty-class-card').first.wait_for()
                        panel.get_by_role('button',name='Close assigned classes').click()
                    # Read-only class details preserve the selected class's term.
                    link.click();panel.get_by_role('link',name='View Class',exact=True).first.click()
                    page.wait_for_url('**/admin/classes/10?term_filter=1')
                    assert page.get_by_role('heading',name='Class details',exact=True).is_visible()
                    assert page.get_by_text('Test Student',exact=True).is_visible()
                    page.goto(base+'/admin/teachers?term_filter=all')
                    assert 'term_filter=all' in page.locator('[data-faculty-load]').get_attribute('href')
                    page.locator('[data-faculty-load]').click()
                    page.locator('#faculty-load-panel').get_by_text('All school terms',exact=False).wait_for()
                    page.keyboard.press('Escape')
                    # Empty faculty uses a preselected teacher in Create Class.
                    page.get_by_role('link',name='Assign Class',exact=True).click()
                    page.wait_for_url('**/admin/classes?teacher_id=3&term_filter=all')
                    context.close()
                browser.close();assert not errors,errors
                print('PASS: counts, lazy teaching-load details, desktop side panel/mobile full screen, focus/Escape/close, term scope, class roster, and assignment links.')
        finally:server.shutdown();server.server_close()


if __name__=='__main__':main()
