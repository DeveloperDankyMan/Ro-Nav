# lib/request.py
from urllib.request import Request as UrlRequest
from urllib.parse import urlparse, parse_qs

class request_proto(UrlRequest):
    @property
    def path(self):
        return urlparse(self.full_url).path

    @property
    def query(self):
        return parse_qs(urlparse(self.full_url).query)

    def get(self, header):
        return self.headers.get(header)
