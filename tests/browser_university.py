"""Browser checks for university-specific forms and current-term enrollment."""
import sys,json,threading,logging
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from srs_fixture import SrsFixture
from app import academic
from app.routes import university
from audit_fixture import PROFILE


def main():
 logging.getLogger('werkzeug').setLevel(logging.ERROR)
 output=Path('audit/university');output.mkdir(exist_ok=True);checks=[];errors=[]
 current=dict(term_id=1,school_year='2026-2027',semester='1st Semester',is_active=1,enlistment_open=0)
 classes=[dict(assignment_id=i,subject_id=i,subject_code=f'DSA 12{i}',subject_name=name,units=3,year_level='4th Year',section=section,teacher_name='Faculty not yet assigned',prerequisite_text='DSA 111',status='DRAFT') for i,name,section in [(1,'Data Structures','BSDSA 4-1'),(2,'Statistical Computing','BSDSA 4-1')]]
 with SrsFixture() as fixture,patch.object(academic,'active',return_value=current),patch('app.routes.student.get_student',return_value=dict(PROFILE,program='BSDSA',year_level='4th Year',section='BSDSA 4-1')),patch.object(university,'offerings',return_value=classes),patch.object(university,'query_all',return_value=[]):
  server=make_server('127.0.0.1',0,fixture.app,threaded=True);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
  try:
   with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    for width in (1440,375,320):
     context=browser.new_context(viewport=dict(width=width,height=960));page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:errors.append(m.text) if m.type=='error' and ('pattern' in m.text or 'SyntaxError' in m.text) else None)
     page.goto(base+'/__audit/login/student');page.goto(base+'/university/enlistme')
     assert page.get_by_text('CURRENT TERM',exact=True).is_visible()
     assert page.locator('#enlist-save').is_disabled()
     assert page.locator('input[name=subject_ids]').count()==2
     assert page.get_by_text('Faculty not yet assigned',exact=False).count()==2
     assert page.locator('input[name=subject_ids]:checked').count()==0
     assert page.locator('#enlist-subjects legend').inner_text()=='4th Year subjects'
     assert page.locator('#enlist-subjects .enlist-subject').count()==2
     first=page.locator('input[name=subject_ids]').first
     first.check()
     assert page.locator('#enlist-save').is_enabled()
     assert page.locator('#enlist-count').inner_text()=='1 subject selected'
     row=first.locator('..');assert first.bounding_box()['x']<row.locator('span').first.bounding_box()['x']
     page.locator('input[name=subject_ids]').last.check()
     assert page.locator('#enlist-count').inner_text()=='2 subjects selected'
     first.uncheck()
     assert page.locator('#enlist-count').inner_text()=='1 subject selected'
     for subject_row in page.locator('#enlist-subjects .enlist-subject').all():
      units=subject_row.locator('.enlist-units');details=subject_row.locator('span').first
      assert units.inner_text()=='3\nUnits'
      assert units.bounding_box()['x']>=details.bounding_box()['x']+details.bounding_box()['width']
     assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
     page.screenshot(path=str(output/f'enlistme-{width}.png'),full_page=True);checks.append(f'{width}px current-term 4th Year subject checkboxes, selection count, and responsive layout')
     page.goto(base+'/student/profile')
     cards=page.locator('.student-profile-stack > .panel')
     assert cards.count()==2
     first_card,second_card=cards.nth(0).bounding_box(),cards.nth(1).bounding_box()
     assert second_card['y']>=first_card['y']+first_card['height']
     assert abs(first_card['x']-second_card['x'])<1 and abs(first_card['width']-second_card['width'])<1
     assert page.locator('.student-profile-stack').get_by_text('STUDENT RECORD',exact=True).is_visible()
     assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
     page.screenshot(path=str(output/f'profile-{width}.png'),full_page=True)
     page.goto(base+'/app/student');page.select_option('#term-filter','all');page.wait_for_url('**term_filter=all');assert page.locator('#term-filter').input_value()=='all'
     page.goto(base+'/app/student/grades');assert page.locator('#term-filter').input_value()=='all';checks.append(f'{width}px All-term filter persists across screens')
     page.goto(base+'/__audit/login/admin');page.goto(base+'/admin/teachers');page.get_by_role('button',name='Add Teacher',exact=True).click()
     modal=page.locator('#addTeacherModal');assert modal.locator('input[name=faculty_code],input[name=username]').count()==0
     assert modal.locator('input[name=first_name],input[name=middle_name],input[name=last_name],input[name=password],input[name=confirm_password]').count()==5
     assert not modal.locator('[name=middle_name]').evaluate('(e)=>e.required')
     for identifier in ('teacher_password','teacher_confirm_password'):
      modal.locator('#'+identifier).click();modal.locator('[data-generate-password="'+identifier+'"]').click()
      assert modal.locator('[name=password]').input_value()==modal.locator('[name=confirm_password]').input_value()
     email=modal.locator('input[name=email]');email.fill('alexis.s.balmores@Isu.edu.ph');assert email.evaluate('(e)=>e.checkValidity()');email.fill('bad@gmail.com');assert not email.evaluate('(e)=>e.checkValidity()')
     email.fill('alexis.s.balmores@isu.edu.ph')
     modal.locator('#teacher_password').click()
     assert modal.locator('[data-generate-password="teacher_password"]').is_visible()
     page.screenshot(path=str(output/f'faculty-create-{width}.png'),full_page=True)
     page.goto(base+'/admin/students');page.get_by_role('button',name='Add Student',exact=True).click();modal=page.locator('#addStudentModal')
     assert modal.locator('input[name=middle_name]').count()==1;assert modal.locator('input[name=password]').count()==0
     for field,valid,invalid in [('id_number','23-2762','CCT-001'),('contact_number','09999999999','12345678901'),('section','BSCS 1-1','BSCS 1A')]:
      control=modal.locator('[name='+field+']');control.fill(valid);assert control.evaluate('(e)=>e.checkValidity()'),field;control.fill(invalid);assert not control.evaluate('(e)=>e.checkValidity()'),field
     checks.append(f'{width}px generated faculty credentials and university student input formats')
     page.goto(base+'/admin/subjects/new?program=BSDSA');assert page.locator('[name=lecture_units],[name=lab_units],[name=bracket_units]').count()==0
     page.goto(base+'/register');assert page.locator('[name=middle_name],[name=contact_number]').count()==2
     pw_input=page.locator('[name=password]');pw_input.fill('alllowercase123!');assert not pw_input.evaluate('(e)=>e.checkValidity()');pw_input.fill('ValidPass123!');assert pw_input.evaluate('(e)=>e.checkValidity()')
     context.close()
    browser.close()
  finally:server.shutdown();server.server_close();thread.join(timeout=5)
 assert not errors,errors
 (output/'browser-results.json').write_text(json.dumps(dict(checks=checks,errors=errors),indent=2),encoding='utf-8');print(json.dumps(dict(checks=len(checks),errors=errors)))

if __name__=='__main__':main()
