from django.test import TestCase, Client
from user.models import User


class AironeViewTest(TestCase):
    def setUp(self):
        self.client = Client()

    def admin_login(self):
        # create test user to authenticate
        user = User(username='admin')
        user.set_password('admin')
        user.save()

        self.client.login(username='admin', password='admin')

        return user
