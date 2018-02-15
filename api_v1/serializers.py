from airone.lib.types import AttrTypeValue
from entity.models import Entity
from entry.models import Entry
from group.models import Group
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

class GetEntrySerializer(serializers.ModelSerializer):
    attrs = serializers.SerializerMethodField()
    class Meta:
        model = Entry
        fields = ('id', 'name', 'attrs')

    def get_attrs(self, obj):
        def get_attr_value(attr):
            attrv = attr.get_latest_value()

            if not attrv:
                return ''

            if attr.schema.type & AttrTypeValue['array']:
                if attr.schema.type & AttrTypeValue['string']:
                    return [x.value for x in attrv.data_array.all()]
    
                elif attr.schema.type & AttrTypeValue['named']:
                    return [{
                        'name': x.value,
                        'ref_id': x.referral.id if x.referral else None,
                        'ref_name': x.referral.name if x.referral else '',
                    } for x in attrv.data_array.all()]
    
                elif attr.schema.type & AttrTypeValue['object']:
                    return [{
                        'id': x.referral.id if x.referral else None,
                        'name': x.referral.name if x.referral else '',
                    } for x in attrv.data_array.all()]
    
            elif (attr.schema.type & AttrTypeValue['string'] or
                  attr.schema.type & AttrTypeValue['text']):
                return attrv.value
    
            elif attr.schema.type & AttrTypeValue['named']:
                return {
                    'name': attrv.value,
                    'ref_id': attrv.referral.id if attrv.referral else None,
                    'ref_name': attrv.referral.name if attrv.referral else '',
                }
    
            elif attr.schema.type & AttrTypeValue['object']:
                return {
                    'id': attrv.referral.id if attrv.referral else None,
                    'name': attrv.referral.name if attrv.referral else '',
                }
    
            elif attr.schema.type & AttrTypeValue['boolean']:
                return attrv.boolean
    
            elif attr.schema.type & AttrTypeValue['group']:
                group = Group.objects.get(id=attrv.value)
                return {
                    'id': group.id,
                    'name': group.name,
                }

        return [{
            'name': x.schema.name,
            'value': get_attr_value(x),
        } for x in obj.attrs.filter(is_active=True)]

class PostEntrySerializer(serializers.Serializer):
    entity = serializers.CharField(required=True, max_length=100)
    name = serializers.CharField(required=True, max_length=100)
    attrs = serializers.DictField(required=True)

    def _validate_attr(self, attr, value):
        """This method validate and convert attirubte valeu to be acceptable for AirOne
        """

        def get_entry(schema, name):
            return Entry.objects.get(is_active=True, schema=schema, name=name)

        def is_entry(schema, name):
            return Entry.objects.filter(is_active=True, schema=schema, name=name)

        def validate_named_attr(value):
            if 'name' not in value:
                value['name'] = ''

            if 'id' not in value or not value['id']:
                value['id'] = None
            else:
                entryset = [get_entry(r, value['id'])
                    for r in attr.referral.all() if is_entry(r, value['id'])]

                # It means that there is no entry which is matched specified referrence
                if not any(entryset):
                    return None

                value['id'] = entryset[0]

            return value

        if attr.type & AttrTypeValue['array']:
            if not isinstance(value, list):
                return None

            if attr.type & AttrTypeValue['string']:
                if not all([isinstance(v, str) for v in value]):
                    return None
                return value

            elif attr.type & AttrTypeValue['named']:
                if not all([isinstance(v, dict) for v in value]):
                    return None

                return [x for x in [validate_named_attr(v) for v in value] if x]

            elif attr.type & AttrTypeValue['object']:
                return sum([[get_entry(r, v)
                    for r in attr.referral.all() if is_entry(r, v)]
                    for v in value], [])

        elif attr.type & AttrTypeValue['string'] or attr.type & AttrTypeValue['text']:
            if not isinstance(value, str):
                return None
            return value

        elif attr.type & AttrTypeValue['named']:
            if not isinstance(value, dict):
                return None

            return validate_named_attr(value)

        elif attr.type & AttrTypeValue['object']:
            if not isinstance(value, str):
                return None

            entryset = [get_entry(x, value)
                for x in attr.referral.all() if is_entry(x, value)]
            if any(entryset):
                return entryset[0]

        elif attr.type & AttrTypeValue['boolean']:
            if not isinstance(value, bool):
                return None
            return value

        elif attr.type & AttrTypeValue['group']:
            if not isinstance(value, str):
                return None

            if not Group.objects.filter(name=value):
                return None

            return str(Group.objects.get(name=value).id)

        return None

    def validate(self, data):
        # checks specified entity is existed
        if not Entity.objects.filter(is_active=True, name=data['entity']):
            raise ValidationError('Invalid Entity is specified (%s)' % data['entity'])

        # checks duplicate name entry is not existed
        entity = data['entity'] = Entity.objects.get(is_active=True, name=data['entity'])
        if Entry.objects.filter(is_active=True, schema=entity, name=data['name']):
            raise ValidationError('A same name entry is existed')

        # checks mandatory keys are specified
        if not all([False for x
            in entity.attrs.filter(is_active=True, is_mandatory=True)
            if x.name not in data['attrs'].keys()]):
            raise ValidationError('Some mandatory attrs are not specified')

        # checks specified attr values are valid
        for attr_name, attr_value  in data['attrs'].items():
            if not entity.attrs.filter(is_active=True, name=attr_name):
                raise ValidationError("Target entity doesn't specified attr(%s)" % (attr_name))

            attr = entity.attrs.get(name=attr_name)
            validated_value = self._validate_attr(attr, attr_value)
            if validated_value is None:
                raise ValidationError("Invalid attribute value(%s) is specified" % (attr_name))

            data['attrs'][attr_name] = validated_value

        return data
