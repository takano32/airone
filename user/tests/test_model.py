from django.test import TestCase
from user.models import User
from django.contrib.auth.models import User as DjangoUser


class ModelTest(TestCase):
    def test_make_user(self):
        user = User(username='ほげ', email='hoge@fuga.com', password='fuga')
        user.save()

        self.assertTrue(isinstance(user, DjangoUser))
        self.assertEqual(user.username, 'ほげ')
        self.assertEqual(user.authorized_type, 0)
        self.assertIsNotNone(user.date_joined)
