from .serializers import PostEntrySerializer
from .serializers import GetEntrySerializer

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import BasicAuthentication
from rest_framework.authentication import TokenAuthentication
from rest_framework.authentication import SessionAuthentication

from airone.lib.acl import ACLType
from user.models import User
from entry.models import Entry


class EntryAPI(APIView):
    authentication_classes = (TokenAuthentication, BasicAuthentication, SessionAuthentication,)

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

        return Response({'result': entry.id})

####
# Disable this REST API endpoint to get whole entries because of the following reaons for a while.
#
# 1. There is no requirement to get whole entries from API.
# 2. This processing requires large amount of CPU time.
#
#    def get(self, request, format=None):
#        entries = Entry.objects.filter(is_active=True)
#        sel = GetEntrySerializer(entries, many=True)
#        return Response(sel.data)
