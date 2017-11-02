from import_export import fields, widgets
from django.contrib import admin
from .models import EntityAttr
from .models import Entity
from acl.models import ACLBase
from airone.lib.resources import AironeModelResource

admin.site.register(EntityAttr)
admin.site.register(Entity)


class EntityResource(AironeModelResource):
    _IMPORT_INFO = {
        'header':               ['id', 'name', 'note', 'status'],
        'mandatory_keys':       ['name'],
        'resource_module':      'entity.admin',
        'resource_model_name':  'EntityResource',
    }

    COMPARING_KEYS = ['name', 'note', 'status']

    class Meta:
        model = Entity
        fields = ('id', 'name', 'note', 'status')
        export_order = ('id', 'name', 'note')

    def import_obj(self, instance, data, dry_run):
        instance.created_user = self.request_user

        # will not import duplicate entity
        if (not self.request_user.is_superuser and
            Entity.objects.filter(name=data['name']).count()):
            entity = Entity.objects.filter(name=data['name']).get()
            if 'id' not in data or not data['id'] or entity.id != data['id']:
                raise RuntimeError('There is a duplicate entity object (%s)' % data['name'])

        super(EntityResource, self).import_obj(instance, data, dry_run)

class EntityAttrResource(AironeModelResource):
    _IMPORT_INFO = {
        'header':               ['id', 'name', 'type', 'refer', 'entity', 'is_mandatory'],
        'mandatory_keys':       ['name', 'type', 'entity'],
        'resource_module':      'entity.admin',
        'resource_model_name':  'EntityAttrResource',
    }

    COMPARING_KEYS = ['name', 'is_mandatory', 'referral', 'parent_entity']
    DISALLOW_UPDATE_KEYS = ['parent_entity']

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
        instance.created_user = self.request_user

        if not self.request_user.is_superuser:
            if not Entity.objects.filter(name=data['entity']).count():
                raise RuntimeError('failed to identify entity object')

            if data['refer'] and not Entity.objects.filter(name=data['refer']).count():
                raise RuntimeError('refer to invalid entity object')

        super(EntityAttrResource, self).import_obj(instance, data, dry_run)
