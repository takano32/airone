import io
import yaml

import custom_view

from django.http import HttpResponse
from django.http.response import JsonResponse
from django.db.models import Q

from airone.lib.http import http_get, http_post, check_permission, render
from airone.lib.http import get_download_response
from airone.lib.http import http_file_upload
from airone.lib.http import HttpResponseSeeOther
from airone.lib.types import AttrTypeValue
from airone.lib.acl import get_permitted_objects
from airone.lib.acl import ACLType
from airone.lib.profile import airone_profile

from entity.models import Entity, EntityAttr
from entity.admin import EntityResource
from entry.models import Entry, Attribute, AttributeValue
from entry.admin import EntryResource, AttrResource, AttrValueResource
from user.models import User
from group.models import Group
from .settings import CONFIG
from .tasks import create_entry_attrs, edit_entry_attrs, delete_entry


@airone_profile
@http_get
@check_permission(Entity, ACLType.Readable)
def index(request, entity_id):
    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    entity = Entity.objects.get(id=entity_id)
    entries = Entry.objects.order_by('name').filter(schema=entity, is_active=True)

    total_count = list_count = len(entries)
    if(len(entries) > CONFIG.MAX_LIST_ENTRIES):
        entries = entries[0:CONFIG.MAX_LIST_ENTRIES]
        list_count = CONFIG.MAX_LIST_ENTRIES

    context = {
        'entity': entity,
        'entries': entries,
        'total_count': total_count,
        'list_count': list_count,
    }
    return render(request, 'list_entry.html', context)

@http_get
@check_permission(Entity, ACLType.Writable)
def create(request, entity_id):
    user = User.objects.get(id=request.user.id)

    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    def get_referrals(attr):
        ret = []
        for entries in [Entry.objects.filter(schema=x, is_active=True) for x in attr.referral.filter(is_active=True)]:
            ret += [{'id': x.id, 'name': x.name} for x in entries]

        return ret

    entity = Entity.objects.get(id=entity_id)
    context = {
        'form_url': '/entry/do_create/%s/' % entity.id,
        'redirect_url': '/entry/%s' % entity.id,
        'nav_headers': [
            {'href': '/', 'text': 'TOP'},
            {'href': '/entry/%s' % entity.id, 'text': '%s' % entity.name},
            {'text': '新規エントリ作成 (%s)' % entity.name},
        ],
        'groups': Group.objects.filter(is_active=True),
        'attributes': [{
            'id': x.id,
            'type': x.type,
            'name': x.name,
            'is_mandatory': x.is_mandatory,
            'referrals': x.referral.count() and get_referrals(x) or [],
        } for x in entity.attrs.filter(is_active=True).order_by('index') if user.has_permission(x, ACLType.Writable)]
    }
    return render(request, 'edit_entry.html', context)

@airone_profile
@http_post([
    {'name': 'entry_name', 'type': str, 'checker': lambda x: x['entry_name']},
    {'name': 'attrs', 'type': list, 'meta': [
        {'name': 'id', 'type': str},
        {'name': 'value', 'type': list,
           'checker': lambda x: (
               EntityAttr.objects.filter(id=x['id']).count() > 0 and
               (EntityAttr.objects.get(id=x['id']).is_mandatory and x['value'] or
               not EntityAttr.objects.get(id=x['id']).is_mandatory)
           )},
    ]}
])
@check_permission(Entity, ACLType.Writable)
def do_create(request, entity_id, recv_data):
    # get objects to be referred in the following processing
    user = User.objects.get(id=request.user.id)
    entity = Entity.objects.get(id=entity_id)

    # checks that a same name entry corresponding to the entity is existed, or not.
    if Entry.objects.filter(schema=entity_id, name=recv_data['entry_name']).count():
        return HttpResponse('Duplicate name entry is existed', status=400)

    # validate contexts of each attributes
    for attr_data in recv_data['attrs']:
        # Checks specified value exceeds the limit of AttributeValue
        if any([len(str(y['data']).encode('utf-8')) > AttributeValue.MAXIMUM_VALUE_SIZE for y in attr_data['value']]):
            return HttpResponse('Passed value is exceeded the limit', status=400)

    # Create a new Entry object
    entry = Entry(name=recv_data['entry_name'],
                  created_user=user,
                  schema=entity,
                  status=Entry.STATUS_CREATING)
    entry.save()

    # register a task to create Attributes for the created entry
    val = create_entry_attrs.delay(user.id, entry.id, recv_data)

    return JsonResponse({
        'entry_id': entry.id,
        'entry_name': entry.name,
    })

