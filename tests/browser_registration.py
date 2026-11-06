"""Real Oracle registration/login and responsive password-control regression check.

Creates two explicitly identified test accounts, then removes only those accounts.
"""
import logging
from pathlib import Path
import secrets
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from app.db import query_one, execute
from config import Config
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server


def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    output = Path('audit/registration'); output.mkdir(exist_ok=True)
    created = []
    with tempfile.TemporaryDirectory(dir='tests') as temp:
        class TestConfig(Config):
            TESTING = True
            SESSION_COOKIE_SECURE = False
            SECURITY_DB = str(Path(temp).resolve() / 'security.sqlite3')
        app = create_app(TestConfig)
        server = make_server('127.0.0.1', 0, app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{server.server_port}'
        errors = []
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel='msedge', headless=True)
                for width in (1440, 375, 320):
                    context = browser.new_context(viewport=dict(width=width, height=1000))
                    page = context.new_page(); page.on('pageerror', lambda e: errors.append(str(e)))
                    page.goto(base + '/register')
                    assert page.locator('input[name=contact_number]').count() == 1
                    if width == 1440:
                        middle = page.locator('#middle_name').bounding_box()
                        contact = page.locator('#contact_number').bounding_box()
                        assert abs(middle['y'] - contact['y']) < 2 and contact['x'] > middle['x']
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    for identifier in ('password', 'confirm_password'):
                        field = page.locator('#' + identifier)
                        button = page.locator(f'[aria-controls="{identifier}"]')
                        assert button.locator('svg').count() == 1
                        assert button.inner_text() == ''
                        a, b = field.bounding_box(), button.bounding_box()
                        assert b['x'] >= a['x'] and b['x'] + b['width'] <= a['x'] + a['width']
                        button.click(); assert field.get_attribute('type') == 'text'
                        button.click(); assert field.get_attribute('type') == 'password'
                    assert page.locator('#suggested_password').count() == 0
                    for identifier in ('password','confirm_password'):
                        page.locator('#'+identifier).click()
                        page.locator('[data-generate-password="'+identifier+'"]').click()
                        assert page.locator('#confirm_password').input_value() == page.locator('#password').input_value()
                        assert len(page.locator('#password').input_value()) == 16
                    page.locator('#password').fill(''); page.locator('#confirm_password').fill('')
                    page.locator('#password').click()
                    assert page.locator('[data-generate-password="password"]').is_visible()
                    page.screenshot(path=str(output / f'register-{width}.png'), full_page=True)
                    page.goto(base + '/login/student')
                    assert page.get_by_label('Username', exact=True).count() == 1
                    page.screenshot(path=str(output / f'login-{width}.png'), full_page=True)
                    context.close()
                for use_suggestion in (True, False):
                    context = browser.new_context()
                    page = context.new_page()
                    with app.app_context():
                        while True:
                            identifier = '99-' + str(secrets.randbelow(10000)).zfill(4)
                            if not query_one('SELECT student_id FROM students WHERE id_number=:i', {'i': identifier}):
                                break
                    email = f'roster.test.{secrets.token_hex(5)}@isu.edu.ph'
                    page.goto(base + '/register')
                    for key, value in dict(first_name='Roster', last_name='Test', middle_name='Browser', contact_number='09999999999', id_number=identifier, section='BSCS 1-1', email=email).items():
                        page.locator('[name=' + key + ']').fill(value)
                    page.select_option('#year_level', '1st Year'); page.select_option('#program', 'BSCS')
                    if use_suggestion:
                        page.locator('#password').click()
                        page.locator('[data-generate-password="password"]').click()
                        password = page.locator('#password').input_value()
                    else:
                        password = 'BrowserCustom1!' + secrets.token_hex(5)
                        page.locator('#password').fill(password); page.locator('#confirm_password').fill(password)
                    created.append(email)
                    page.get_by_role('button', name='Register', exact=True).click()
                    page.wait_for_url('**/login/student')
                    assert page.get_by_text('Registration successful.', exact=False).count() == 1
                    for login_id in (identifier, email.upper()):
                        page.locator('#username').fill(login_id); page.locator('#password').fill(password)
                        page.get_by_role('button', name='Login', exact=True).click()
                        page.wait_for_url('**/app/student')
                        assert page.locator('body').inner_text().find('Something went wrong') == -1
                        # New context resets the browser session between identifiers.
                        context.close(); context = browser.new_context(); page = context.new_page()
                        page.goto(base + '/login/student')
                    context.close()
                browser.close()
                assert not errors, errors
                print('PASS: desktop/mobile layout, eye controls, suggested/custom registration, Student ID and case-insensitive email login against Oracle.')
        finally:
            server.shutdown()
            with app.app_context():
                for email in created:
                    execute("DELETE FROM users WHERE email=:email AND role='student'", {'email': email})
                    execute("DELETE FROM notifications WHERE message='Student registered: Roster Browser Test.'")


if __name__ == '__main__':
    main()
