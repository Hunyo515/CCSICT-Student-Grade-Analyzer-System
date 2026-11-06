"""Read-only grade selection, publication status, and unit total browser checks."""
import logging
from pathlib import Path
import sys
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from srs_fixture import SrsFixture


def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    output=Path('audit/student-grades');output.mkdir(exist_ok=True)
    errors=[]
    with SrsFixture() as fixture:
        server=make_server('127.0.0.1',0,fixture.app,threaded=True)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='msedge',headless=True)
                for width in (1440,375,320):
                    context=browser.new_context(viewport=dict(width=width,height=960))
                    page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                    base=f'http://127.0.0.1:{server.server_port}'
                    page.goto(base+'/__audit/login/student')
                    page.goto(base+'/app/student/grades?term_filter=all&assignment_id=20')
                    assert page.locator('.final-result').is_visible()
                    assert page.locator('#total-enrolled-units').inner_text()=='6 units'
                    page.select_option('#subject','10')
                    page.wait_for_url('**assignment_id=10')
                    assert page.locator('#subject').input_value()=='10'
                    assert 'term_filter=all' in page.url
                    assert page.get_by_text('No published grade yet',exact=True).is_visible()
                    assert page.locator('.final-result').count()==0
                    assert page.locator('#total-enrolled-units').inner_text()=='6 units'
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    page.screenshot(path=str(output/f'pending-{width}.png'),full_page=True)
                    page.select_option('#subject','20')
                    page.wait_for_url('**assignment_id=20')
                    assert page.locator('.final-result').is_visible()
                    assert page.get_by_text('Grade A',exact=True).is_visible()
                    assert page.locator('#subject').input_value()=='20'
                    page.screenshot(path=str(output/f'published-{width}.png'),full_page=True)
                    page.goto(base+'/student/profile')
                    assert page.locator('tfoot').inner_text()=='Total enrolled units\t6'
                    context.close()
                browser.close()
                assert not errors,errors
                print('PASS: published/pending subject selection, term-filter retention, total enrolled units in My Grades/Profile, and responsive layout.')
        finally:server.shutdown();server.server_close()


if __name__=='__main__':main()
