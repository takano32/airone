from django.test import TestCase
from group.models import Group, Member, User


class ModelTest(TestCase):
    def test_make_group(self):
        group = Group(name='test-g')
        group.save()

        self.assertTrue(isinstance(group, Member))
        self.assertEqual(list(group.users.all()), [])

    def test_register_users(self):
        group = Group(name='test-g')
        group.save()

        # makes users to register
        user1 = User(name='hoge')
        user1.save()
        user2 = User(name='fuga')
        user2.save()

        group.users.add(user1)
        group.users.add(user2)

        self.assertEqual(len(group.users.all()), 2)
        self.assertEqual(group.users.first(), user1)
