import unittest
from io import BytesIO

from PIL import Image
from sqlalchemy import func, select

import test_admin as admin_tests
from app.models.media import MediaFile


def photo(fmt='JPEG', size=(2400, 1800), mode='RGB', gps=False):
    image = Image.new(mode, size, (200, 170, 120) if mode == 'RGB' else (200, 170, 120, 0))
    out = BytesIO()
    kwargs = {}
    if gps:
        exif = Image.Exif()
        exif[0x8825] = {1: 'S', 2: (5.0, 47.0, 0.0)}  # GPSInfo: latitude de Natal
        exif[0x010F] = 'Camera do celular'
        exif[0x0112] = 6  # foto tirada "deitada": precisa girar
        kwargs['exif'] = exif
    image.save(out, fmt, **kwargs)
    return out.getvalue()


class MediaTests(unittest.TestCase):
    setUp = admin_tests.AdminTests.setUp
    tearDown = admin_tests.AdminTests.tearDown

    def upload(self, data, content_type='image/jpeg', headers=None):
        return self.client.post('/api/v1/admin/media', content=data,
                                headers={**(self.admin_headers if headers is None else headers),
                                         'Content-Type': content_type})

    def test_only_admins_can_upload(self):
        for headers, status in [({}, 401), (self.customer_headers, 403)]:
            with self.subTest(status=status):
                self.assertEqual(self.upload(photo(), headers=headers).status_code, status)
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(MediaFile)), 0)

    def test_upload_strips_location_resizes_and_serves_with_long_cache(self):
        response = self.upload(photo(gps=True))
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertTrue(body['url'].endswith(f"/api/v1/media/{body['id']}.jpg"))
        # 2400x1800 deitada: gira para 1800x2400 e reduz para caber em 1600.
        self.assertEqual((body['width'], body['height']), (1200, 1600))
        served = self.client.get(f"/api/v1/media/{body['id']}.jpg")
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served.headers['content-type'], 'image/jpeg')
        self.assertIn('immutable', served.headers['cache-control'])
        self.assertEqual(served.headers['cross-origin-resource-policy'], 'cross-origin')
        self.assertEqual(served.headers['x-content-type-options'], 'nosniff')
        stored = Image.open(BytesIO(served.content))
        self.assertEqual(stored.size, (1200, 1600))
        self.assertEqual(len(stored.getexif()), 0, 'a foto não pode levar GPS nem dados da câmera')
        # A mesma foto de novo não duplica.
        again = self.upload(photo(gps=True))
        self.assertEqual(again.json()['id'], body['id'])
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(MediaFile)), 1)

    def test_png_with_transparency_becomes_white_jpeg(self):
        response = self.upload(photo('PNG', (800, 800), 'RGBA'), 'image/png')
        self.assertEqual(response.status_code, 201, response.text)
        served = self.client.get(f"/api/v1/media/{response.json()['id']}.jpg")
        self.assertEqual(Image.open(BytesIO(served.content)).getpixel((10, 10)), (255, 255, 255))

    def test_rejects_fake_huge_tiny_and_wrong_type(self):
        cases = [
            (b'<script>alert(1)</script>', 'image/jpeg', 422),
            (photo(), 'text/html', 422),
            (photo('PNG', (2000, 2000)), 'image/gif', 422),
            (photo(size=(120, 120)), 'image/jpeg', 422),
            (b'\xff' * (4 * 1024 * 1024 + 1), 'image/jpeg', 413),
            (b'', 'image/jpeg', 422),
        ]
        for data, content_type, status in cases:
            with self.subTest(content_type=content_type, status=status, size=len(data)):
                self.assertEqual(self.upload(data, content_type).status_code, status)
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(MediaFile)), 0)

    def test_decompression_bomb_is_refused(self):
        bomb = BytesIO()
        Image.new('1', (9000, 9000)).save(bomb, 'PNG')  # arquivo minúsculo, 81 milhões de pixels
        self.assertLess(len(bomb.getvalue()), 4 * 1024 * 1024)
        self.assertEqual(self.upload(bomb.getvalue(), 'image/png').status_code, 422)

    def test_unknown_or_malformed_media_names_are_not_found(self):
        for name in ['0' * 64 + '.jpg', '../../etc/passwd', 'abc.jpg', '0' * 64 + '.png']:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(f'/api/v1/media/{name}').status_code, 404)

    def test_uploaded_photo_url_is_accepted_as_product_image(self):
        url = self.upload(photo()).json()['url']
        created = self.client.post('/api/v1/admin/products', headers=self.admin_headers,
                                   json={**self.product_body, 'image_url': url.replace('http://', 'https://')})
        self.assertEqual(created.status_code, 201, created.text)


if __name__ == '__main__':
    unittest.main()
