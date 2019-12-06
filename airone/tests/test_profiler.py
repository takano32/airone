import mock
import re
import unittest

from airone.lib.profile import airone_profile
from django.conf import settings
from django.http.request import HttpRequest
from testfixtures import LogCapture


class AirOneProfilerTest(unittest.TestCase):

    def setUp(self):
        # this saves original configurations to be able to retrieve them
        self.org_conf_profile = None
        if hasattr(settings, 'AIRONE') and 'ENABLE_PROFILE' in settings.AIRONE:
            self.org_conf_profile = settings.AIRONE['ENABLE_PROFILE']

        # this enables do profiling
        settings.AIRONE['ENABLE_PROFILE'] = True

    def tearDown(self):
        # this retrieves original configurations
        settings.AIRONE['ENABLE_PROFILE'] = self.org_conf_profile

    def test_airone_profile_decorator(self):
        # Initialize mock request objects
        mock_user = mock.Mock()
        mock_user.id = 1234

        mock_request = mock.Mock(spec=HttpRequest)
        mock_request.method = 'GET'
        mock_request.path = '/test'
        mock_request.user = mock_user

        @airone_profile
        def mock_handler(request):
            return 'mock_response'

        # This is the output format of the airone profiling result
        pattern = r'^\(Profiling result: 0.[0-9]+s\) \(user-id: 1234\) GET /test$'

        with LogCapture() as log:
            # call mocked http request handler which decorate airone_profile
            mock_handler(mock_request)

            # This checks output is matched with expected format as below
            # e.g. "[06/Dec/2019 17:34:36] (Profiling result: 0.000049s) (user-id: 1234) GET /test"
            [(log_app, log_level, log_context)] = log.actual()
            self.assertEqual(log_app, 'airone')
            self.assertEqual(log_level, 'INFO')
            self.assertTrue(re.match(pattern, log_context))
