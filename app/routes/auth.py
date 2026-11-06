from flask import abort, Blueprint, flash, redirect, render_template, request, session, url_for

from ..curriculum import canonical_program
from ..auth import hash_password, verify_password
from ..db import execute, execute_returning_id, query_all, query_one
from ..notifications import notify_many
from ..validation import PASSWORD_MIN_LENGTH

auth_bp = Blueprint("auth", __name__)

ROLE_DASHBOARD = {
    "admin": "admin.dashboard",
    "faculty": "faculty.dashboard",
    "student": "student.dashboard",
}

ROLE_LABELS = {
    "admin": "Admin",
    "faculty": "Faculty",
    "student": "Student",
}


def finish_login(user):
    profile=None;role=user['role']
    if role in ('faculty','student'):
        table,key=('teachers','teacher_id') if role=='faculty' else ('students','student_id')
        profile=query_one(f'SELECT {key},status FROM {table} WHERE user_id=:id',{'id':user['user_id']})
        if not profile or profile['status']!='ACTIVE':
            flash('This account is inactive. Contact your administrator.','error')
            return redirect(url_for('auth.login',role=role))
    from ..security import create_session
    session.clear();session.permanent=True;create_session(user)
    session.update({k:user[k] for k in ('user_id','username','full_name','role')})
    if profile:session[key]=profile[key]
    return redirect(url_for('auth.change_password' if user.get('must_change_password') and role!='faculty' else ROLE_DASHBOARD[role]))


@auth_bp.route("/")
def select_role():
    if session.get("user_id") and session.get("role") in ROLE_DASHBOARD:
        return redirect(url_for(ROLE_DASHBOARD[session['role']]))
    return render_template("auth/select_role.html")


