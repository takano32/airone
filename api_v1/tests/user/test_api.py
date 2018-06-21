from airone.lib.test import AironeViewTest
from datetime import datetime, timedelta

from rest_framework.authtoken.models import Token

from user.models import User
from django.contrib.auth.models import User as DjangoUser


class APITest(AironeViewTest):
    def test_create_token(self):
        admin = self.admin_login()

        resp = self.client.put('/api/v1/user/access_token')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue('results' in resp.json())
        self.assertTrue(isinstance(resp.json()['results'], str))
        self.assertEqual(resp.json()['results'], str(Token.objects.get(user=admin)))

    def test_refresh_token(self):
        admin = self.admin_login()
        token = Token.objects.create(user=admin)

        resp = self.client.put('/api/v1/user/access_token')
        self.assertEqual(resp.status_code, 200)
        self.assertNotEqual(resp.json()['results'], str(token))

    def test_get_token(self):
        admin = self.admin_login()
        token = Token.objects.create(user=admin)

        resp = self.client.get('/api/v1/user/access_token')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['results'], str(token))

    def test_refresh_token_using_token(self):
        # This processing doesn't login but just only create an User 'guest'
        user = User.objects.create(username='guest')
        token = Token.objects.create(user=DjangoUser.objects.get(id=user.id))

        resp = self.client.get('/api/v1/user/access_token', **{
            'HTTP_AUTHORIZATION': 'Token %s' % str(token),
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['results'], str(token))
