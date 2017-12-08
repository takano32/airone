import json

from airone.lib.test import AironeViewTest
from airone.lib.types import AttrTypeValue

from django.urls import reverse

from entity.models import Entity, EntityAttr
from entry.models import Entry, Attribute, AttributeValue

from xml.etree import ElementTree

TEST_RACK_HEIGHT = 3


class ViewTest(AironeViewTest):
    def setUp(self):
        super(ViewTest, self).setUp()

        admin = self.admin_login()

        self.srv_entity = Entity.objects.create(name='Server', created_user=admin)

        # create RackSpace entity
        self.rs_entity = Entity.objects.create(name='RackSpace (%d-U)' % TEST_RACK_HEIGHT,
                                               created_user=admin)
        for unit_no in range(TEST_RACK_HEIGHT, 0, -1):
            attr = EntityAttr.objects.create(name=("%d" % unit_no),
                                             type=AttrTypeValue['array_object'],
                                             created_user=admin,
                                             parent_entity=self.rs_entity)
            attr.referral.add(self.srv_entity)
            self.rs_entity.attrs.add(attr)

        # create Rack entity
        attrinfo = [
            {'name': 'RackSpace', 'referrals': [self.rs_entity]},
            {'name': 'ZeroU', 'referrals': [self.srv_entity]},
        ]
        rack_entity = Entity.objects.create(name='ラック', created_user=admin)

        for attr in attrinfo:
            rack_attr = EntityAttr.objects.create(name=attr['name'],
                                                  type=AttrTypeValue['object'],
                                                  created_user=admin,
                                                  parent_entity=self.rs_entity)
            for referral in attr['referrals']:
                rack_attr.referral.add(referral)

            rack_entity.attrs.add(rack_attr)

        # create Rack entry
        self.rack = Entry.objects.create(name='TestR', schema=rack_entity, created_user=admin)
        self.rack.complement_attrs(admin)

    def create_rs_entry(self, user):
        rs_entry = Entry.objects.create(name='TestRackSpace',
                                        schema=self.rs_entity,
                                        created_user=user)
        rs_attr = self.rack.attrs.get(name='RackSpace')
        rs_attr.values.add(AttributeValue.objects.create(**{
            'created_user': user,
            'parent_attr': rs_attr,
            'referral': rs_entry,
            'status': AttributeValue.STATUS_LATEST,
        }))

        return rs_entry

    def test_show_entry_without_rackspace_entry(self):
        resp = self.client.get(reverse('entry:show', args=[self.rack.id]))
        self.assertEqual(resp.status_code, 200)

        # custom_view doesn't apper because of target entry have no RackSpace entry
        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNone(root.find('.//div[@id="rackspace"]'))

    def test_show_entry_with_rackspace_entry(self):
        user = self.guest_login()

        # create RackSpace entry to show custom_view
        self.create_rs_entry(user)

        resp = self.client.get(reverse('entry:show', args=[self.rack.id]))
        self.assertEqual(resp.status_code, 200)

        # custom_view doesn't apper because of target entry have no RackSpace entry
        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertIsNotNone(root.find('.//div[@id="rackspace"]'))

    def test_edit_entry_without_rackspace_entry(self):
        resp = self.client.get(reverse('entry:edit', args=[self.rack.id]))
        self.assertEqual(resp.status_code, 200)

        # custom_view doesn't apper because of target entry have no RackSpace entry
        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertFalse(any(e.text == 'RackSpace' for e in root.findall('.//h2')))

    def test_edit_entry_with_rackspace_entry(self):
        user = self.guest_login()

        # create RackSpace entry to show custom_view
        self.create_rs_entry(user)

        resp = self.client.get(reverse('entry:edit', args=[self.rack.id]))
        self.assertEqual(resp.status_code, 200)

        # custom_view doesn't apper because of target entry have no RackSpace entry
        root = ElementTree.fromstring(resp.content.decode('utf-8'))
        self.assertTrue(any(e.text == 'RackSpace' for e in root.findall('.//h2')))

    def test_do_edit(self):
        user = self.guest_login()

        # create RackSpace entry to show custom_view
        rs_entry = self.create_rs_entry(user)

        # create Server entry to set RackSpace
        srv1 = Entry.objects.create(name='srv0001', schema=self.srv_entity, created_user=user)
        srv2 = Entry.objects.create(name='srv0002', schema=self.srv_entity, created_user=user)

        params = {
            'entry_name': self.rack.name,
            'attrs': [],
            'rse_info': [
                {'position': '3','target_id': str(srv1.id)},
                {'position': '3','target_id': str(srv2.id)},
                {'position': '2','target_id': str(srv1.id)},
            ],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[self.rack.id]),
                                json.dumps(params),
                                'application/json')
        self.assertEqual(resp.status_code, 200)

        for attr in rs_entry.attrs.all():
            self.assertIsNotNone(attr)

        self.assertEqual(rs_entry.attrs.get(name='1').get_latest_value().data_array.count(), 0)
        self.assertEqual(rs_entry.attrs.get(name='2').get_latest_value().data_array.count(), 1)
        self.assertEqual(rs_entry.attrs.get(name='3').get_latest_value().data_array.count(), 2)