@airone_profile
@http_get
@check_permission(Entry, ACLType.Writable)
def edit(request, entry_id):
    user = User.objects.get(id=request.user.id)

    if not Entry.objects.filter(id=entry_id).count():
        return HttpResponse('Failed to get an Entry object of specified id', status=400)

    entry = Entry.objects.get(id=entry_id)

    # prevent to show edit page under the creating processing
    if entry.get_status(Entry.STATUS_CREATING):
        return HttpResponse('Target entry is now under processing', status=400)

    entry.complement_attrs(user)

    context = {
        'entry': entry,
        'groups': Group.objects.filter(is_active=True),
        'nav_headers': [
            {'href': '/', 'text': 'TOP'},
            {'href': '/entry/%s' % entry.schema.id, 'text': '%s' % entry.schema.name},
            {'href': '/entry/show/%s' % entry.id, 'text': '%s' % entry.name},
            {'text': '%s の編集' % entry.name},
        ],
        'attributes': entry.get_available_attrs(user, ACLType.Writable, get_referral_entries=True),
        'form_url': '/entry/do_edit/%s' % entry.id,
        'redirect_url': '/entry/show/%s' % entry.id,
    }

    if custom_view.is_custom_edit_entry(entry.schema.name):
        # show custom view
        return custom_view.call_custom_edit_entry(entry.schema.name, request, user, entry, context)
    else:
        return render(request, 'edit_entry.html', context)

@airone_profile
@http_post([
    {'name': 'entry_name', 'type': str, 'checker': lambda x: (
        x['entry_name']
    )},
    {'name': 'attrs', 'type': list, 'meta': [
        {'name': 'id', 'type': str},
        {'name': 'value', 'type': list,
           'checker': lambda x: (
               Attribute.objects.filter(id=x['id']).count() > 0 and
               (Attribute.objects.get(id=x['id']).schema.is_mandatory and x['value'] or
               not Attribute.objects.get(id=x['id']).schema.is_mandatory)
           )},
    ]},
])
@check_permission(Entry, ACLType.Writable)
def do_edit(request, entry_id, recv_data):
    user = User.objects.get(id=request.user.id)
    entry = Entry.objects.get(id=entry_id)

    # checks that a same name entry corresponding to the entity is existed.
    query = Q(schema=entry.schema, name=recv_data['entry_name']) & ~Q(id=entry.id)
    if Entry.objects.filter(query).count():
        return HttpResponse('Duplicate name entry is existed', status=400)

    # Checks specified value exceeds the limit of AttributeValue
    for attr_data in recv_data['attrs']:
        # Checks specified value exceeds the limit of AttributeValue
        if any([len(str(y['data']).encode('utf-8')) > AttributeValue.MAXIMUM_VALUE_SIZE for y in attr_data['value']]):
            return HttpResponse('Passed value is exceeded the limit', status=400)

    if entry.get_status(Entry.STATUS_CREATING):
        return HttpResponse('Target entry is now under processing', status=400)

    if custom_view.is_custom_do_edit_entry(entry.schema.name):
        (is_continue, code, msg) = custom_view.call_custom_do_edit_entry(entry.schema.name,
                                                                         request, recv_data,
                                                                         user, entry)
        if not is_continue:
            return HttpResponse(msg, status=code)

    # update name of Entry object
    entry.name = recv_data['entry_name']

    # set flags that indicates target entry is under processing
    entry.set_status(Entry.STATUS_EDITING)

    entry.save()

    # register a task to edit entry attributes
    edit_entry_attrs.delay(user.id, entry.id, recv_data)

    return JsonResponse({
        'entry_id': entry.id,
        'entry_name': entry.name,
    })

