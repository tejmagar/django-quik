import unittest

from src.django_quik.server import http


class TestHttp(unittest.TestCase):
    """
    More tests later :/
    """

    def test_extract_http_starting_header_info(self):
        request_method, path, http_version = http.extract_http_starting_header_info('GET / HTTP/1.0')
        self.assertEqual(request_method, 'GET')
        self.assertEqual(path, '/')
        self.assertEqual(http_version, 'HTTP/1.0')


if __name__ == '__main__':
    unittest.main()
