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

    def create_entry_for_attrs(self):
        user = self.get_admin()
        msg = 'Create Entities corresponding to the Attribute of Racktables'

        dict_all = self._fetch_db('Dictionary', ['dict_key', 'dict_value'], distinct=True)
        attr_all = self._fetch_db('Attribute', ['id', 'type', 'name'], distinct=True)
        attrmap_all = self._fetch_db('AttributeMap', ['attr_id', 'chapter_id'], distinct=True)

        data_all = self._fetch_db('Attribute', ['id', 'name'], 'type="dict"')
        data_len = len(data_all)
        for data_index, data in enumerate(data_all):
            entity = self.get_entity('(%s)' % data['name'], user)

            all_entry = Entry.objects.filter(schema=entity)

            data_attr_all = self._fetch_db('Attribute,AttributeMap,Dictionary', ['Dictionary.dict_value, Dictionary.dict_key'],
                    'AttributeMap.attr_id = %d and AttributeMap.chapter_id = Dictionary.chapter_id' % data['id'], distinct=True)
            data_attr_len = len(data_attr_all)
            for data_attr_index, data_attr in enumerate(data_attr_all):
                sys.stdout.write('\r%s: %6d/%6d (%6d/%6d)' % (msg, data_attr_index+1, data_attr_len, data_index+1, data_len))
                sys.stdout.flush()

                if all_entry.filter(name=data_attr['dict_value']).count():
                    entry = all_entry.get(name=data_attr['dict_value'])
                else:
                    entry = Entry.objects.create(name=data_attr['dict_value'],
                                                 schema=entity,
                                                 created_user=user)

                self.dict_map[int(data_attr['dict_key'])] = entry
            print('')

    def create_entry_for_objects(self):
        user = self.get_admin()

        obj_all = self._fetch_db('Object', ['id', 'name', 'objtype_id'], distinct=True)
        dict_all = self._fetch_db('Dictionary', ['dict_key', 'dict_value'], distinct=True)
        attr_all = self._fetch_db('Attribute', ['id', 'type', 'name'], distinct=True)
        attrval_all = self._fetch_db('AttributeValue',
                                     ['object_id', 'object_tid', 'attr_id', 'string_value', 'uint_value', 'float_value'])

        objtypes = [x['objtype_id'] for x in obj_all]

        def create_entry_for_object(entity, user, obj_data):
            entry = Entry.objects.create(name=obj_data['name'], schema=entity, created_user=user)
            entry.complement_attrs(user)

            for attval in [x for x in attrval_all if x['object_id'] == obj_data['id']]:
                rk_attr = [x for x in attr_all if x['id'] == attval['attr_id']][0]

                referral = None
                value = ''

                try:
                    if rk_attr['type'] == 'string':
                        value = attval['string_value']
                    elif rk_attr['type'] == 'uint':
                        value = attval['uint_value']
                    elif rk_attr['type'] == 'float':
                        value = attval['float_value']
                    elif rk_attr['type'] == 'date':
                        vttalue = datetime.fromtimestamp(int(attval['uint_value'])).strftime('%Y-%m-%d %H:%M:%S')
                    elif rk_attr['type'] == 'dict':
                        referral = self.dict_map[int(attval['uint_value'])]

                    attr = entry.attrs.get(name=rk_attr['name'])
                    attr.values.add(AttributeValue.objects.create(**{
                        'created_user': user,
                        'parent_attr': attr,
                        'referral': referral,
                        'value': value,
                        'status': AttributeValue.STATUS_LATEST,
                    }))
                except KeyError as e:
                    print('[WARNING] Failed to set AttributeValue from (Dictionary: "%s")' % attval)

            return entry

        # create Entities
        for data in [x for x in dict_all if x['dict_key'] in objtypes]:

            if not Entity.objects.filter(name=data['dict_value']).count():
                sys.stdout.write('\nCreate Entity "%s"' % data['dict_value'])
                entity = self.get_entity(data['dict_value'], user)

                # get EntityAttrs
                for attr_data in self._fetch_db('AttributeValue',
                                                ['object_tid', 'attr_id', 'uint_value'],
                                                'object_tid = %s' % data['dict_key'],
                                                distinct=True):

                    attrinfo = [x for x in attr_all if x['id'] == attr_data['attr_id']][0]
                    if entity.attrs.filter(name=attrinfo['name'], parent_entity=entity).count():
                        continue

                    if attrinfo['type'] == 'dict':
                        attrtype = AttrTypeValue['object']
                        referral = Entity.objects.get(name='(%s)' % attrinfo['name'])
                    else:
                        attrtype = AttrTypeValue['string']
                        referral = None

                    entity_attr = EntityAttr.objects.create(name=attrinfo['name'],
                                                            type=attrtype,
                                                            created_user=user,
                                                            parent_entity=entity)

                    if referral:
                        entity_attr.referral.add(referral)

                    entity.attrs.add(entity_attr)
            else:
                entity = self.get_entity(data['dict_value'], user)
                sys.stdout.write('\nEntity "%s" has already been created' % data['dict_value'])

            # set status top level
            entity.set_status(Entity.STATUS_TOP_LEVEL)

            # create All entries for objects of Racktables
            part_of_all = [x for x in obj_all if x['objtype_id'] == data['dict_key']]
            obj_len = len(part_of_all)
            for obj_index, obj_data in enumerate(part_of_all):
                sys.stdout.write('\rCreate Entry for "%s" (%6d/%6d)' % (data['dict_value'], obj_index+1, obj_len))
                sys.stdout.flush()

                if not Entry.objects.filter(name=obj_data['name'], schema=entity).count():
                    self.object_map[int(obj_data['id'])] = create_entry_for_object(entity, user, obj_data)
                else:
                    self.object_map[int(obj_data['id'])] = Entry.objects.get(name=obj_data['name'], schema=entity)

    def create_ipaddr_entries(self):
        user = self.get_admin()

        print('\nCreating Entities for IP address...')
        def create_entity_lport():
            if not Entity.objects.filter(name='(LogicalPort)').count():
                entity = self.get_entity('(LogicalPort)', user)

                attrinfos = [
                    {'name': 'I/F', 'type': AttrTypeValue['string']},
                    {'name': 'IPAddress', 'type': AttrTypeValue['object']},
                    {'name': 'AttachedNode', 'type': AttrTypeValue['object']},
                ]
                for attr_data in attrinfos:
                    entity.attrs.add(EntityAttr.objects.create(name=attr_data['name'],
                                                               type=attr_data['type'],
                                                               created_user=user,
                                                               parent_entity=entity))
                return entity
            else:
                return Entity.objects.get(name='(LogicalPort)')

        def create_entity_ipaddr():
            if not Entity.objects.filter(name='(IPaddress)').count():
                entity = self.get_entity('(IPaddress)', user)

                attrinfos = [
                    {'name': 'Network', 'type': AttrTypeValue['object']},
                    {'name': 'Note', 'type': AttrTypeValue['string']},
                ]
                for attr_data in attrinfos:
                    entity.attrs.add(EntityAttr.objects.create(name=attr_data['name'],
                                                               type=attr_data['type'],
                                                               created_user=user,
                                                               parent_entity=entity))
                return entity
            else:
                return Entity.objects.get(name='(IPaddress)')

        def create_entity_network():
            if not Entity.objects.filter(name='(Network)').count():
                entity = self.get_entity('(Network)', user)

                attrinfos = [
                    {'name': 'Route', 'type': AttrTypeValue['object']},
                    {'name': 'Address', 'type': AttrTypeValue['string']},
                    {'name': 'Netmask', 'type': AttrTypeValue['string']},
                    {'name': 'Note', 'type': AttrTypeValue['string']},
                ]
                for attr_data in attrinfos:
                    entity.attrs.add(EntityAttr.objects.create(name=attr_data['name'],
                                                               type=attr_data['type'],
                                                               created_user=user,
                                                               parent_entity=entity))
                return entity
            else:
                return Entity.objects.get(name='(Network)')

        def create_entry_ipaddr(data):
            name = inet_dtos(data['ip'])
            if not Entry.objects.filter(schema=entity_ipaddr, name=name).count():
                entry = Entry.objects.create(name=name, created_user=user, schema=entity_ipaddr)

                entry.complement_attrs(user)
                for attr in entry.attrs.all():
                    params = {
                        'created_user': user,
                        'status': AttributeValue.STATUS_LATEST,
                        'parent_attr': attr,
                        'value': '',
                    }
                    if attr.get_latest_value():
                        continue

                    if attr.name == 'Note':
                        if 'comment' in data:
                            params['value'] += data['comment']
                        if 'name' in data:
                            params['value'] += ' (%s)' % (data['name'])
                    elif attr.name == 'Network':
                        for elem in nw_entry_maps:
                            if elem['addr_first'] <= int(data['ip']) and int(data['ip']) <= elem['addr_last']:
                                params['referral'] = elem['nw_entry']

                    attr.values.add(AttributeValue.objects.create(**params))
            else:
                entry = Entry.objects.get(schema=entity_ipaddr, name=name)

            return entry

        # convert decimal IP address to String
        def inet_dtos(decimal_addr):
            return socket.inet_ntoa(struct.pack('!L', decimal_addr))

        # create Entities
        entity_lport = create_entity_lport()
        entity_ipaddr = create_entity_ipaddr()
        entity_network = create_entity_network()

        # set referrals for each entities
        attr_lport2ipaddr = entity_lport.attrs.get(name='IPAddress')
        if not attr_lport2ipaddr.referral.filter(id=entity_ipaddr.id):
            attr_lport2ipaddr.referral.add(entity_ipaddr)

        attr_ipaddr2network = entity_ipaddr.attrs.get(name='Network')
        if not attr_ipaddr2network.referral.filter(id=entity_network.id):
            attr_ipaddr2network.referral.add(entity_network)

        attr_network2ipaddr = entity_network.attrs.get(name='Route')
        if not attr_network2ipaddr.referral.filter(id=entity_ipaddr.id):
            attr_network2ipaddr.referral.add(entity_ipaddr)

        # create Network Entries
        msg = 'Creating Network Entries'
        network_all = self._fetch_db('IPv4Network', ['ip', 'mask', 'name', 'comment'])
        data_len = len(network_all)
        nw_entry_maps = []
        sys.stdout.write('\n%s' % (msg))
        for data_index, data in enumerate(network_all):
            sys.stdout.write('\r%s: (%6d/%6d)' % (msg, data_index+1, data_len))
            sys.stdout.flush()

            name = "%s/%s" % (inet_dtos(data['ip']), data['mask'])

            if not Entry.objects.filter(schema=entity_network, name=name).count():
                entry = Entry.objects.create(name=name, created_user=user, schema=entity_network)

                entry.complement_attrs(user)
                for attr in entry.attrs.all():
                    params = {
                        'created_user': user,
                        'status': AttributeValue.STATUS_LATEST,
                        'parent_attr': attr,
                        'value': '',
                    }
                    if attr.get_latest_value():
                        continue

                    if attr.name == 'Address':
                        params['value'] = inet_dtos(data['ip'])
                    elif attr.name == 'Netmask':
                        params['value'] = str(data['mask'])
                    elif attr.name == 'Note':
                        params['value'] = data['comment'] if data['comment'] else ''
                    else:
                        continue

                    try:
                        attr.values.add(AttributeValue.objects.create(**params))
                    except django.db.utils.IntegrityError as e:
                        print('[ERROR] (data:%s)' % data)
                        print('[ERROR] entry: %s, attr: %s' % (entry.name, attr.name))
                        raise(e)
            else:
                entry = Entry.objects.get(schema=entity_network, name=name)

            nw_entry_maps.append({
                'addr_first': int(data['ip']),
                'addr_last': int(data['ip']) + (1 << (32 - data['mask'])) - 1,
                'nw_entry': entry,
            })

        # create IPAddress Entries
        ip_map = {}
        msg = 'Creating IPaddress Entries'
        ipaddr_all = self._fetch_db('IPv4Address', ['ip', 'name', 'comment'])
        data_len = len(ipaddr_all)
        sys.stdout.write('\n%s' % (msg))
        for data_index, data in enumerate(ipaddr_all):
            sys.stdout.write('\r%s: (%6d/%6d)' % (msg, data_index+1, data_len))
            sys.stdout.flush()

            ip_map[data['ip']] = create_entry_ipaddr(data)

        # create LogicalPort Entries
        msg = 'Creating LogicalPort Entries'
        ipalloc_all = self._fetch_db('IPv4Allocation', ['object_id', 'ip', 'name', 'type', 'type'])
        data_len = len(ipalloc_all)
        sys.stdout.write('\n%s' % (msg))
        for data_index, data in enumerate(ipalloc_all):
            sys.stdout.write('\r%s: (%6d/%6d)' % (msg, data_index+1, data_len))
            sys.stdout.flush()

            if data['object_id'] not in self.object_map:
                print('\n[Warning] Creating LogicalPort invalid object_id is found: %s' % data)
                continue

            if data['ip'] not in ip_map:
                # Create a non registered IP Address entry in Racktables
                ip_map[data['ip']] = create_entry_ipaddr({'ip':data['ip'], 'comment':data['name']})

            # set Route attribute of Network entry
            if data['type'] == 'router':
                entry_ip = ip_map[data['ip']]
                # get ACLObject for Network Entry
                obj_nw = entry_ip.attrs.get(name='Network').get_latest_value()
                if obj_nw:
                    entry_nw = Entry.objects.get(id=obj_nw.referral.id)
                    attr_route = entry_nw.attrs.get(name='Route')
                    if not attr_route.get_latest_value():
                        attr_route.values.add(AttributeValue.objects.create(**{
                            'created_user': user,
                            'status': AttributeValue.STATUS_LATEST,
                            'parent_attr': attr_route,
                            'referral': entry_ip,
                            'value': '',
                        }))

            node_entry = self.object_map[data['object_id']]

            name = "%s [%s/%s])" % (data['name'], node_entry.name, node_entry.schema.name)
            if not Entry.objects.filter(schema=entity_lport, name=name).count():
                entry = Entry.objects.create(name=name, created_user=user, schema=entity_lport)

                entry.complement_attrs(user)
                for attr in entry.attrs.all():
                    params = {
                        'created_user': user,
                        'status': AttributeValue.STATUS_LATEST,
                        'parent_attr': attr,
                        'value': '',
                    }
                    if attr.get_latest_value():
                        continue

                    if attr.name == 'I/F':
                        params['value'] = data['name']
                    elif attr.name == 'IPAddress':
                        params['referral'] = ip_map[data['ip']]
                    elif attr.name == 'AttachedNode':
                        params['referral'] = node_entry

                        # checks target node schema is registered to the EntityAttr
                        if not attr.schema.referral.filter(id=node_entry.schema.id).count():
                            attr.schema.referral.add(node_entry.schema)
                    else:
                        continue

                    attr.values.add(AttributeValue.objects.create(**params))
            else:
                entry = Entry.objects.get(schema=entity_lport, name=name)

        # create Entities

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
    t0 = datetime.now()
    option = get_options()

    with Driver(option) as driver:
        driver.create_entry_for_attrs()
        print('\nAfter create_entry_for_attrs: %s' % str(datetime.now() - t0))

        driver.create_entry_for_objects()
        print('\nAfter create_entry_for_objects: %s' % str(datetime.now() - t0))

        driver.create_ipaddr_entries()

    print('\nfinished')
