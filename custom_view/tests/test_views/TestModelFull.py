from django.http import HttpResponse

def show_entry(*args, **kwargs):
    return HttpResponse(200)
