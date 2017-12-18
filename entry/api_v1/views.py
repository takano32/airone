from django.http import HttpResponse
from django.http.response import JsonResponse
from airone.lib.http import http_get

from entry.models import Entry
from entity.models import Entity
from entry.settings import CONFIG


@http_get
def get_referrals(request, entry_id):
    if not Entry.objects.filter(id=entry_id).count():
        return HttpResponse('Failed to get ', status=400)

    keyword = None
    if 'keyword' in request.GET:
        keyword = request.GET.get('keyword')

    entry = Entry.objects.get(id=entry_id)
    (entries, total_count) = entry.get_referred_objects(keyword=keyword)

    # serialize data for each entries to convert json format
    entries_data = [{
        'id': x.id,
        'name': x.name,
        'entity': x.schema.name
    } for c, x in enumerate(entries) if c < CONFIG.MAX_LIST_REFERRALS]

    # return referred entries as JSON
    return JsonResponse({
        'entries': entries_data,
        'found_count': len(entries_data),
        'total_count': total_count
    })

@http_get
def get_entries(request, entity_id):
    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity(%s)' % entity_id, status=400)

    entries = Entry.objects.order_by('name').filter(schema=Entity.objects.get(id=entity_id), is_active=True)
    if 'keyword' in request.GET:
        entries = entries.filter(name__regex=request.GET.get('keyword'))

    if(len(entries) > CONFIG.MAX_LIST_ENTRIES):
        entries = entries[0:CONFIG.MAX_LIST_ENTRIES]

    # serialize data for each entries to convert json format
    entries_data = [{
        'id': x.id,
        'name': x.name,
    } for x in entries]

    # return entries as JSON
    return JsonResponse({'results': entries_data})
