from datetime import datetime, timedelta, timezone
from django.contrib.auth.models import User as DjangoUser

from rest_framework.views import APIView
from rest_framework.authtoken.models import Token
from rest_framework.authentication import BasicAuthentication
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed

from user.models import User


class AironeAPIView(APIView):
    authentication_classes = (TokenAuthentication, BasicAuthentication,)

    def initial(self, request, *args, **kwargs):
        super(AironeAPIView, self).initial(request, *args, **kwargs)

        if isinstance(request.successful_authenticator, TokenAuthentication):
            user = User.objects.get(id=request.user.id)
            token = Token.objects.get(user=DjangoUser.objects.get(id=user.id))

            if token.created + timedelta(seconds=user.token_lifetime) < datetime.now(timezone.utc):
                raise AuthenticationFailed('Token lifetime is expired')
