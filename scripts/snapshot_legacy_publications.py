"""Preserve existing published percentages as explicitly labeled legacy snapshots."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_app,gradebook as gb
from app.db import query_all,query_one,get_connection
from app.grading import compute_weighted_total
from flask import session


def main():
    if '--apply' not in sys.argv:raise SystemExit('Pass --apply to preserve published legacy revisions.')
    app=create_app()
    with app.test_request_context('/'):
        actor=query_one("SELECT user_id FROM users WHERE role='admin' AND status='ACTIVE' FETCH FIRST 1 ROWS ONLY")
        if not actor:raise RuntimeError('An active administrator is required for migration provenance.')
        session.update(user_id=actor['user_id'])
        rows=query_all("SELECT assignment_id FROM teacher_subjects WHERE status='PUBLISHED' AND aggregation='LEGACY'")
        count=0
        for item in rows:
            aid=item['assignment_id'];row=gb.classroom(aid,True)
            if gb.latest(aid,'PUBLICATION'):continue
            payload=gb.snapshot(row);cats,assessments,roster,scores=gb.content(aid)
            weights={c['category_id']:c['weight_percent'] for c in cats}
            for student in payload['students']:
                student['result']['total']=compute_weighted_total(scores.get(student['enrollment_id'],{}),assessments,weights)
                student['result']['equivalent']=None
                student['result']['legacy']=True
            payload['legacy']=True
            gb.save_version(row,'PUBLICATION',payload,reason='Migration of existing teacher-published records. No administrator approval or ISU equivalence inferred.')
            count+=1
        get_connection().commit()
        print('Legacy publications preserved:',count)


if __name__=='__main__':main()
