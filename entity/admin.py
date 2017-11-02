from import_export import fields, widgets
from django.contrib import admin
from .models import EntityAttr
from .models import Entity
from user.models import User
from acl.models import ACLBase
from airone.lib.resources import AironeModelResource

admin.site.register(EntityAttr)
admin.site.register(Entity)


class EntityResource(AironeModelResource):
    _IMPORT_INFO = {
        'header':               ['id', 'name', 'note', 'created_user', 'status'],
        'mandatory_keys':       ['name', 'created_user'],
        'resource_module':      'entity.admin',
        'resource_model_name':  'EntityResource',
    }

    COMPARING_KEYS = ['name', 'note', 'created_user', 'status']
    DISALLOW_UPDATE_KEYS = ['created_user']

    user = fields.Field(column_name='created_user', attribute='created_user',
                        widget=widgets.ForeignKeyWidget(User, 'username'))

    class Meta:
        model = Entity
        fields = ('id', 'name', 'note', 'status')
        export_order = ('id', 'name', 'note', 'user')

    def import_obj(self, instance, data, dry_run):
        # will not import duplicate entity
        if Entity.objects.filter(name=data['name']).count():
            entity = Entity.objects.filter(name=data['name']).get()
            if 'id' not in data or not data['id'] or entity.id != data['id']:
                raise RuntimeError('There is a duplicate entity object (%s)' % data['name'])

        super(EntityResource, self).import_obj(instance, data, dry_run)

class EntityAttrResource(AironeModelResource):
    _IMPORT_INFO = {
        'header':               ['id', 'name', 'type', 'refer', 'entity',
                                 'created_user', 'is_mandatory'],
        'mandatory_keys':       ['name', 'type', 'entity', 'created_user'],
        'resource_module':      'entity.admin',
        'resource_model_name':  'EntityAttrResource',
    }

    COMPARING_KEYS = ['name', 'is_mandatory', 'referral', 'parent_entity', 'created_user']
    DISALLOW_UPDATE_KEYS = ['parent_entity', 'created_user']

    user = fields.Field(column_name='created_user', attribute='created_user',
                        widget=widgets.ForeignKeyWidget(User, 'username'))
    refer = fields.Field(column_name='refer', attribute='referral',
                         widget=widgets.ForeignKeyWidget(model=ACLBase, field='name'))
    entity = fields.Field(column_name='entity',
                          attribute='parent_entity',
                          widget=widgets.ForeignKeyWidget(model=Entity, field='name'))

    class Meta:
        model = EntityAttr
        fields = ('id', 'name', 'type', 'is_mandatory')

    def after_save_instance(self, instance, using_transactions, dry_run):
        # If a new EntityAttr object is created,
        # this processing append it to the associated Entity object.
        if not dry_run:
            entity = instance.parent_entity

            if not entity.attrs.filter(id=instance.id):
                entity.attrs.add(instance)

    def import_obj(self, instance, data, dry_run):
        if not Entity.objects.filter(name=data['entity']).count():
            raise RuntimeError('failed to identify entity object')

        if data['refer'] and not Entity.objects.filter(name=data['refer']).count():
            raise RuntimeError('refer to invalid entity object')

        super(EntityAttrResource, self).import_obj(instance, data, dry_run)
