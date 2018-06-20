from .serializers import PostEntrySerializer
from .serializers import GetEntrySerializer

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import BasicAuthentication
from rest_framework.authentication import SessionAuthentication

from api_v1.auth import AironeTokenAuth
from airone.lib.acl import ACLType
from user.models import User
from entity.models import Entity
from entry.models import Entry


class EntryAPI(APIView):
    authentication_classes = (AironeTokenAuth, BasicAuthentication, SessionAuthentication,)

    def post(self, request, format=None):
        user = User.objects.get(id=request.user.id)
        sel = PostEntrySerializer(data=request.data)

        if not sel.is_valid():
            ret = {
                'result': 'Validation Error',
                'details': ['(%s) %s' % (k, ','.join(e)) for k,e in sel._errors.items()],
            }
            return Response(ret, status=status.HTTP_400_BAD_REQUEST)

        # checking that target user has permission to create an entry
        if not user.has_permission(sel.validated_data['entity'], ACLType.Writable):
            return Response({'result': 'Permission denied to create(or update) entry'},
                            status=status.HTTP_400_BAD_REQUEST)

        entry_condition = {
            'schema': sel.validated_data['entity'],
            'name': sel.validated_data['name'],
            'is_active': True,
        }
        if 'id' in sel.validated_data:
            entry = Entry.objects.get(id=sel.validated_data['id'])
            entry.name = sel.validated_data['name']
            entry.save()

        elif Entry.objects.filter(**entry_condition):
            entry = Entry.objects.get(**entry_condition)

        else:
            entry = Entry.objects.create(created_user=user, **entry_condition)

        entry.complement_attrs(user)
        for name, value in sel.validated_data['attrs'].items():
            # If user doesn't have readable permission for target Attribute, it won't be created.
            if not entry.attrs.filter(name=name):
                continue

            attr = entry.attrs.get(name=name)
            if user.has_permission(attr.schema, ACLType.Writable) and attr.is_updated(value):
                attr.add_value(user, value)

        # register target Entry to the Elasticsearch
        entry.register_es()

        return Response({'result': entry.id})

    def get(self, request, *args, **kwargs):
        if not request.user.id:
            return Response({'result': 'You have to login AirOne to perform this request'},
                            status=status.HTTP_400_BAD_REQUEST)

        param_entity = request.query_params.get('entity')
        param_entry = request.query_params.get('entry')
        if not param_entity or not param_entry:
            return Response({'result': 'Parameter "entity" and "entry" are mandatory'},
                            status=status.HTTP_400_BAD_REQUEST)

        entity = Entity.objects.filter(name=param_entity).first()
        if not entity:
            return Response({'result': 'Failed to find specified Entity (%s)' % param_entity},
                            status=status.HTTP_404_NOT_FOUND)

        entry = Entry.objects.filter(name=param_entry, schema=entity).first()
        if not entry:
            return Response({'result': 'Failed to find specified Entry (%s)' % param_entry},
                            status=status.HTTP_404_NOT_FOUND)

        # permission check
        user = User.objects.get(id=request.user.id)
        if not all([user.has_permission(x, ACLType.Readable) for x in [entity, entry]]):
            return Response({'result': 'Permission denied to access target information'},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'id': entry.id,
            'attrs': [{
                'name': x.schema.name,
                'value': x.get_latest_value().get_value()
            } for x in entry.attrs.filter(is_active=True) if user.has_permission(x, ACLType.Readable)]
        })

    def delete(self, request, *args, **kwargs):
        if not request.user.id:
            return Response('You have to login AirOne to perform this request',
                            status=status.HTTP_400_BAD_REQUEST)

        # checks mandatory parameters are specified
        if not all([x in request.data for x in ['entity', 'entry']]):
            return Response('Parameter "entity" and "entry" are mandatory',
                            status=status.HTTP_400_BAD_REQUEST)

        entity = Entity.objects.filter(name=request.data['entity']).first()
        if not entity:
            return Response('Failed to find specified Entity (%s)' % request.data['entity'],
                            status=status.HTTP_404_NOT_FOUND)

        entry = Entry.objects.filter(name=request.data['entry'], schema=entity).first()
        if not entry:
            return Response('Failed to find specified Entry (%s)' % request.data['entry'],
                            status=status.HTTP_404_NOT_FOUND)

        # permission check
        user = User.objects.get(id=request.user.id)
        if (not user.has_permission(entry, ACLType.Full) or
            not user.has_permission(entity, ACLType.Readable)):
            return Response('Permission denied to operate', status=status.HTTP_400_BAD_REQUEST)

        # Delete the specified entry then return its id, if is active
        if entry.is_active:
            entry.delete()

        return Response({'id': entry.id})
