
from django.test import TestCase
from django.contrib.auth.models import Group
from user.models import User

class ModelTest(TestCase):
    def test_create_group(self):
        name = "ほげgroup"
        user1 = self._create_user("user1")
        user2 = self._create_user("user2")

        group = Group(name=name)
        group.save()

        user1.groups.add(group)
        user2.groups.add(group)

        group = Group.objects.get(name=name)
        self.assertTrue(isinstance(group, Group))
        self.assertEqual(group.name, name)

        self.assertEqual(user1.groups.count(), 1)
        self.assertEqual(user2.groups.count(), 1)
        
    def _create_user(self, name):
        user = User(username=name)
        user.save()
        return user

