import mock
import re

from airone.lib.test import AironeViewTest
from airone.lib import types as atype
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

        # checks each objects are created safety
        self.assertEqual(Entity.objects.count(), 3)
        self.assertEqual(AttributeBase.objects.count(), 4)

        # checks keeping the correspondence relationship with id and name
        self.assertEqual(Entity.objects.get(id='1').name, 'entity1')
        self.assertEqual(AttributeBase.objects.get(id='5').name, 'attr-obj')

        # checks contains required attributes (for Entity)
        entity = Entity.objects.get(name='entity')
        self.assertEqual(entity.note, 'note1')

        # checks contains required attributes (for AttributeBase)
        self.assertEqual(entity.attr_bases.count(), 4)
        self.assertEqual(entity.attr_bases.get(name='attr-str').type, atype.AttrTypeStr)
        self.assertEqual(entity.attr_bases.get(name='attr-obj').type, atype.AttrTypeObj)
        self.assertEqual(entity.attr_bases.get(name='attr-arr-str').type, atype.AttrTypeArrStr)
        self.assertEqual(entity.attr_bases.get(name='attr-arr-obj').type, atype.AttrTypeArrObj)
        self.assertFalse(entity.attr_bases.get(name='attr-str').is_mandatory)
        self.assertTrue(entity.attr_bases.get(name='attr-obj').is_mandatory)

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
        self.assertTrue(re.match(r'^.*AttrBase.*Unnecessary key is specified$',
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
        self.assertTrue(re.match(r"^.*AttrBase.*Mandatory key doesn't exist$",
                                 warning_messages[1]))

        self.assertEqual(Entity.objects.count(), 1)
        self.assertEqual(AttributeBase.objects.count(), 2)

    def test_import_entity_with_spoofing_user(self):
        admin = self.admin_login()
        warning_messages = []

        # A user who creates original mock object
        user = User.objects.create(username='test-user')

        Entity.objects.create(id=3, name='baz-original', created_user=user)
        
        fp = self.open_fixture_file('entity.yaml')
        with mock.patch('import_export.resources.logging') as lg_mock:
            def side_effect(message):
                warning_messages.append(str(message))

            lg_mock.exception = mock.Mock(side_effect=side_effect)

            resp = self.client.post(reverse('dashboard:do_import'), {'file': fp})
            self.assertEqual(resp.status_code, 303)
        fp.close()

        # checks to show warning messages
        msg = r"failed to identify entity object"
        self.assertEqual(len(warning_messages), 4)
        self.assertTrue(all([re.match(msg, x) for x in warning_messages]))

        # checks that import data doens't appied
        entity = Entity.objects.get(id=3)
        self.assertEqual(entity.name, 'baz-original')

        # checks that the AttributeBase objects which refers invalid Entity won't create
        self.assertEqual(entity.attr_bases.count(), 0)
        self.assertEqual(AttributeBase.objects.filter(name='attr-str').count(), 0)

    def test_import_entry(self):
        user = self.admin_login()

        fp = self.open_fixture_file('entry.yaml')
        resp = self.client.post(reverse('dashboard:do_import'), {'file': fp})
        self.assertEqual(resp.status_code, 303)
        fp.close()

        # checks that imported objects were normally created
        self.assertEqual(Entry.objects.count(), 5)
        self.assertEqual(Attribute.objects.count(), 4)

        # checks that after_save_instance processing was normally worked
        entry = Entry.objects.get(name='entry1')
        self.assertEqual(entry.attrs.count(), 4)
        self.assertEqual(entry.attrs.get(name='attr-str').type, atype.AttrTypeStr)
        self.assertEqual(entry.attrs.get(name='attr-obj').type, atype.AttrTypeObj)
        self.assertEqual(entry.attrs.get(name='attr-arr-str').type, atype.AttrTypeArrStr)
        self.assertEqual(entry.attrs.get(name='attr-arr-obj').type, atype.AttrTypeArrObj)

        # checks that a new AttribueValue was created by import-data
        self.assertEqual(Attribute.objects.get(name='attr-str').values.count(), 2)

        # checks for the Array String attributes
        attr = Attribute.objects.get(name='attr-arr-str')
        self.assertEqual(attr.values.count(), 1)

        attr_value = attr.values.last()
        self.assertTrue(attr_value.status & AttributeValue.STATUS_DATA_ARRAY_PARENT)
