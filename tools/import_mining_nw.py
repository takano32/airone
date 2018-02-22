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

    def create_entries(self):
        user = self.get_admin()

        entity = self.get_entity('Network Switch', user)
        with open('entries.csv', 'r') as f:
            head_line = f.readline().rstrip('\n')

            # detected EntityAttrs for each parameters
            attrbases = {}
            for i in range(2, 8):
                attrname = head_line.split(',')[i]
                attrbases[i] = entity.attrs.get(name=attrname)

            # create Entry according to the specified parameters
            for dataline in f.readlines():
                data = dataline.rstrip('\n').split(',')
                print('[onix/01] (%d) %s' % (i, data))

                entry = Entry.objects.create(name=data[1], schema=entity, created_user=user)
                entry.complement_attrs(user)

                # add AttributeValue for each parameters
                for i in range(2, 8):
                    attrbase = attrbases.get(i)
                    attr = entry.attrs.get(schema=attrbase)
                   
                    if attrbase.type & AttrTypeValue['object']:
                        refobj = [Entry.objects.filter(name=data[i], schema=x) for x in attrbase.referral.all()]
                        if refobj and any([x.count() for x in refobj]):
                            ref_entry = refobj[0].first()
                            entry.attrs.get(schema=attrbase).add_value(user, str(ref_entry.id))

                    elif attrbase.type & AttrTypeValue['string']:
                        entry.attrs.get(schema=attrbase).add_value(user, data[i])

def get_options():
    parser = OptionParser()

    (options, _) = parser.parse_args()

    return options

if __name__ == "__main__":
    t0 = datetime.now()
    option = get_options()

    with Driver(option) as driver:
        driver.create_entries()

    print('\nfinished (%s)' % str(datetime.now() - t0))
