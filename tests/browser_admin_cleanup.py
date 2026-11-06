"""Read-only dashboard and navigation regression checks."""
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
    output=Path('audit/admin-cleanup');output.mkdir(exist_ok=True);errors=[]
    with SrsFixture() as fixture:
        server=make_server('127.0.0.1',0,fixture.app,threaded=True)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='msedge',headless=True)
                page=browser.new_page(viewport=dict(width=1440,height=900));page.on('pageerror',lambda e:errors.append(str(e)))
                base=f'http://127.0.0.1:{server.server_port}'
                page.goto(base+'/__audit/login/admin');page.goto(base+'/app/admin')
                assert page.get_by_role('heading',name='Recent activity',exact=True).count()==0
                assert page.get_by_role('heading',name='Classes this term',exact=True).count()==0
                assert page.get_by_role('heading',name='Enrollment by program',exact=True).is_visible()
                page.screenshot(path=str(output/'dashboard-1440.png'),full_page=True)
                # A long real page exercises document scrolling with sticky navigation.
                page.goto(base+'/admin/subjects/new?program=BSDSA')
                page.evaluate("document.querySelector('.page-body').style.minHeight='2400px'")
                page.evaluate('window.scrollTo(0,650)')
                assert page.evaluate('window.scrollY')>0
                assert abs(page.locator('#sidebar').bounding_box()['y'])<1
                toggle=page.locator('#sidebarToggleBtn')
                toggle.click();page.wait_for_timeout(250)
                assert page.locator('#sidebar').evaluate('(e)=>e.classList.contains("collapsed")')
                assert toggle.get_attribute('aria-expanded')=='false'
                toggle.click();page.wait_for_timeout(250)
                assert not page.locator('#sidebar').evaluate('(e)=>e.classList.contains("collapsed")')
                assert toggle.get_attribute('aria-expanded')=='true'
                # A short viewport must still allow reaching Settings and Logout.
                page.set_viewport_size(dict(width=1440,height=400))
                page.locator('#sidebar .nav-item').last.scroll_into_view_if_needed()
                settings=page.locator('#sidebar .nav-item').last.bounding_box()
                assert settings['y']>=0 and settings['y']+settings['height']<=400
                logout=page.locator('#sidebar .nav-logout').bounding_box()
                assert logout['y']>=0 and logout['y']+logout['height']<=400
                for width in (768,375,320):
                    page.set_viewport_size(dict(width=width,height=500));page.goto(base+'/app/admin')
                    page.get_by_role('button',name='Open navigation',exact=True).click()
                    assert not page.locator('#sidebar').evaluate('(e)=>e.inert')
                    page.locator('#sidebar .nav-item').last.scroll_into_view_if_needed()
                    assert page.locator('#sidebar').bounding_box()['y']==0
                    assert page.locator('#sidebar .nav-logout-label').is_visible()
                    page.screenshot(path=str(output/f'navigation-{width}.png'),full_page=True)
                    page.keyboard.press('Escape')
                    assert page.locator('#sidebar').evaluate('(e)=>e.inert')
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                assert not errors,errors
                browser.close()
                print('PASS: removed dashboard sections, sticky scrolling, desktop collapse/expand, short-screen scrolling, mobile navigation and Escape.')
        finally:server.shutdown();server.server_close()


if __name__=='__main__':main()
