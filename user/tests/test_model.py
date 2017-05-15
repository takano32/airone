from django.test import TestCase
from user.models import User, Member


class ModelTest(TestCase):
    def test_make_user(self):
        user = User(name='ほげ', userid='hoge', passwd='fuga')

        self.assertTrue(isinstance(user, Member))
        self.assertEqual(user.name, 'ほげ')
        self.assertEqual(user.userid, 'hoge')
        self.assertEqual(user.type, 0)
