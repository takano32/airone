import mock
import re

from django.test import TestCase

from entity.models import Entity
from history.models import History
from user.models import User


class ModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='test')
        
        self.op_sets = {
            'entity': [
                {'op': 'add_entity', 'flag': History.OP_ADD_ENTITY, 'msg_ptn': ".*を作成"},
                {'op': 'mod_entity', 'flag': History.OP_MOD_ENTITY, 'msg_ptn': ".*を変更"},
                {'op': 'del_entity', 'flag': History.OP_DEL_ENTITY, 'msg_ptn': ".*を削除"},
            ],
        }

    def test_record_entity(self):
        entity = Entity.objects.create(name='entity', created_user=self.user)
     
        count = 0
        for op_set in self.op_sets['entity']:
            # make a History object
            getattr(History, op_set['op'])(entity, self.user)

            count += 1
            self.assertEqual(History.objects.count(), count)
    
            elem = History.objects.last()
            self.assertEqual(elem.user, self.user)
            self.assertEqual(elem.target_obj.id, entity.id)
            self.assertEqual(elem.operation, op_set['flag'])
            self.assertIsNotNone(re.match(op_set['msg_ptn'], elem.detail))

    def test_record_entity_without_detail(self):
        entity = Entity.objects.create(name='entity', created_user=self.user)
       
        count = 0
        save_msg = 'history_record'
        for op_set in self.op_sets['entity']:
            # make a History object
            getattr(History, op_set['op'])(entity, self.user, save_msg)

            count += 1
            self.assertEqual(History.objects.count(), count)
            self.assertEqual(History.objects.last().detail, save_msg)

    def test_record_entity_with_invalid_obj(self):
        err_msgs = []

        count = 0
        with mock.patch('history.models.Logger') as lg_mock:
            def side_effect(message):
                err_msgs.append(message)

            lg_mock.error = mock.Mock(side_effect=side_effect)

            for op_set in self.op_sets['entity']:
                count += 1
                # make a History object with invalid object '{}'
                getattr(History, op_set['op'])({}, self.user)

        self.assertEqual(History.objects.count(), 0)
        self.assertEqual(len(err_msgs), count)
