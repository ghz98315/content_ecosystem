import json
import unittest
from unittest.mock import MagicMock, patch

from storage3.exceptions import StorageApiError

from repost_images import reuse_first_publication


class RepostImageTests(unittest.TestCase):
    def setUp(self):
        self.stage = {'task_id': 'new', 'params': {'image_aspect_ratio': '4:3'}}
        self.context = {'rewrite_mode': 'repost_dedup', 'source_task_id': 'first'}
        hill = '先看看山上的风景。' * 13
        sea = '再说说海边的步道。' * 13
        self.text = hill + sea
        self.entries = [
            {'path': 'first/sea.png', 'sentence': sea, 'char_count': len(sea)},
            {'path': 'first/hill.png', 'sentence': hill, 'char_count': len(hill)},
        ]
        self.client = MagicMock()
        self.client.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
            {'id': 'first', 'owner': 'same'}, {'id': 'new', 'owner': 'same'},
        ]
        self.bucket = self.client.storage.from_.return_value
        for target, value in (
            ('repost_images.db.get_client', self.client),
            ('stages.render._load_json_artifact', self.entries),
            ('stages.render._apply_image_replacements', self.entries),
            ('stages.image._existing_image_artifacts', {}),
        ):
            self.enterContext(patch(target, return_value=value))
        self.upload = self.enterContext(patch('repost_images.storage.upload_bytes'))
        self.enterContext(patch('repost_images.storage.add_artifact'))

    def test_copies_owned_images_and_builds_new_order_and_text_ranges(self):
        path = reuse_first_publication(self.stage, self.text, self.context)
        self.assertTrue(path.startswith('new/repost-images/'))
        index = json.loads(self.upload.call_args.args[1])
        self.assertEqual(self.text, ''.join(item['sentence'] for item in index))
        copies = {call.args[1]: call.args[0] for call in self.bucket.copy.call_args_list}
        self.assertEqual(['first/hill.png', 'first/sea.png'], [copies[item['path']] for item in index])
        self.assertEqual(len(self.text), index[-1]['char_end'])

    def test_missing_source_image_returns_to_generation_before_copy(self):
        self.bucket.info.side_effect = [None, StorageApiError('Object not found', 'not_found', 404)]
        self.assertIsNone(reuse_first_publication(self.stage, self.text, self.context))
        self.bucket.copy.assert_not_called()
        self.upload.assert_not_called()

    def test_transport_or_permission_error_is_not_treated_as_expired(self):
        self.bucket.info.side_effect = StorageApiError('Access denied', 'forbidden', 403)
        with self.assertRaises(StorageApiError):
            reuse_first_publication(self.stage, self.text, self.context)

    def test_manual_regeneration_does_not_reuse(self):
        self.stage['params']['generation_id'] = 'new-generation'
        self.assertIsNone(reuse_first_publication(self.stage, self.text, self.context))
        self.bucket.copy.assert_not_called()
