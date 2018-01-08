from django.http import HttpResponse
from django.http.response import JsonResponse
from airone.lib.http import http_get
from airone.lib.types import AttrTypeValue

from entry.models import Entry, Attribute
from entity.models import Entity
from entry.settings import CONFIG


@http_get
def get_referrals(request, entry_id):
    """
    This returns entries by which specified entry is referred.
    """
    if not Entry.objects.filter(id=entry_id).count():
        return HttpResponse('Failed to get ', status=400)

    entry = Entry.objects.get(id=entry_id)
    (entries, total_count) = entry.get_referred_objects()

    # filters the result by keyword
    if 'keyword' in request.GET:
        entries = [x for x in entries if request.GET.get('keyword') in x.name]

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
        'status': x.status,
    } for x in entries]

    # return entries as JSON
    return JsonResponse({'results': entries_data})

@http_get
def get_attr_referrals(request, attr_id):
    """
    This returns entries that target attribute refers to.
    """
    if not Attribute.objects.filter(id=attr_id).count():
        return HttpResponse('Failed to get target attribute(%s)' % attr_id, status=400)

    attr = Attribute.objects.get(id=attr_id)
    if (attr.schema.type != AttrTypeValue['object'] and
        attr.schema.type != AttrTypeValue['array_object']):
        return HttpResponse('Target Attribute does not referring type', status=400)

    if 'keyword' not in request.GET:
        return HttpResponse('Keyword is mandatory to response in this request', status=400)

    results = []
    for referral in attr.schema.referral.all():
        results += [{'id': x.id, 'name': x.name}
                    for x in Entry.objects.filter(schema=referral,
                                                  is_active=True,
                                                  name__regex=request.GET['keyword'])]

    return JsonResponse({'results': results[0:CONFIG.MAX_LIST_REFERRALS]})
