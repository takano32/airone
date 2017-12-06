from django.http import HttpResponse

def show_entry(*args, **kwargs):
    return HttpResponse(200)

def list_entry(*args, **kwargs):
    return HttpResponse(200)

def edit_entry(*args, **kwargs):
    return HttpResponse(200)

def do_edit_entry(*args, **kwargs):
    return HttpResponse(200)
