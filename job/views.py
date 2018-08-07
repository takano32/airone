from datetime import datetime, timezone
from django.shortcuts import render

# libraries of AirOne
from airone.lib.http import http_get, render

# related models in AirOne
from job.models import Job
from user.models import User

# configuration of this app
from .settings import CONFIG


@http_get
def index(request):
    user = User.objects.get(id=request.user.id)

    limitation = CONFIG.MAX_LIST_VIEW
    if request.GET.get('nolimit', None):
        limitation = None

    context = {
        'jobs': [{
            'id': x.id,
            'target': x.target,
            'text': x.text,
            'status': x.status,
            'operation': x.operation,
            'created_at': x.created_at,
            'passed_time': (x.updated_at - x.created_at).seconds 
                    if x.status == Job.STATUS_DONE else \
                    (datetime.now(timezone.utc) - x.created_at).seconds,
        } for x in Job.objects.filter(user=user).order_by('-created_at')[:limitation]]
    }

    return render(request, 'list_jobs.html', context)
