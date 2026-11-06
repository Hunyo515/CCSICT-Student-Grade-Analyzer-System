"""Read-only semester worksheet layout and live calculation checks."""
import logging
from urllib.parse import parse_qs
from pathlib import Path
import sys,threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_flexible_grading import FlexibleFixture
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    output=Path('audit/flexible-grading');output.mkdir(exist_ok=True);errors=[]
    with FlexibleFixture() as fixture:
        server=make_server('127.0.0.1',0,fixture.app,threaded=True);threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='msedge',headless=True)
                for width in (1440,768,375,320):
                    context=browser.new_context(viewport=dict(width=width,height=1000));page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                    page.on('dialog',lambda d:d.accept())
                    base=f'http://127.0.0.1:{server.server_port}'
                    page.goto(base+'/__audit/login/faculty');page.goto(base+'/app/teacher')
                    assert page.get_by_role('link',name='My Classes',exact=True).count()==1
                    assert page.get_by_role('link',name='Open gradebook',exact=False).count()==0
                    page.goto(base+'/app/teacher/classes?term_filter=1')
                    assert page.get_by_role('link',name='Open gradebook',exact=False).count()==2
                    page.get_by_role('link',name='Open gradebook',exact=False).first.click()
                    assert page.get_by_text('← Dashboard',exact=True).count()==0
                    assert page.locator('.class-context .state-pill').count()==0
                    row=page.locator('[data-student-row]').first
                    assert row.locator('[data-semester-total]').inner_text()=='78'
                    assert abs(page.locator('.sheet-maximum th[title]').first.bounding_box()['x']-row.locator('.sheet-score-cell').first.bounding_box()['x'])<1
                    row.locator('input[data-category="1"]').fill('100')
                    assert row.locator('[data-semester-total]').inner_text()=='94'
                    assert row.locator('[data-university-grade]').inner_text()=='1.50'
                    assert 'Unsaved' in page.locator('.save-indicator').inner_text()
                    maximum=page.locator('[data-maximum-edit="1"]')
                    maximum.fill('200')
                    assert row.locator('[data-semester-total]').inner_text()=='54'
                    maximum.fill('')
                    assert row.locator('[data-semester-total]').inner_text()=='—'
                    maximum.fill('100')
                    parent=page.locator('[data-parent-edit="1"]')
                    parent.fill('70')
                    assert row.locator('[data-semester-total]').inner_text()=='84'
                    assert row.locator('[data-remarks]').inner_text()=='In progress'
                    parent.fill('80')
                    first=row.locator('input[data-activity="1"]')
                    first.evaluate("e=>{const data=new DataTransfer();data.setData('text/plain','90\\t40\\t60');e.dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));}")
                    assert row.locator('[data-semester-total]').inner_text()=='86'
                    first.evaluate("e=>{const data=new DataTransfer();data.setData('text/plain','999\\t40');e.dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));}")
                    assert first.input_value()=='90'
                    assert 'Paste cancelled' in page.locator('#sheet-cell-help').inner_text()
                    first.press('Enter')
                    assert page.locator('[data-student-row]').nth(1).locator('input[data-activity="1"]').evaluate('(e)=>e===document.activeElement')
                    assert page.get_by_role('button',name='Add grading section',exact=True).count()==0
                    assert page.get_by_role('button',name='Add activities',exact=True).count()==0
                    assert page.locator('[data-weight-edit]:visible').count()==0
                    assert page.locator('input[name="new_category_name"]:visible').count()==0
                    assert page.locator('.sheet-new-component,.sheet-assessment-key').count()==0
                    assert page.get_by_role('button',name='Add component',exact=True).is_visible()
                    assert page.locator('[data-count-edit]:visible').count()==0
                    assert page.locator('.sheet-activity-number').first.evaluate('(e)=>parseFloat(getComputedStyle(e).fontSize)')>=17
                    assert page.locator('.isu-record-heading img').evaluate('(e)=>getComputedStyle(e).filter')=='none'
                    assert page.locator('input[type=date]').count()==0
                    assert page.locator('.sheet-activity-date').first.get_attribute('placeholder')=='mm/dd/yy'
                    assert page.locator('.sheet-activity-date').first.input_value()==''
                    assert row.locator('[data-weighted]').first.evaluate("e=>getComputedStyle(e).backgroundColor")=='rgb(255, 255, 255)'
                    assert row.locator('.sheet-id').inner_text()=='TEST-001'
                    assert row.locator('.sheet-name small').count()==0
                    assert page.locator('.srs-tabs').get_by_role('link',name='Grading settings').count()==0
                    assert page.locator('.srs-tabs').get_by_role('link',name='Analytics',exact=False).count()==0
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    page.screenshot(path=str(output/f'gradebook-{width}.png'),full_page=True)
                    # Horizontal scroll retains student identifiers.
                    scroll=page.locator('.semester-sheet-scroll');scroll.evaluate('(e)=>e.scrollLeft=650')
                    assert row.locator('.sheet-id').bounding_box()['x']>=scroll.bounding_box()['x']-1
                    page.get_by_role('button',name='Add component',exact=True).click()
                    dialog=page.locator('#component-add-dialog')
                    assert dialog.is_visible()
                    dialog.locator('input[name="new_category_name"]').fill('Examination')
                    dialog.locator('input[name="new_category_weight"]').fill('20')
                    dialog.locator('input[name="new_category_count"]').fill('2')
                    page.screenshot(path=str(output/f'component-dialog-{width}.png'),full_page=True)
                    dialog.get_by_role('button',name='Cancel',exact=True).click()
                    assert not dialog.is_visible()
                    assert row.locator('[data-semester-total]').inner_text()=='86'
                    assert page.locator('input[name="new_category_name"]').is_disabled()
                    page.locator('[data-component-edit="2"]').evaluate('(b)=>{const s=b.closest(".semester-sheet-scroll");s.scrollLeft+=b.getBoundingClientRect().right-s.getBoundingClientRect().right+10;}')
                    page.locator('[data-component-edit="2"]').click()
                    editor=page.locator('#component-edit-dialog')
                    assert editor.is_visible()
                    assert editor.locator('[data-editor-count-output]').inner_text()=='2 activities'
                    editor.press('Escape')
                    assert page.locator('[data-count-edit="2"]').input_value()=='2'
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    context.close()
                fixture.records[0]['row']['aggregation']='POINTS'
                context=browser.new_context(viewport=dict(width=1440,height=1000));page=context.new_page()
                page.goto(base+'/__audit/login/faculty');page.goto(base+'/app/teacher/class/10')
                row=page.locator('[data-student-row]').first
                assert row.locator('[data-semester-total]').inner_text()=='77'
                page.locator('[data-maximum-edit="2"]').fill('100')
                assert row.locator('[data-percentage="2"]').inner_text()=='50.00'
                assert row.locator('[data-semester-total]').inner_text()=='74'
                page.locator('[data-maximum-edit="2"]').fill('50')
                row.locator('input[data-activity="3"]').fill('')
                assert row.locator('[data-semester-total]').inner_text()=='69'
                assert row.locator('[data-remarks]').inner_text()=='In progress'
                page.locator('[data-maximum-edit="3"]').fill('')
                assert row.locator('[data-semester-total]').inner_text()=='80'
                page.locator('[data-maximum-edit="3"]').fill('100')
                row.locator('input[data-activity="3"]').fill('60')
                page.locator('input[name="activity__2__date"]').fill('10/25/26')
                page.locator('.semester-sheet-scroll').evaluate('(e)=>e.scrollLeft=0')
                page.locator('[data-component-edit="2"]').click()
                assert page.locator('[data-editor-count-output]').inner_text()=='2 activities'
                page.screenshot(path=str(output/'edit-component-1440.png'),full_page=True)
                captured=[]
                def capture(route):
                    captured.append(parse_qs(route.request.post_data,keep_blank_values=True))
                    route.fulfill(status=200,content_type='text/html',body='<p>Saved test request</p>')
                page.route('**/scores',capture)
                page.locator('#component-edit-dialog').get_by_role('button',name='Save component',exact=True).click()
                page.wait_for_url('**/scores')
                assert captured[-1]['cat__2__count']==['2']
                assert captured[-1]['activity__2__date']==['10/25/26']
                assert captured[-1]['mark__1__1']==['80']
                page.goto(base+'/app/teacher/class/10')
                add=page.locator('[data-insert-activity="2"]').last
                menu=add.locator('../..')
                menu.locator('..').hover()
                menu.locator('summary').click()
                assert page.locator('.activity-menu[open]').count()==1
                assert add.locator('..').evaluate('(e)=>e.matches(":popover-open")')
                add.evaluate('(b)=>{const s=b.closest(".semester-sheet-scroll");s.scrollLeft+=b.getBoundingClientRect().right-s.getBoundingClientRect().right+10;}')
                add.click()
                page.wait_for_url('**/scores')
                assert captured[-1]['cat__2__count']==['3']
                assert captured[-1]['mark__1__1']==['80']
                page.goto(base+'/app/teacher/class/10')
                page.get_by_role('button',name='Add component',exact=True).click()
                page.locator('input[name="new_category_name"]').fill('Examination')
                page.locator('input[name="new_category_weight"]').fill('20')
                page.locator('input[name="new_category_count"]').fill('2')
                page.locator('#component-add-dialog').get_by_role('button',name='Save component',exact=True).click()
                assert page.locator('#component-add-dialog').is_visible()
                assert 'exceeds 100%' in page.locator('#component-add-dialog [data-allocation-warning]').inner_text()
                page.locator('input[name="new_category_weight"]').fill('0')
                page.locator('#component-add-dialog').get_by_role('button',name='Save component',exact=True).click()
                page.wait_for_url('**/scores')
                assert captured[-1]['new_category_name']==['Examination']
                assert captured[-1]['new_category_count']==['2']
                assert captured[-1]['mark__1__1']==['80']
                page.goto(base+'/app/teacher/class/10')
                remove=page.locator('[data-component-remove="1"]')
                page.locator('.gradebook-toolbar').hover()
                assert remove.evaluate('(e)=>getComputedStyle(e).opacity')=='0'
                remove.locator('..').hover()
                page.wait_for_function("selector => getComputedStyle(document.querySelector(selector)).opacity === '1'",arg='[data-component-remove="1"]')
                remove.click()
                assert page.locator('#component-delete-dialog').is_visible()
                assert page.locator('[data-confirm-component-delete]').is_disabled()
                page.locator('[data-confirm-score-deletion]').check()
                page.locator('[data-confirm-component-delete]').click()
                page.wait_for_url('**/scores')
                assert captured[-1]['delete_category_id']==['1']
                assert captured[-1]['confirm_delete_scores']==['yes']
                assert captured[-1]['mark__1__2']==['40']
                context.close()
                browser.close();assert not errors,errors
                print('PASS: My Classes navigation, semester worksheet, nested live calculations, frozen identifiers, plus-button component creation, compact activity editor, cancel/escape and atomic form submissions, monochrome sheet, template points calculations, and responsive layout.')
        finally:server.shutdown();server.server_close()

if __name__=='__main__':main()