@airone_profile
@http_get
@check_permission(Entry, ACLType.Readable)
def show(request, entry_id):
    user = User.objects.get(id=request.user.id)

    if not Entry.objects.filter(id=entry_id).count():
        return HttpResponse('Failed to get an Entry object of specified id', status=400)

    entry = Entry.objects.get(id=entry_id)

    if entry.get_status(Entry.STATUS_CREATING):
        return HttpResponse('Target entry is now under processing', status=400)

    # create new attributes which are appended after creation of Entity
    entry.complement_attrs(user)

    # create new attributes which are appended after creation of Entity
    for attr_id in (set(entry.schema.attrs.values_list('id', flat=True)) -
                    set([x.schema.id for x in entry.attrs.filter(is_active=True)])):

        entity_attr = entry.schema.attrs.get(id=attr_id)
        if not entity_attr.is_active or not user.has_permission(entity_attr, ACLType.Readable):
            continue

        newattr = entry.add_attribute_from_base(entity_attr, user)
        if entity_attr.type & AttrTypeValue['array']:
            # Create a initial AttributeValue for editing processing
            attr_value = AttributeValue.objects.create(created_user=user, parent_attr=newattr)

            # Set a flag that means this is the latest value
            attr_value.set_status(AttributeValue.STATUS_LATEST)

            # Set status of parent data_array
            attr_value.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)

            newattr.values.add(attr_value)

    # get all values that are set in the past
    value_history = sum([x.get_value_history(user) for x in entry.attrs.filter(is_active=True)], [])

    # get referred entries and count of them
    (referred_objects, referred_total) = entry.get_referred_objects(CONFIG.MAX_LIST_REFERRALS,
                                                                    use_cache=True)

    context = {
        'entry': entry,
        'attributes': entry.get_available_attrs(user),
        'value_history': sorted(value_history, key=lambda x: x['created_time']),
        'referred_objects': referred_objects[0:CONFIG.MAX_LIST_REFERRALS],
        'referred_total': referred_total,
    }

    if custom_view.is_custom_show_entry(entry.schema.name):
        # show custom view
        return custom_view.call_custom_show_entry(entry.schema.name, request, user, entry, context)
    else:
        # show ordinal view
        return render(request, 'show_entry.html', context)

@http_get
def export(request, entity_id):
    output = io.StringIO()
    user = User.objects.get(id=request.user.id)

    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    entity = Entity.objects.get(id=entity_id)
    if not user.has_permission(entity, ACLType.Readable):
        return HttpResponse('Permission denied to export "%s"' % entity.name, status=400)

    exported_data = []
    for entry in Entry.objects.filter(schema=entity, is_active=True):
        if user.has_permission(entry, ACLType.Readable):
            exported_data.append(entry.export(user))

    if 'format' in request.GET and request.GET.get('format') == 'CSV':
        fname = 'entry_%s.csv' % entity.name

        attrs = [x.name for x in entity.attrs.filter(is_active=True)]
        output.write('%s\n' % (','.join(['Name', *attrs])))

        def data2str(data):
            if not data:
                return ''
            elif isinstance(data, str):
                return '"%s"' % data.replace('"', '""')
            elif isinstance(data, list) or isinstance(data, hash):
                return '"""%s"""' % str(data)
            else:
                return '""' % str(data)

        for data in exported_data:
            output.write('%s\n' % ','.join([data['name'], *[data2str(data['attrs'][x]) for x in attrs]]))

    else:
        fname = 'entry_%s.yaml' % entity.name
        output.write(yaml.dump({entity.name: exported_data}, default_flow_style=False, allow_unicode=True))

    return get_download_response(output, fname)


@http_get
def import_data(request, entity_id):
    if not Entity.objects.filter(id=entity_id, is_active=True).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    return render(request, 'import_entry.html', {'entity': Entity.objects.get(id=entity_id)})

