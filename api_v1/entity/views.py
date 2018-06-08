import json

from functools import reduce

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

        entities = [Entity.objects.filter(id=x, is_active=True) for x in entity_ids.split(',')]
        if not all(entities):
            return Response("Target Entity doesn't exist", status=status.HTTP_400_BAD_REQUEST)
        else:
            entities = [x.first() for x in entities]

        attrs = reduce(lambda x,y: set(x) & set(y),
                       [[a.name for a in e.attrs.filter(is_active=True)
                           if user.has_permission(a, ACLType.Readable)] for e in entities])

        return Response({'result': attrs}, content_type='application/json; charset=UTF-8')
