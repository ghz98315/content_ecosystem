import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import r2_media
import storage
from migrate_r2_media import migrate_one

KEY = 'b4f321ac-51d0-497e-bf55-950a4ec91c1b/renders/run/final.mp4'


class R2MediaTests(unittest.TestCase):
    def test_new_media_goes_to_r2_while_json_stays_in_supabase(self):
        with patch.object(r2_media, 'enabled', return_value=True), \
             patch.object(r2_media, 'upload_bytes') as r2_upload, \
             patch.object(storage, 'upload_limit_bytes', return_value=100), \
             patch.object(storage.db, 'retry') as supabase:
            storage.upload_bytes(KEY, b'media', 'video/mp4')
            storage.upload_bytes(KEY.replace('.mp4', '.json'), b'{}', 'application/json')
        r2_upload.assert_called_once_with(KEY, b'media', 'video/mp4')
        supabase.assert_called_once()
        self.assertFalse(r2_media.media_path(KEY.replace('/run/', '/../')))
        self.assertFalse(r2_media.media_path('user-music/owner/test.png'))

    def test_download_falls_back_only_when_r2_object_is_absent(self):
        with patch.object(r2_media, 'enabled', return_value=True), \
             patch.object(r2_media, 'info', return_value=None) as head, \
             patch.object(storage.db, 'retry', return_value=b'legacy') as supabase:
            target = Path(storage.download_artifact(KEY))
            try:
                self.assertEqual(target.read_bytes(), b'legacy')
            finally:
                target.unlink()
            head.side_effect = PermissionError('R2 denied')
            with self.assertRaises(PermissionError):
                storage.download_artifact(KEY)
        supabase.assert_called_once()

    def test_migration_never_removes_source_when_verification_differs(self):
        sb, source = MagicMock(), MagicMock()
        sb.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {'status': 'done'}
        source.info.return_value = {'size': 3, 'last_modified': '2026-11-17T00:00:00+00:00'}
        source.download.return_value = b'abc'
        report = {'scanned': 0, 'bytes': 0, 'verified': 0, 'removed': 0}
        with patch.object(r2_media, 'info', return_value={'ContentLength': 3}), \
             patch.object(r2_media, 'download_file', side_effect=lambda _, path: Path(path).write_bytes(b'xyz')):
            with self.assertRaisesRegex(ValueError, '副本与原件不一致'):
                migrate_one(sb, source, KEY, KEY.split('/')[0], 'remove-verified', report)
        source.remove.assert_not_called()
