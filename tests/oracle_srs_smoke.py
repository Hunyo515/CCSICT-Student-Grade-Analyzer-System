"""Read-only route smoke against real Oracle using isolated test sessions."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flask import session
from app import create_app
from app.db import query_all,query_one
from app.security import create_session
from config import Config


def main():
    with tempfile.TemporaryDirectory(dir=Path('tests').resolve()) as tmp:
        class SmokeConfig(Config):
            TESTING=True
            SECURITY_DB=str(Path(tmp)/'security.db')
            SESSION_COOKIE_SECURE=False
        app=create_app(SmokeConfig);count=0
        paths={'admin':['/app/admin','/app/admin/analytics','/app/admin/subjects','/app/admin/subjects?q=DSA','/app/admin/subjects?page=2','/admin/classes','/admin/students','/admin/teachers','/admin/settings'],
               'faculty':['/app/teacher','/app/teacher/analytics','/app/teacher/top-performers'],
               'student':['/app/student','/app/student/grades','/app/student/analytics','/app/student/rank','/app/student/join','/student/profile']}
        with app.app_context():
            users=query_all("SELECT user_id,username,full_name,role,password_hash,email FROM users WHERE status='ACTIVE'")
            examples={}
            for user in users:
                if user['role'] in examples:continue
                if user['role'] in ('faculty','student'):
                    table,key=('teachers','teacher_id') if user['role']=='faculty' else ('students','student_id')
                    profile=query_one(f'SELECT {key} FROM {table} WHERE user_id=:id AND status=\'ACTIVE\'',{'id':user['user_id']})
                    if not profile:continue
                    user.update(profile)
                examples[user['role']]=user
            for role,user in examples.items():
                if role=='faculty':
                    classes=query_all('SELECT assignment_id FROM teacher_subjects WHERE teacher_id=:id',{'id':user['teacher_id']})
                    for row in classes[:2]:
                        for tab in ('grades','weighting','class'):paths[role].append(f'/app/teacher/class/{row["assignment_id"]}?tab={tab}')
                if role=='admin':
                    classes=query_all('SELECT assignment_id FROM teacher_subjects FETCH FIRST 2 ROWS ONLY')
                    paths[role].append('/admin/students/assign')
        for role in paths:
            paths[role]+=[path+'?term_filter=all' for path in paths[role][:4] if '?' not in path]
        paths['student'].append('/university/enlistme')
        paths['admin']+=['/app/admin/subjects?program=BSDSA','/admin/subjects/new?program=BSDSA','/university/credentials']
        for role,user in examples.items():
            client=app.test_client()
            with app.test_request_context('/'):
                session.update({k:v for k,v in user.items() if k!='password_hash'});create_session(user);values=dict(session)
            with client.session_transaction() as s:s.update(values)
            for path in paths[role]:
                response=client.get(path,follow_redirects=True)
                assert response.status_code==200,(path,response.status_code)
                print(role,path,response.status_code);count+=1
        print('Real Oracle read-only routes passed:',count)


if __name__=='__main__':main()
