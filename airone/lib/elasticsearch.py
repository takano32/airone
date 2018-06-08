import json

from django.conf import settings
from elasticsearch import Elasticsearch


class ESS(Elasticsearch):
    MAX_TERM_SIZE = 32766

    def __init__(self, index=None, *args, **kwargs):
        if not index:
            self._index = settings.ES_CONFIG['INDEX']

        super(ESS, self).__init__(settings.ES_CONFIG['NODES'], *args, **kwargs)

    def delete(self, *args, **kwargs):
        return super(ESS, self).delete(index=self._index, *args, **kwargs)

    def refresh(self, *args, **kwargs):
        return self.indices.refresh(index=self._index, *args, **kwargs)

    def index(self, *args, **kwargs):
        return super(ESS, self).index(index=self._index, *args, **kwargs)

    def search(self, *args, **kwargs):
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
                            'analyzer': 'keyword'
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
