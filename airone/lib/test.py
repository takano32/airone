import inspect
import os

from django.test import TestCase, Client
from django.conf import settings
from user.models import User


class AironeViewTest(TestCase):
    def setUp(self):
        self.client = Client()

        if hasattr(settings, 'AIRONE') and 'ENABLE_PROFILE' in settings.AIRONE:
            settings.AIRONE['ENABLE_PROFILE'] = False

    def admin_login(self):
        # create test user to authenticate
        user = User(username='admin')
        user.set_password('admin')
        user.save()

        self.client.login(username='admin', password='admin')

        return user

    def open_fixture_file(self, fname):
        test_file_path = inspect.getfile(self.__class__)
        test_base_path = os.path.dirname(test_file_path)

        return open("%s/fixtures/%s" % (test_base_path, fname), 'r')
