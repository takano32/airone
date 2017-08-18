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
                   'created_user', 'status', 'data_array'],
        'mandatory_keys': ['attribute_id', 'created_user', 'status'],
        'resource_module': 'entry.admin',
        'resource_model_name': 'AttrValueResource',
    }
    COMPARING_KEYS = []
    DISALLOW_UPDATE_KEYS = ['created_time', 'created_user', 'parent_attr',
                            'value', 'referral', 'data_array', 'status']

    attr_id = fields.Field(column_name='attribute_id', attribute='parent_attr',
                        widget=widgets.ForeignKeyWidget(model=Attribute, field='id'))
    refer = fields.Field(column_name='refer', attribute='referral',
                         widget=widgets.ForeignKeyWidget(model=ACLBase, field='id'))
    user = fields.Field(column_name='created_user', attribute='created_user',
                        widget=widgets.ForeignKeyWidget(User, 'username'))

    class Meta:
        model = AttributeValue
        fields = ('id', 'name', 'value', 'created_time', 'status', 'data_array')

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

class AttrResource(AironeModelResource):
    _IMPORT_INFO = {
        'header': ['id', 'name', 'entity', 'schema_id', 'entry_id', 'created_user',
                   'type', 'is_mandatory'],
        'mandatory_keys': ['name', 'entity', 'schema_id', 'entry_id', 'created_user',
                           'type'],
        'resource_module': 'entry.admin',
        'resource_model_name': 'AttrResource',
    }
    COMPARING_KEYS = ['name', 'is_mandatory', 'referral', 'parent_entity', 'created_user']
    DISALLOW_UPDATE_KEYS = ['is_mandatory', 'parent_entity', 'created_user']

    entry = fields.Field(column_name='entry_id', attribute='parent_entry',
                         widget=widgets.ForeignKeyWidget(model=Entry, field='id'))
    user = fields.Field(column_name='created_user', attribute='created_user',
                        widget=widgets.ForeignKeyWidget(User, 'username'))
    entity = fields.Field(column_name='entity',
                          attribute='parent_entity',
                          widget=widgets.ForeignKeyWidget(model=Entity, field='name'))

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