@auth_bp.route("/login/<role>", methods=["GET", "POST"])
def login(role):
    if role not in ROLE_DASHBOARD:
        return redirect(url_for("auth.select_role"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        identifier_clause = "username = :username"
        if role == 'student':
            identifier_clause = "(LOWER(username) = LOWER(:username) OR LOWER(email) = LOWER(:username) OR user_id IN (SELECT user_id FROM students WHERE id_number = :username))"
        elif role == 'faculty':
            identifier_clause = "LOWER(email) = LOWER(:username)"
        user = query_one(
            f"""
            SELECT user_id, username, password_hash, role, full_name, status, email, must_change_password
            FROM users
            WHERE {identifier_clause} AND role = :role
            """,
            {"username": username, "role": role},
        )

        if not user or user['role'] != role or not verify_password(password, user['password_hash']):
            flash('Invalid email address or password.' if role=='faculty' else 'Invalid username or password.', 'error')
            return render_template('auth/login.html', role=role, role_label=ROLE_LABELS[role])
        if user['status'] != 'ACTIVE':
            flash('This account is inactive. Contact your administrator.', 'error')
            return render_template('auth/login.html', role=role, role_label=ROLE_LABELS[role])
        # Explicit product requirement: email OTP is required only for administrators.
        if role!='admin':return finish_login(user)
        from ..email_otp import begin
        import smtplib
        try:
            begin(user)
        except (RuntimeError, OSError, smtplib.SMTPException) as error:
            from flask import current_app
            current_app.logger.warning('Email sign-in delivery failed: %s',type(error).__name__)
            flash(str(error) if isinstance(error,RuntimeError) else 'Email delivery failed. Please try again or contact your administrator.', 'error')
            return render_template('auth/login.html',role=role,role_label=ROLE_LABELS[role]),503
        return redirect(url_for('auth.otp'))

    return render_template("auth/login.html", role=role, role_label=ROLE_LABELS[role])


@auth_bp.route('/verify-email',methods=['GET','POST'])
def otp():
    from ..email_otp import pending,consume,begin
    challenge=pending()
    if not challenge:
        flash('Sign in to request a new code.','error')
        return redirect(url_for('auth.select_role'))
    user=query_one('SELECT user_id,username,password_hash,role,full_name,status,email,must_change_password FROM users WHERE user_id=:id',{'id':challenge['user_id']})
    if not user or user['status']!='ACTIVE' or user['role']!='admin' or user['role']!=session.get('otp_role'):
        session.clear();return redirect(url_for('auth.select_role'))
    from ..security import credential_fingerprint
    import hmac
    if not hmac.compare_digest(challenge['credential'],credential_fingerprint(user['password_hash']+'|'+(user.get('email') or ''))):
        session.clear();return redirect(url_for('auth.select_role'))
    if request.method=='POST':
        if request.form.get('action')=='resend':
            import smtplib
            try:begin(user);flash('A new code was sent. Previous codes no longer work.','success')
            except (RuntimeError,OSError,smtplib.SMTPException) as error:
                flash(str(error) if isinstance(error,RuntimeError) else 'Email delivery failed. Please retry.','error')
        elif consume(request.form.get('otp','').strip(),user):
            return finish_login(user)
        else:flash('Invalid or expired code. Request a new code if needed.','error')
    return render_template('auth/otp.html')


@auth_bp.route('/change-password',methods=['GET','POST'])
def change_password():
    if not session.get('user_id'):return redirect(url_for('auth.select_role'))
    user=query_one('SELECT user_id,username,role,full_name,email,password_hash,status,must_change_password FROM users WHERE user_id=:id',{'id':session['user_id']})
    if not user or user['status']!='ACTIVE':session.clear();return redirect(url_for('auth.select_role'))
    if user['role']=='faculty' and request.method=='GET':
        return redirect(url_for(ROLE_DASHBOARD['faculty']))
    if request.method=='POST':
        from ..security import rate_limit,revoke_session
        rate_limit('change-password:'+str(user['user_id']),5,900)
        current=request.form.get('current_password','');new=request.form.get('new_password','')
        if not verify_password(current,user['password_hash']):flash('Current password is incorrect.','error')
        elif new!=request.form.get('confirm_password'):flash('New passwords do not match.','error')
        elif new==current:flash('Choose a password different from your temporary password.','error')
        else:
            value=hash_password(new)
            execute('UPDATE users SET password_hash=:pw,must_change_password=0,updated_at=SYSTIMESTAMP WHERE user_id=:id',{'pw':value,'id':user['user_id']})
            revoke_session();user.update(password_hash=value,must_change_password=0)
            flash('Password updated.','success');return finish_login(user)
    return render_template('auth/change_password.html',required=bool(user.get('must_change_password')))


@auth_bp.route("/logout", methods=["POST"])
def logout():
    from ..security import revoke_session
    revoke_session()
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.select_role"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    def registration_form(form):
        return render_template('auth/registration.html', form=form)
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        middle_name = request.form.get("middle_name", "").strip()
        contact = request.form.get("contact_number", "").strip()
        last_name = request.form.get("last_name", "").strip()
        id_number = request.form.get("id_number", "").strip().upper()
        year_level = "1st Year"
        section = "UNASSIGNED"
        program = canonical_program(request.form.get("program", ""))
        email = request.form.get("email", "").strip().lower()
        sex = request.form.get("sex", "").strip() or None
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        form_data = {k:v for k,v in request.form.items() if "password" not in k and k != "csrf_token"}

        if not all([first_name, last_name, id_number, year_level, section, program, email, password]):
            flash("Please fill in all required fields.", "error")
            return registration_form(form_data)

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return registration_form(form_data)

        if len(password) < PASSWORD_MIN_LENGTH:
            flash(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.", "error")
            return registration_form(form_data)

        if query_one("SELECT student_id FROM students WHERE id_number = :i", {"i": id_number}):
            flash(f"ID number {id_number} is already registered.", "error")
            return registration_form(form_data)

        if query_one("SELECT user_id FROM users WHERE LOWER(email) = :email", {"email": email}):
            flash('An account with this email address already exists.', 'error')
            return registration_form(form_data)

        username = id_number.lower()
        if query_one("SELECT user_id FROM users WHERE username = :u", {"u": username}):
            flash("An account with this ID already exists.", "error")
            return registration_form(form_data)

        full_name = " ".join(v for v in (first_name,middle_name,last_name) if v)
        user_id = execute_returning_id(
            """
            INSERT INTO users (username, password_hash, role, full_name, email, status)
            VALUES (:username, :pw, 'student', :full_name, :email, 'ACTIVE')
            RETURNING user_id INTO :out_id
            """,
            {"username": username, "pw": hash_password(password), "full_name": full_name, "email": email},
        )
        execute(
            """
            INSERT INTO students (user_id, id_number, first_name, middle_name, last_name, contact_number, program, year_level, section, sex, age, progress_school_year, enrollment_type, status)
            VALUES (:user_id, :id_number, :first, :middle, :last, :contact, :program, :year_level, :section, :sex, :age, (SELECT TO_NUMBER(SUBSTR(school_year,1,4)) FROM school_terms WHERE is_active=1), 'REGULAR', 'ACTIVE')
            """,
            {"user_id": user_id, "id_number": id_number, "program": program, "year_level": year_level, "section": section, "sex": sex, "age":request.form.get("age",type=int), "first":first_name,"middle":middle_name,"last":last_name,"contact":contact},
        )

        admins=query_all("SELECT user_id FROM users WHERE role='admin' AND status='ACTIVE'")
        notify_many([a['user_id'] for a in admins],f'Student registered: {full_name}.',link=url_for('admin.students'))
        flash('Registration successful. You can now sign in with your email address or Student ID and password.', 'success')
        return redirect(url_for("auth.login", role="student"))

    return registration_form({})


@auth_bp.route("/forgot-password/<role>", methods=["GET", "POST"])
def forgot_password(role):
    if role not in ROLE_DASHBOARD:
        return redirect(url_for("auth.select_role"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        identifier_clause = 'LOWER(email) = LOWER(:u)' if role=='faculty' else 'username = :u'
        user = query_one(
            f"SELECT user_id, full_name FROM users WHERE {identifier_clause} AND role = :r",
            {"u": username, "r": role},
        )
        if user:
            admins = query_all("SELECT user_id FROM users WHERE role = 'admin' AND status = 'ACTIVE'")
            notify_many(
                [a["user_id"] for a in admins],
                f"Password reset requested by {user['full_name']} ({ROLE_LABELS[role]}, username: {username}).",
                link=url_for("admin.teachers" if role == "faculty" else "admin.students" if role == "student" else "admin.settings"),
            )
        # Always show the same message whether or not the account exists,
        # so this can't be used to check which usernames are registered.
        flash("If that account exists, your system administrator has been notified and will reach out to reset your password.", "success")
        return redirect(url_for("auth.login", role=role))

    return render_template("auth/forgot_password.html", role=role, role_label=ROLE_LABELS[role])


@auth_bp.route('/register/faculty',methods=['GET','POST'])
def register_faculty():
    if request.method=='POST':
        from ..university_accounts import faculty_id
        program=canonical_program(request.form.get('program'))
        if not program:abort(400,description='Choose a supported program.')
        if request.form['password']!=request.form['confirm_password']:abort(400,description='Passwords do not match.')
        email=request.form['email'].strip().lower()
        if query_one('SELECT user_id FROM users WHERE LOWER(email)=:email',{'email':email}):
            flash('An account with this email already exists.','error')
            return render_template('auth/faculty_registration.html',form=request.form),409
        name=' '.join(request.form.get(k,'').strip() for k in ('first_name','middle_name','last_name') if request.form.get(k,'').strip())
        if len(name.encode())>150:abort(400,description='Full name is too long.')
        code=faculty_id()
        uid=execute_returning_id("INSERT INTO users(username,password_hash,role,full_name,email,status,must_change_password) VALUES(:username,:pw,'faculty',:name,:email,'ACTIVE',0) RETURNING user_id INTO :out_id",dict(username=code,pw=hash_password(request.form['password']),name=name,email=email))
        execute("INSERT INTO teachers(user_id,faculty_code,program,status) VALUES(:uid,:code,:program,'ACTIVE')",dict(uid=uid,code=code,program=program))
        flash('Faculty registration successful. Sign in with your institutional email.','success')
        return redirect(url_for('auth.login',role='faculty'))
    return render_template('auth/faculty_registration.html',form={})
