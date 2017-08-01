import tablib


class Importable(object):
    @classmethod
    def import_data(self, data, request_user):
        resource = getattr(importlib.import_module(self._IMPORT_INFO['resource_module']),
                           self._IMPORT_INFO['resource_model_name'])()
        if not resource:
            raise RuntimeError("Resource object is not defined")

        # set user who import the data for checking permission
        resource.request_user = request_user

        # check mandatory keys are existed, or not
        if not all([x in data for x in self._IMPORT_INFO['mandatory_keys']]):
            raise RuntimeError("Mandatory key doesn't exist")

        # check unnecessary parameters are specified, or not
        if not all([x in self._IMPORT_INFO['header'] for x in data.keys()]):
            raise RuntimeError("Unnecessary key is specified")

        # get dataset to import
        dataset = tablib.Dataset([x in data and data[x] or '' for x in self._IMPORT_INFO['header']],
                                 headers=self._IMPORT_INFO['header'])

        resource.import_data(dataset)
