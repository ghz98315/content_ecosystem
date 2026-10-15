import json
import unittest
from unittest.mock import patch

from resolvers import share_page


def page(item):
    return '<script>window._ROUTER_DATA = ' + json.dumps({
        'loaderData': {'layout': None, 'video_(id)/page': {
            'videoInfoRes': {'item_list': [item]}}}}) + ';</script>'


class SharePageTests(unittest.TestCase):
    def test_video(self):
        result = share_page.parse_page(page({
            'aweme_id': '123', 'desc': '测试正文',
            'video': {'duration': 12300, 'play_addr': {'url_list': ['https://example.com/video']}},
            'author': {'nickname': '作者'}, 'statistics': {'digg_count': 12},
        }), '123')
        self.assertTrue(result.ok)
        self.assertEqual(result.duration, 12.3)
        self.assertEqual(result.play_count, 12)
        self.assertEqual(result.raw['resolver'], 'share_page')

    def test_challenge(self):
        with self.assertRaises(ValueError):
            share_page.parse_page('<html>验证</html>', '123')

    def test_wrong_video(self):
        with self.assertRaises(ValueError):
            share_page.parse_page(page({'aweme_id': '456'}), '123')

    def test_missing_video(self):
        with self.assertRaises(ValueError):
            share_page.parse_page(page({'aweme_id': '123', 'images': []}), '123')

    def test_invalid_id_does_not_request(self):
        with patch.object(share_page.httpx, 'Client') as client:
            with self.assertRaises(ValueError):
                share_page.resolve('https://other.example/')
            client.assert_not_called()

    def test_resolver_prefers_share_page(self):
        from resolvers import self_resolver
        expected = object()
        with patch.object(share_page, 'resolve', return_value=expected), \
             patch.object(self_resolver, 'load_cookie_file', return_value=''), \
             patch.object(self_resolver, 'gen_anon_cookie') as anonymous:
            self.assertIs(self_resolver.resolve('https://www.douyin.com/video/123'), expected)
            anonymous.assert_not_called()


if __name__ == '__main__':
    unittest.main()
