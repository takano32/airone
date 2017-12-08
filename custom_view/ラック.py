from airone.lib.http import render
from entity.models import Entity
from entry.models import Entry, AttributeValue

import collections

def _get_rackspace_entries(entry):
    rackspace_obj = Entry.objects.get(id=entry.attrs.get(name='RackSpace').get_latest_value().referral.id)

    rackspace = {}
    for attr in rackspace_obj.attrs.all():
        attrv_parent = attr.get_latest_value()
        if attrv_parent:
            rackspace[attr.schema.name] = attrv_parent.data_array.all()

    # sorted rackspacec entries
    return collections.OrderedDict(sorted(rackspace.items(), key=lambda x:int(x[0]), reverse=True))


def show_entry(request, user, entry, context):
    if (entry.attrs.filter(name='RackSpace').count() and
        entry.attrs.get(name='RackSpace').get_latest_value()):

        # set rackspace informatios
        context['rackspace'] = _get_rackspace_entries(entry)

        return render(request, 'custom_view/show_entry_rack.html', context)
    else:
        # show ordinal view if this rack doesn't have RackSpace entry
        return render(request, 'show_entry.html', context)

def edit_entry(request, user, entry, context):
    if (entry.attrs.filter(name='RackSpace').count() and
        entry.attrs.get(name='RackSpace').get_latest_value()):

        # set rackspace informatios
        context['rackspace'] = _get_rackspace_entries(entry)

        rse_referrals = []
        for ref_entity in entry.attrs.get(name='ZeroU').schema.referral.all():
            rse_referrals.append(list(Entry.objects.filter(schema=ref_entity)))
        context['rse_referrals'] = sum(rse_referrals, [])

        # Remove RackSpace from editing Attributes
        context['attributes'] = [x for x in context['attributes'] if x['name'] != 'RackSpace']

        return render(request, 'custom_view/edit_entry_rack.html', context)
    else:
        return render(request, 'edit_entry.html', context)

def do_edit_entry(request, recv_data, user, rack_entry):
    if (rack_entry.attrs.filter(name='RackSpace').count() and
        rack_entry.attrs.get(name='RackSpace').get_latest_value()):

        rse = Entry.objects.get(id=rack_entry.attrs.get(name='RackSpace').get_latest_value().referral.id)
        rse.complement_attrs(user)

        for attr in rse.attrs.all():
            old_attrv = attr.get_latest_value()
            # The case update is not specified 
            if not old_attrv and attr.name not in [x['position'] for x in recv_data['rse_info']]:
                continue

            if old_attrv:
                old_values = sorted([int(x.id) for x in old_attrv.data_array.all()])
                set_values = sorted([int(x['target_id']) for x in recv_data['rse_info'] if x['position'] == attr.name])
                # The case there is no updated
                if old_values == set_values:
                    continue

            # clear latest flag from old values
            if old_attrv:
                [x.del_status(AttributeValue.STATUS_LATEST) for x in old_attrv.data_array.all()]
            [x.del_status(AttributeValue.STATUS_LATEST) for x in attr.values.all()]

            new_parent_attrv = AttributeValue(created_user=user, parent_attr=attr)
            new_parent_attrv.set_status(AttributeValue.STATUS_DATA_ARRAY_PARENT)
            new_parent_attrv.set_status(AttributeValue.STATUS_LATEST)
            new_parent_attrv.save()

            attr.values.add(new_parent_attrv)

            for data in [x for x in recv_data['rse_info'] if x['position'] == attr.name]:
                attrv = AttributeValue(**{
                    'created_user': user,
                    'parent_attr': attr,
                    'referral': Entry.objects.get(id=data['target_id']),
                    'status': AttributeValue.STATUS_LATEST,
                })
                attrv.save()

                new_parent_attrv.data_array.add(attrv)

    # This means continuing normal processing
    return (True, None, '')
