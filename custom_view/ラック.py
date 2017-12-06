from airone.lib.http import render
from entity.models import Entity
from entry.models import Entry, AttributeValue

import collections

def _get_rackspace_entries(entry):
    rackspace_obj = Entry.objects.get(id=entry.attrs.get(name='RackSpace').get_latest_value().referral.id)

    rackspace = {}
    for attr in rackspace_obj.attrs.all():
        rackspace[attr.schema.name] = None
        if attr.get_latest_value():
            rs_entry = Entry.objects.get(id=attr.get_latest_value().referral.id)

            rackspace[attr.schema.name] = {
                'front': rs_entry.attrs.get(name='前面').get_latest_value(),
                'back': rs_entry.attrs.get(name='背面').get_latest_value(),
            }

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
        entry.attrs.get(name='RackSpace').get_latest_value() and
        Entity.objects.filter(name='RackSpaceEntry').count()):

        # set rackspace informatios
        context['rackspace'] = _get_rackspace_entries(entry)

        rse_referrals = []
        for ref_entity in Entity.objects.get(name='RackSpaceEntry').attrs.last().referral.all():
            rse_referrals.append(list(Entry.objects.filter(schema=ref_entity)))
        context['rse_referrals'] = sum(rse_referrals, [])

        # Remove RackSpace from editing Attributes
        context['attributes'] = [x for x in context['attributes'] if x['name'] != 'RackSpace']

        return render(request, 'custom_view/edit_entry_rack.html', context)
    else:
        return render(request, 'edit_entry.html', context)

def do_edit_entry(request, recv_data, user, rack_entry):

    def update_rse(rackside, position, entry_id=None):
        rs_entry = Entry.objects.get(
            id=rack_entry.attrs.get(name='RackSpace').get_latest_value().referral.id
        )
        rs_entry.complement_attrs(user)
        rs_attr = rs_entry.attrs.get(name='%s' % position)

        # If there is no RackSpaceEntry, create and append it to the RackSpace entry
        if not rs_attr.get_latest_value():
            if not entry_id:
                # skip to update RackSpaceEntry when it is not changed
                return

            rse_entry = Entry.objects.create(name='%s-%sU' % (rack_entry.name, position),
                                             schema=Entity.objects.get(name='RackSpaceEntry'),
                                             created_user=user)
            rse_entry.complement_attrs(user)

            rs_attr.values.add(AttributeValue.objects.create(**{
                'created_user': user,
                'parent_attr': rs_attr,
                'referral': rse_entry,
                'status': AttributeValue.STATUS_LATEST,
            }))
        else:
            rse_entry = Entry.objects.get(id=rs_attr.get_latest_value().referral.id)
            rse_entry.complement_attrs(user)

        if rackside == 'rse_front':
            rse_attr = rse_entry.attrs.get(name='前面')
        else:
            rse_attr = rse_entry.attrs.get(name='背面')

        last_value = rse_attr.get_latest_value()
        if ((not last_value and not entry_id) or
            (last_value and not last_value.referral and not entry_id) or
            (last_value and entry_id and last_value.referral and last_value.referral.id == int(entry_id))):

            # skip to update RackSpaceEntry when it is not changed
            return

        # unset latest flag to all existed AttributeValues
        [x.del_status(AttributeValue.STATUS_LATEST) for x in rse_attr.values.all()]

        rse_attr.values.add(AttributeValue.objects.create(**{
            'created_user': user,
            'parent_attr': rs_attr,
            'referral': Entry.objects.get(id=entry_id) if entry_id else None,
            'status': AttributeValue.STATUS_LATEST,
        }))

    if (rack_entry.attrs.filter(name='RackSpace').count() and
        rack_entry.attrs.get(name='RackSpace').get_latest_value() and
        Entity.objects.filter(name='RackSpaceEntry').count()):

        for entry in recv_data['rse_info']:
            entry_id = int(entry['value'])
            if entry_id:
                # update or create RackSpaceEntry and makes a relation with the current Rack
                update_rse(entry['rse_side'], entry['position'], entry_id)
            else:
                # remove if RackSpaceEntry has a referral
                update_rse(entry['rse_side'], entry['position'])

    # This means continuing normal processing
    return (True, None, '')
