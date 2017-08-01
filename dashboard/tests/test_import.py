import mock
import re

from airone.lib.test import AironeViewTest
from datetime import datetime
from django.urls import reverse
from entity.models import Entity, AttributeBase
from entry.models import Entry, Attribute, AttributeValue
from user.models import User


class ImportTest(AironeViewTest):
    def test_import_entity(self):
        user = self.admin_login()

        fp = self.open_fixture_file('entity.yaml')
        resp = self.client.post(reverse('dashboard:do_import'), {'file': fp})
        self.assertEqual(resp.status_code, 303)
        fp.close()

        self.assertEqual(Entity.objects.count(), 3)
        self.assertEqual(Entity.objects.get(name='foo').id, 1)
        self.assertEqual(AttributeBase.objects.last().name, 'attr5')
        self.assertEqual(Entity.objects.get(name='foo').attr_bases.count(), 3)

    def test_import_entity_with_unnecessary_param(self):
        user = self.admin_login()
        warning_messages = []

        fp = self.open_fixture_file('entity_with_unnecessary_param.yaml')
        with mock.patch('dashboard.views.Logger') as lg_mock:
            def side_effect(message):
                warning_messages.append(message)

            lg_mock.warning = mock.Mock(side_effect=side_effect)

            resp = self.client.post(reverse('dashboard:do_import'), {'file': fp})
            self.assertEqual(resp.status_code, 303)
        fp.close()

        # checks that warning messagees were outputted
        self.assertEqual(len(warning_messages), 2)
        self.assertTrue(re.match(r'^.*Entity.*Unnecessary key is specified$',
                                 warning_messages[0]))
        self.assertTrue(re.match(r'^.*AttributeBase.*Unnecessary key is specified$',
                                 warning_messages[1]))

        self.assertEqual(Entity.objects.count(), 1)
        self.assertEqual(AttributeBase.objects.count(), 2)

    def test_import_entity_without_mandatory_param(self):
        user = self.admin_login()
        warning_messages = []

        fp = self.open_fixture_file('entity_without_mandatory_param.yaml')
        with mock.patch('dashboard.views.Logger') as lg_mock:
            def side_effect(message):
                warning_messages.append(message)

            lg_mock.warning = mock.Mock(side_effect=side_effect)

            resp = self.client.post(reverse('dashboard:do_import'), {'file': fp})
            self.assertEqual(resp.status_code, 303)
        fp.close()

        # checks that warning messagees were outputted
        self.assertEqual(len(warning_messages), 2)
        self.assertTrue(re.match(r"^.*Entity.*Mandatory key doesn't exist$",
                                 warning_messages[0]))
        self.assertTrue(re.match(r"^.*AttributeBase.*Mandatory key doesn't exist$",
                                 warning_messages[1]))

        self.assertEqual(Entity.objects.count(), 1)
        self.assertEqual(AttributeBase.objects.count(), 2)

    def test_import_entity_with_spoofing_user(self):
        admin = self.admin_login()

        # A user who creates original mock object
        user = User.objects.create(username='test-user')

        Entity.objects.create(id=6, name='baz-original', created_user=user)
        
        fp = self.open_fixture_file('entity.yaml')
        resp = self.client.post(reverse('dashboard:do_import'), {'file': fp})
        self.assertEqual(resp.status_code, 303)
        fp.close()

        # checks that import data doens't appied
        self.assertEqual(Entity.objects.get(id=6).name, 'baz-original')

        # checks that the AttributeBase objects which refers invalid Entity won't create
        self.assertEqual(AttributeBase.objects.filter(name='attr4').count(), 0)

    def test_import_entry(self):
        user = self.admin_login()

        fp = self.open_fixture_file('entry.yaml')
        resp = self.client.post(reverse('dashboard:do_import'), {'file': fp})
        self.assertEqual(resp.status_code, 303)
        fp.close()

        # checks that imported objects were normally created
        self.assertEqual(Entry.objects.count(), 1)
        self.assertEqual(Attribute.objects.count(), 3)

        # checks that after_save_instance processing was normally worked
        self.assertEqual(Entry.objects.last().attrs.count(), 3)
        self.assertEqual(Entry.objects.last().attrs.get(name='aa').values.count(), 1)

        # checks that a new AttribueValue was created by import-data
        self.assertEqual(Attribute.objects.get(name='bb').values.count(), 2)
