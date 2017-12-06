import json

from airone.lib.test import AironeViewTest
from airone.lib.types import AttrTypeValue

from django.urls import reverse

from entity.models import Entity, EntityAttr
from entry.models import Entry, Attribute, AttributeValue

from xml.etree import ElementTree

TEST_RACK_HEIGHT = 2


class ViewTest(AironeViewTest):
    def setUp(self):
        super(ViewTest, self).setUp()

        admin = self.admin_login()

        self.srv_entity = Entity.objects.create(name='Server', created_user=admin)

        # create RackSpaceEntry entity
        rse_entity = Entity.objects.create(name='RackSpaceEntry', created_user=admin)
        for attrname in ['前面', '背面']:
            # create a new EntityAttr
            attr = EntityAttr.objects.create(name=attrname,
                                             type=AttrTypeValue['object'],
                                             created_user=admin,
                                             parent_entity=rse_entity)
            attr.referral.add(self.srv_entity)
            rse_entity.attrs.add(attr)

        # create RackSpace entity
        self.rs_entity = Entity.objects.create(name='RackSpace (%d-U)' % TEST_RACK_HEIGHT,
                                               created_user=admin)
        for unit_no in range(TEST_RACK_HEIGHT, 0, -1):
            attr = EntityAttr.objects.create(name=("%d" % unit_no),
                                             type=AttrTypeValue['object'],
                                             created_user=admin,
                                             parent_entity=self.rs_entity)
            attr.referral.add(rse_entity)
            self.rs_entity.attrs.add(attr)

        # create Rack entity
        rack_entity = Entity.objects.create(name='ラック', created_user=admin)
        rack_attr = EntityAttr.objects.create(name='RackSpace',
                                              type=AttrTypeValue['object'],
                                              created_user=admin,
                                              parent_entity=self.rs_entity)
        rack_attr.referral.add(self.rs_entity)
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
        srv_entry = Entry.objects.create(name='srv0001',
                                         schema=self.srv_entity,
                                         created_user=user)

        params = {
            'entry_name': self.rack.name,
            'attrs': [],
            'rse_info': [
                {'position': '2', 'rse_side': 'rse_front', 'value': str(srv_entry.id)},
                {'position': '2', 'rse_side': 'rse_back',  'value': '0'},
                {'position': '1', 'rse_side': 'rse_front', 'value': '0'},
                {'position': '1', 'rse_side': 'rse_back',  'value': '0'},
            ],
        }
        resp = self.client.post(reverse('entry:do_edit', args=[self.rack.id]),
                                json.dumps(params),
                                'application/json')
        self.assertEqual(resp.status_code, 200)

        self.assertIsNone(rs_entry.attrs.get(name='1').get_latest_value())
        self.assertIsNotNone(rs_entry.attrs.get(name='2').get_latest_value())

        rse_entry = Entry.objects.get(id=rs_entry.attrs.get(name='2').get_latest_value().referral.id)
        self.assertIsNotNone(rse_entry.attrs.get(name='前面').get_latest_value())
        self.assertIsNone(rse_entry.attrs.get(name='背面').get_latest_value())

        target_entry = Entry.objects.get(id=rse_entry.attrs.get(name='前面').get_latest_value().referral.id)
        self.assertEqual(target_entry, srv_entry)
