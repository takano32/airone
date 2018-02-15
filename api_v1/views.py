from .serializers import PostEntrySerializer
from .serializers import GetEntrySerializer

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from user.models import User
from entry.models import Entry


class EntryAPI(APIView):
    def post(self, request, format=None):
        user = User.objects.get(id=request.user.id)
        sel = PostEntrySerializer(data=request.data)

        if not sel.is_valid():
            ret = {
                'result': 'Validation Error',
                'details': ['(%s) %s' % (k, ','.join(e)) for k,e in sel._errors.items()],
            }
            return Response(ret, status=status.HTTP_400_BAD_REQUEST)

        entry = Entry.objects.create(name=sel.validated_data['name'],
                                     schema=sel.validated_data['entity'],
                                     created_user=user)
        entry.complement_attrs(user)
        for name, value in sel.validated_data['attrs'].items():
            entry.attrs.get(name=name).add_value(user, value)

        return Response({'result': entry.id})

    def get(self, request, format=None):
        entries = Entry.objects.filter(is_active=True)
        sel = GetEntrySerializer(entries, many=True)
        return Response(sel.data)
