import re

from django.test import TestCase
from unittest.mock import patch
from unittest.mock import Mock

from entry import tasks


class TaskTest(TestCase):
    @patch('entry.tasks.Logger')
    def test_reconstruct_referral_cache_with_invalid_attrv_id(self, mock_logger):
        def log_handler(x): 
            self.err_msg = x

        mock_logger.error.side_effect = log_handler

        tasks._reconstruct_referral_cache(1234)

        # checks that error log will be shown by specifying an invalid attribute id
        self.assertTrue(hasattr(self, 'err_msg'))
        self.assertIsNotNone(re.match(r"^.*1234.*is not existed", self.err_msg))
