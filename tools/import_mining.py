import MySQLdb

import django
import os
import sys
import socket, struct

from datetime import datetime
from optparse import OptionParser

# append airone directory to the default path
sys.path.append("%s/../" % os.path.dirname(os.path.abspath(__file__)))

# prepare to load the data models of AirOne
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "airone.settings")

# load AirOne application
django.setup()

# import each models of AirOne
from user.models import User
from entity.models import Entity, EntityAttr
from entry.models import Entry, Attribute, AttributeValue
from airone.lib.types import AttrTypeValue


class Driver(object):
    def __init__(self, option):
        self.option = option
        self.rack_map = {}
        self.object_map = {} # object_id => Entry for Object
        self.dict_map = {} # dict_id => Entry for Dict
        self.port_map = {} # port_id => Entry for Port

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def get_admin(self):
        if User.objects.filter(username='admin').count():
            return User.objects.get(username='admin')
        else:
            return User.objects.create(username='admin')

    def get_entity(self, entity_name, user=None):
        if Entity.objects.filter(name=entity_name).count():
            return Entity.objects.get(name=entity_name)

        if not user:
            raise ValueError('user is not specified')

        return Entity.objects.create(name=entity_name, created_user=user)

    def get_entry(self, name, schema, user=None):
        if Entry.objects.filter(name=name, schema=schema).count():
            return Entry.objects.get(name=name, schema=schema)

        if not user:
            raise ValueError('user is not specified')

        return Entry.objects.create(name=name, schema=schema, created_user=user)

    def get_rack_referral_entities(self):
        referrals = []
        for data in self._fetch_db('EntityLink', ['child_entity_id'],
                                  'parent_entity_type="rack" and child_entity_type="object"'):

            if data['child_entity_id'] in self.object_map:
                rack_entity = self.object_map[data['child_entity_id']].schema

                if rack_entity not in referrals:
                    referrals.append(rack_entity)

        return referrals

    def create_entry_rig(self):
        user = self.get_admin()

        def set_attr_value(attr, val, attr_type=AttrTypeValue['object'], count=1):
            referral = None
            value = ''
            if attr_type == AttrTypeValue['string']:
                value = val
            elif attr_type == AttrTypeValue['object']:
                referral = Entry.objects.get(id=val)
            elif attr_type == AttrTypeValue['array_named_object']:
                referral = Entry.objects.get(id=val)
    
            attr_value = AttributeValue.objects.create(**{
                'created_user': user,
                'parent_attr': attr,
                'referral': referral if not attr_type == AttrTypeValue['array_named_object'] else None,
                'value': value,
                'status': AttributeValue.STATUS_LATEST,
            })

            if attr_type == AttrTypeValue['array_named_object']:
                attr_value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

                [attr_value.data_array.add(AttributeValue.objects.create(**{
                    'created_user': user,
                    'parent_attr': attr,
                    'referral': referral,
                    'value': '#%d' % (x + 1) if attr_type == AttrTypeValue['array_named_object'] else value,
                    'status': AttributeValue.STATUS_LATEST,
                 })) for x in range(0, count)]

            attr.values.add(attr_value)

        entity = self.get_entity('RIG/GPU', user)
        for i in range(1, 801):
            entity_name = "rig%04d-g" % (i)
            sys.stdout.write('\rCreate RIG Entry (%4d/%4d)' % (i, 800))
            sys.stdout.flush()


            if Entry.objects.filter(name=entity_name, schema=entity).count():
                entry = Entry.objects.get(name=entity_name, schema=entity)
            else:
                entry = Entry.objects.create(name=entity_name, schema=entity, created_user=user)
                entry.complement_attrs(user)

            set_attr_value(entry.attrs.get(name='ラック'), 124)
            set_attr_value(entry.attrs.get(name='使用状況'), 33)
            set_attr_value(entry.attrs.get(name='マザーボード'), 126)
            set_attr_value(entry.attrs.get(name='CPU'), 102)
            set_attr_value(entry.attrs.get(name='RAM'), 114)
            set_attr_value(entry.attrs.get(name='電源'), 132)
            set_attr_value(entry.attrs.get(name='GPU'), 108, AttrTypeValue['array_named_object'], 8)

def get_options():
    parser = OptionParser()

    (options, _) = parser.parse_args()

    return options

if __name__ == "__main__":
    t0 = datetime.now()
    option = get_options()

    with Driver(option) as driver:
        driver.create_entry_rig()

    print('\nfinished (%s)' % str(datetime.now() - t0))
