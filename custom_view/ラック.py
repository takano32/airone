from airone.lib.http import render
from entry.models import Entry

import collections

def show_entry(request, user, entry, context):
    if (entry.attrs.filter(name='RackSpace').count() and
        entry.attrs.get(name='RackSpace').get_latest_value()):

        rackspace_obj = Entry.objects.get(id=entry.attrs.get(name='RackSpace').get_latest_value().referral.id)

        # set rackspace informatios
        rackspace = collections.OrderedDict()
        for attr in rackspace_obj.attrs.all():
            rackspace[attr.schema.name] = None
            if attr.get_latest_value():
                rs_entry = Entry.objects.get(id=attr.get_latest_value().referral.id)

                rackspace[attr.schema.name] = {
                    'front': rs_entry.attrs.get(name='前面').get_latest_value(),
                    'back': rs_entry.attrs.get(name='背面').get_latest_value(),
                }
        context['rackspace'] = rackspace
        return render(request, 'custom_view/show_entry_rack.html', context)
    else:
        # show ordinal view if this rack doesn't have RackSpace entry
        return render(request, 'show_entry.html', context)
