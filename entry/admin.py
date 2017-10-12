from airone.lib.resources import AironeModelResource
from airone.lib.types import AttrTypeValue
from django.contrib import admin
from import_export import fields, widgets
from user.models import User
from .models import Entry
from .models import Attribute, AttributeValue
from acl.models import ACLBase
from entity.models import Entity, AttributeBase
from entry.models import Entry

admin.site.register(Entry)
admin.site.register(Attribute)
admin.site.register(AttributeValue)


class AttrValueResource(AironeModelResource):
    _IMPORT_INFO = {
        'header': ['id', 'refer', 'value', 'attribute_id', 'created_time',
                   'created_user', 'status', 'data_arr'],
        'mandatory_keys': ['id', 'attribute_id', 'created_user', 'status'],
        'resource_module': 'entry.admin',
        'resource_model_name': 'AttrValueResource',
    }
    COMPARING_KEYS = []
    DISALLOW_UPDATE_KEYS = ['created_time', 'created_user', 'parent_attr',
                            'value', 'referral', 'status']

    attr_id = fields.Field(column_name='attribute_id', attribute='parent_attr',
                           widget=widgets.ForeignKeyWidget(model=Attribute, field='id'))
    refer = fields.Field(column_name='refer', attribute='referral',
                         widget=widgets.ForeignKeyWidget(model=ACLBase, field='id'))
    user = fields.Field(column_name='created_user', attribute='created_user',
                        widget=widgets.ForeignKeyWidget(User, 'username'))
    data_arr = fields.Field(column_name='data_arr', attribute='data_array',
                            widget=widgets.ManyToManyWidget(model=AttributeValue, field='id'))

    class Meta:
        model = AttributeValue
        fields = ('id', 'name', 'value', 'created_time', 'status')

    def after_save_instance(self, instance, using_transactions, dry_run):
        # If a new AttributeValue object is created,
        # this processing append it to the associated Entity object.
        self._saved_instance = None
        if not dry_run:
            attr = instance.parent_attr

            if (not attr.values.filter(id=instance.id) and
                (not attr.type & AttrTypeValue['array'] or
                 (attr.type & AttrTypeValue['array'] and
                  instance.get_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)))):
                attr.values.add(instance)

            self._saved_instance = instance

    @classmethod
    def after_import_completion(self, results):
        # make relation between the array of AttributeValue
        for data in [x['data'] for x in results
                if x['data']['status'] & AttributeValue.STATUS_DATA_ARRAY_PARENT]:

            attr_value = AttributeValue.objects.get(id=data['id'])
            for child_id in [int(x) for x in  data['data_arr'].split(',')]:
                if (AttributeValue.objects.filter(id=child_id).count() and
                    not attr_value.data_array.filter(id=child_id).count()):

                    # append related AttributeValue if it's not existed
                    attr_value.data_array.add(AttributeValue.objects.get(id=child_id))

        # set latest status for each attributes
        for attr in Attribute.objects.all():
            # first of all, clear the latest flag for each values
            [x.del_status(AttributeValue.STATUS_LATEST) for x in attr.values.all()]

            # reset latest status flag
            latest_value = attr.get_latest_value()

            latest_value.set_status(AttributeValue.STATUS_LATEST)
            if latest_value.get_status(AttributeValue.STATUS_DATA_ARRAY_PARENT):
                [v.set_status(AttributeValue.STATUS_LATEST) for v in latest_value.data_array.all()]

class AttrResource(AironeModelResource):
    _IMPORT_INFO = {
        'header': ['id', 'name', 'schema_id', 'entry_id', 'created_user',
                   'type', 'is_mandatory', 'refer'],
        'mandatory_keys': ['name', 'schema_id', 'entry_id', 'created_user',
                           'type'],
        'resource_module': 'entry.admin',
        'resource_model_name': 'AttrResource',
    }
    COMPARING_KEYS = ['name', 'is_mandatory', 'referral', 'created_user']
    DISALLOW_UPDATE_KEYS = ['is_mandatory', 'created_user']

    entry = fields.Field(column_name='entry_id', attribute='parent_entry',
                         widget=widgets.ForeignKeyWidget(model=Entry, field='id'))
    user = fields.Field(column_name='created_user', attribute='created_user',
                        widget=widgets.ForeignKeyWidget(User, 'username'))
    refer = fields.Field(column_name='refer', attribute='referral',
                         widget=widgets.ForeignKeyWidget(model=ACLBase, field='id'))

    class Meta:
        model = Attribute
        fields = ('id', 'name', 'schema_id', 'type', 'is_mandatory')

    def after_save_instance(self, instance, using_transactions, dry_run):
        # If a new Attribute object is created,
        # this processing append it to the associated Entity object.
        if not dry_run:
            entry = instance.parent_entry

            if not entry.attrs.filter(id=instance.id):
                entry.attrs.add(instance)

class EntryResource(AironeModelResource):
    _IMPORT_INFO = {
        'header': ['id', 'name', 'entity', 'created_user'],
        'mandatory_keys': ['name', 'entity', 'created_user'],
        'mandatory_values': ['name'],
        'resource_module': 'entry.admin',
        'resource_model_name': 'EntryResource',
    }
    COMPARING_KEYS = ['name']

    entity = fields.Field(column_name='entity', attribute='schema',
                          widget=widgets.ForeignKeyWidget(model=Entity, field='name'))
    user = fields.Field(column_name='created_user', attribute='created_user',
                        widget=widgets.ForeignKeyWidget(User, 'username'))

    class Meta:
        model = Entry
        fields = ('id', 'name')

    def import_obj(self, instance, data, dry_run):
        # will not import entry which refers invalid entity
        if not Entity.objects.filter(name=data['entity']).count():
            raise RuntimeError("Specified entity(%s) doesn't exist" % data['entity'])

        # will not import entry which has same name and refers same entity
        entity = Entity.objects.get(name=data['entity'])
        if Entry.objects.filter(schema=entity, name=data['name']).count():
            entry = Entry.objects.get(schema=entity, name=data['name'])
            if 'id' not in data or not data['id'] or entry.id != data['id']:
                raise RuntimeError('There is a duplicate entry object')

        super(EntryResource, self).import_obj(instance, data, dry_run)
