import unittest
from unittest.mock import patch

import config


class ImageNetworkTests(unittest.TestCase):
    def test_direct_image_download_does_not_use_system_proxy(self):
        from unittest.mock import MagicMock
        from stages.image import _download_image
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'image'
        opener = MagicMock()
        opener.open.return_value = response
        with patch('stages.image.urllib.request.build_opener', return_value=opener), \
             patch('stages.image.urllib.request.urlopen') as system_open:
            self.assertEqual(b'image', _download_image('https://example.test/a.png', direct=True))
        system_open.assert_not_called()
        opener.open.assert_called_once()

    def test_apimart_submission_uses_explicit_proxy_policy(self):
        for trust_env in (False, True):
            with self.subTest(trust_env=trust_env), \
                 patch.object(config, 'APIMART_IMAGE_API_KEY', 'test-not-a-key'), \
                 patch.object(config, 'APIMART_IMAGE_TRUST_ENV', trust_env), \
                 patch.object(config, 'openai_client') as create:
                config.image_client('apimart')
                http = create.call_args.kwargs['http_client']
                try:
                    self.assertEqual(http.trust_env, trust_env)
                    self.assertTrue(http._transport._pool._ssl_context.check_hostname)
                finally:
                    http.close()


if __name__ == '__main__':
    unittest.main()
