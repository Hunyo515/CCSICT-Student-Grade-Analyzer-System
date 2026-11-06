"""Read-only populated desktop/mobile QA for the rebuilt application."""
import json
import logging
from pathlib import Path
import sys
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from rebuild_fixture import RebuildFixture,A


def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    output=Path('audit/rebuild');output.mkdir(exist_ok=True);results=[];errors=[]
    routes={
        'admin':['/workspace/overview','/admin/subjects','/admin/subjects?program=BSDSA','/workspace/sections','/admin/students','/admin/teachers','/admin/classes','/workspace/review','/workspace/review/10','/workspace/reports','/admin/settings'],
        'faculty':['/workspace/classes','/workspace/class/10','/workspace/class/10?tab=setup','/workspace/class/10?tab=analytics','/workspace/class/10?tab=details','/workspace/classes?view=submissions'],
        'student':['/workspace/subjects','/workspace/subjects?view=history','/workspace/join?code=ABC1234567','/student/profile'],
    }
    with RebuildFixture() as fixture:
        server=make_server('127.0.0.1',0,fixture.app,threaded=True);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='msedge',headless=True)
                for width in (1440,768,375,320):
                    for role,paths in routes.items():
                        context=browser.new_context(viewport=dict(width=width,height=960));page=context.new_page()
                        page.on('pageerror',lambda error:errors.append(str(error)))
                        page.goto(f'http://127.0.0.1:{server.server_port}/__audit/login/{role}')
                        for index,path in enumerate(paths):
                            response=page.goto(f'http://127.0.0.1:{server.server_port}'+path,wait_until='networkidle')
                            assert response.status==200,(role,path,response.status)
                            overflow=page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                            if overflow:
                                page.screenshot(path=str(output/'overflow.png'),full_page=True)
                                print(page.evaluate('[...document.querySelectorAll("body *")].filter(e=>e.getBoundingClientRect().right>innerWidth+1&&getComputedStyle(e).position!=="fixed").slice(0,12).map(e=>({tag:e.tagName,cls:e.className,width:e.getBoundingClientRect().width,right:e.getBoundingClientRect().right}))'))
                            assert not overflow,(width,path,'horizontal page overflow')
                            assert 'Segoe UI' in page.locator('body').evaluate('(e)=>getComputedStyle(e).fontFamily')
                            if width in (1440,375):page.screenshot(path=str(output/f'{role}-{width}-{index}.png'),full_page=True)
                            results.append(dict(role=role,width=width,path=path,status=response.status,overflow=overflow))
                        context.close()
                # Confirm locked gradebook exposes no editable score or release action.
                A['status']='SUBMITTED'
                context=browser.new_context();page=context.new_page();page.goto(f'http://127.0.0.1:{server.server_port}/__audit/login/faculty')
                page.goto(f'http://127.0.0.1:{server.server_port}/workspace/class/10')
                assert page.locator('input[name^=mark__]:enabled').count()==0
                assert page.get_by_role('button',name='Save and release',exact=True).count()==0
                context.close();A['status']='IN_PROGRESS'
                context=browser.new_context();page=context.new_page();page.goto(f'http://127.0.0.1:{server.server_port}/login/faculty')
                page.locator('#password').fill('ExamplePassword')
                page.get_by_role('button',name='Show password',exact=True).click()
                assert page.locator('#password').get_attribute('type')=='text'
                page.get_by_role('button',name='Hide password',exact=True).click()
                assert page.locator('#password').get_attribute('type')=='password'
                page.screenshot(path=str(output/'login.png'),full_page=True)
                context.close();browser.close()
        finally:server.shutdown();server.server_close();thread.join(timeout=5)
    (output/'browser-results.json').write_text(json.dumps(dict(results=results,errors=errors),indent=2))
    print(json.dumps(dict(page_checks=len(results),extra_checks=['locked gradebook','show/hide password'],errors=errors)))
    return bool(errors)


if __name__=='__main__':sys.exit(main())
