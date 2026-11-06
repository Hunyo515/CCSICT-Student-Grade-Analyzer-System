"""SRS UI acceptance: populated/empty states, responsive layout, and interactions."""
import json
import logging
from pathlib import Path
import sys
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from srs_fixture import SrsFixture
from audit_fixture import AuditFixture


def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    output=Path('audit/srs-alignment');output.mkdir(exist_ok=True);results=[];errors=[];interactions=[]
    routes={'admin':['/app/admin','/app/admin/analytics','/admin/subjects','/admin/subjects?program=BSDSA','/admin/subjects?q=DSA','/admin/teachers','/admin/students','/admin/classes','/admin/settings'],
            'faculty':['/app/teacher','/app/teacher/class/10','/app/teacher/class/10?tab=weighting','/app/teacher/class/10?tab=class','/app/teacher/analytics','/app/teacher/top-performers','/app/teacher/class/20'],
            'student':['/app/student','/app/student/grades','/app/student/analytics','/app/student/rank','/app/student/join?code=ABC1234567','/student/profile']}
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='msedge',headless=True)
        for fixture_type in (SrsFixture,AuditFixture):
            mode='populated' if fixture_type==SrsFixture else 'empty'
            with fixture_type() as fixture:
                server=make_server('127.0.0.1',0,fixture.app,threaded=True);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                base=f'http://127.0.0.1:{server.server_port}'
                try:
                    for width in ((1440,1024,768,375,320) if mode=='populated' else (1440,375)):
                        for role,paths in routes.items():
                            context=browser.new_context(viewport=dict(width=width,height=960));page=context.new_page()
                            page.on('pageerror',lambda error:errors.append(str(error)))
                            page.on('dialog',lambda dialog:dialog.accept())
                            page.goto(base+'/__audit/login/'+role)
                            for index,path in enumerate(paths):
                                if mode=='empty' and ('/class/' in path or 'code=' in path):continue
                                response=page.goto(base+path,wait_until='networkidle')
                                assert response.status==200,(mode,width,path,response.status)
                                overflow=page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                                if overflow:
                                    page.screenshot(path=str(output/'overflow.png'),full_page=True)
                                    print(page.evaluate('[...document.querySelectorAll("body *")].filter(e=>e.getBoundingClientRect().right>innerWidth+1&&getComputedStyle(e).position!=="fixed").slice(0,10).map(e=>({tag:e.tagName,cls:e.className,width:e.getBoundingClientRect().width,right:e.getBoundingClientRect().right}))'))
                                assert not overflow,(mode,width,path)
                                assert 'Segoe UI' in page.locator('body').evaluate('(e)=>getComputedStyle(e).fontFamily')
                                if mode=='populated' and path=='/app/student':
                                    assert 'Fundamentals of Programming' in page.locator('body').inner_text()
                                    assert page.locator('.srs-table tbody tr').count()==2
                                if mode=='populated' and path=='/app/student/grades':assert 'Grade A' in page.locator('body').inner_text()
                                for form in page.locator('form[method=post],form[method=POST]').all():assert form.locator('input[name=csrf_token]').count()==1,path
                                if mode=='populated' and width in (1440,375):page.screenshot(path=str(output/f'{role}-{width}-{index}.png'),full_page=True)
                                if mode=='populated' and width==1440 and path=='/app/teacher/class/10':
                                    page.get_by_role('button',name='Publish grades',exact=True).click();assert page.locator('dialog.confirm-dialog').is_visible()
                                    page.get_by_role('button',name='Cancel',exact=True).click();page.locator('dialog.confirm-dialog').wait_for(state='detached')
                                    page.get_by_role('button',name='Import CSV',exact=True).click();assert page.locator('#csvImport').is_visible()
                                    interactions.extend(['publication confirmation and cancellation','CSV import panel'])
                                if mode=='populated' and width==1440 and path.endswith('tab=weighting'):
                                    page.locator('.row-menu summary').first.click();assert page.locator('dialog.edit-dialog').is_visible()
                                    page.screenshot(path=str(output/'edit-component-dialog.png'),full_page=True)
                                    page.get_by_role('button',name='Close edit dialog',exact=True).click();interactions.append('component edit dialog')
                                if mode=='populated' and width==375 and path=='/app/teacher':
                                    page.get_by_role('button',name='Open navigation',exact=True).click();assert page.locator('#sidebar').evaluate('(e)=>!e.inert')
                                    page.keyboard.press('Escape');assert page.locator('#sidebar').evaluate('(e)=>e.inert')
                                    interactions.append('mobile navigation open and escape close')
                                if mode=='populated' and path=='/app/teacher/class/20':assert page.locator('input[name^=mark__]:enabled').count()==0
                                results.append(dict(mode=mode,width=width,role=role,path=path,status=response.status,overflow=overflow))
                            context.close()
                finally:server.shutdown();server.server_close();thread.join(timeout=5)
        browser.close()
    (output/'browser-results.json').write_text(json.dumps(dict(results=results,interactions=interactions,errors=errors),indent=2))
    print(json.dumps(dict(page_checks=len(results),interactions=interactions,errors=errors)))
    return bool(errors)


if __name__=='__main__':sys.exit(main())
