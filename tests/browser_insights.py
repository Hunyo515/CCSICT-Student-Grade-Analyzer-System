"""Browser QA for six reporting pages, with isolated synthetic data."""
import json
import logging
from pathlib import Path
import sys
import threading
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from audit_fixture import AuditFixture, PopulatedAuditFixture

logging.getLogger('werkzeug').setLevel(logging.ERROR)

def main():
    output=Path('audit/insights');output.mkdir(exist_ok=True)
    results=[];errors=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='msedge',headless=True)
        for fixture_type in (AuditFixture,PopulatedAuditFixture):
            mode='empty' if fixture_type==AuditFixture else 'populated'
            with fixture_type() as fixture:
                server=make_server('127.0.0.1',0,fixture.app,threaded=True)
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                base=f'http://127.0.0.1:{server.server_port}'
                context=browser.new_context()
                page=context.new_page()
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('console',lambda msg:errors.append(msg.text) if msg.type=='error' else None)
                try:
                    for width in (1440,768,375,320):
                        page.set_viewport_size({'width':width,'height':960})
                        for role in ('admin','faculty','student'):
                            context.clear_cookies();page.goto(base+'/__audit/login/'+role)
                            for view in ('dashboard','analytics'):
                                path=f'/{role}/{view}'
                                response=page.goto(base+path,wait_until='networkidle')
                                overflow=page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                                assert response.status==200,(path,response.status)
                                assert not overflow,(mode,width,path)
                                assert page.locator('.insights').is_visible()
                                assert page.locator('.insight-hero, .insight-eyebrow, .insight-method').count()==0
                                assert 'How to read these numbers' not in page.locator('body').inner_text()
                                for href in page.locator('.insights a[href]').evaluate_all('(els)=>els.map(e=>e.getAttribute("href"))'):
                                    from urllib.parse import urlsplit
                                    fixture.app.url_map.bind('localhost').match(urlsplit(href).path,method='GET')
                                if width in (1440,375):
                                    page.screenshot(path=str(output/f'{mode}-{width}-{role}-{view}.png'),full_page=True)
                                results.append(dict(mode=mode,width=width,path=path,status=response.status,overflow=overflow))
                            if mode=='populated' and width==1440 and role in ('faculty','student'):
                                selector=page.locator('.insight-filter select')
                                selector.select_option('20')
                                page.get_by_role('button',name='Apply',exact=True).click()
                                page.wait_for_url('**assignment_id=20')
                                assert selector.input_value()=='20'
                                assert 'CS202' in page.locator('.insights').inner_text()
                            if role=='student':
                                page.goto(base+'/student/dashboard')
                                page.get_by_role('button',name='Join course +',exact=True).click()
                                assert page.locator('#joinCourseModal').is_visible()
                                page.get_by_role('button',name='Cancel',exact=True).click()
                                assert not page.locator('#joinCourseModal').is_visible()
                            if role=='admin':
                                response=page.goto(base+'/admin/subjects/curriculum')
                                assert response.status==200
                                assert page.locator('.curriculum-folder').count()==5
                                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                                if width in (1440,375) and mode=='populated':
                                    page.screenshot(path=str(output/f'folders-{width}.png'),full_page=True)
                                page.locator('.curriculum-folder',has_text='BSDSA').click()
                                assert page.locator('.curriculum-semester').count()==8
                                assert page.locator('.curriculum-table tbody tr').count()==52
                                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                                if width in (1440,375) and mode=='populated':
                                    for index in range(4):
                                        page.locator('.curriculum-year').nth(index).screenshot(path=str(output/f'bsdsa-year-{index+1}-{width}.png'))
                                with page.expect_download() as download:
                                    page.locator('a[href$="/bsdsa/source"]').click()
                                assert download.value.suggested_filename=='BSDSA Curriculum SY 2023-2024.docx'
                                page.get_by_role('link',name='← Programs',exact=True).click()
                                assert page.locator('.curriculum-folder').count()==5
                                results.append(dict(mode=mode,width=width,path='curriculum-folders-and-bsdsa',status=200,overflow=False))
                finally:
                    context.close();server.shutdown();server.server_close();thread.join(timeout=5)
        browser.close()
    (output/'browser-results.json').write_text(json.dumps(dict(results=results,errors=errors),indent=2),encoding='utf-8')
    print(json.dumps(dict(checks=len(results),errors=errors)))
    return bool(errors)

if __name__=='__main__':sys.exit(main())
