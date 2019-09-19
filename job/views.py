import io

from datetime import datetime, timezone
from django.http import HttpResponse
from django.shortcuts import render

# libraries of AirOne
from airone.lib.http import get_download_response
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
                    if x.is_finished() else (datetime.now(timezone.utc) - x.created_at).seconds,
        } for x in Job.objects.filter(user=user).order_by('-created_at')[:limitation] \
                if (x.operation == Job.OP_EXPORT or (x.operation != Job.OP_EXPORT and x.target.is_active))]
    }

    return render(request, 'list_jobs.html', context)

@http_get
def download(request, job_id):
    user = User.objects.get(id=request.user.id)

    job = Job.objects.filter(id=job_id).first()
    if not job:
        return HttpResponse("Invalid Job-ID is specified", status=400)

    if job.user.id != user.id:
        return HttpResponse("Target Job is executed by other people", status=400)

    if job.operation not in [Job.OP_EXPORT]:
        return HttpResponse("Target Job has no value to return", status=400)

    # get value associated this Job from cache
    io_stream = io.StringIO()
    try:
        io_stream.write(job.get_cache())
    except FileNotFoundError:
        return HttpResponse("This result is no longer available", status=400)

    return get_download_response(io_stream, job.text)
