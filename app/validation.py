"""Server-side validation for all submitted fields; no dependence on browser checks."""
import math
import re
import unicodedata
from flask import abort, request

PASSWORD_MIN_LENGTH = 8
PASSWORD_HELP = 'Use at least 8 characters with one uppercase letter, one lowercase letter, one number, and one special character (maximum 72 UTF-8 bytes).'


def password_error(value):
    if (len(value) < PASSWORD_MIN_LENGTH or len(value.encode('utf-8')) > 72
        or not re.search(r'[A-Z]',value) or not re.search(r'[a-z]',value) or not re.search(r'[0-9]',value)
        or not any(not c.isalnum() and not c.isspace() for c in value)
        or value.casefold() in {'password','password123','password1','12345678','123456789','qwerty123','letmein123','admin123'}):
        return PASSWORD_HELP
    return None


LIMITS = dict(username=50, first_name=50, middle_name=50, last_name=50, full_name=150, email=150,
              subject_code=20, subject_name=150, faculty_code=20, id_number=20,
              section=20, program=100, contact_number=30, component_name=50,
              category_name=50, q=150, code=10, school_year=20, link=255,
              prerequisite_text=500, exception_reason=180, source_section=20, reason=500)
CHOICES = {
    'year_level': ('1st Year', '2nd Year', '3rd Year', '4th Year'),
    'sex': ('MALE', 'FEMALE'), 'enrollment_type': ('REGULAR', 'IRREGULAR'),
    'semester': ('1st Semester', '2nd Semester', 'Summer'),
    'semester_offered': ('1st Semester', '2nd Semester', 'Summer'),
    'redirect_to': ('grade_entry', 'grade_weighting'), 'shared': ('on',),
    'mode': ('bulk', 'individual', 'remove'), 'archived': ('0','1'), 'bracket_units': ('on',),
}
REQUIRED = {
    'auth.register_faculty': 'first_name last_name program email password confirm_password',
    'auth.login': 'username password',
    'auth.forgot_password': 'username',
    'auth.register': 'age first_name last_name id_number program email contact_number password confirm_password',
    'admin.add_subject': 'program subject_code subject_name units year_level semester_offered',
    'admin.edit_subject': 'program subject_code subject_name units year_level semester_offered',
    'admin.add_curriculum_subject': 'program subject_code subject_name units year_level semester_offered',
    'admin.edit_curriculum_subject': 'program subject_code subject_name units year_level semester_offered',
    'admin.add_teacher': 'first_name last_name email password confirm_password',
    'admin.edit_teacher': 'full_name email status',
    'admin.add_student': 'first_name last_name email id_number program year_level section contact_number',
    'admin.edit_student': 'first_name last_name email id_number program year_level section status contact_number',
    'auth.change_password': 'current_password new_password confirm_password',
    'admin.assign_subject': 'teacher_id subject_id section',
    'srs.create_class': 'teacher_id subject_id section class_term_id',
    'srs.assign_faculty': 'teacher_id',
    'university.enlistme': 'enlistment_term_id',
    'admin.assign_student_to_section': 'assignment_id mode',
    'admin.add_term': 'school_year semester', 'admin.update_profile': 'full_name email',
    'faculty.add_component': 'assignment_id component_name weight_percent',
    'faculty.add_category': 'assignment_id category_name weight_percent',
    'faculty.edit_category': 'assignment_id category_name weight_percent',
    'faculty.delete_component': 'assignment_id', 'faculty.delete_category': 'assignment_id',
    'faculty.save_scores': 'assignment_id revision', 'faculty.update_status': 'assignment_id status',
    'faculty.csv_upload': 'assignment_id', 'faculty.section_detail_toggle': 'assignment_id',
    'faculty.section_detail_regenerate': 'assignment_id', 'student.join_course': 'code',
}


def number(value, low, high, integer=False):
    try:
        n = float(value)
        return math.isfinite(n) and low <= n <= high and (not integer or n.is_integer())
    except (ValueError, TypeError):
        return False