@http_file_upload
def do_import_data(request, entity_id, context):
    user = User.objects.get(id=request.user.id)
    if not Entity.objects.filter(id=entity_id).count():
        return HttpResponse('Failed to get entity of specified id', status=400)

    entity = Entity.objects.get(id=entity_id)
    if not user.has_permission(entity, ACLType.Readable):
        return HttpResponse('Permission denied to export "%s"' % entity.name, status=400)

    try:
        data = yaml.load(context)
    except yaml.parser.ParserError:
        return HttpResponse("Couldn't parse uploaded file", status=400)

    # validate uploaded format and context
    values = data.get(entity.name)
    if not values:
        return HttpResponse("Uploaded file has not import data for '%s'" % entity.name, status=400)

    if not all(['name' in x or 'attrs' in x or isinstance(x['attrs'], dict) for x in values]):
        return HttpResponse("Uploaded file is invalid format to import", status=400)

    entity_attrs = [x.name for x in entity.attrs.filter(is_active=True)]
    if not all([any([k in y.keys() for k in entity_attrs]) for y in [x['attrs'] for x in values]]):
        return HttpResponse("Uploaded file has invalid parameter", status=400)

    # create or update entry
    for entry_data in values:
        if Entry.objects.filter(name=entry_data['name'], schema=entity):
            entry = Entry.objects.get(name=entry_data['name'], schema=entity)
        else:
            entry = Entry.objects.create(name=entry_data['name'], schema=entity, created_user=user)

        entry.complement_attrs(user)
        for attr_name, value in entry_data['attrs'].items():
            # If user doesn't have readable permission for target Attribute, it won't be created.
            if not entry.attrs.filter(name=attr_name):
                continue

            attr = entry.attrs.get(name=attr_name)
            input_value = attr.convert_value_to_register(value)
            if user.has_permission(attr.schema, ACLType.Writable) and attr.is_updated(input_value):
                attr.add_value(user, input_value)

    return HttpResponseSeeOther('/entry/%s/' % entity_id)

@http_post([]) # check only that request is POST, id will be given by url
@check_permission(Entry, ACLType.Full)
def do_delete(request, entry_id, recv_data):
    user = User.objects.get(id=request.user.id)
    ret = {}

    if not Entry.objects.filter(id=entry_id).count():
        return HttpResponse('Failed to get an Entry object of specified id', status=400)

    # update name of Entry object
    entry = Entry.objects.filter(id=entry_id).get()

    # set deleted flag in advance because deleting processing taks long time
    entry.is_active = False

    # save deleting Entry name before do it
    ret['name'] = entry.name

    # register operation History for deleting entry
    user.seth_entry_del(entry)

    delete_entry.delay(entry.id)

    return JsonResponse(ret)

@airone_profile
@http_get
@check_permission(Entry, ACLType.Writable)
def copy(request, entry_id):
    user = User.objects.get(id=request.user.id)

    if not Entry.objects.filter(id=entry_id).count():
        return HttpResponse('Failed to get an Entry object of specified id', status=400)

    entry = Entry.objects.get(id=entry_id)

    context = {
        'form_url': '/entry/do_copy/%s' % entry.id,
        'redirect_url': '/entry/%s' % entry.schema.id,
        'entry': entry,
    }
    return render(request, 'copy_entry.html', context)

@airone_profile
@http_post([
    {'name': 'entries', 'type': str},
])
@http_post([])
@check_permission(Entry, ACLType.Writable)
def do_copy(request, entry_id, recv_data):
    user = User.objects.get(id=request.user.id)

    # validation check
    if 'entries' not in recv_data:
        return HttpResponse('Malformed data is specified (%s)' % recv_data, status=400)

    if not Entry.objects.filter(id=entry_id).count():
        return HttpResponse('Failed to get an Entry object of specified id', status=400)

    ret = []
    entry = Entry.objects.get(id=entry_id)
    for new_name in [x for x in recv_data['entries'].split('\n') if x]:
        if Entry.objects.filter(schema=entry.schema, name=new_name).count() > 0:
            ret.append({
                'status': 'fail',
                'msg': 'A same named entry (%s) is already existed' % new_name,
            })
            continue

        new_entry = entry.clone(user, name=new_name)
        ret.append({
            'status': 'success',
            'msg': "Success to create new entry '%s'" % new_name,
        })

    return JsonResponse({'results': ret})
