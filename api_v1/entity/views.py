import json

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import BasicAuthentication
from rest_framework.authentication import TokenAuthentication
from rest_framework.authentication import SessionAuthentication

from airone.lib.acl import ACLType
from entity.models import Entity
from user.models import User


class EntityAttrsAPI(APIView):
    authentication_classes = (TokenAuthentication, BasicAuthentication, SessionAuthentication,)

    def get(self, request, entity_ids, format=None):
        user = User.objects.get(id=request.user.id)

        if not all([Entity.objects.filter(id=x) for x in entity_ids.split(',')]):
            return Response("Target Entity doesn't exist", status=status.HTTP_400_BAD_REQUEST)

        attrs = []
        for entity_id in entity_ids.split(','):
            entity = Entity.objects.get(id=entity_id)

            if not entity.is_active or not user.has_permission(entity, ACLType.Readable):
                continue

            attrs.append([x.name for x in entity.attrs.filter(is_active=True)
                if user.has_permission(x, ACLType.Readable)])

        return Response({'result': set(sum(attrs, []))}, content_type='application/json; charset=UTF-8')