def field_error(key, value, endpoint='', post=True):
    label = key.replace('_', ' ').capitalize()
    limit = 150 if key == 'username' and endpoint in ('auth.login','auth.forgot_password') else LIMITS.get(key)
    if limit and len(value.encode('utf-8')) > limit:
        return f'{label} must be at most {limit} bytes.'
    if any(ord(c) < 32 for c in value):
        return f'{label} contains invalid control characters.'
    if not value.strip():
        if key.startswith("score__") and not re.fullmatch(r"score__[1-9][0-9]*__[1-9][0-9]*", key):
            return "Invalid score field."
        return None
    if key in CHOICES and value not in CHOICES[key]:
        return f'Select a valid {label.lower()}.'
    if key == 'status' and value not in (('DRAFT', 'IN_PROGRESS', 'PUBLISHED') if endpoint == 'faculty.update_status' else ('ACTIVE', 'INACTIVE')):
        return 'Select a valid status.'
    if key == 'email' and not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value):
        return 'Enter a valid email address.'
    if key=='email' and endpoint in ('auth.register','auth.register_faculty','admin.add_teacher','admin.edit_teacher','admin.add_student','admin.edit_student'):
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)+@isu\.edu\.ph',value,re.I):return 'Use your institutional email, such as alexis.s.balmores@isu.edu.ph.'
    if key in ('first_name','middle_name','last_name','full_name'):
        if not any(c.isalpha() for c in value) or any(not(c.isalpha() or unicodedata.category(c)=='Mn' or c in " .'-") for c in value):return 'Names may contain letters, spaces, apostrophes, periods, and hyphens.'
    if key=='id_number' and not re.fullmatch(r'\d{2}-\d{4}',value):return 'Student ID must use the format 23-2762.'
    if post and key in ('section','source_section') and not re.fullmatch(r'(?:BSCS|BSIT|BSIS|BSDSA|BLIS) [1-4]-[1-9][0-9]?',value):return 'Use a university section such as BSDSA 1-1.'
    if key == 'subject_code' and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 ./_\-]*', value):
        return 'Course code contains invalid characters.'
    if key in ('username', 'faculty_code', 'id_number', 'code') and not re.fullmatch(r'[A-Za-z0-9_.@+\-]+', value.strip() if key=='username' and endpoint in ('auth.login','auth.forgot_password') else value):
        return f'{label} contains invalid characters.'
    if key == 'contact_number' and not re.fullmatch(r'09[0-9]{9}', value):
        return 'Contact number must contain 11 digits starting with 09, such as 09999999999.'
    if key == 'school_year' and (not re.fullmatch(r'\d{4}-\d{4}', value) or int(value[5:]) != int(value[:4]) + 1):
        return 'School year must use consecutive years, such as 2026-2027.'
    if key in ('password', 'new_password') and endpoint != 'auth.login':
        return password_error(value)
    if key in ('password', 'confirm_password') and len(value.encode('utf-8')) > 72:
        return 'Password is too long (maximum 72 UTF-8 bytes).'
    if key.endswith('_id') or key == 'page':
        if not re.fullmatch(r'[0-9]+', value) or not number(value, 1, 2147483647, True):
            return f'{label} must be a positive integer.'
    if key == 'revision' and (not re.fullmatch(r'[0-9]+', value) or not number(value, 0, 2147483647, True)):
        return 'Invalid form revision.'
    if key == 'age' and not number(value,1,120,True):
        return 'Age must be a whole number from 1 to 120.'
    if key == 'units' and not number(value, 1, 9, True):
        return 'Units must be a whole number from 1 to 9.'
    if key in ('lecture_units','lab_units') and not number(value,0,9,True):
        return 'Lecture and laboratory units must be whole numbers from 0 to 9.'
    if key == 'weight_percent' and not number(value, 0, 100):
        return 'Weight must be between 0 and 100.'
    if key.startswith('score__'):
        if not re.fullmatch(r'score__[1-9][0-9]*__[1-9][0-9]*', key) or not number(value, 0, 100):
            return 'Scores must be finite numbers from 0 to 100.'
    return None


def validate_request():
    data = request.form if request.method == 'POST' else request.args
    errors = []
    if request.method == 'POST':
        for key in REQUIRED.get(request.endpoint, '').split():
            if not data.get(key, '').strip():
                errors.append(f'{key.replace("_", " ").capitalize()} is required.')
    for key in data:
        if request.endpoint=='notifications.delete_selected' and request.method=='POST' and key=='notification_id':
            if len(data.getlist(key))>200 or any(not re.fullmatch(r'[1-9][0-9]{0,14}',value) for value in data.getlist(key)):
                errors.append('Select valid notifications to delete.')
            continue
        if request.endpoint=='university.enlistme' and key=='subject_ids':
            if len(data.getlist(key))>100 or any(not re.fullmatch(r'[1-9][0-9]{0,9}',v) for v in data.getlist(key)):errors.append('Choose valid offered subjects.')
            continue
        if len(data.getlist(key)) != 1:
            errors.append(f'Duplicate field: {key}.')
        if len(data[key]) > 4096:
            errors.append('Input is too long.')
        else:
            error = field_error(key, data[key], request.endpoint, request.method == 'POST')
            if error:
                errors.append(error)
    if request.endpoint in ("admin.add_subject", "admin.edit_subject", "admin.add_curriculum_subject", "admin.edit_curriculum_subject") and data.get("program") not in ("BSCS", "BSIT", "BSIS", "BSDSA", "BLIS"):
        errors.append("Select a valid curriculum program.")
    if request.method=='POST' and request.endpoint in ('auth.register','admin.add_student','admin.edit_student'):
        from .curriculum import canonical_program
        if not canonical_program(data.get('program')):
            errors.append('Choose a supported program.')
        section=data.get('section','');program=canonical_program(data.get('program'))
        if program and section and not section.startswith(program+' '):errors.append('Section must belong to the selected program.')
        year={'1st Year':'1','2nd Year':'2','3rd Year':'3','4th Year':'4'}.get(data.get('year_level'))
        if year and section and not section.split(' ')[-1].startswith(year+'-'):errors.append('Section year must match the selected year level.')
        name=' '.join(data.get(k,'').strip() for k in ('first_name','middle_name','last_name') if data.get(k,'').strip())
        if len(name.encode())>150:errors.append('Combined student name must not exceed 150 bytes.')
    if request.method=='POST' and request.endpoint=='admin.add_teacher':
        name=' '.join(data.get(key,'').strip() for key in ('first_name','middle_name','last_name') if data.get(key,'').strip())
        if len(name.encode())>150:errors.append('Combined teacher name must not exceed 150 bytes.')
        if data.get('password') != data.get('confirm_password'):errors.append('Passwords do not match.')
    if errors:
        abort(400, description=' '.join(errors[:8]))
