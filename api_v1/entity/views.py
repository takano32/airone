from functools import reduce

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import BasicAuthentication
from rest_framework.authentication import SessionAuthentication

from airone.lib.acl import ACLType
from api_v1.auth import AironeTokenAuth
from entity.models import Entity, EntityAttr
from user.models import User


class EntityAttrsAPI(APIView):
    authentication_classes = (AironeTokenAuth, BasicAuthentication, SessionAuthentication,)

    def get(self, request, entity_ids, format=None):
        user = User.objects.get(id=request.user.id)

        entities = [Entity.objects.filter(id=x, is_active=True).first()
                    for x in entity_ids.split(',') if x]

        def get_attrs_of_specific_entities():
            return reduce(lambda x, y: set(x) & set(y),
                          [[a.name for a in e.attrs.filter(is_active=True)
                              if user.has_permission(a, ACLType.Readable)] for e in entities])

        def get_attrs_of_all_entities():
            return sorted(list(set([x.name for x in EntityAttr.objects.filter(is_active=True)
                                    if user.has_permission(x, ACLType.Readable)])), key=lambda x: x)

        if entities:
            # the case invalid entity-id was specified
            if not all(entities):
                return Response("Target Entity doesn't exist", status=status.HTTP_400_BAD_REQUEST)

            attrs = get_attrs_of_specific_entities()
        else:
            attrs = get_attrs_of_all_entities()

        return Response({'result': attrs}, content_type='application/json; charset=UTF-8')
