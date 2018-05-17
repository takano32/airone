from pathlib import Path
from django.http import HttpResponse

import importlib.util
import os

BASE_DIR = os.path.dirname(os.path.realpath(__file__))

# to cache custom view
CUSTOM_VIEW = {}


def _isin_cache(entity_name, method_name):
    return entity_name in CUSTOM_VIEW and method_name in CUSTOM_VIEW

def _is_view(entity_name, method_name):
    # return if cache is hit
    if _isin_cache(entity_name, method_name):
        return True

    filepath = '%s/%s.py' % (BASE_DIR, entity_name)
    if not Path(filepath).is_file():
        return False

    spec = importlib.util.spec_from_file_location(entity_name, filepath)
    model = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(model)

    if entity_name not in CUSTOM_VIEW:
        CUSTOM_VIEW[entity_name] = {}

    if not hasattr(model, method_name):
        return False

    # set custom_view cache
    CUSTOM_VIEW[entity_name][method_name] = getattr(model, method_name)

    return True

def is_custom_create_entry(entity_name):
    return _is_view(entity_name, 'create_entry')

def call_custom_create_entry(entity_name, *args, **kwargs):
    if(_isin_cache(entity_name, 'create_entry') or _is_view(entity_name, 'create_entry')):
        return CUSTOM_VIEW[entity_name]['create_entry'](*args, **kwargs)
    else:
        return HttpResponse("Custom view of create_entry doesn't exist", status=500)

def is_custom_show_entry(entity_name):
    return _is_view(entity_name, 'show_entry')

def call_custom_show_entry(entity_name, *args, **kwargs):
    if(_isin_cache(entity_name, 'show_entry') or _is_view(entity_name, 'show_entry')):
        return CUSTOM_VIEW[entity_name]['show_entry'](*args, **kwargs)
    else:
        return HttpResponse("Custom view of show_entry doesn't exist", status=500)

def is_custom_list_entry(entity_name):
    return _is_view(entity_name, 'list_entry')

def call_custom_list_entry(entity_name, *args, **kwargs):
    if(_isin_cache(entity_name, 'list_entry') or _is_view(entity_name, 'list_entry')):
        return CUSTOM_VIEW[entity_name]['list_entry'](*args, **kwargs)
    else:
        return HttpResponse("Custom view of list_entry doesn't exist", status=500)

def is_custom_edit_entry(entity_name):
    return _is_view(entity_name, 'edit_entry')

def call_custom_edit_entry(entity_name, *args, **kwargs):
    if(_isin_cache(entity_name, 'edit_entry') or _is_view(entity_name, 'edit_entry')):
        return CUSTOM_VIEW[entity_name]['edit_entry'](*args, **kwargs)
    else:
        return HttpResponse("Custom view of edit_entry doesn't exist", status=500)

def is_custom_after_create_entry(entity_name):
    return _is_view(entity_name, 'after_create_entry')

def call_custom_after_create_entry(entity_name, *args, **kwargs):
    if(_isin_cache(entity_name, 'after_create_entry') or _is_view(entity_name, 'after_create_entry')):
        return CUSTOM_VIEW[entity_name]['after_create_entry'](*args, **kwargs)
    else:
        return HttpResponse("Custom view of after_create_entry doesn't exist", status=500)

def is_custom_do_edit_entry(entity_name):
    return _is_view(entity_name, 'do_edit_entry')

def call_custom_do_edit_entry(entity_name, *args, **kwargs):
    if(_isin_cache(entity_name, 'do_edit_entry') or _is_view(entity_name, 'do_edit_entry')):
        return CUSTOM_VIEW[entity_name]['do_edit_entry'](*args, **kwargs)
    else:
        return HttpResponse("Custom view of do_edit_entry doesn't exist", status=500)
