import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import db


class ReplacementClaimTests(unittest.TestCase):
    def client(self, rows, claimed):
        client = MagicMock()
        query = client.table.return_value
        for method in ('select', 'eq', 'is_', 'order', 'limit'):
            getattr(query, method).return_value = query
        query.execute.return_value = SimpleNamespace(data=rows)
        client.rpc.return_value.execute.return_value = SimpleNamespace(data=claimed)
        return client, query

    def test_scoped_worker_only_reads_its_own_replacement_queue(self):
        client, query = self.client([{'id': 'request'}], [{'id': 'request', 'status': 'processing'}])
        with patch.object(db, 'get_client', return_value=client), patch.object(db.config, 'WORKER_TASK_ID', 'isolated-task'):
            self.assertEqual('request', db.claim_next_image_replacement()['id'])
        query.eq.assert_any_call('task_id', 'isolated-task')
        client.rpc.assert_called_once_with('claim_image_replacement', {'p_request_id': 'request'})
        query.update.assert_not_called()

    def test_invalidated_or_busy_request_is_not_claimed(self):
        client, _ = self.client([{'id': 'obsolete-request'}], [])
        with patch.object(db, 'get_client', return_value=client):
            self.assertIsNone(db.claim_next_image_replacement())

    def test_empty_queue_does_not_attempt_claim(self):
        client, _ = self.client([], [])
        with patch.object(db, 'get_client', return_value=client):
            self.assertIsNone(db.claim_next_image_replacement())
        client.rpc.assert_not_called()
