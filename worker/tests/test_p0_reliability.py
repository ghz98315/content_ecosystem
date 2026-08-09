from __future__ import annotations

import hashlib
import json
import unittest
from unittest.mock import MagicMock, patch

from stages.image import _generate_grid_bytes


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


if __name__ == "__main__":
    unittest.main()
