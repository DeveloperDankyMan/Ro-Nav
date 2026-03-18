# lib/response.py
from urllib.response import addinfourl
import json

class response_proto(addinfourl):
    def status(self, code):
        self.code = code
        return self

    def set(self, key, value):
        self.headers[key] = value
        return self

    def send(self, data):
        if isinstance(data, str):
            self.headers["Content-Type"] = "text/html; charset=utf-8"
            self.body = data.encode("utf-8")
        else:
            self.body = data
        return self

    def render(self, template_name, context=None):
        html = self.app.view_engine.render(template_name, context)
        return self.send(html)
    # def send(self, body):
    #     if isinstance(body, str):
    #         body = body.encode("utf-8")
    #         self.headers["Content-Type"] = "text/html; charset=utf-8"
    #     self.body = body
    #     return self

    def json(self, obj):
        self.headers["Content-Type"] = "application/json"
        self.body = json.dumps(obj).encode("utf-8")
        return self
