from __future__ import annotations

import hashlib
import json
import unittest
from unittest.mock import MagicMock, patch

from stages.image import _download_image, _generate_grid_bytes, _replacement_path, process_replacement_request
from stages.render import _apply_image_replacements


class APIMartIdempotencyTests(unittest.TestCase):
    @staticmethod
    def _completed_http():
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "data": {
                "status": "completed",
                "result": {"images": [{"url": "https://example.test/image.png"}]},
            }
        }
        http = MagicMock()
        http.__enter__.return_value = http
        http.__exit__.return_value = None
        http.get.return_value = response
        return http

    def test_submission_persists_provider_task_before_polling(self):
        provider = MagicMock()
        raw_response = MagicMock()
        raw_response.text = json.dumps({"data": [{"task_id": "provider-task-1"}]})
        provider.with_options.return_value.images.with_raw_response.generate.return_value = raw_response
        http = self._completed_http()

        with patch("stages.image.config.IMAGE_BASE_URL", "https://api.apimart.ai/v1"), patch(
            "stages.image._load_image_provider_jobs", return_value={}
        ), patch("stages.image._save_image_provider_job") as save_job, patch(
            "stages.image.httpx.Client", return_value=http
        ), patch("stages.image._download_image", return_value=b"grid-image"):
            result = _generate_grid_bytes(
                provider,
                "gpt-image-2",
                "grid prompt",
                stage_id="stage-1",
                batch_key="grid_000",
            )

        self.assertEqual(b"grid-image", result)
        generate = provider.with_options.return_value.images.with_raw_response.generate
        generate.assert_called_once()
        self.assertIn("Idempotency-Key", generate.call_args.kwargs["extra_headers"])
        submitted = save_job.call_args_list[0].args[2]
        self.assertEqual("provider-task-1", submitted["provider_task_id"])
        self.assertEqual("submitted", submitted["status"])
        self.assertEqual("completed", save_job.call_args_list[-1].args[2]["status"])

    def test_retry_resumes_existing_task_without_resubmission(self):
        prompt = "same grid prompt"
        existing = {
            "grid_000": {
                "provider": "apimart",
                "provider_task_id": "provider-task-existing",
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "model": "gpt-image-2",
                "size": "1536x1024",
                "status": "polling_timeout",
            }
        }
        provider = MagicMock()
        http = self._completed_http()

        with patch("stages.image.config.IMAGE_BASE_URL", "https://api.apimart.ai/v1"), patch(
            "stages.image._GRID_SIZE", "1536x1024"
        ), patch("stages.image._load_image_provider_jobs", return_value=existing), patch(
            "stages.image._save_image_provider_job"
        ) as save_job, patch("stages.image.httpx.Client", return_value=http), patch(
            "stages.image._download_image", return_value=b"existing-grid"
        ):
            result = _generate_grid_bytes(
                provider,
                "gpt-image-2",
                prompt,
                stage_id="stage-1",
                batch_key="grid_000",
            )

        self.assertEqual(b"existing-grid", result)
        provider.with_options.assert_not_called()
        http.get.assert_called_once_with(
            "https://api.apimart.ai/v1/tasks/provider-task-existing"
        )
        self.assertEqual("completed", save_job.call_args.args[2]["status"])


class ImageDownloadRetryTests(unittest.TestCase):
    def test_download_retries_timeout_without_resubmitting_the_image(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = None
        response.read.return_value = b"image-bytes"
        with patch("stages.image.urllib.request.urlopen", side_effect=[
            TimeoutError("The read operation timed out"), response,
        ]) as urlopen, patch("stages.image.time.sleep") as sleep:
            self.assertEqual(b"image-bytes", _download_image("https://example.test/image.png"))

        self.assertEqual(2, urlopen.call_count)
        sleep.assert_called_once_with(2)


class ImageReplacementRequestTests(unittest.TestCase):
    def test_replacement_path_versions_increment(self):
        table = MagicMock()
        table.select.return_value = table
        table.eq.return_value = table
        table.is_.return_value = table
        getattr(table, 'not_').is_.return_value.execute.return_value = MagicMock(data=[{"replacement_path": "a"}, {"replacement_path": "b"}])
        client = MagicMock()
        client.table.return_value = table
        with patch("stages.image.db.get_client", return_value=client):
            self.assertEqual("task-1/replacements/img_003_v003.png", _replacement_path("task-1", 3))

    def test_process_replacement_request_uses_note_and_persists_artifact(self):
        request = {"id": "req-1", "task_id": "task-1", "stage_id": "stage-1", "image_index": 0, "note": "人物不要正脸"}
        with patch("stages.image._load_image_index", return_value=[{"sentence": "清晨厨房里准备早餐", "path": "task-1/img_000.png"}]), patch(
            "stages.image.config.image_client", return_value=(MagicMock(), "gpt-image-2")
        ), patch("stages.image._generate_grid_bytes", return_value=b"grid-bytes") as gen, patch(
            "stages.image._split_grid", return_value=[b"single-image"]
        ), patch("stages.image._replacement_path", return_value="task-1/replacements/img_000_v001.png"), patch(
            "stages.image.storage.upload_bytes"
        ) as upload_bytes, patch("stages.image.storage.add_artifact") as add_artifact:
            result = process_replacement_request(request)

        self.assertEqual("task-1/replacements/img_000_v001.png", result)
        self.assertIn("人物不要正脸", gen.call_args.args[2])
        upload_bytes.assert_called_once_with("task-1/replacements/img_000_v001.png", b"single-image", "image/png")
        add_artifact.assert_called_once()


    def test_render_prefers_latest_done_replacement(self):
        table = MagicMock()
        table.select.return_value = table
        table.eq.return_value = table
        table.is_.return_value = table
        table.order.return_value = table
        table.execute.return_value = MagicMock(data=[
            {"image_index": 1, "replacement_path": "task-1/replacements/img_001_v002.png", "status": "done", "requested_at": "2026-08-12T10:00:00Z"},
            {"image_index": 1, "replacement_path": "task-1/replacements/img_001_v001.png", "status": "done", "requested_at": "2026-08-12T09:00:00Z"},
        ])
        client = MagicMock()
        client.table.return_value = table
        images = [{"path": "task-1/img_000.png"}, {"path": "task-1/img_001.png"}]
        with patch("stages.render.db.get_client", return_value=client):
            result = _apply_image_replacements("task-1", images)
        self.assertEqual("task-1/replacements/img_001_v002.png", result[1]["path"])
        table.is_.assert_called_with("invalidated_at", "null")


if __name__ == "__main__":
    unittest.main()
