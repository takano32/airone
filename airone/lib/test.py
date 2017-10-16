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

    def _do_login(self, uname, is_admin=False):
        # create test user to authenticate
        user = User(username=uname, is_superuser=is_admin)
        user.set_password(uname)
        user.save()

        self.client.login(username=uname, password=uname)

        return user

    def admin_login(self):
        return self._do_login('admin', True)

    def guest_login(self):
        return self._do_login('guest')

    def open_fixture_file(self, fname):
        test_file_path = inspect.getfile(self.__class__)
        test_base_path = os.path.dirname(test_file_path)

        return open("%s/fixtures/%s" % (test_base_path, fname), 'r')
