"""Isolated faculty email login UI and browser sign-in regression check."""
import logging
from pathlib import Path
import sys
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audit_fixture import AuditFixture
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server


def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    output=Path('audit/faculty-email-login');output.mkdir(exist_ok=True)
    with AuditFixture() as fixture:
        server=make_server('127.0.0.1',0,fixture.app,threaded=True)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='msedge',headless=True)
                for width in (1440,375):
                    context=browser.new_context(viewport=dict(width=width,height=900));page=context.new_page()
                    base=f'http://127.0.0.1:{server.server_port}'
                    page.goto(base+'/login/faculty')
                    field=page.get_by_label('Email address',exact=True)
                    assert field.get_attribute('type')=='email'
                    assert field.get_attribute('placeholder')=='Enter your institutional email'
                    assert 'Faculty ID' not in page.locator('body').inner_text()
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    page.screenshot(path=str(output/f'login-{width}.png'),full_page=True)
                    page.get_by_role('link',name='Forgot Password?').click()
                    assert page.get_by_label('Email address',exact=True).get_attribute('type')=='email'
                    page.goto(base+'/login/faculty')
                    page.get_by_label('Email address',exact=True).fill('FACULTY@EXAMPLE.INVALID')
                    page.locator('[name=password]').fill('AuditPassword123!')
                    page.get_by_role('button',name='Login',exact=True).click()
                    page.wait_for_url('**/app/teacher')
                    context.close()
                browser.close()
                print('PASS: faculty email field/placeholder, password recovery, desktop/mobile layout, and case-insensitive browser sign-in.')
        finally:server.shutdown();server.server_close()


if __name__=='__main__':main()
