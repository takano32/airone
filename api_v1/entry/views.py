import json

from airone.lib.profile import airone_profile

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import BasicAuthentication
from rest_framework.authentication import TokenAuthentication
from rest_framework.authentication import SessionAuthentication

from entry.models import Entry
from entry.settings import CONFIG as CONFIG_ENTRY
from user.models import User


class EntrySearchAPI(APIView):
    authentication_classes = (TokenAuthentication, BasicAuthentication, SessionAuthentication,)

    @airone_profile
    def post(self, request, format=None):
        user = User.objects.get(id=request.user.id)

        hint_entity = request.data.get('entities')
        hint_attr = request.data.get('attrinfo')
        entry_limit = request.data.get('entry_limit', CONFIG_ENTRY.MAX_LIST_ENTRIES)

        if not hint_entity or not hint_attr:
            return Response('The entities and attrinfo parameters are required',
                            status=status.HTTP_400_BAD_REQUEST)

        resp = Entry.search_entries(user, hint_entity, hint_attr, entry_limit)

        return Response({'result': resp}, content_type='application/json; charset=UTF-8')
