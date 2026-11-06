"""Browser verification of all four curriculum catalogs with isolated fixtures."""
import logging,sys,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from audit_fixture import AuditFixture,all_rows
from app.curriculum import curriculum_rows
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

def rows(program):
    return [dict(subject_id=i,subject_code=r['code'],subject_name=r['name'],units=r['units'],year_level=r['year_level'],semester_offered=r['semester'],program=program,lecture_units=r['lecture'],lab_units=r['lab'],prerequisite_text=r['prerequisite'],units_note=r['note'],is_archived=0,prerequisite_code=None) for i,r in enumerate(curriculum_rows(program),1)]

def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR);errors=[]
    output=Path('audit/program-curricula');output.mkdir(exist_ok=True,parents=True)
    with AuditFixture() as fixture:
        def query(sql,params=None):
            params=params or {}
            if 'from subjects s' in sql.lower() and params.get('program') in ('BSCS','BSIT','BSIS','BLIS'):return rows(params['program'])
            return all_rows(sql,params)
        fixture.stack.enter_context(patch('app.routes.admin.query_all',side_effect=query))
        server=make_server('127.0.0.1',0,fixture.app,threaded=True);threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='msedge',headless=True)
                for width in (1440,375):
                    context=browser.new_context(viewport=dict(width=width,height=1000));page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
                    base=f'http://127.0.0.1:{server.server_port}';page.goto(base+'/__audit/login/admin')
                    for program,count,terms in [('BSCS',57,9),('BSIT',56,9),('BSIS',54,8),('BLIS',57,8)]:
                        page.goto(base+'/app/admin/subjects?program='+program)
                        assert page.locator('#sidebar').count()==1
                        assert page.locator('.curriculum-year tbody tr').count()==count
                        page.get_by_role('button',name='4th Year',exact=True).click()
                        assert page.locator('.curriculum-year:visible').get_attribute('data-group')=='4th Year'
                        page.locator('#catalog-search').fill('no possible course match')
                        assert page.locator('#catalog-empty').is_visible()
                        page.get_by_role('button',name='1st Year',exact=True).click()
                        options=page.locator('.course-options:visible').first
                        options.locator('summary').click()
                        assert options.get_by_role('button',name='Archive').is_visible()
                        options.locator('summary').click()
                        assert page.locator('.curriculum-semester').count()==terms
                        assert page.locator('.curriculum-year').count()==4
                        if program in ('BSCS','BSIT'):assert page.locator('.curriculum-semester h3').filter(has_text='Summer').count()==1
                        page.locator('.curriculum-source-notes summary').click()
                        assert page.locator('.curriculum-source-notes li').count()>0
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                        page.screenshot(path=str(output/f'catalog-{program.lower()}-{width}.png'),full_page=False)
                    context.close()
                browser.close();assert not errors,errors
                print('PASS: four program catalogs, 224 course rows, every year and semester including Summer, source links/notes, edit actions, and desktop/mobile layout.')
        finally:server.shutdown();server.server_close()

if __name__=='__main__':main()
