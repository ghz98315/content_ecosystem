import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from ready_script import build_payload, materialize
from stages import ingest, rewrite


class ReadyScriptTests(unittest.TestCase):
    def test_import_preserves_confirmed_paragraphs_and_downstream_contract(self):
        text = '这是已经确认的第一段文案，请直接朗读。\n\n这是第二段，保留原有标点和段落。'
        payload = build_payload(text, 'guoxue')
        self.assertEqual(text, payload['final_text'])
        self.assertEqual([text], payload['candidates'])
        self.assertEqual(0, payload['chosen'])
        self.assertTrue(payload['imported_final_script'])

    def test_ingest_adapter_skips_source_collection(self):
        stage = {'task_id': 'example', 'params': {'input_mode': 'ready_script', 'ready_script_text': '已经确认的文案' * 6}}
        with patch('ready_script.materialize', return_value='example/rewrite/imported.json') as materialize:
            self.assertEqual(('done', 'example/rewrite/imported.json'), ingest.run(stage))
        materialize.assert_called_once_with(stage)

    def test_too_short_script_is_rejected(self):
        with self.assertRaises(ValueError):
            build_payload('太短', 'health')

    def test_rerunning_confirmed_script_never_calls_rewrite_model(self):
        stage = {'id': 'rewrite-stage', 'task_id': 'example', 'params': {'input_mode': 'ready_script'}}
        ingest_query = SimpleNamespace(data={'params': {'input_mode': 'ready_script', 'ready_script_text': '确认文案' * 8}})
        chain = MagicMock()
        chain.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = ingest_query
        with patch('stages.rewrite.db.retry', return_value=SimpleNamespace(data={'params': {'input_mode': 'ready_script'}})), \
             patch('stages.rewrite.db.get_client', return_value=chain), \
             patch('ready_script.materialize', return_value='example/rewrite/imported.json') as materialize:
            self.assertEqual(('done', 'example/rewrite/imported.json'), rewrite.run(stage))
        materialize.assert_called_once()

    def test_adapter_marks_only_skipped_stages_and_publishes_final_text(self):
        text = '这是一份完整确认稿，第一段保持原有表述。\n\n第二段继续说明画面与配音要使用同一份文案。'
        rows = {kind: {'id': kind, 'params': {'existing': True}} for kind in ('transcribe', 'clean', 'rewrite')}
        updates = {}

        class Query:
            def __init__(self, table): self.table = table; self.kind = ''
            def select(self, *_): return self
            def update(self, patch): self.patch = patch; return self
            def eq(self, field, value):
                if field == 'kind': self.kind = value
                if field == 'id': self.kind = value
                return self
            def limit(self, *_): return self
            def single(self): return self
            def execute(self):
                if self.table == 'artifacts': return SimpleNamespace(data=[])
                if hasattr(self, 'patch'):
                    updates[self.kind] = self.patch
                    return SimpleNamespace(data=[rows[self.kind]])
                return SimpleNamespace(data=rows[self.kind])

        client = SimpleNamespace(table=lambda table: Query(table))
        with patch('ready_script.db.get_task_prompt_context', return_value={'content_category': 'guoxue'}), \
             patch('ready_script.db.get_client', return_value=client), \
             patch('ready_script.storage.upload_bytes') as upload, \
             patch('ready_script.storage.add_artifact'):
            path = materialize({'task_id': 'test-task', 'params': {'ready_script_text': text}})
        payload = __import__('json').loads(upload.call_args.args[1])
        self.assertEqual(text, payload['final_text'])
        self.assertTrue(updates['transcribe']['params']['skipped'])
        self.assertTrue(updates['clean']['params']['skipped'])
        self.assertEqual(text, updates['rewrite']['params']['final_text'])
        self.assertEqual(path, updates['rewrite']['output_ref'])
