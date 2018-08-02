import json

from api_v1.auth import AironeTokenAuth
from airone.lib.profile import airone_profile

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import BasicAuthentication
from rest_framework.authentication import SessionAuthentication

from entity.models import Entity
from entry.models import Entry
from entry.settings import CONFIG as CONFIG_ENTRY
from user.models import User


class EntrySearchAPI(APIView):
    authentication_classes = (AironeTokenAuth, BasicAuthentication, SessionAuthentication,)

    @airone_profile
    def post(self, request, format=None):
        user = User.objects.get(id=request.user.id)

        hint_entity = request.data.get('entities')
        hint_attr = request.data.get('attrinfo')
        entry_limit = request.data.get('entry_limit', CONFIG_ENTRY.MAX_LIST_ENTRIES)

        if not hint_entity or not hint_attr:
            return Response('The entities and attrinfo parameters are required',
                            status=status.HTTP_400_BAD_REQUEST)

        hint_entity_ids = []
        for hint in hint_entity:
            try:
                if Entity.objects.filter(id=hint).exists():
                    hint_entity_ids.append(hint)

            except ValueError:
                # This may happen when a string value is specified in the entities parameter
                entity = Entity.objects.filter(name=hint).first()
                if entity:
                    hint_entity_ids.append(entity.id)

        resp = Entry.search_entries(user, hint_entity_ids, hint_attr, entry_limit)

        return Response({'result': resp}, content_type='application/json; charset=UTF-8')
