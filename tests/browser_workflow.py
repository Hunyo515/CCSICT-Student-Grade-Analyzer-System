"""Read-only browser checks with synthetic class and roster data."""
import json
import logging
from pathlib import Path
import sys
import threading
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from audit_fixture import AuditFixture, all_rows, one


def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    output = Path('audit/workflow'); output.mkdir(exist_ok=True)
    subjects = all_rows('SELECT * FROM subjects s', {'program': 'BSDSA'})
    assignment = dict(assignment_id=10, subject_id=1001, term_id=1, program='BSDSA',
        year_level='1st Year', section='1A', status='DRAFT', teacher_name='Test Teacher',
        subject_code=subjects[0]['subject_code'], subject_name=subjects[0]['subject_name'], student_count=0)
    students = [dict(student_id=i, id_number=f'TEST-{i}', full_name=f'Test Student {i}',
        program='BSDSA', year_level='1st Year', section='1A') for i in (1, 2)]
    def query_all(sql, params=None):
        if 'FROM subjects WHERE' in sql: return subjects
        if 'FROM teachers t' in sql: return [dict(teacher_id=2, full_name='Test Teacher')]
        return all_rows(sql, params)
    def query_one(sql, params=None):
        if 'SELECT * FROM subjects' in sql: return subjects[0]
        return one(sql, params)
    results=[]; errors=[]
    with AuditFixture() as fixture, patch('app.routes.admin.query_all', side_effect=query_all), \
            patch('app.routes.admin.query_one', side_effect=query_one), \
            patch('app.routes.admin._offered_classes', return_value=[assignment]), \
            patch('app.routes.admin._enrollment_data', return_value=(students, [], set())):
        server=make_server('127.0.0.1',0,fixture.app,threaded=True)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='msedge',headless=True)
                page=browser.new_page()
                page.on('pageerror',lambda error: errors.append(str(error)))
                base=f'http://127.0.0.1:{server.server_port}'
                page.goto(base+'/__audit/login/admin')
                for width in (1440,375,320):
                    page.set_viewport_size(dict(width=width,height=960))
                    for path in ('/admin/subjects/new?program=BSDSA','/admin/subjects/1001',
                                 '/admin/classes','/admin/students/assign?assignment_id=10'):
                        response=page.goto(base+path)
                        assert response.status==200, (path,response.status)
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'), (path,width)
                        assert 'Segoe UI' in page.locator('body').evaluate('(e)=>getComputedStyle(e).fontFamily')
                        if '/classes' in path:
                            page.locator('#class-program').select_option('BSCS')
                            assert page.locator('#class-subject option[data-program]:enabled').count()==0
                            page.locator('#class-program').select_option('BSDSA')
                            assert page.locator('#class-subject option[data-program]:enabled').count()==52
                        if '/students/assign' in path:
                            assert page.get_by_role('button',name='Enroll 2 students',exact=True).is_visible()
                            assert page.locator('input[name=preview_token]').input_value()
                            page.locator('summary').click()
                            assert page.locator('#reason').is_visible()
                        if width in (1440,375):
                            page.screenshot(path=str(output/f'{width}-{len(results)}.png'),full_page=True)
                        results.append(dict(width=width,path=path,status=response.status))
                browser.close()
        finally:
            server.shutdown();server.server_close();thread.join(timeout=5)
    (output/'results.json').write_text(json.dumps(dict(results=results,errors=errors),indent=2))
    print(json.dumps(dict(checks=len(results),errors=errors)))
    return bool(errors)


if __name__=='__main__': sys.exit(main())
