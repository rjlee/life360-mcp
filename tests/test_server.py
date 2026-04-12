import unittest
from unittest import mock
import time

# Import the module under test
from life360_mcp import server


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.headers = headers or {}
        self.text = text
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._json


class ServerTests(unittest.TestCase):
    def setUp(self):
        # Ensure a clean token cache for each test
        server.TOKEN_PATH.unlink(missing_ok=True)
        # Patch time.sleep to avoid real delays
        self.sleep_patcher = mock.patch('time.sleep', return_value=None)
        self.mock_sleep = self.sleep_patcher.start()
        # Reset in‑memory caches
        server._LOCATION_CACHE.clear()

    def tearDown(self):
        self.sleep_patcher.stop()
        server.TOKEN_PATH.unlink(missing_ok=True)

    @mock.patch('requests.post')
    def test_login_success(self, mock_post):
        mock_post.return_value = FakeResponse(
            status_code=200,
            json_data={'access_token': 'tok123', 'expires_in': 3600}
        )
        token = server._login()
        self.assertEqual(token.access_token, 'tok123')
        self.assertTrue(server._load_token().access_token, 'tok123')

    @mock.patch('requests.request')
    @mock.patch('requests.post')
    def test_rate_limit_backoff(self, mock_post, mock_req):
        # First request returns 429 with Retry-After 2, second returns success.
        mock_post.return_value = FakeResponse(
            status_code=200,
            json_data={'access_token': 'tok123', 'expires_in': 3600}
        )
        mock_req.side_effect = [
            FakeResponse(status_code=429, headers={'Retry-After': '2'}),
            FakeResponse(status_code=200, json_data={'circles': []})
        ]
        circles = server.list_circles()
        self.assertEqual(circles, [])
        # Ensure we slept for (2 + 10) seconds = 12 (mocked, so just called)
        self.mock_sleep.assert_called_once_with(12)

    @mock.patch('requests.request')
    @mock.patch('requests.post')
    def test_get_location_caching(self, mock_post, mock_req):
        # Mock login
        mock_post.return_value = FakeResponse(
            status_code=200,
            json_data={'access_token': 'tok123', 'expires_in': 3600}
        )
        # Mock API sequence: circles -> members -> member detail
        mock_req.side_effect = [
            FakeResponse(status_code=200, json_data={'circles': [{'id': 'c1', 'name': 'Home'}]}),
            FakeResponse(status_code=200, json_data={'members': [{'id': 'm1', 'firstName': 'Alice'}]}),
            FakeResponse(status_code=200, json_data={'location': {'latitude': 10, 'longitude': 20, 'accuracy': 5, 'timestamp': 1}, 'batteryLevel': 80})
        ]
        # First call – should hit the API three times
        loc1 = server.get_location('Alice')
        self.assertEqual(loc1['latitude'], 10)
        self.assertFalse(loc1['cached'])
        # Reset side_effect to raise if called again (should not be called)
        mock_req.side_effect = AssertionError('Unexpected API call')
        # Second call – should be served from cache
        loc2 = server.get_location('Alice')
        self.assertTrue(loc2['cached'])
        self.assertEqual(loc2['latitude'], 10)

    def test_rpc_handler(self):
        # Simple sanity check of RPC dispatcher
        with mock.patch.object(server, 'list_circles', return_value=[{'id': 'c'}]):
            resp = server._handle_rpc({'jsonrpc': '2.0', 'method': 'list_circles', 'id': 1})
            self.assertIn('result', resp)
            self.assertEqual(resp['result'], [{'id': 'c'}])
            self.assertEqual(resp['id'], 1)

if __name__ == '__main__':
    unittest.main()
