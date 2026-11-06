import io,re,unittest
from unittest.mock import patch
from PIL import Image
from srs_fixture import SrsFixture
from app.profile_photos import prepare_photo

class StudentProfileUpdatesTests(unittest.TestCase):
    def test_photo_validation_and_owned_upload(self):
        with self.assertRaises(ValueError):prepare_photo(io.BytesIO(b'<svg>not a photo</svg>'))
        data=io.BytesIO();Image.new('RGB',(80,120),'blue').save(data,'PNG')
        with SrsFixture() as f:
            f.app.instance_path=f.tmp
            client=f.client('student');page=client.get('/student/profile').data.decode()
            token=re.search(r'name="csrf_token" value="([^"]+)"',page).group(1)
            self.assertNotIn('id="termFilter"',page)
            response=client.post('/student/profile/photo',data={'csrf_token':token,'profile_photo':(io.BytesIO(data.getvalue()),'picture.png')},content_type='multipart/form-data')
            self.assertEqual(response.status_code,302)
            photo=client.get('/student/profile/photo');self.assertEqual(photo.status_code,200)
            with Image.open(io.BytesIO(photo.data)) as image:self.assertEqual(image.size,(512,512));self.assertEqual(image.format,'JPEG')
            photo.close()
            self.assertIn(b'class="student-avatar"',client.get('/app/student').data)

    def test_personal_details_cannot_be_changed(self):
        from flask import session
        from werkzeug.exceptions import Forbidden
        from app.routes import student
        with SrsFixture() as f,f.app.test_request_context('/student/profile',method='POST',data=dict(full_name='Changed Name',email='changed@example.com')):
            session.update(user_id=3,student_id=3,role='student')
            with patch.object(student,'execute') as write,self.assertRaises(Forbidden):student.profile()
            write.assert_not_called()
        with SrsFixture() as f:
            page=f.client('student').get('/student/profile').data
            self.assertNotIn(b'name="full_name"',page)
            self.assertNotIn(b'Save profile',page)
            self.assertIn(b'profile-photo-trigger',page)

    def test_view_grade_newest_first_and_subjects_are_not_links(self):
        context=dict(term=None,student={},report={'own':[]},enrollments=[dict(assignment_id=1,school_year='2023-2024',semester='1st Semester',status='DRAFT',subject_code='OLD',subject_name='Old subject',teacher_name='Teacher',units=3),dict(assignment_id=2,school_year='2026-2027',semester='2nd Semester',status='DRAFT',subject_code='NEW',subject_name='New subject',teacher_name='Teacher',units=3)])
        with SrsFixture() as f:
            client=f.client('student')
            with patch('app.routes.srs.student_data',return_value=context):response=client.get('/app/student/view-grade')
            self.assertEqual(response.status_code,200)
            self.assertLess(response.data.index(b'2026-2027'),response.data.index(b'2023-2024'))
            self.assertNotIn(b'<a class="student-grade-title"',response.data)

if __name__=='__main__':unittest.main()
