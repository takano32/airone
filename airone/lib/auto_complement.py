from django.conf import settings
from user.models import User


def get_auto_complement_user(user):
    if ('AUTO_COMPLEMENT' in settings.AIRONE
        and settings.AIRONE['AUTO_COMPLEMENT']
        and 'AUTO_COMPLEMENT_USER' in settings.AIRONE
        and settings.AIRONE['AUTO_COMPLEMENT_USER']
        and User.objects.filter(username=settings.AIRONE['AUTO_COMPLEMENT_USER']).exists()):
        user = User.objects.get(username=settings.AIRONE['AUTO_COMPLEMENT_USER'])

    return user
