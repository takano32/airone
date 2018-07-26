from datetime import datetime, timedelta, timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authentication import BasicAuthentication
from rest_framework.authentication import SessionAuthentication

from job.models import Job
from job.settings import CONFIG as JOB_CONFIG
from user.models import User

from api_v1.auth import AironeTokenAuth


class JobAPI(APIView):
    authentication_classes = (AironeTokenAuth, BasicAuthentication, SessionAuthentication,)

    def get(self, request, format=None):
        user = User.objects.get(id=request.user.id)
        time_threashold = (datetime.now(timezone.utc) - timedelta(seconds=JOB_CONFIG.RECENT_SECONDS))

        constant = {
            'status': {
                'processing': Job.STATUS_PROCESSING,
                'done': Job.STATUS_DONE,
                'error': Job.STATUS_ERROR,
                'timeout': Job.STATUS_TIMEOUT,
            },
            'operation': {
                'create': Job.OP_CREATE,
                'edit': Job.OP_EDIT,
                'delete': Job.OP_DELETE,
                'copy': Job.OP_COPY,
            }
        }

        query = {
            'user': user,
            'created_at__gte': time_threashold,
        }
        jobs = [{
            'target': {
                'id': x.target.id,
                'name': x.target.name,
            },
            'text': x.text,
            'status': x.status,
            'operation': x.operation,
            'created_at': x.created_at,
            'updated_at': x.updated_at,
        } for x in Job.objects.filter(**query).order_by('-created_at')[:JOB_CONFIG.MAX_LIST_NAV]]

        return Response({
            'result': jobs,
            'constant': constant,
        }, content_type='application/json; charset=UTF-8')
