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

    def get_rack_referral_entities(self):
        referrals = []
        for data in self._fetch_db('EntityLink', ['child_entity_id'],
                                  'parent_entity_type="rack" and child_entity_type="object"'):

            if data['child_entity_id'] in self.object_map:
                rack_entity = self.object_map[data['child_entity_id']].schema

                if rack_entity not in referrals:
                    referrals.append(rack_entity)

        return referrals

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

            data_attr_all = self._fetch_db('Attribute,AttributeMap,Dictionary',
                                           ['Dictionary.dict_value, Dictionary.dict_key'],
                                           'AttributeMap.attr_id = %d and AttributeMap.chapter_id = Dictionary.chapter_id' % data['id'],
                                           distinct=True)
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

    def create_ports_and_links(self):
        user = self.get_admin()

        port_all = self._fetch_db('Port', ['id', 'object_id', 'name', 'type'])
        link_all = self._fetch_db('Link', ['porta', 'portb', 'cable'])
        if_all = self._fetch_db('PortOuterInterface', ['id', 'oif_name'])

        if_map = {}

        # Create Entities for Interfaces
        msg = 'Create Interface type Entries'
        sys.stdout.write('\n%s' % (msg))
        if not Entity.objects.filter(name='(PortInterface)').count():
            if_entity = Entity.objects.create(name='(PortInterface)', created_user=user)
        else:
            if_entity = self.get_entity('(PortInterface)')

        if_len = len(if_all)
        for if_index, if_data in enumerate(if_all):
            sys.stdout.write('\r%s (%6d/%6d)' % (msg, if_index+1, if_len))
            sys.stdout.flush()

            if not Entry.objects.filter(name=if_data['oif_name'], schema=if_entity).count():
                if_map[if_data['id']] = Entry.objects.create(name=if_data['oif_name'],
                                                             created_user=user,
                                                             schema=if_entity)
            else:
                if_map[if_data['id']] = Entry.objects.get(name=if_data['oif_name'], schema=if_entity)

        # Create Entities for Port and Links
        sys.stdout.write('\nCreate Entity for Port and Links')
        if not Entity.objects.filter(name='(Port)').count():
            port_entity = Entity.objects.create(name='(Port)', created_user=user)

            attrinfos = [
                {'name': 'I/F TYPE', 'type': AttrTypeValue['object'], 'referrals': [if_entity]},
                {'name': '装着機器', 'type': AttrTypeValue['object'], 'referrals': []},
                {'name': '対向ポート', 'type': AttrTypeValue['object'], 'referrals': [ port_entity ]},
                {'name': 'Note', 'type': AttrTypeValue['string'], 'referrals': []},
            ]
            for attr_data in attrinfos:
                entity_attr = EntityAttr.objects.create(name=attr_data['name'],
                                                        type=attr_data['type'],
                                                        created_user=user,
                                                        parent_entity=port_entity)
                for referral in attr_data['referrals']:
                    entity_attr.referral.add(referral)

                port_entity.attrs.add(entity_attr)
        else:
            port_entity = self.get_entity('(Port)')

        obj_referrals = []
        def create_port_entry(if_name, if_type, entry, data):
            port_entry = self.get_entry(if_name, port_entity, user)
            port_entry.complement_attrs(user)

            # set attr if_type
            for attr_name in ['I/F TYPE', '装着機器']:
                attr = port_entry.attrs.get(name=attr_name)
                params = {
                    'created_user': user,
                    'status': AttributeValue.STATUS_LATEST,
                    'parent_attr': attr,
                    'value': '',
                }

                if attr_name == 'I/F TYPE':
                    params['referral'] = if_type
                elif attr_name == '装着機器':
                    params['referral'] = entry

                    # update AttributeValue referral
                    if entry.schema not in obj_referrals:
                        obj_referrals.append(entry.schema)
                        attr.schema.referral.add(entry.schema)

                attr.values.add(AttributeValue.objects.create(**params))

            return port_entry

        # Create Entries
        msg = 'Create Port Entries'
        sys.stdout.write('\n%s' % msg)
        port_len = len(port_all)
        for port_index, port_data in enumerate(port_all):
            sys.stdout.write('\r%s (%6d/%6d)' % (msg, port_index+1, port_len))
            sys.stdout.flush()

            if port_data['object_id'] not in self.object_map:
                print('[Warning] (import_port_and_links) object(id:%s) is not in AirOne' % port_data['object_id'])
                continue

            obj_entry = self.object_map[port_data['object_id']]

            # create Port entry and set to the object entry
            if_name = "%s (%s)" % (obj_entry.name, port_data['name'])
            if_type = if_map[port_data['type']]

            if not Entry.objects.filter(name=if_name, schema=port_entity).count():
                self.port_map[port_data['id']] = create_port_entry(if_name, if_type, obj_entry, port_data)
            else:
                # The case when Racktables has same port data
                 self.port_map[port_data['id']] = Entry.objects.filter(name=if_name, schema=port_entity).last()

        def set_link_information(port_entry, otherside_port, note=''):
            attr = port_entry.attrs.get(name='対向ポート')

            if not attr.get_latest_value():
                attr.values.add(AttributeValue.objects.create(**{
                    'created_user': user,
                    'status': AttributeValue.STATUS_LATEST,
                    'parent_attr': attr,
                    'referral': otherside_port,
                    'value': '',
                }))

        # Fill-out otherside information from Link data
        msg = 'Set Link information to Port entries'
        sys.stdout.write('\n%s' % msg)
        link_len = len(link_all)
        for link_index, link_data in enumerate(link_all):
            sys.stdout.write('\r%s (%6d/%6d)' % (msg, link_index+1, link_len))
            sys.stdout.flush()

            if (link_data['porta'] not in self.port_map or
                link_data['portb'] not in self.port_map):
                print('[Warning] (import_port_and_links) Target Port entry is not in AirOne [%s]' % (link_data))
                continue

            porta = self.port_map[link_data['porta']]
            portb = self.port_map[link_data['portb']]

            set_link_information(porta, portb)
            set_link_information(portb, porta)

            # set Note information for PortA
            note_attr = porta.attrs.get(name='Note')
            if note_attr.get_latest_value() and link_data['cable']:
                note_attr.values.add(AttributeValue.objects.create(**{
                    'created_user': user,
                    'status': AttributeValue.STATUS_LATEST,
                    'parent_attr': note_attr,
                    'value': link_data['cable'],
                }))

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

    def create_rackspace_entries(self):
        user = self.get_admin()

        def create_rackspace():
            sys.stdout.write('\nCreate "RackSpaces"')

            entities = []
            data_all = self._fetch_db('Rack', ['height'], condition=None, distinct=True)
            data_len = len(data_all)
            for data_index, data in enumerate(data_all):
                sys.stdout.write('\rCreate RackSpace entities: %6d/%6d' % (data_index+1, data_len))
                sys.stdout.flush()

                entity_name = 'RackSpace (%d-U)' % data['height']
                if not Entity.objects.filter(name=entity_name).count():
                    entity = self.get_entity(entity_name, user)

                    # create a new EntityAttr
                    for unit_no in range(data['height'], 0, -1):
                        if not entity.attrs.filter(name=("%s" % unit_no)).count():
                            entity_attr = EntityAttr.objects.create(name=("%s" % unit_no),
                                                                    type=AttrTypeValue['array_object'],
                                                                    created_user=user,
                                                                    parent_entity=entity)

                            [entity_attr.referral.add(e) for e in self.get_rack_referral_entities()]

                            entity.attrs.add(entity_attr)

                    entities.append(entity)
                else:
                    entities.append(self.get_entity(entity_name))

            return entities

        def create_datacenter():
            sys.stdout.write('\nCreate "データセンタ"')

            entity = self.get_entity('データセンタ', user)
            entity.set_status(Entity.STATUS_TOP_LEVEL)

            # create Entries
            data_all = self._fetch_db('Location', ['name'])
            data_len = len(data_all)
            for data_index, data in enumerate(data_all):
                sys.stdout.write('\rCreate "データセンタ": %d/%d' % (data_index+1, data_len))
                sys.stdout.flush()

                if Entry.objects.filter(name=data['name'], schema=entity).count():
                    continue

                self.get_entry(name=data['name'], user=user, schema=entity)

            return entity

        def create_floor(dc_entity):
            sys.stdout.write('\nCreate "フロア"')

            # create Entity
            if not Entity.objects.filter(name='フロア').count():
                entity = self.get_entity('フロア', user)
                entity.set_status(Entity.STATUS_TOP_LEVEL)

                entity_attr = EntityAttr.objects.create(name='データセンタ',
                                                        type=AttrTypeValue['object'],
                                                        created_user=user,
                                                        parent_entity=entity)
                entity_attr.referral.add(dc_entity)
                entity.attrs.add(entity_attr)
            else:
                entity = self.get_entity('フロア')

            # create Entries
            data_all = self._fetch_db('Row', ['name', 'location_name'])
            data_len = len(data_all)
            for data_index, data in enumerate(data_all):
                sys.stdout.write('\rCreate "フロア": %d/%d' % (data_index+1, data_len))
                sys.stdout.flush()

                entry_name = "%s-%s" % (data['location_name'], data['name'])
                if Entry.objects.filter(name=entry_name, schema=entity).count():
                    continue

                entry = self.get_entry(entry_name, entity, user)

                # create Attribute
                entry.complement_attrs(user)
                attr = entry.attrs.get(name='データセンタ')

                # create AttributeValue
                attr_value = AttributeValue(created_user=user, parent_attr=attr)
                attr_value.referral = Entry.objects.get(name=data['location_name'], schema=dc_entity)
                attr_value.set_status(AttributeValue.STATUS_LATEST)

                attr_value.save()
                attr.values.add(attr_value)

            return entity

        def create_rack(floor_entity):
            sys.stdout.write('\nCreate "ラック"')

            user = self.get_admin()

            # create Entity
            if not Entity.objects.filter(name='ラック').count():
                entity = self.get_entity('ラック', user)
                entity.set_status(Entity.STATUS_TOP_LEVEL)

                new_attrs = {
                    'フロア': {'refers': [ floor_entity ], 'type': AttrTypeValue['object']},
                    'height': {'refers': [], 'type': AttrTypeValue['string']},
                    'RackSpace': {'refers': Entity.objects.filter(name__regex='RackSpace '), 'type': AttrTypeValue['object']},
                    'ZeroU': {'refers': self.get_rack_referral_entities(),
                              'type': AttrTypeValue['array_object']},
                }

                for attrname, info in new_attrs.items():
                    if entity.attrs.filter(name=attrname).count():
                        continue

                    entity_attr = EntityAttr.objects.create(name=attrname,
                                                            type=info['type'],
                                                            created_user=user,
                                                            parent_entity=entity)

                    for refer in info['refers']:
                        entity_attr.referral.add(refer)

                    entity.attrs.add(entity_attr)
            else:
                entity = self.get_entity('ラック', user)


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

        def set_zerou():
            sys.stdout.write('\nCreate Zero-U Entries.')

            object_all = self._fetch_db('Object', ['id', 'name'], condition=None, distinct=True)
            data_all = self._fetch_db('EntityLink',
                                      ['parent_entity_id', 'child_entity_id'],
                                      'parent_entity_type="rack" and child_entity_type="object"')

            data_len = len(data_all)
            for data_index, data in enumerate(data_all):
                sys.stdout.write('\rCreate Zero-U Entries: %6d/%6d' % (data_index+1, data_len))
                sys.stdout.flush()

                if data['parent_entity_id'] in self.rack_map:
                    rack_entry = self.rack_map[data['parent_entity_id']]
                    rack_entry.complement_attrs(user)

                    attr_zerou = rack_entry.attrs.get(name='ZeroU')
                    av_parent = attr_zerou.get_latest_value()
                    if not av_parent:
                        av_parent = AttributeValue(parent_attr=attr_zerou, created_user=user)
                        av_parent.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)
                        av_parent.set_status(AttributeValue.STATUS_LATEST)
                        av_parent.save()

                        attr_zerou.value.add(av_parent)

                    rk_obj = [x for x in object_all if x['id'] == data['child_entity_id']]
                    if rk_obj and Entry.objects.filter(name=rk_obj[0]['name']).count():
                        target_entry = Entry.objects.get(name=rk_obj[0]['name'])

                        attrv = AttributeValue.objects.create(created_user=user,
                                                              parent_attr=attr_zerou,
                                                              referral=target_entry,
                                                              status=AttributeValue.STATUS_LATEST)

                        av_parent.data_array.add(attrv)

        def create_rackspace_entry():
            sys.stdout.write('\nCreate RackSpace Entry...')
            user = self.get_admin()

            data_all = self._fetch_db('RackSpace',
                                      ['rack_id', 'unit_no', 'atom', 'object_id'],
                                      'state="T"')
            data_len = len(data_all)
            for data_index, data in enumerate(data_all):
                sys.stdout.write('\rCreate RackSpace Entry: %6d/%6d' % (data_index+1, data_len))
                sys.stdout.flush()

                if (data['rack_id'] not in self.rack_map or
                    data['object_id'] not in self.object_map):
                    continue

                rack_entry = self.rack_map[data['rack_id']]
                attr_rack_rs = rack_entry.attrs.get(name='RackSpace')
                if attr_rack_rs.get_latest_value():
                    rs_entry = Entry.objects.get(id=attr_rack_rs.get_latest_value().referral.id)
                else:

                    rack_height = rack_entry.attrs.get(name='height').get_latest_value().value
                    rs_entry = self.get_entry(name='RackSpace (%s)' % rack_entry.name,
                                              schema=self.get_entity('RackSpace (%s-U)' % rack_height),
                                              user=user)

                    attr_rack_rs.values.add(AttributeValue.objects.create(**{
                        'created_user': user,
                        'parent_attr': attr_rack_rs,
                        'referral': rs_entry,
                        'status': AttributeValue.STATUS_LATEST,
                    }))

                # create Attributes of RackSpace
                rs_entry.complement_attrs(user)
                attr_rs_entry = rs_entry.attrs.get(name="%d" % data['unit_no'])

                # get AttributeValue correspoing to the Rack-Unit
                attrv_parent = attr_rs_entry.get_latest_value()
                if not attrv_parent:
                    attrv_parent = AttributeValue(created_user=user, parent_attr=attr_rs_entry)
                    attrv_parent.set_status(AttributeValue.STATUS_LATEST)
                    attrv_parent.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)
                    attrv_parent.save()

                    attr_rs_entry.values.add(attrv_parent)

                target_entry = self.object_map[data['object_id']]
                if not attrv_parent.data_array.filter(referral=target_entry).count():
                    attrv_parent.data_array.add(AttributeValue.objects.create(**{
                        'created_user': user,
                        'parent_attr': attr_rs_entry,
                        'referral': target_entry,
                        'status': AttributeValue.STATUS_LATEST,
                    }))

        # Create RackSpace Entity
        create_rackspace()

        # Create 'データセンタ' Entity & Entries
        dc_entity = create_datacenter()

        # Create 'フロア' Entity & Entries
        fr_entity = create_floor(dc_entity)

        # Create 'ラック' Entity & Entries
        rk_entity = create_rack(fr_entity)

        # Filling out 'ZeroU' parameter for each 'ラック'
        set_zerou()

        # create RackSpace Entries which indicates position in the Rack
        create_rackspace_entry()

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

        driver.create_ports_and_links()
        print('\nAfter create_ports_and_links: %s' % str(datetime.now() - t0))

        driver.create_ipaddr_entries()
        print('\nAfter create_ipaddr_entries: %s' % str(datetime.now() - t0))

        # create Entities and Entries for RackSpace
        driver.create_rackspace_entries()

    print('\nfinished (%s)' % str(datetime.now() - t0))
