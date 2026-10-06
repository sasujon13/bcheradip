from io import BytesIO
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from cheradip.models import Customer, CustomerToken


class ProfilePictureApiTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()
        self.user = Customer.objects.create_user(
            username='01700000001',
            password='test-password',
            fullName='Profile Picture User',
            acctype='Student',
        )
        token = CustomerToken.objects.create(key='profile-picture-token', customer=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.key}')

    def tearDown(self):
        self.media_override.disable()
        self.media_directory.cleanup()

    @staticmethod
    def image_upload(file_name, image_format, content_type):
        data = BytesIO()
        Image.new('RGB', (48, 32), color=(25, 120, 110)).save(data, format=image_format)
        return SimpleUploadedFile(file_name, data.getvalue(), content_type=content_type)

    def test_jpg_jpeg_png_and_webp_uploads_return_public_relative_url(self):
        formats = (
            ('picture.jpg', 'JPEG', 'image/jpeg'),
            ('picture.jpeg', 'JPEG', 'image/jpeg'),
            ('picture.png', 'PNG', 'image/png'),
            ('picture.webp', 'WEBP', 'image/webp'),
        )
        for file_name, image_format, content_type in formats:
            with self.subTest(file_name=file_name):
                response = self.client.post(
                    '/api/profile_picture/',
                    {'image': self.image_upload(file_name, image_format, content_type)},
                    format='multipart',
                    secure=True,
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.data['profileImageUrl'].startswith('/manage/media/profiles/'))
                self.assertNotIn('127.0.0.1', response.data['profileImageUrl'])

                self.user.refresh_from_db()
                self.assertTrue(self.user.profile_image.storage.exists(self.user.profile_image.name))

    def test_clear_removes_stored_picture_and_url(self):
        self.client.post(
            '/api/profile_picture/',
            {'image': self.image_upload('picture.png', 'PNG', 'image/png')},
            format='multipart',
            secure=True,
        )
        response = self.client.delete('/api/profile_picture/', secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['profileImageUrl'])
        self.user.refresh_from_db()
        self.assertFalse(self.user.profile_image)
