import re

from django.db.models import Q
from django.http import HttpResponse
from django.http.response import JsonResponse
from airone.lib.http import http_get, http_post
from airone.lib.types import AttrTypeValue
from airone.lib.profile import airone_profile

from entry.models import Entry, Attribute
from entity.models import Entity, EntityAttr
from entry.settings import CONFIG


@airone_profile
@http_get
def get_referrals(request, entry_id):
    """
    This returns entries by which specified entry is referred.
    """
    if not Entry.objects.filter(id=entry_id).exists():
        return HttpResponse('Failed to get ', status=400)

    entry = Entry.objects.get(id=entry_id)
    entries = list(entry.get_referred_objects())
    total_count = len(entries)

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
        'total_count': total_count,
    })

@http_post([
    {'name': 'cond_params', 'type': list, 'meta': [
        {'name': 'type', 'type': str,
         'checker': lambda x: x['type'] == 'text' or x['type'] == 'entry'},
    ]},
])
def search_entries(request, entity_ids, recv_data):
    cond_link = 'or'
    if 'cond_link' in recv_data and any([x for x in ['and', 'or'] if x == recv_data['cond_link']]):
        cond_link = recv_data['cond_link']

    total_entries = []
    for entity_id in entity_ids.split(','):
        if not Entity.objects.filter(id=entity_id).exists():
            return HttpResponse('Failed to get entity(%s)' % entity_id, status=400)

        entries = Entry.objects.order_by('name').filter(schema__id=entity_id, is_active=True)
        total_entries += entries.all()

    if not total_entries:
        return JsonResponse({'results': []})

    def _is_match_value(attrv, cond):
        if cond['type'] == 'text':
            return re.match(r'.*%s' % cond['value'], attrv.value)
        else:
            return int(cond['value']) == attrv.referral.id

    def _is_match_attrs(attrs, cond):
        # Ignore he case a value is not specified
        if 'value' not in cond or not cond['value']:
            return False

        for attr in attrs:
            # The case specified condition doesn't match with attribute type
            if ((cond['type'] == 'text' and not attr.schema.type & AttrTypeValue['string']) or
                (cond['type'] == 'entry' and not attr.schema.type & AttrTypeValue['object'])):
                continue

            # The case target attribute has no value
            attrv = attr.get_latest_value()
            if not attrv:
                continue

            if attr.schema.type & AttrTypeValue['array']:
                ret = any([_is_match_value(x, cond) for x in attrv.data_array.all()])
            else:
                ret = _is_match_value(attrv, cond)

            # Interrupt search processing when a matched parameter is found
            if ret:
                return True

    def _is_match_entry(entry):
        attrs = entry.attrs.filter(is_active=True)
        if cond_link == 'or':
            return any([_is_match_attrs(attrs, cond) for cond in recv_data['cond_params']])
        else:
            return all([_is_match_attrs(attrs, cond) for cond in recv_data['cond_params']])

    ret_entries = [x for x in total_entries if _is_match_entry(x)]

    return JsonResponse({
        'results': [{
            'id': x.id,
            'name': x.name,
            'schema_id': x.schema.id,
            'schema_name': x.schema.name,
        } for x in ret_entries],
    })

@http_get
def get_entries(request, entity_ids):
    total_entries = []
    for entity_id in [x for x in entity_ids.split(',') if x and Entity.objects.filter(id=x, is_active=True).exists()]:
        keyword = request.GET.get('keyword')
        if keyword:
            query_name_regex = Q(name__regex=keyword)
        else:
            query_name_regex = Q()

        total_entries += Entry.objects.order_by('name').filter(Q(schema__id=entity_id, is_active=True), query_name_regex)
        if(len(total_entries) > CONFIG.MAX_LIST_ENTRIES):
            break

    if(len(total_entries) > CONFIG.MAX_LIST_ENTRIES):
        total_entries = total_entries[0:CONFIG.MAX_LIST_ENTRIES]

    # serialize data for each entries to convert json format
    entries_data = [{
        'id': x.id,
        'name': x.name,
        'status': x.status,
    } for x in total_entries]

    # return entries as JSON
    return JsonResponse({'results': entries_data})

@http_get
def get_attr_referrals(request, attr_id):
    """
    This returns entries that target attribute refers to.
    """
    if (not Attribute.objects.filter(id=attr_id).exists() and
        not EntityAttr.objects.filter(id=attr_id).exists()):
        return HttpResponse('Failed to get target attribute(%s)' % attr_id, status=400)

    attr = None
    if Attribute.objects.filter(id=attr_id).exists():
        attr = Attribute.objects.get(id=attr_id).schema
    else:
        attr = EntityAttr.objects.get(id=attr_id)

    if not attr.type & AttrTypeValue['object']:
        return HttpResponse('Target Attribute does not referring type', status=400)

    results = []
    for referral in attr.referral.all():
        keyword = request.GET.get('keyword')
        if keyword:
            query_name_regex = Q(name__regex=keyword)
        else:
            query_name_regex = Q()

        results += [{'id': x.id, 'name': x.name}
                    for x in Entry.objects.filter(Q(schema=referral, is_active=True), query_name_regex)]

        if len(results) > CONFIG.MAX_LIST_REFERRALS:
            break

    return JsonResponse({'results': results[0:CONFIG.MAX_LIST_REFERRALS]})
