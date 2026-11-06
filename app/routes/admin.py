import math

from flask import abort, Blueprint, flash, redirect, render_template, request, session, url_for

from ..curriculum import canonical_program
from ..auth import hash_password, login_required
from ..db import execute, execute_returning_id, query_all, query_one
from ..notifications import notify

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

PAGE_SIZE = 10


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def active_term():
    from ..academic import selected
    return selected()


def paginate(total_count, page, page_size=PAGE_SIZE):
    total_pages = max(1, math.ceil(total_count / page_size))
    page = min(max(1, page), total_pages)
    offset = (page - 1) * page_size
    return page, total_pages, offset


def log_activity(message):
    execute(
        "INSERT INTO activity_log (actor_user_id, message) VALUES (:user_id, :msg)",
        {"user_id": session.get("user_id"), "msg": message.encode("utf-8")[:300].decode("utf-8", errors="ignore")},
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@admin_bp.route("/dashboard")
@login_required("admin")
def dashboard():
    from ..insights import load_sections, summarize, enrollment_by_program
    term = active_term()
    sections = load_sections(term["term_id"] if term else 0)
    recent_activity = query_all("SELECT message, created_at FROM activity_log ORDER BY created_at DESC FETCH FIRST 5 ROWS ONLY")
    return render_template("admin/dashboard.html", term=term, sections=sections,
                           report=summarize(sections, published_only=True), recent_activity=recent_activity,
                           program_counts=enrollment_by_program(sections))


# ---------------------------------------------------------------------------
# Subjects
# ---------------------------------------------------------------------------

def catalog_folder_db():
    from ..security import connect
    return connect()


def ensure_catalog_folders(db):
    db.execute("CREATE TABLE IF NOT EXISTS catalog_folders(id INTEGER PRIMARY KEY,name TEXT NOT NULL UNIQUE COLLATE NOCASE,subjects TEXT NOT NULL)")

    db.execute("CREATE TABLE IF NOT EXISTS retired_catalog_folders(id INTEGER PRIMARY KEY)")


@admin_bp.post('/subjects/folders/<int:folder_id>/delete')
@login_required('admin')
def delete_catalog_folder(folder_id):
    with catalog_folder_db() as db:
        ensure_catalog_folders(db)
        db.execute("BEGIN IMMEDIATE")
        if not db.execute("SELECT id FROM catalog_folders WHERE id=?", (folder_id,)).fetchone():
            abort(404)
        execute("UPDATE subjects SET catalog_folder_id=NULL WHERE catalog_folder_id=:fid", {"fid": folder_id})
        db.execute("INSERT INTO retired_catalog_folders(id) VALUES(?)", (folder_id,))
        db.execute("DELETE FROM catalog_folders WHERE id=?", (folder_id,))
    flash('Folder deleted. Its subjects are available in their program folders.', 'success')
    return redirect(url_for('admin.subjects'))


@admin_bp.route('/subjects/folders/new',methods=['GET','POST'])
@admin_bp.route('/subjects/folders/<int:folder_id>',methods=['GET','POST'])
@login_required('admin')
def catalog_folder(folder_id=None):
    import json
    with catalog_folder_db() as db:
        ensure_catalog_folders(db)
        folder=db.execute("SELECT * FROM catalog_folders WHERE id=?",(folder_id,)).fetchone() if folder_id else None
        if folder_id and not folder:abort(404)
        selected=set(json.loads(folder['subjects'])) if folder else set()
        if request.method=='POST':
            name=request.form.get('folder_name','').strip()
            if not 1<=len(name)<=80:abort(400,description='Enter a folder name of up to 80 characters.')
            if db.execute("SELECT id FROM catalog_folders WHERE name=? AND id<>?",(name,folder_id or 0)).fetchone():abort(409,description='This folder name already exists.')
            values=(name,json.dumps(sorted(selected)))
            if folder:db.execute("UPDATE catalog_folders SET name=?,subjects=? WHERE id=?",values+(folder_id,))
            else:folder_id=db.execute("INSERT INTO catalog_folders(id,name,subjects) SELECT COALESCE(MAX(id),0)+1,?,? FROM (SELECT id FROM catalog_folders UNION ALL SELECT id FROM retired_catalog_folders)",values).lastrowid
            return redirect(url_for('admin.catalog_folder',folder_id=folder_id))
    if not folder or request.args.get('edit')=='1':
        return render_template('admin/catalog_folder.html',folder=folder,editing=True)
    archived=request.args.get('show_archived')=='1'
    condition='catalog_folder_id=:fid'
    params=dict(fid=folder_id,archived=int(archived))
    if selected:
        keys=[]
        for i,subject_id in enumerate(selected):
            key=f'legacy{i}';keys.append(':'+key);params[key]=int(subject_id)
        condition+=' OR subject_id IN ('+','.join(keys)+')'
    rows=query_all(f'SELECT * FROM subjects WHERE ({condition}) AND is_archived=:archived ORDER BY subject_code,subject_id',params)
    grouped={}
    for row in rows:
        grouped.setdefault(row['year_level'],{}).setdefault(row['semester_offered'] or 'Semester not set',[]).append(row)
    return render_template('admin/curriculum_guide.html',folder=folder,program=folder['name'],program_name='Curriculum subjects',grouped=grouped,archived=archived,year_order=YEAR_ORDER,semester_order=['1st Semester','2nd Semester','Summer','Semester not set'])



@admin_bp.route("/subjects")
@login_required("admin")
def subjects():
    from ..curriculum import PROGRAM_NAMES,source_curriculum
    term = active_term()
    program = request.args.get("program", "").upper()
    search=request.args.get('q','').strip()
    if search:
        rows=query_all('''SELECT subject_id,subject_code,subject_name,program,units,year_level,semester_offered
            FROM subjects WHERE is_archived=0 AND (LOWER(subject_code) LIKE :q OR LOWER(subject_name) LIKE :q)
            ORDER BY program,subject_code''',{'q':'%'+search.lower()+'%'})
        return render_template('srs/subject_search.html',term=term,rows=rows,q=search)
    if not program:
        counts = query_all("SELECT program, COUNT(*) AS n FROM subjects WHERE is_archived=0 GROUP BY program")
        with catalog_folder_db() as db:
            ensure_catalog_folders(db)
            folders=db.execute("SELECT id,name FROM catalog_folders ORDER BY name").fetchall()
        return render_template("admin/curriculum_folders.html",folders=folders, term=term, programs=PROGRAM_NAMES,
                               counts={r["program"]:r["n"] for r in counts})
    if program not in PROGRAM_NAMES and program != 'UNSORTED':
        abort(404)
    archived = request.args.get('show_archived') == '1'
    condition = 's.program IS NULL' if program == 'UNSORTED' else 's.program=:program'
    params = {} if program == 'UNSORTED' else {'program':program}
    rows = query_all(f"""SELECT s.subject_id, s.subject_code, s.subject_name, s.units,
        s.year_level, s.program, s.semester_offered, s.lecture_units, s.lab_units,
        s.prerequisite_text, s.units_note, s.is_archived,
        p.subject_code AS prerequisite_code
        FROM subjects s LEFT JOIN subjects p ON p.subject_id=s.prerequisite_subject_id
        WHERE {condition} AND s.is_archived={1 if archived else 0}
        ORDER BY s.year_level, s.semester_offered, s.subject_code, s.subject_id""",params)
    grouped = {}
    for row in rows:
        grouped.setdefault(row['year_level'],{}).setdefault(row['semester_offered'] or 'Semester not set',[]).append(row)
    return render_template('admin/curriculum_guide.html', term=term, program=program,
        curriculum=source_curriculum(program),
        program_name=PROGRAM_NAMES.get(program,'Needs program'), grouped=grouped, archived=archived,
        year_order=YEAR_ORDER, semester_order=['1st Semester','2nd Semester','Summer','Semester not set'])


PROGRAMS = ["BSCS", "BSIT", "BSIS", "BSDSA", "BLIS"]
YEAR_ORDER = ["1st Year", "2nd Year", "3rd Year", "4th Year"]


@admin_bp.route('/subjects/new')
@admin_bp.route('/subjects/<int:subject_id>')
@login_required('admin')
def subject_form(subject_id=None):
    from ..curriculum import PROGRAM_NAMES
    row = query_one('SELECT * FROM subjects WHERE subject_id=:id',{'id':subject_id}) if subject_id else None
    if subject_id and not row:
        abort(404)
    program = row['program'] if row else request.args.get('program','').upper()
    if program and program not in PROGRAM_NAMES:
        abort(404)
    return render_template('admin/subject_form.html',term=active_term(),subject=row,
                           folder_id=row.get('catalog_folder_id') if row else request.args.get('folder_id',type=int),program=program, programs=PROGRAM_NAMES, year_levels=YEAR_ORDER)


def _save_curriculum_subject(subject_id=None):
    from ..curriculum import PROGRAM_NAMES
    program=request.form.get('program','').strip().upper()
    if program not in PROGRAM_NAMES:
        abort(400, description='Choose the program this subject belongs to.')
    values=dict(code=request.form.get('subject_code','').strip(), name=request.form.get('subject_name','').strip(),
        program=program, units=request.form.get('units',type=int), year_level=request.form.get('year_level'),
        semester=request.form.get('semester_offered') or None,
        lecture=request.form.get('lecture_units',type=int), lab=request.form.get('lab_units',type=int),
        prerequisite=request.form.get('prerequisite_text','').strip() or None)
    if not values['code'] or not values['name'] or values['units'] is None:
        abort(400,description='Course code, title, and units are required.')
    if values['lecture'] is not None and values['lab'] is not None and values['lecture']+values['lab'] != values['units']:
        abort(400,description='Lecture and laboratory units must add up to total units.')
    values['note']=None
    current=None
    folder_id=request.form.get('folder_id',type=int)
    if folder_id:
        with catalog_folder_db() as db:
            ensure_catalog_folders(db)
            if not db.execute('SELECT id FROM catalog_folders WHERE id=?',(folder_id,)).fetchone():abort(404)
    if subject_id:
        current=query_one('SELECT * FROM subjects WHERE subject_id=:id FOR UPDATE WAIT 5',{'id':subject_id})
        if not current:abort(404)
        values.update(lecture=current.get('lecture_units'),lab=current.get('lab_units'),note=current.get('units_note'))
        used=query_one('SELECT assignment_id FROM teacher_subjects WHERE subject_id=:id FETCH FIRST 1 ROWS ONLY',{'id':subject_id})
        if used and (current['subject_code']!=values['code'] or current['units']!=values['units'] or
                     (current['program'] and current['program']!=program)):
            abort(409,description='This subject is used by a class. Its code, units, and assigned program must be preserved. Archive it and add a replacement if needed.')
    duplicate=query_one("""SELECT subject_id FROM subjects WHERE program=:program
        AND UPPER(TRIM(subject_code))=UPPER(:code) AND UPPER(TRIM(subject_name))=UPPER(:name)
        AND subject_id<>:id""",{'program':program,'code':values['code'],'name':values['name'],'id':subject_id or 0})
    if duplicate:abort(409,description='This course code and title already exist in the program, including archived subjects.')
    if subject_id:
        execute("""UPDATE subjects SET subject_code=:code, subject_name=:name, program=:program,
            units=:units, year_level=:year_level, semester_offered=:semester,
            lecture_units=:lecture, lab_units=:lab, prerequisite_text=:prerequisite,
            prerequisite_subject_id=NULL, units_note=:note, updated_at=SYSTIMESTAMP WHERE subject_id=:id""",
            {**values,'id':subject_id})
    else:
        execute("""INSERT INTO subjects(catalog_folder_id,subject_code,subject_name,program,units,year_level,
            semester_offered,lecture_units,lab_units,prerequisite_text,units_note)
            VALUES(:folder_id,:code,:name,:program,:units,:year_level,:semester,:lecture,:lab,:prerequisite,:note)""",dict(values,folder_id=folder_id))
    log_activity(f"Admin {'updated' if subject_id else 'added'} {values['code']} in {program}")
    flash('Subject saved.','success')
    if folder_id:return redirect(url_for('admin.catalog_folder',folder_id=folder_id))
    return redirect(url_for('admin.subjects',program=program))


@admin_bp.route('/subjects/add',methods=['POST'])
@login_required('admin')
def add_subject():
    return _save_curriculum_subject()


@admin_bp.route('/subjects/<int:subject_id>/edit',methods=['POST'])
@login_required('admin')
def edit_subject(subject_id):
    return _save_curriculum_subject(subject_id)


@admin_bp.route('/subjects/<int:subject_id>/delete',methods=['POST'])
@login_required('admin')
def delete_subject(subject_id):
    row=query_one('SELECT subject_id, program FROM subjects WHERE subject_id=:id FOR UPDATE WAIT 5',{'id':subject_id})
    if not row:abort(404)
    if query_one('SELECT assignment_id FROM teacher_subjects WHERE subject_id=:id FETCH FIRST 1 ROWS ONLY',{'id':subject_id}):
        abort(409,description='This subject has class history. Archive it instead of deleting it.')
    execute('DELETE FROM subjects WHERE subject_id=:id',{'id':subject_id})
    log_activity(f'Admin deleted unused subject {subject_id}')
    flash('Subject deleted.','success')
    return redirect(url_for('admin.subjects',program=row['program'] or 'UNSORTED'))


@admin_bp.route('/subjects/<int:subject_id>/archive',methods=['POST'])
@login_required('admin')
def archive_subject(subject_id):
    row=query_one('SELECT subject_id,program FROM subjects WHERE subject_id=:id FOR UPDATE WAIT 5',{'id':subject_id})
    if not row:abort(404)
    archived=request.form.get('archived',type=int)
    if archived not in (0,1):abort(400)
    execute('UPDATE subjects SET is_archived=:value, updated_at=SYSTIMESTAMP WHERE subject_id=:id',{'value':archived,'id':subject_id})
    log_activity(f"Admin {'archived' if archived else 'restored'} subject {subject_id}")
    flash('Subject archived. Existing classes are retained.' if archived else 'Subject restored.','success')
    return redirect(url_for('admin.subjects',program=row['program'] or 'UNSORTED'))


@admin_bp.route('/subjects/curriculum')
@login_required('admin')
def curriculum_guide():
    return redirect(url_for('admin.subjects',**request.args.to_dict()))


@admin_bp.route('/subjects/curriculum/bsdsa/source')
@login_required('admin')
def curriculum_source():
    from flask import send_file
    from ..curriculum import DATA_DIR
    return send_file(DATA_DIR/'bsdsa-2023-2024.docx',as_attachment=True,download_name='BSDSA Curriculum SY 2023-2024.docx')


@admin_bp.route('/subjects/curriculum/<program>/source')
@login_required('admin')
def program_curriculum_source(program):
    from flask import send_file
    from ..curriculum import DATA_DIR,source_curriculum
    program=program.upper();source=source_curriculum(program)
    if not source:abort(404)
    filename=source.get('source_file','bsdsa-2023-2024.docx')
    return send_file(DATA_DIR/filename,as_attachment=True,download_name=filename)


@admin_bp.route('/subjects/curriculum/add',methods=['POST'])
@login_required('admin')
def add_curriculum_subject():
    return _save_curriculum_subject()


@admin_bp.route('/subjects/curriculum/<int:subject_id>/edit',methods=['POST'])
@login_required('admin')
def edit_curriculum_subject(subject_id):
    return _save_curriculum_subject(subject_id)


@admin_bp.route('/subjects/curriculum/<int:subject_id>/delete',methods=['POST'])
@login_required('admin')
def delete_curriculum_subject(subject_id):
    return delete_subject(subject_id)


# ---------------------------------------------------------------------------
# Teachers
# ---------------------------------------------------------------------------

@admin_bp.route("/teachers")
@login_required("admin")
def teachers():
    term = active_term()
    q = request.args.get("q", "").strip()

    where = ""
    params = {"term_id": term["term_id"] if term else 0}
    if q:
        where = "WHERE LOWER(u.full_name) LIKE :q"
        params["q"] = f"%{q.lower()}%"

    rows = query_all(
        f"""
        SELECT
            t.teacher_id,
            t.faculty_code, t.program,
            u.full_name,
            u.email,
            t.status,
            COUNT(ts.assignment_id) AS class_count
        FROM teachers t
        JOIN users u ON u.user_id = t.user_id
        LEFT JOIN teacher_subjects ts ON ts.teacher_id = t.teacher_id AND (:term_id IS NULL OR ts.term_id = :term_id)
        {where}
        GROUP BY t.teacher_id, t.faculty_code, t.program, u.full_name, u.email, t.status
        ORDER BY u.full_name
        """,
        params,
    )

    return render_template(
        "admin/teachers.html",
        term=term,
        teachers=rows,
        q=q,
    )


@admin_bp.route('/teachers/<int:teacher_id>/classes')
@login_required('admin')
def faculty_classes(teacher_id):
    term=active_term()
    teacher=query_one('''SELECT t.teacher_id,t.faculty_code,u.full_name,t.status
        FROM teachers t JOIN users u ON u.user_id=t.user_id WHERE t.teacher_id=:id''',{'id':teacher_id})
    if not teacher:abort(404)
    classes=query_all('''SELECT ts.assignment_id,ts.section,ts.status,ts.term_id,
        s.subject_code,s.subject_name,s.program,s.year_level,s.units,st.school_year,st.semester,
        (SELECT COUNT(*) FROM enrollments e WHERE e.assignment_id=ts.assignment_id) AS student_count
        FROM teacher_subjects ts JOIN subjects s ON s.subject_id=ts.subject_id
        JOIN school_terms st ON st.term_id=ts.term_id
        WHERE ts.teacher_id=:teacher AND (:term_id IS NULL OR ts.term_id=:term_id)
        ORDER BY st.school_year DESC,st.term_id DESC,s.subject_code,ts.section''',
        {'teacher':teacher_id,'term_id':term['term_id'] if term else 0})
    template='admin/_faculty_classes.html' if request.args.get('panel')=='1' else 'admin/faculty_classes.html'
    return render_template(template,teacher=teacher,classes=classes,term=term)


@admin_bp.route('/classes/<int:assignment_id>')
@login_required('admin')
def class_details(assignment_id):
    classroom=query_one('''SELECT ts.assignment_id,ts.teacher_id,ts.term_id,ts.section,ts.status,
        s.subject_code,s.subject_name,s.program,s.year_level,s.units,st.school_year,st.semester,
        COALESCE(u.full_name,'Faculty not yet assigned') AS teacher_name
        FROM teacher_subjects ts JOIN subjects s ON s.subject_id=ts.subject_id
        JOIN school_terms st ON st.term_id=ts.term_id
        LEFT JOIN teachers t ON t.teacher_id=ts.teacher_id LEFT JOIN users u ON u.user_id=t.user_id
        WHERE ts.assignment_id=:id''',{'id':assignment_id})
    if not classroom:abort(404)
    students=query_all('''SELECT s.id_number,u.full_name,s.program,s.year_level
        FROM enrollments e JOIN students s ON s.student_id=e.student_id
        JOIN users u ON u.user_id=s.user_id WHERE e.assignment_id=:id ORDER BY u.full_name,s.id_number''',{'id':assignment_id})
    return render_template('admin/class_details.html',classroom=classroom,students=students,term=active_term())


@admin_bp.route("/teachers/add", methods=["POST"])
@login_required("admin")
def add_teacher():
    from ..university_accounts import faculty_id
    if not canonical_program(request.form.get('program')):abort(400,description='Choose a supported faculty program.')
    full_name=' '.join(request.form.get(key,'').strip() for key in ('first_name','middle_name','last_name') if request.form.get(key,'').strip())
    email=request.form['email'].strip().lower()
    if query_one("SELECT user_id FROM users WHERE role='faculty' AND LOWER(email)=:email",{'email':email}):
        abort(409,description='A faculty account with this email address already exists.')
    password=request.form['password']
    if password != request.form.get('confirm_password'):
        abort(400, description='Passwords do not match.')
    username=faculty_id();hashed=hash_password(password)
    uid=execute_returning_id("""INSERT INTO users(username,password_hash,role,full_name,email,status,must_change_password)
        VALUES(:username,:pw,'faculty',:name,:email,'ACTIVE',0) RETURNING user_id INTO :out_id""",
        dict(username=username,pw=hashed,name=full_name,email=email))
    execute("INSERT INTO teachers(user_id,faculty_code,program,status) VALUES(:user_key,:code,:program,'ACTIVE')",dict(user_key=uid,code=username,program=canonical_program(request.form.get("program"))))
    log_activity(f'Admin created faculty account {username}')
    flash('Faculty registered successfully.', 'success')
    return redirect(url_for('admin.teachers'))


@admin_bp.route("/teachers/<int:teacher_id>/edit", methods=["POST"])
@login_required("admin")
def edit_teacher(teacher_id):
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    status = request.form.get("status", "ACTIVE")

    row = query_one("SELECT user_id FROM teachers WHERE teacher_id = :id", {"id": teacher_id})
    if not row:
        flash("Teacher not found.", "error")
        return redirect(url_for("admin.teachers"))

    if query_one("SELECT user_id FROM users WHERE role='faculty' AND LOWER(email)=:email AND user_id<>:id",{'email':email,'id':row['user_id']}):
        abort(409,description='A faculty account with this email address already exists.')

    execute(
        "UPDATE users SET full_name = :name, email = :email, updated_at = SYSTIMESTAMP WHERE user_id = :user_id",
        {"name": full_name, "email": email, "user_id": row["user_id"]},
    )
    execute("UPDATE users SET status=:status WHERE user_id=:user_key", {"status": status, "user_key": row["user_id"]})
    new_password = request.form.get("new_password", "")
    if new_password and request.endpoint=="admin.edit_teacher":abort(400,description="Use Generate temporary password to reset credentials.")
    if new_password:
        execute(
            "UPDATE users SET password_hash = :pw WHERE user_id = :user_id",
            {"pw": hash_password(new_password), "user_id": row["user_id"]},
        )
        notify(row["user_id"], "Your password was reset by an administrator.", link=url_for("auth.select_role"))
    if request.form.get("program") and not canonical_program(request.form["program"]):abort(400,description="Choose a supported faculty program.")
    execute("UPDATE teachers SET status = :status,program=:program WHERE teacher_id = :id", {"status": status,"program":canonical_program(request.form.get("program")), "id": teacher_id})
    flash("Teacher updated.", "success")
    return redirect(url_for("admin.teachers"))


@admin_bp.route("/teachers/<int:teacher_id>/delete", methods=["POST"])
@login_required("admin")
def delete_teacher(teacher_id):
    # Serialize with class creation/assignment and enlistment before detaching.
    query_all('SELECT term_id FROM school_terms ORDER BY term_id FOR UPDATE WAIT 5')
    query_all('SELECT assignment_id FROM teacher_subjects WHERE teacher_id=:id ORDER BY assignment_id FOR UPDATE WAIT 5',{'id':teacher_id})
    row = query_one("SELECT t.user_id,u.full_name FROM teachers t JOIN users u ON u.user_id=t.user_id WHERE t.teacher_id=:id FOR UPDATE OF u.status WAIT 5", {"id": teacher_id})
    if row:
        execute('UPDATE grade_versions SET actor_name=COALESCE(actor_name,:name) WHERE actor_user_id=:id',{'name':row['full_name'],'id':row['user_id']})
        execute('UPDATE teacher_subjects SET teacher_id=NULL,revision=revision+1 WHERE teacher_id=:id',{'id':teacher_id})
        execute("DELETE FROM users WHERE user_id = :user_id", {"user_id": row["user_id"]})
        log_activity(f'Admin deleted faculty account {teacher_id}; classes, enrollments, grades, and publication history retained.')
    flash("Faculty account deleted. Classes, enrollments, and grades were kept.", "success")
    return redirect(url_for("admin.teachers"))


def _offered_classes(term_id):
    return query_all("""SELECT ts.assignment_id, ts.subject_id, ts.teacher_id, ts.term_id, ts.section, ts.status, st.school_year, st.semester,
        s.subject_code, s.subject_name, s.program, s.year_level, COALESCE(u.full_name,'Faculty not yet assigned') AS teacher_name,
        (SELECT COUNT(*) FROM enrollments e WHERE e.assignment_id=ts.assignment_id) AS student_count
        FROM teacher_subjects ts JOIN subjects s ON s.subject_id=ts.subject_id
        LEFT JOIN teachers t ON t.teacher_id=ts.teacher_id LEFT JOIN users u ON u.user_id=t.user_id
        JOIN school_terms st ON st.term_id=ts.term_id
        WHERE (:tid IS NULL OR ts.term_id=:tid) ORDER BY s.program,s.subject_code,ts.section""",{'tid':term_id})


@admin_bp.route('/classes')
@login_required('admin')
def classes():
    from ..curriculum import PROGRAM_NAMES
    from ..academic import offering_terms
    term=active_term()
    subjects=query_all("""SELECT subject_id,subject_code,subject_name,program,year_level,semester_offered
        FROM subjects WHERE is_archived=0
        ORDER BY program,year_level,subject_code,subject_name""")
    teachers=query_all("""SELECT t.teacher_id,t.program,u.full_name FROM teachers t JOIN users u ON u.user_id=t.user_id
        WHERE t.status='ACTIVE' AND u.status='ACTIVE' ORDER BY u.full_name""")
    return render_template('admin/classes.html',term=term,subjects=subjects,teachers=teachers,
        assignments=_offered_classes(term['term_id'] if term else 0),programs=PROGRAM_NAMES,
        selected_teacher=request.args.get('teacher_id',type=int),selected_subject=request.args.get('subject_id',type=int),selected_program=request.args.get('program',''),offering_terms=offering_terms())


@admin_bp.route("/teachers/assign", methods=["POST"])
@login_required("admin")
def assign_subject():
    from ..curriculum import PROGRAM_NAMES
    term=query_one('SELECT term_id,semester FROM school_terms WHERE is_active=1')
    if not term:abort(409,description='Activate an academic term in Settings first.')
    teacher_id=request.form.get('teacher_id',type=int)
    subject_id=request.form.get('subject_id',type=int)
    section=request.form.get('section','').strip()
    # Lock the subject so two admins cannot concurrently create the same class.
    subject=query_one('SELECT * FROM subjects WHERE subject_id=:id FOR UPDATE WAIT 5',{'id':subject_id})
    if not subject:abort(404)
    if subject['is_archived'] or subject['program'] not in PROGRAM_NAMES:
        abort(409,description='Choose an active subject inside a program curriculum.')
    if subject['semester_offered']!=term['semester']:
        abort(409,description='This curriculum subject is not offered in the active semester.')
    teacher=query_one("""SELECT t.teacher_id,t.user_id,t.program FROM teachers t JOIN users u ON u.user_id=t.user_id
        WHERE t.teacher_id=:id AND t.status='ACTIVE' AND u.status='ACTIVE'""",{'id':teacher_id})
    if not teacher or teacher.get('program')!=subject['program']:abort(400,description='Choose an active faculty member from the subject program.')
    existing=query_one("""SELECT assignment_id FROM teacher_subjects WHERE subject_id=:sid
        AND UPPER(TRIM(section))=UPPER(:section) AND term_id=:tid""",
        {'sid':subject_id,'section':section,'tid':term['term_id']})
    if existing:abort(409,description='This subject already has a class for that section and term.')
    aid=execute_returning_id("""INSERT INTO teacher_subjects(teacher_id,subject_id,term_id,section)
        VALUES(:teacher,:subject,:term,:section) RETURNING assignment_id INTO :out_id""",
        {'teacher':teacher_id,'subject':subject_id,'term':term['term_id'],'section':section})
    log_activity(f"Admin created class {aid} for {subject['subject_code']} / {section}")
    notify(teacher.get('user_id'),f"You were assigned {subject['subject_code']} · {section}.",link=url_for('srs.classroom',aid=aid))
    flash('Class created. Enroll its students next.','success')
    return redirect(url_for('admin.assign_student_to_section',assignment_id=aid))


@admin_bp.route("/teachers/assignment/<int:assignment_id>/remove", methods=["POST"])
@login_required("admin")
def remove_assignment(assignment_id):
    if query_one("SELECT enrollment_id FROM enrollments WHERE assignment_id=:id", {"id": assignment_id}):
        abort(409, description="This record has academic history and cannot be deleted. Deactivate it or keep it for archival use.")
    execute("DELETE FROM teacher_subjects WHERE assignment_id = :id", {"id": assignment_id})
    flash("Assignment removed.", "success")
    return redirect(url_for("admin.teachers"))


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------

@admin_bp.route("/students")
@login_required("admin")
def students():
    term = active_term()
    q = request.args.get("q", "").strip()
    year_level = request.args.get("year_level", "").strip()
    section = request.args.get("section", "").strip()
    program = request.args.get("program", "").strip()
    page = int(request.args.get("page", 1))

    filters = []
    params = {}
    if q:
        filters.append("(LOWER(u.full_name) LIKE :q OR LOWER(s.id_number) LIKE :q OR LOWER(s.program) LIKE :q)")
        params["q"] = f"%{q.lower()}%"
    if year_level:
        filters.append("s.year_level = :year_level")
        params["year_level"] = year_level
    if section:
        filters.append("s.section = :section")
        params["section"] = section
    if program:
        filters.append("s.program = :program")
        params["program"] = program

    enrollment_sql="EXISTS (SELECT 1 FROM enrollments e JOIN teacher_subjects ts ON ts.assignment_id=e.assignment_id WHERE e.student_id=s.student_id AND (:directory_term IS NULL OR ts.term_id=:directory_term))"
    selection=request.args.get('enrolled')
    tid=term['term_id'] if term else 0
    counts_where=("WHERE "+" AND ".join(filters)) if filters else ""
    counts=query_one(f"SELECT COUNT(*) AS n, COALESCE(SUM(CASE WHEN {enrollment_sql} THEN 1 ELSE 0 END),0) AS enrolled FROM students s JOIN users u ON u.user_id=s.user_id {counts_where}",dict(params,directory_term=tid))
    tab_counts={'':counts['n'],'yes':counts.get('enrolled',0),'no':counts['n']-counts.get('enrolled',0)}
    if selection in ('yes','no'):
        filters.append(('NOT ' if selection=='no' else '')+enrollment_sql)
        params['directory_term']=tid
    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    total = query_one(
        f"""
        SELECT COUNT(*) AS n
        FROM students s JOIN users u ON u.user_id = s.user_id
        {where}
        """,
        params,
    )["n"]
    limit=request.args.get('limit',25,type=int)
    if limit not in (10,25,50,100):limit=25
    total_pages=max(1,(total+limit-1)//limit)
    page=max(1,min(page,total_pages));offset=(page-1)*limit
    exporting=request.args.get('export')=='csv'
    pagination='' if exporting else f'OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY'
    sort_column='s.id_number' if request.args.get('sort')=='id' else 'u.full_name'
    params["directory_term"]=tid
    rows = query_all(
        f"""
        SELECT CASE WHEN {enrollment_sql} THEN 1 ELSE 0 END AS enrolled,s.student_id, s.user_id, s.id_number, s.first_name, s.middle_name, s.last_name, u.full_name, u.email, s.program, s.year_level,
               s.section, s.contact_number, s.sex, s.enrollment_type, s.status
        FROM students s JOIN users u ON u.user_id = s.user_id
        {where}
        ORDER BY {sort_column},s.student_id
        {pagination}
        """,
        params,
    )

    year_levels = ["1st Year", "2nd Year", "3rd Year", "4th Year"]
    from ..curriculum import PROGRAM_NAMES
    from ..profile_photos import photo_path
    programs=list(PROGRAM_NAMES)
    known=query_all("SELECT section_name AS section FROM academic_sections UNION SELECT section FROM students WHERE section<>'UNASSIGNED' ORDER BY section")
    sections=sorted({r['section'] for r in known}|{f'{p} {y}-1' for p in programs for y in range(1,5)})
    from ..student_progress import residency
    from .. import academic
    current_term=academic.active()
    for row in rows:
        row.update(residency(row,current_term))
        row['photo_url']=url_for('admin.student_photo',student_id=row['student_id']) if row.get('user_id') and photo_path(row['user_id']).is_file() else None

    if exporting:
        import csv,io
        from flask import Response
        output=io.StringIO();writer=csv.writer(output)
        writer.writerow(['Student ID','Name','Program','Year level','Section','Status'])
        chosen=set(request.args.get('selected','').split(',')) if request.args.get('selected') else None
        for row in rows:
            if chosen and str(row['student_id']) not in chosen:continue
            values=[row['id_number'],row['full_name'],row['program'],row['standing_year'],row['section'],'Enrolled' if row['enrolled'] else 'Not enrolled']
            writer.writerow(["'"+str(v) if str(v).lstrip().startswith(('=','+','-','@')) else v for v in values])
        return Response(output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=students.csv'})
    return render_template(
        "admin/students.html",
        term=term,
        students=rows,tab_counts=tab_counts,
        q=q,
        year_level=year_level,
        section=section,
        program=program,
        year_levels=year_levels,
        programs=programs,
        sections=sections,
        page=page,
        total_pages=total_pages,
        total=total,
    )


@admin_bp.route("/students/add", methods=["POST"])
@login_required("admin")
def add_student():
    from ..university_accounts import temporary_password,issue
    names={key:request.form.get(key,'').strip() for key in ('first_name','middle_name','last_name')}
    identifier=request.form['id_number'].strip()
    if query_one('SELECT student_id FROM students WHERE id_number=:id',{'id':identifier}) or query_one('SELECT user_id FROM users WHERE username=:id',{'id':identifier}):
        abort(409,description='This student ID already exists.')
    password=temporary_password();hashed=hash_password(password)
    uid=execute_returning_id("""INSERT INTO users(username,password_hash,role,full_name,email,status,must_change_password)
        VALUES(:username,:pw,'student',:name,:email,'ACTIVE',1) RETURNING user_id INTO :out_id""",
        dict(username=identifier,pw=hashed,name=' '.join(v for v in names.values() if v),email=request.form['email'].strip().lower()))
    execute("""INSERT INTO students(user_id,id_number,first_name,middle_name,last_name,program,year_level,section,contact_number,sex,enrollment_type,progress_school_year,status)
        VALUES(:user_key,:id,:first_name,:middle_name,:last_name,:program,:year,:section,:contact,:sex,:kind,(SELECT TO_NUMBER(SUBSTR(school_year,1,4)) FROM school_terms WHERE is_active=1),'ACTIVE')""",
        dict(names,user_key=uid,id=identifier,program=canonical_program(request.form['program']),year=request.form['year_level'],section=request.form['section'],contact=request.form['contact_number'],sex=request.form.get('sex') or None,kind=request.form.get('enrollment_type') or 'REGULAR'))
    issue(uid,identifier,password,hashed)
    log_activity(f'Admin created student account {identifier}')
    return redirect(url_for('university.credentials'))


@admin_bp.route("/students/<int:student_id>/edit", methods=["POST"])
@login_required("admin")
def edit_student(student_id):
    row=query_one('SELECT user_id FROM students WHERE student_id=:id FOR UPDATE WAIT 5',{'id':student_id})
    if not row:abort(404)
    if request.form.get('new_password'):abort(400,description='Use Generate temporary password to reset credentials.')
    names={key:request.form.get(key,'').strip() for key in ('first_name','middle_name','last_name')}
    identifier=request.form['id_number'].strip()
    if query_one('SELECT student_id FROM students WHERE id_number=:n AND student_id<>:id',dict(n=identifier,id=student_id)) or query_one('SELECT user_id FROM users WHERE username=:n AND user_id<>:id',dict(n=identifier,id=row['user_id'])):
        abort(409,description='This student ID already exists.')
    execute("""UPDATE users SET username=:username,full_name=:name,email=:email,status=:status,updated_at=SYSTIMESTAMP WHERE user_id=:user_key""",
        dict(username=identifier,name=' '.join(v for v in names.values() if v),email=request.form['email'].strip().lower(),status=request.form['status'],user_key=row['user_id']))
    execute("""UPDATE students SET id_number=:number,first_name=:first_name,middle_name=:middle_name,last_name=:last_name,
        program=:program,year_level=:year,section=:section,contact_number=:contact,status=:status,sex=:sex,enrollment_type=:kind WHERE student_id=:id""",
        dict(names,number=identifier,program=canonical_program(request.form['program']),year=request.form['year_level'],section=request.form['section'],contact=request.form['contact_number'],status=request.form['status'],sex=request.form.get('sex') or None,kind=request.form.get('enrollment_type') or 'REGULAR',id=student_id))
    flash('Student updated. The student ID is also the login username.','success')
    return redirect(url_for('admin.students'))


@admin_bp.post('/students/<int:student_id>/deactivate')
@login_required('admin')
def deactivate_student(student_id):
    row=query_one('SELECT user_id FROM students WHERE student_id=:id FOR UPDATE WAIT 5',{'id':student_id})
    if not row:abort(404)
    execute("UPDATE users SET status='INACTIVE' WHERE user_id=:account_id",{'account_id':row['user_id']})
    execute("UPDATE students SET status='INACTIVE' WHERE student_id=:id",{'id':student_id})
    log_activity(f'Admin deactivated student {student_id}')
    flash('Student account deactivated. Academic records have been preserved.','success')
    return redirect(url_for('admin.student_detail',student_id=student_id))


@admin_bp.route("/students/<int:student_id>/delete", methods=["POST"])
@login_required("admin")
def delete_student(student_id):
    from ..db import get_connection
    from ..profile_photos import photo_path
    from ..security import connect

    row=query_one("SELECT user_id,id_number FROM students WHERE student_id=:id FOR UPDATE WAIT 5", {"id": student_id})
    if not row:abort(404)
    if request.form.get('confirm_student_number','').strip()!=row['id_number']:
        flash('Enter the matching Student ID to permanently delete this record.', 'error')
        return redirect(url_for('admin.student_detail',student_id=student_id))

    execute('DELETE FROM student_term_memberships WHERE student_id=:id', {'id':student_id})
    # The account owns the student, enrollments, grades and notifications via cascading foreign keys.
    execute("DELETE FROM users WHERE user_id=:account_id AND role='student'", {'account_id':row['user_id']})
    log_activity(f'Admin permanently deleted student record {student_id}')
    get_connection().commit()
    photo_path(row['user_id']).unlink(missing_ok=True)
    with connect() as security_db:
        for table in ('sessions','previews'):
            security_db.execute(f'DELETE FROM {table} WHERE user_id=?',(row['user_id'],))
    flash('Student account, enrollments and grades permanently deleted.','success')
    return redirect(url_for("admin.students"))


def _enrollment_data(assignment):
    students=query_all("""SELECT s.student_id,s.id_number,s.program,s.year_level,s.section,u.full_name
        FROM students s JOIN users u ON u.user_id=s.user_id
        WHERE s.status='ACTIVE' AND u.status='ACTIVE' ORDER BY u.full_name""")
    roster=query_all("""SELECT e.enrollment_id,s.student_id,s.id_number,u.full_name,s.program,s.section,
        (SELECT COUNT(*) FROM grades g WHERE g.enrollment_id=e.enrollment_id) AS grade_count
        FROM enrollments e JOIN students s ON s.student_id=e.student_id JOIN users u ON u.user_id=s.user_id
        WHERE e.assignment_id=:aid ORDER BY u.full_name""",{'aid':assignment['assignment_id']})
    conflicts=query_all("""SELECT e.student_id FROM enrollments e JOIN teacher_subjects ts ON ts.assignment_id=e.assignment_id
        WHERE ts.subject_id=:sid AND ts.term_id=:tid AND ts.assignment_id<>:aid""",
        {'sid':assignment['subject_id'],'tid':assignment['term_id'],'aid':assignment['assignment_id']})
    return students,roster,{r['student_id'] for r in conflicts}


def _bulk_preview(assignment, students, roster, conflicts, section):
    from ..curriculum import cohort_matches
    enrolled={r['student_id'] for r in roster}
    cohort=[s for s in students if cohort_matches(s,assignment,section)]
    eligible=[s for s in cohort if s['student_id'] not in enrolled and s['student_id'] not in conflicts]
    return cohort,eligible


@admin_bp.route("/students/assign", methods=["GET", "POST"])
@login_required("admin")
def assign_student_to_section():
    from ..curriculum import cohort_matches
    from hashlib import sha256
    term=active_term()
    assignments=_offered_classes(term['term_id'] if term else 0)
    aid=(request.form if request.method=='POST' else request.args).get('assignment_id',type=int)
    assignment=next((a for a in assignments if a['assignment_id']==aid),None)
    if aid and not assignment:abort(404)
    students,roster,conflicts=_enrollment_data(assignment) if assignment else ([],[],set())
    source_section=(request.form if request.method=='POST' else request.args).get('source_section','').strip()
    sections=sorted({s['section'] for s in students if assignment and cohort_matches(s,assignment,s['section'])})
    if not source_section and assignment and assignment['section'] in sections:
        source_section=assignment['section']
    cohort,eligible=_bulk_preview(assignment,students,roster,conflicts,source_section) if assignment else ([],[])
    # Compare the confirmed candidate set, not merely its count, after taking the class lock.
    signature=lambda rows: sha256(','.join(str(s['student_id']) for s in sorted(rows,key=lambda s:s['student_id'])).encode()).hexdigest()
    if request.method=='POST':
        if not assignment:abort(400,description='Choose a class first.')
        locked=query_one('SELECT assignment_id,status FROM teacher_subjects WHERE assignment_id=:id FOR UPDATE WAIT 5',{'id':aid})
        if not locked:abort(404)
        if locked['status']=='PUBLISHED':abort(409,description='This class is published. The teacher must reopen grading before its roster can change.')
        mode=request.form.get('mode')
        if mode=='remove':
            eid=request.form.get('enrollment_id',type=int)
            row=query_one('SELECT enrollment_id FROM enrollments WHERE enrollment_id=:id AND assignment_id=:aid',{'id':eid,'aid':aid})
            if not row:abort(404)
            if query_one('SELECT grade_id FROM grades WHERE enrollment_id=:id FETCH FIRST 1 ROWS ONLY',{'id':eid}):
                abort(409,description='This enrollment has grade records and cannot be removed.')
            execute('DELETE FROM enrollments WHERE enrollment_id=:id AND assignment_id=:aid',{'id':eid,'aid':aid})
            message='Enrollment removed.'
        elif mode in ('bulk','individual'):
            students,roster,conflicts=_enrollment_data(assignment)
            enrolled={r['student_id'] for r in roster}
            if mode=='bulk':
                _,candidates=_bulk_preview(assignment,students,roster,conflicts,source_section)
                if not source_section or request.form.get('preview_token')!=signature(candidates):
                    abort(409,description='The section roster changed. Preview the current students before confirming.')
                if not candidates:abort(409,description='No new eligible students to enroll.')
            else:
                student=next((s for s in students if s['student_id']==request.form.get('student_id',type=int)),None)
                if not student:abort(400,description='Choose an active student.')
                if student['student_id'] in enrolled:abort(409,description='This student is already in the class.')
                if student['student_id'] in conflicts:abort(409,description='This student already takes this subject in another class this term.')
                if not cohort_matches(student,assignment,assignment['section']) and not request.form.get('exception_reason','').strip():
                    abort(400,description='Enter a reason for enrolling a student outside the class program, year, or section.')
                candidates=[student]
            for student in sorted(candidates,key=lambda s:s['student_id']):
                # Serialize enrollment of this student across different class rosters.
                current_student=query_one('SELECT student_id,program,year_level,section,status FROM students WHERE student_id=:id FOR UPDATE WAIT 5',{'id':student['student_id']})
                if not current_student or current_student['status']!='ACTIVE':
                    abort(409,description='A student record changed. Reload the preview before confirming.')
                if mode=='bulk' and not cohort_matches(current_student,assignment,source_section):
                    abort(409,description='A student changed program, year, or section. Reload the preview before confirming.')
                if mode=='individual' and not cohort_matches(current_student,assignment,assignment['section']) and not request.form.get('exception_reason','').strip():
                    abort(409,description='The student record changed. Enter an exception reason before enrolling.')
                if query_one("""SELECT e.enrollment_id FROM enrollments e JOIN teacher_subjects ts ON ts.assignment_id=e.assignment_id
                    WHERE e.student_id=:sid AND ts.subject_id=:subject AND ts.term_id=:term FETCH FIRST 1 ROWS ONLY""",
                    {'sid':student['student_id'],'subject':assignment['subject_id'],'term':assignment['term_id']}):
                    abort(409,description='An enrollment changed during confirmation. Reload the roster and try again.')
                execute('INSERT INTO enrollments(student_id,assignment_id) VALUES(:sid,:aid)',{'sid':student['student_id'],'aid':aid})
            message=f'{len(candidates)} students enrolled.'
        else:abort(400,description='Choose bulk enrollment, individual enrollment, or removal.')
        execute('UPDATE teacher_subjects SET revision=revision+1 WHERE assignment_id=:id',{'id':aid})
        reason=request.form.get('exception_reason','').strip()
        log_activity(f"Admin {mode} enrollment in class {aid}: {message}"+(f' Reason: {reason}' if reason else ''))
        flash(message,'success')
        return redirect(url_for('admin.assign_student_to_section',assignment_id=aid,source_section=source_section))
    return render_template('admin/assign_student.html',term=term,assignments=assignments,assignment=assignment,
        students=students,roster=roster,sections=sections,source_section=source_section,
        cohort=cohort,eligible=eligible,preview_token=signature(eligible),conflicts=conflicts)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@admin_bp.route("/settings")
@login_required("admin")
def settings():
    from ..academic import order
    terms = query_all("SELECT term_id, school_year, semester, is_active, enlistment_open FROM school_terms ORDER BY term_id DESC")
    active = next((t for t in terms if t["is_active"]), None)
    active_id = active["term_id"] if active else None
    for t in terms:
        if t["is_active"]:
            t["state"] = "active"
        elif active and order(t)>order(active):
            t["state"] = "upcoming"
        else:
            t["state"] = "completed"
    admin_user = query_one(
        "SELECT username, full_name, email FROM users WHERE user_id = :user_id",
        {"user_id": session["user_id"]},
    )
    return render_template("admin/settings.html", terms=terms, admin_user=admin_user, term=active)


@admin_bp.route("/settings/terms/add", methods=["POST"])
@login_required("admin")
def add_term():
    school_year = request.form.get("school_year", "").strip()
    semester = request.form.get("semester", "").strip()

    if not school_year or not semester:
        flash("School year and semester are required.", "error")
        return redirect(url_for("admin.settings"))

    if query_one(
        "SELECT term_id FROM school_terms WHERE school_year = :y AND semester = :s",
        {"y": school_year, "s": semester},
    ):
        flash("That term already exists.", "error")
        return redirect(url_for("admin.settings"))

    execute(
        "INSERT INTO school_terms (school_year, semester, is_active) VALUES (:y, :s, 0)",
        {"y": school_year, "s": semester},
    )
    flash("Term added.", "success")
    return redirect(url_for("admin.settings"))


@admin_bp.route("/settings/terms/<int:term_id>/activate", methods=["POST"])
@login_required("admin")
def activate_term(term_id):
    from ..academic import order
    query_all("SELECT term_id FROM school_terms ORDER BY term_id FOR UPDATE WAIT 5")
    chosen=query_one("SELECT term_id,school_year,semester FROM school_terms WHERE term_id=:id", {"id": term_id})
    if not chosen:
        abort(404)
    for opened in query_all('SELECT term_id,school_year,semester FROM school_terms WHERE enlistment_open=1'):
        if order(opened)<=order(chosen):execute('UPDATE school_terms SET enlistment_open=0 WHERE term_id=:id',{'id':opened['term_id']})
    execute("UPDATE school_terms SET is_active = 0")
    execute("UPDATE school_terms SET is_active = 1, enlistment_open=0 WHERE term_id = :id", {"id": term_id})
    from ..student_progress import advance_years
    advance_years(chosen)
    flash("Active term updated.", "success")
    return redirect(url_for("admin.settings"))


@admin_bp.route("/settings/profile", methods=["POST"])
@login_required("admin")
def update_profile():
    from ..auth import verify_password
    user = query_one("SELECT password_hash FROM users WHERE user_id=:id", {"id": session["user_id"]})
    if not user or not verify_password(request.form.get("current_password", ""), user["password_hash"]):
        abort(400, description="Enter your current password to change account settings.")
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    new_password = request.form.get("new_password", "")

    execute(
        "UPDATE users SET full_name = :name, email = :email, updated_at = SYSTIMESTAMP WHERE user_id = :user_id",
        {"name": full_name, "email": email, "user_id": session["user_id"]},
    )
    if new_password:
        execute(
            "UPDATE users SET password_hash = :pw WHERE user_id = :user_id",
            {"pw": hash_password(new_password), "user_id": session["user_id"]},
        )
    session["full_name"] = full_name
    flash("Profile updated.", "success")
    return redirect(url_for("admin.settings"))


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@admin_bp.route("/analytics")
@login_required("admin")
def analytics():
    from ..insights import load_sections, summarize
    term = active_term()
    sections = load_sections(term["term_id"] if term else 0)
    return render_template("admin/analytics.html", term=term,
                           sections=sorted(sections, key=lambda s: (s["mean"] is None, s["mean"] or 0)),
                           report=summarize(sections, published_only=True))


@admin_bp.route('/students/<int:student_id>/profile')
@login_required('admin')
def student_detail(student_id):
    from ..profile_photos import photo_path
    from ..student_progress import academic_status,curriculum,passed_subjects
    from .. import academic
    row=query_one('SELECT s.*,u.full_name,u.email FROM students s JOIN users u ON u.user_id=s.user_id WHERE s.student_id=:id',{'id':student_id})
    if not row:abort(404)
    row['has_history']=bool(query_one('SELECT enrollment_id FROM enrollments WHERE student_id=:id FETCH FIRST 1 ROW ONLY',{'id':student_id}))
    row['photo_url']=url_for('admin.student_photo',student_id=student_id) if photo_path(row['user_id']).is_file() else None
    from ..student_progress import residency
    row.update(residency(row,academic.active()))
    row['enrollment_type']=academic_status(dict(row,year_level=row['curriculum_year']),academic.active(),curriculum(row['program']),passed_subjects(student_id))
    active=academic.active()
    row['current_enrolled']=bool(active and query_one('SELECT 1 AS enrolled FROM enrollments e JOIN teacher_subjects ts ON ts.assignment_id=e.assignment_id WHERE e.student_id=:sid AND ts.term_id=:tid FETCH FIRST 1 ROW ONLY',dict(sid=student_id,tid=active['term_id'])))
    return render_template('admin/student_detail.html',s=row,term=academic.active())


@admin_bp.route('/students/<int:student_id>/photo')
@login_required('admin')
def student_photo(student_id):
    from flask import send_file
    from ..profile_photos import photo_path
    row=query_one('SELECT user_id FROM students WHERE student_id=:id',{'id':student_id})
    if not row:abort(404)
    path=photo_path(row['user_id'])
    if not path.is_file():abort(404)
    response=send_file(path,mimetype='image/jpeg',max_age=0)
    response.headers['Cache-Control']='private, no-store'
    return response

@admin_bp.post('/students/<int:student_id>/photo')
@login_required('admin')
def upload_student_photo(student_id):
    import tempfile,os
    from ..profile_photos import photo_path,prepare_photo
    row=query_one('SELECT user_id FROM students WHERE student_id=:id',{'id':student_id})
    if not row:abort(404)
    photo=request.files.get('profile_photo')
    if not photo:abort(400,description='Choose a photo.')
    try:data=prepare_photo(photo.stream)
    except ValueError as exc:abort(400,description=str(exc))
    path=photo_path(row['user_id']);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as tmp:tmp.write(data)
    try:os.replace(tmp.name,path)
    finally:
        if os.path.exists(tmp.name):os.unlink(tmp.name)
    return redirect(url_for('admin.student_detail',student_id=student_id))
