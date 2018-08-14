import inspect
import os

from django.test import TestCase, Client, override_settings
from django.conf import settings
from user.models import User
from .elasticsearch import ESS


@override_settings(ES_CONFIG={
    'NODES': ['localhost:9200'],
    'INDEX': 'test-airone',
    'MAXIMUM_RESULTS_NUM': 10000,
    'TIMEOUT': 300
})
class AironeTestCase(TestCase):
    def setUp(self):
        # Before starting test, clear all documents in the Elasticsearch of test index
        self._es = ESS()
        self._es.recreate_index()

class AironeViewTest(AironeTestCase):
    def setUp(self):
        super(AironeViewTest, self).setUp()

        self.client = Client()

        if hasattr(settings, 'AIRONE') and 'ENABLE_PROFILE' in settings.AIRONE:
            settings.AIRONE['ENABLE_PROFILE'] = False

    def _do_login(self, uname, is_superuser=False):
        # create test user to authenticate
        user = User(username=uname, is_superuser=is_superuser)
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
