import json

from django.conf import settings
from elasticsearch import Elasticsearch


class ESS(Elasticsearch):
    MAX_TERM_SIZE = 32766

    def __init__(self, index=None, *args, **kwargs):
        self.additional_config = False

        if not index:
            self._index = settings.ES_CONFIG['INDEX']

        if ('timeout' not in kwargs) and (settings.ES_CONFIG['TIMEOUT'] is not None):
            kwargs['timeout'] = settings.ES_CONFIG['TIMEOUT']

        super(ESS, self).__init__(settings.ES_CONFIG['NODES'], *args, **kwargs)

    def delete(self, *args, **kwargs):
        return super(ESS, self).delete(index=self._index, *args, **kwargs)

    def refresh(self, *args, **kwargs):
        return self.indices.refresh(index=self._index, *args, **kwargs)

    def index(self, *args, **kwargs):
        return super(ESS, self).index(index=self._index, *args, **kwargs)

    def search(self, *args, **kwargs):
        # expand max_result_window parameter which indicates numbers to return at one searching
        if not self.additional_config:
            self.additional_config = True

            body = {"index": {"max_result_window" : settings.ES_CONFIG['MAXIMUM_RESULTS_NUM']}}
            self.indices.put_settings(index=self._index, body=body)

        return super(ESS, self).search(index=self._index,
                                       size=settings.ES_CONFIG['MAXIMUM_RESULTS_NUM'], *args, **kwargs)

    def recreate_index(self):
        self.indices.delete(index=self._index, ignore=[400, 404])
        self.indices.create(index=self._index, ignore=400, body=json.dumps({
            'mappings': {
                'entry': {
                    'properties': {
                        'name': {
                            'type': 'text',
                            'index': 'true',
                            'analyzer': 'keyword',
                            'fields': {
                                'keyword': { 'type': 'keyword' },
                            },
                        },
                        'entity': {
                            'type': 'nested',
                            'properties': {
                                'id': {
                                    'type': 'integer',
                                    'index': 'true',
                                },
                                'name': {
                                    'type': 'text',
                                    'index': 'true',
                                    'analyzer': 'keyword'
                                }
                            }
                        },
                        'attr': {
                            'type': 'nested',
                            'properties': {
                                'name': {
                                    'type': 'text',
                                    'index': 'true',
                                    'analyzer': 'keyword'
                                },
                                'type': {
                                    'type': 'integer',
                                    'index': 'false',
                                },
                                'id': {
                                    'type': 'integer',
                                    'index': 'false',
                                },
                                'key': {
                                    'type': 'text',
                                    'index': 'true',
                                },
                                'date_value': {
                                    'type': 'date',
                                    'index': 'true',
                                },
                                'value': {
                                    'type': 'text',
                                    'index': 'true',
                                    'analyzer': 'keyword'
                                },
                                'referral_id': {
                                    'type': 'integer',
                                    'index': 'false',
                                }
                            }
                        }
                    }
                }
            }
        }))
