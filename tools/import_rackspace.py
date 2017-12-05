import MySQLdb

import django
import os
import sys

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
        self.object_map = {}

    def __enter__(self):
        self._conn = MySQLdb.connect(db=self.option.database,
                                     user=self.option.userid,
                                     passwd=self.option.passwd,
                                     charset="utf8")

        self.cursor = self._conn.cursor(MySQLdb.cursors.DictCursor)

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cursor.close()
        self._conn.close()

    def _db_query(self, query):
        self.cursor.execute(query)
        return self.cursor.fetchall()

    def _fetch_db(self, table, params=['*'], condition=None, distinct=None):
        query = 'select '
        if distinct:
            query += 'distinct '

        query += '%s from %s' % (','.join(params), table)

        if condition:
            query += ' where %s' % condition

        return self._db_query(query)

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

    def get_rack_attr(self, entry, user):
        if not entry.schema.attrs.filter(name='ラック').count():
            attr = EntityAttr.objects.create(name='ラック',
                                             type=AttrTypeValue['object'],
                                             created_user=user,
                                             parent_entity=entry.schema)

            attr.referral.add(Entity.objects.get(name='ラック'))

            # update schema attribute
            entry.schema.attrs.add(attr)

        # create Attribute
        entry.complement_attrs(user)

        return entry.attrs.get(name='ラック')

    def create_datacenter(self):
        sys.stdout.write('\nCreate "データセンタ"')
        user = self.get_admin()
        # create Entity
        entity = self.get_entity('データセンタ', user)
        entity.set_status(Entity.STATUS_TOP_LEVEL)

        # create Entries
        data_all = self._fetch_db('Location', ['name'])
        data_len = len(data_all)
        for data_index, data in enumerate(data_all):
            if Entry.objects.filter(name=data['name'], schema=entity).count():
                continue

            self.get_entry(name=data['name'], user=user, schema=entity)
            sys.stdout.write('\rCreate "データセンタ": %d/%d' % (data_index+1, data_len))
            sys.stdout.flush()

        return entity

    def create_floor(self, dc_entity):
        sys.stdout.write('\nCreate "フロア"')
        user = self.get_admin()

        # create Entity
        entity = self.get_entity('フロア', user)
        entity.set_status(Entity.STATUS_TOP_LEVEL)

        entity_attr = EntityAttr.objects.create(name='データセンタ',
                                                type=AttrTypeValue['object'],
                                                created_user=user,
                                                parent_entity=entity)
        entity_attr.referral.add(dc_entity)
        entity.attrs.add(entity_attr)

        # create Entries
        data_all = self._fetch_db('Row', ['name', 'location_name'])
        data_len = len(data_all)
        for data_index, data in enumerate(data_all):
            if Entry.objects.filter(name="%s-%s" % (data['location_name'], data['name']),
                                    schema=entity).count():
                continue

            entry = self.get_entry("%s-%s" % (data['location_name'], data['name']), entity, user)

            # create Attribute
            attr = entry.add_attribute_from_base(entity_attr, user)

            # create AttributeValue
            attr_value = AttributeValue(created_user=user, parent_attr=attr)
            attr_value.referral = Entry.objects.get(name=data['location_name'], schema=dc_entity)
            attr_value.set_status(AttributeValue.STATUS_LATEST)

            attr_value.save()
            attr.values.add(attr_value)

            sys.stdout.write('\rCreate "フロア": %d/%d' % (data_index+1, data_len))
            sys.stdout.flush()

        return entity

    def create_rackspace_entry(self):
        sys.stdout.write('\nCreate RackSpace Entry...')
        user = self.get_admin()

        rse_entity = self.get_entity('RackSpaceEntry')

        def create_rse_entry(data):
            rack_entry = self.rack_map[data['rack_id']]

            rse_entry = self.get_entry(name="%s-%dU" % (rack_entry.name, data['unit_no']),
                                       schema=rse_entity, user=user)

            # make Attributes if needed
            rse_entry.complement_attrs(user)

            if data['atom'] == 'front':
                attr = rse_entry.attrs.get(name='前面')
            else:
                attr = rse_entry.attrs.get(name='背面')

            # append Value of Entry
            attr.values.add(AttributeValue.objects.create(**{
                'created_user': user,
                'parent_attr': attr,
                'referral': self.object_map[data['object_id']],
                'status': AttributeValue.STATUS_LATEST,
            }))

            return rse_entry

        data_all = self._fetch_db('RackSpace',
                                  ['rack_id', 'unit_no', 'atom', 'object_id'],
                                  'state="T" and atom <> "interior"')
        data_len = len(data_all)
        for data_index, data in enumerate(data_all):
            sys.stdout.write('\rCreate RackSpace Entry: %6d/%6d' % (data_index+1, data_len))
            sys.stdout.flush()

            if (data['rack_id'] not in self.rack_map or
                data['object_id'] not in self.object_map):
                continue

            rack_entry = self.rack_map[data['rack_id']]
            rack_height = rack_entry.attrs.get(name='height').get_latest_value().value

            rs_entry = self.get_entry(name='RackSpace (%s)' % rack_entry.name,
                                      schema=self.get_entity('RackSpace (%s-U)' % rack_height),
                                      user=user)

            # create Attributes of RackSpace
            rs_entry.complement_attrs(user)

            attr_rs_entry = rs_entry.attrs.get(name="%d" % data['unit_no'])
            # clear latest flag
            [x.del_status(AttributeValue.STATUS_LATEST) for x in attr_rs_entry.values.all()]

            attr_rs_entry.values.add(AttributeValue.objects.create(**{
                'created_user': user,
                'parent_attr': attr_rs_entry,
                'referral': create_rse_entry(data),
                'status': AttributeValue.STATUS_LATEST,
            }))

            attr_rack_rs = rack_entry.attrs.get(name='RackSpace')
            # clear latest flag
            [x.del_status(AttributeValue.STATUS_LATEST) for x in attr_rack_rs.values.all()]

            attr_rack_rs.values.add(AttributeValue.objects.create(**{
                'created_user': user,
                'parent_attr': attr_rack_rs,
                'referral': rs_entry,
                'status': AttributeValue.STATUS_LATEST,
            }))

            target_entry = self.object_map[data['object_id']]
            rack_attr = self.get_rack_attr(target_entry, user)
            if not rack_attr.get_latest_value():
                rack_attr.values.add(AttributeValue.objects.create(**{
                    'created_user': user,
                    'parent_attr': rack_attr,
                    'referral': rack_entry,
                    'status': AttributeValue.STATUS_LATEST,
                }))

    def create_rack(self, floor_entity):
        sys.stdout.write('\nCreate "ラック"')

        user = self.get_admin()

        # create Entity
        entity = self.get_entity('ラック', user)
        entity.set_status(Entity.STATUS_TOP_LEVEL)

        new_attrs = [
            {'name': 'フロア', 'refers': [ floor_entity ], 'type': AttrTypeValue['object']},
            {'name': 'height', 'refers': [], 'type': AttrTypeValue['string']},
            {'name': 'RackSpace', 'refers': Entity.objects.filter(name__regex='RackSpace '), 'type': AttrTypeValue['object']},
        ]
        for info in new_attrs:
            if entity.attrs.filter(name=info['name']).count():
                continue

            entity_attr = EntityAttr.objects.create(name=info['name'],
                                                    type=info['type'],
                                                    created_user=user,
                                                    parent_entity=entity)

            for refer in info['refers']:
                entity_attr.referral.add(refer)

            entity.attrs.add(entity_attr)

        # create Entries
        data_all = self._fetch_db('Rack', ['id', 'name', 'row_name', 'location_name', 'height'])
        data_len = len(data_all)
        for data_index, data in enumerate(data_all):
            rack_name = name="%s-%s-%s" % (data['location_name'],
                                           data['row_name'],
                                           data['name'])

            sys.stdout.write('\rCreate "ラック": %d/%d' % (data_index+1, data_len))
            sys.stdout.flush()

            if Entry.objects.filter(name=rack_name, schema=entity).count():
                self.rack_map[data['id']] = Entry.objects.get(name=rack_name)
                continue

            entry = self.get_entry(name=rack_name, user=user, schema=entity)

            # set rack map
            self.rack_map[data['id']] = entry

            # create Attribute
            entry.complement_attrs(user)

            for attrname in ['フロア', 'height']:
                [x.del_status(AttributeValue.STATUS_LATEST) for x in entry.attrs.get(name=attrname).values.all()]

            # set Values
            entry.attrs.get(name='フロア').values.add(AttributeValue.objects.create(**{
                'created_user': user,
                'parent_attr': entry.attrs.get(name='フロア'),
                'referral': Entry.objects.get(name="%s-%s" % (data['location_name'], data['row_name']), schema=floor_entity),
                'status': AttributeValue.STATUS_LATEST,
            }))
            entry.attrs.get(name='height').values.add(AttributeValue.objects.create(**{
                'created_user': user,
                'parent_attr': entry.attrs.get(name='height'),
                'value': data['height'],
                'status': AttributeValue.STATUS_LATEST,
            }))

        return entity

    def create_rackspace(self):
        sys.stdout.write('\nChecking referral of RackSpaceEntry...')
        user = self.get_admin()

        rse_entity = self.get_entity('RackSpaceEntry', user)

        referrals = []
        data_all = self._fetch_db('EntityLink',
                                  ['parent_entity_id', 'child_entity_id'],
                                  'parent_entity_type="rack" and child_entity_type="object"')
        data_len = len(data_all)
        for data_index, data in enumerate(data_all):
            sys.stdout.write('\rChecking referral of RackSpaceEntry: %6d/%6d' % (data_index+1, data_len))

            if data['child_entity_id'] in self.object_map:
                rack_entity = self.object_map[data['child_entity_id']].schema

                if rack_entity not in referrals:
                    referrals.append(rack_entity)

        sys.stdout.write('\nCreate RackSpace Entity...')
        for attrname in ['前面', '背面']:
            # skip if it has been already created
            if rse_entity.attrs.filter(name=attrname).count():
                continue

            # create a new EntityAttr
            entity_attr = EntityAttr.objects.create(name=attrname,
                                                    type=AttrTypeValue['object'],
                                                    created_user=user,
                                                    parent_entity=rse_entity)

            # register Entity which RackSpace refers to
            for referral in referrals:
                entity_attr.referral.add(referral)

            rse_entity.attrs.add(entity_attr)

        data_all = self._fetch_db('Rack', ['height'], condition=None, distinct=True)
        data_len = len(data_all)
        for data_index, data in enumerate(data_all):
            entity = self.get_entity('RackSpace (%d-U)' % data['height'], user)

            # create a new EntityAttr
            for unit_no in range(data['height'], 0, -1):
                if not entity.attrs.filter(name=("%s" % unit_no)).count():
                    entity_attr = EntityAttr.objects.create(name=("%s" % unit_no),
                                                            type=AttrTypeValue['object'],
                                                            created_user=user,
                                                            parent_entity=rse_entity)
                    entity_attr.referral.add(rse_entity)
                    entity.attrs.add(entity_attr)

            sys.stdout.write('\rCreate RackSpace entities: %6d/%6d' % (data_index+1, data_len))
            sys.stdout.flush()

    def update_server_entity(self, rack_entity):
        sys.stdout.write('\nUpdate Server Entity...')
        user = self.get_admin()

        entity = self.get_entity('Server', user)
        if not entity.attrs.filter(name='ラック').count():
            entity_attr = EntityAttr.objects.create(name='ラック',
                                                    type=AttrTypeValue['object'],
                                                    created_user=user,
                                                    parent_entity=entity)
            entity_attr.referral.add(rack_entity)
            entity.attrs.add(entity_attr)

    def set_zerou(self):
        sys.stdout.write('\nCreate Zero-U Entries.')
        user = self.get_admin()

        data_all = self._fetch_db('EntityLink',
                                  ['parent_entity_id', 'child_entity_id'],
                                  'parent_entity_type="rack" and child_entity_type="object"')
        data_len = len(data_all)
        for data_index, data in enumerate(data_all):
            if data['parent_entity_id'] in self.rack_map:
                rack_entry = self.rack_map[data['parent_entity_id']]

                srv_obj = self._fetch_db('Object', ['name'], 'id=%s' % data['child_entity_id'])
                if srv_obj and Entry.objects.filter(name=srv_obj[0]['name']).count():
                    target_entry = Entry.objects.get(name=srv_obj[0]['name'])
                    attr = self.get_rack_attr(target_entry, user)
                    if attr.get_latest_value():
                        continue

                    attr_value = AttributeValue(created_user=user, parent_attr=attr)
                    attr_value.referral = rack_entry
                    attr_value.set_status(AttributeValue.STATUS_LATEST)

                    attr_value.save()
                    attr.values.add(attr_value)

            sys.stdout.write('\rCreate Zero-U Entries: %6d/%6d' % (data_index+1, data_len))
            sys.stdout.flush()

    def create_object_map(self):
        sys.stdout.write('\nCreate object_map')

        data_all = self._fetch_db('Object', ['id', 'name'])
        data_len = len(data_all)
        for data_index, data in enumerate(data_all):
            if Entry.objects.filter(name=data['name']).count():
                self.object_map[data['id']] = Entry.objects.get(name=data['name'])

            sys.stdout.write('\rCreate object_map: %6d/%6d' % (data_index+1, data_len))
            sys.stdout.flush()

def get_options():
    parser = OptionParser()

    parser.add_option("-u", "--userid", type=str, dest="userid", default='rackuser',
                      help="Username to access the Database on the MySQL")
    parser.add_option("-p", "--passwd", type=str, dest="passwd",
                      help="Password associated with the Username to authenticate")
    parser.add_option("-d", "--database", type=str, dest="database", default='racktables',
                      help="Database name that contains Racktables data")

    (options, _) = parser.parse_args()

    return options

if __name__ == "__main__":
    option = get_options()

    with Driver(option) as driver:
        # make object_map
        driver.create_object_map()

        # create a new rackspace entity
        driver.create_rackspace()

        # create Entity & Entry for Data Center
        dc_entity = driver.create_datacenter()

        # create Entity & Entry for Floor
        fr_entity = driver.create_floor(dc_entity)

        # create Entity & Entry for Rack
        rk_entity = driver.create_rack(fr_entity)

        # create Server Entity
        driver.update_server_entity(rk_entity)

        # filling Zero-U
        driver.set_zerou()

        # create a new rackspace entries
        driver.create_rackspace_entry()
