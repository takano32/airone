import custom_view
import os

from unittest import mock
from unittest import TestCase

class CustomViewBase(TestCase):
    def setUp(self):
        # re-set directory that has test custom views
        custom_view.BASE_DIR = os.path.dirname(os.path.realpath(__file__)) + '/test_views'

    def test_refer_to_invalid_file(self):
        self.assertFalse(custom_view.is_custom_show_entry('InvalidFile'))
        self.assertFalse(custom_view.is_custom_list_entry('InvalidFile'))
        self.assertFalse(custom_view.is_custom_edit_entry('InvalidFile'))
        self.assertFalse(custom_view.is_custom_do_edit_entry('InvalidFile'))

        self.assertFalse('InvalidFile' in custom_view.CUSTOM_VIEW)

        self.assertEqual(custom_view.call_custom_show_entry('InvalidFile').status_code, 500)
        self.assertEqual(custom_view.call_custom_list_entry('InvalidFile').status_code, 500)
        self.assertEqual(custom_view.call_custom_edit_entry('InvalidFile').status_code, 500)
        self.assertEqual(custom_view.call_custom_do_edit_entry('InvalidFile').status_code, 500)

    def test_refer_to_invalid_method(self):
        self.assertFalse(custom_view.is_custom_show_entry('TestModelEmpty'))
        self.assertFalse(custom_view.is_custom_list_entry('TestModelEmpty'))
        self.assertFalse(custom_view.is_custom_edit_entry('TestModelEmpty'))
        self.assertFalse(custom_view.is_custom_do_edit_entry('TestModelEmpty'))

        self.assertTrue('TestModelEmpty' in custom_view.CUSTOM_VIEW)
        self.assertFalse('show_entry' in custom_view.CUSTOM_VIEW['TestModelEmpty'])

        self.assertEqual(custom_view.call_custom_show_entry('TestModelEmpty').status_code, 500)
        self.assertEqual(custom_view.call_custom_list_entry('TestModelEmpty').status_code, 500)
        self.assertEqual(custom_view.call_custom_edit_entry('TestModelEmpty').status_code, 500)
        self.assertEqual(custom_view.call_custom_do_edit_entry('TestModelEmpty').status_code, 500)

    def test_refer_to_valid_model(self):
        self.assertTrue(custom_view.is_custom_show_entry('TestModelFull'))
        self.assertTrue(custom_view.is_custom_list_entry('TestModelFull'))
        self.assertTrue(custom_view.is_custom_edit_entry('TestModelFull'))
        self.assertTrue(custom_view.is_custom_do_edit_entry('TestModelFull'))

        self.assertTrue('TestModelFull' in custom_view.CUSTOM_VIEW)
        self.assertTrue('show_entry' in custom_view.CUSTOM_VIEW['TestModelFull'])

        self.assertEqual(custom_view.call_custom_show_entry('TestModelFull').status_code, 200)
        self.assertEqual(custom_view.call_custom_list_entry('TestModelFull').status_code, 200)
        self.assertEqual(custom_view.call_custom_edit_entry('TestModelFull').status_code, 200)
        self.assertEqual(custom_view.call_custom_do_edit_entry('TestModelFull').status_code, 200)

    def test_refer_to_valid_model_without_checking(self):
        self.assertFalse(custom_view._isin_cache('TestModelFull', 'show_entry'))
        self.assertEqual(custom_view.call_custom_show_entry('TestModelFull').status_code, 200)
