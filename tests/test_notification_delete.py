import unittest
import re
from unittest.mock import patch
from flask import session
from werkzeug.exceptions import BadRequest
from audit_fixture import AuditFixture
from app.routes.notifications import delete_selected

class NotificationDeleteTests(unittest.TestCase):
    def test_multiple_selection_passes_full_request_validation(self):
        with AuditFixture() as f:
            client=f.client('student')
            page=client.get('/app/student').data.decode()
            token=re.search(r'name="csrf_token" value="([^"]+)"',page).group(1)
            with patch('app.db.execute') as write:
                response=client.post('/notifications/delete',data={'csrf_token':token,'notification_id':['12','13']})
                self.assertEqual(response.status_code,302)
                self.assertIn('user_id=:user_id',write.call_args.args[0])
    def test_selected_delete_is_owned_and_parameterized(self):
        with AuditFixture() as f,f.app.test_request_context('/notifications/delete',method='POST',data={'notification_id':['12','13','12']}):
            session.update(user_id=7,role='student')
            with patch('app.db.execute') as write:
                delete_selected()
                sql,params=write.call_args.args
                self.assertIn('user_id=:user_id',sql)
                self.assertEqual(params,{'user_id':7,'n0':12,'n1':13})
    def test_bad_selection_does_not_write(self):
        for ids in [[],['bad'],['0'],['1 OR 1=1']]:
            with AuditFixture() as f,f.app.test_request_context('/notifications/delete',method='POST',data={'notification_id':ids}):
                session.update(user_id=7,role='student')
                with patch('app.db.execute') as write,self.assertRaises(BadRequest):delete_selected()
                write.assert_not_called()

if __name__=='__main__':unittest.main()
