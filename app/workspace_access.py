"""Route historical bookmarks to the SRS UI; retire superseded write paths."""
from flask import request,session,redirect,url_for,abort


def install_workspace_routes(app):
    @app.before_request
    def workspace_routes():
        if not session.get('user_id'):return
        endpoint=request.endpoint or ''
        if endpoint in ('admin.assign_student_to_section','student.join_course','srs.joining'):
            if request.method=='GET':return redirect(url_for('admin.classes' if session['role']=='admin' else 'university.enlistme'))
            abort(410,description='Use student EnlistMe for enrollment in an opened upcoming term.')
        if request.method=='GET':
            if endpoint=='admin.subjects':return redirect(url_for('srs.subject_catalog',**request.args.to_dict()))
            if endpoint=='admin.dashboard':return redirect(url_for('srs.admin_home'))
            if endpoint=='admin.analytics':return redirect(url_for('srs.admin_analytics'))
            if endpoint=='faculty.dashboard':return redirect(url_for('srs.teacher_home'))
            if endpoint=='faculty.top_performers':return redirect(url_for('srs.top_performers'))
            if endpoint in ('faculty.grade_entry','faculty.grade_weighting','faculty.section_detail','faculty.grade_registry','faculty.analytics'):
                aid=request.args.get('assignment_id',type=int)
                if aid:
                    if endpoint=='faculty.analytics':return redirect(url_for('srs.teacher_analytics',assignment_id=aid))
                    tab={'faculty.grade_weighting':'weighting','faculty.section_detail':'class'}.get(endpoint,'grades')
                    return redirect(url_for('srs.classroom',aid=aid,tab=tab))
                return redirect(url_for('srs.teacher_home'))
            if endpoint=='faculty.grade_export' and request.args.get('assignment_id',type=int):return redirect(url_for('srs.export',aid=request.args.get('assignment_id',type=int)))
            if endpoint in ('student.dashboard','student.grades','student.analytics','student.my_rank'):
                target={'student.dashboard':'srs.student_home','student.grades':'srs.student_grades','student.analytics':'srs.student_analytics','student.my_rank':'srs.student_rank'}[endpoint]
                return redirect(url_for(target))
            if endpoint.startswith('workspace.'):
                aid=(request.view_args or {}).get('aid') or request.args.get('assignment_id',type=int)
                if session['role']=='faculty':
                    return redirect(url_for('srs.classroom',aid=aid)) if aid else redirect(url_for('srs.teacher_home'))
                if session['role']=='student':return redirect(url_for('srs.join' if endpoint=='workspace.join' else 'srs.student_home',**({'code':request.args['code']} if request.args.get('code') else {})))
                return redirect(url_for('admin.classes' if aid else 'srs.admin_home'))
        if request.method=='POST' and endpoint=='student.join_course':
            return redirect(url_for('srs.join'),code=307)
        if request.method=='POST' and endpoint=='admin.assign_subject':return redirect(url_for('srs.create_class'),code=307)
        if request.method=='POST' and (endpoint.startswith('faculty.') or endpoint.startswith('workspace.')):
            abort(409,description='This form belongs to a previous workflow. Open the current dashboard and review the latest class before saving.')
        if request.method=='POST' and endpoint=='admin.assign_student_to_section':
            from .db import query_one
            aid=request.form.get('assignment_id',type=int)
            row=query_one('SELECT status FROM teacher_subjects WHERE assignment_id=:id FOR UPDATE WAIT 5',{'id':aid})
            if row and row['status'] in ('SUBMITTED','PUBLISHED'):abort(409,description='Submitted or published rosters are locked.')
