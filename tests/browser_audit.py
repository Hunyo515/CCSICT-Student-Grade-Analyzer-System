"""Real Edge browser audit against isolated SQL fixtures, never production data."""
import json
import sys
import threading
import time
import logging
logging.getLogger("werkzeug").setLevel(logging.ERROR)
from pathlib import Path
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audit_fixture import AuditFixture, PopulatedAuditFixture


def main():
    results=[];errors=[]
    populated="--populated" in sys.argv
    with (PopulatedAuditFixture() if populated else AuditFixture()) as fixture:
        server=make_server('127.0.0.1',0,fixture.app,threaded=True)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='msedge',headless=True)
                context=browser.new_context(viewport={'width':1440,'height':900})
                page=context.new_page()
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('console',lambda msg: errors.append(msg.text) if msg.type=='error' and ('Content Security Policy' in msg.text or 'Refused to' in msg.text) else None)
                routes={role:[r.rule for r in fixture.app.url_map.iter_rules() if r.endpoint.startswith(role+'.') and 'GET' in r.methods and not r.arguments and r.endpoint not in ('faculty.grade_export','faculty.csv_preview','admin.curriculum_source')] for role in ('admin','faculty','student')}
                if populated: routes.pop('admin')
                routes['public']=['/','/login/admin','/login/faculty','/login/student','/register','/forgot-password/student','/does-not-exist']
                for width in (1440,375,320):
                    page.set_viewport_size({'width':width,'height':900 if width==1440 else 812})
                    for role,paths in routes.items():
                        context.clear_cookies()
                        if role!='public': page.goto(base+'/__audit/login/'+role)
                        for path in paths:
                            start=time.perf_counter()
                            response=page.goto(base+path,wait_until='networkidle')
                            overflow=page.evaluate('document.documentElement.scrollWidth > innerWidth + 1')
                            results.append(dict(width=width,path=path,status=response.status,overflow=overflow,seconds=round(time.perf_counter()-start,3),overflow_elements=page.evaluate('Array.from(document.querySelectorAll("body *")).filter(e=>e.getBoundingClientRect().right>innerWidth+1 && getComputedStyle(e).position!=="fixed").slice(0,8).map(e=>({tag:e.tagName,cls:e.className}))') if overflow else []))
                            if path in ('/register','/admin/dashboard','/student/dashboard','/faculty/dashboard') and width in (1440,375):
                                page.screenshot(path=f'audit/{width}-{path.strip("/").replace("/","-")}.png',full_page=True)
                            # Local rendered links must resolve to a registered route or static asset.
                            for href in page.locator('a[href]').evaluate_all('(els)=>els.map(e=>e.getAttribute("href"))'):
                                if not href.startswith('/') or href.startswith('//'):continue
                                from urllib.parse import urlsplit
                                try: fixture.app.url_map.bind('localhost').match(urlsplit(href).path,method='GET')
                                except Exception as e:errors.append(f'Broken route link {path}: {href} ({type(e).__name__})')
                if populated:
                    from audit_fixture import ASSIGNMENT
                    original=ASSIGNMENT['subject_name']
                    ASSIGNMENT['subject_name']="');window.__xss=1;//"
                    try:
                        context.clear_cookies();page.goto(base+'/__audit/login/faculty')
                        page.goto(base+'/faculty/grade-entry')
                        page.once('dialog',lambda dialog:dialog.dismiss())
                        page.get_by_role('button',name='Publish Grades',exact=True).click()
                        assert page.evaluate('window.__xss || 0') == 0
                        results.append(dict(condition='confirmation-injection',status=200))
                    finally:ASSIGNMENT['subject_name']=original
                # Exercise actual modal/tab UI and browser validation at phone width.
                context.clear_cookies();page.goto(base+'/__audit/login/admin')
                page.goto(base+'/admin/students')
                page.get_by_role('button',name='Add Student',exact=True).first.click()
                page.locator('#addStudentModal input[name="first_name"]').fill('Audit')
                assert page.locator('#addStudentModal input[name="email"]').evaluate('(e)=>e.checkValidity()') is False
                page.locator('#addStudentModal').screenshot(path='audit/mobile-student-form.png')
                page.goto(base+'/admin/settings')
                page.get_by_role('button',name='General',exact=True).click()
                assert page.locator('input[name="current_password"]').is_visible()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                results.append(dict(condition='mobile-modal-and-settings',status=200))
                # Network throttling applies to a real browser with fresh context/cache.
                context.clear_cookies();page.set_viewport_size({'width':375,'height':812})
                cdp=context.new_cdp_session(page)
                cdp.send('Network.enable')
                cdp.send('Network.setCacheDisabled',{'cacheDisabled':True})
                cdp.send('Network.emulateNetworkConditions',{'offline':False,'latency':400,'downloadThroughput':50000,'uploadThroughput':20000})
                start=time.perf_counter();response=page.goto(base+'/register',wait_until='networkidle',timeout=60000)
                results.append(dict(condition='slow-network',path='/register',status=response.status,seconds=round(time.perf_counter()-start,3)))
                cdp.send('Network.emulateNetworkConditions',{'offline':True,'latency':0,'downloadThroughput':0,'uploadThroughput':0})
                try:
                    page.goto(base+'/login/student',timeout=10000)
                    errors.append('Offline navigation unexpectedly succeeded')
                except Exception:results.append(dict(condition='offline',result='browser reports connection failure; no false success'))
                browser.close()
        finally:
            server.shutdown();server.server_close();thread.join(timeout=5)
    Path('audit/browser-populated-results.json' if populated else 'audit/browser-results.json').write_text(json.dumps({'results':results,'errors':errors},indent=2))
    failures=[r for r in results if r.get('overflow') or (r.get('status',200)>=400 and r.get('path')!='/does-not-exist')]
    print(json.dumps({'checks':len(results),'failures':failures,'javascript_or_link_errors':errors},indent=2))
    return 1 if errors or failures else 0

if __name__=='__main__':sys.exit(main())
