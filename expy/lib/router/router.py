# lib/router.py
from .utils import compile_path

class Router:
    def __init__(self):
        self.routes = []

    def add(self, method, path, handler):
        regex, keys = compile_path(path)
        self.routes.append((method, regex, keys, handler))

    def handle(self, req, res, environ, start_response):
        path = environ["PATH_INFO"]
        method = environ["REQUEST_METHOD"]

        for m, regex, keys, handler in self.routes:
            if m == method:
                match = regex.match(path)
                if match:
                    req.params = dict(zip(keys, match.groups()))
                    handler(req, res)

                    start_response(f"{res.code} OK", list(res.headers.items()))
                    return [res.body]

        start_response("404 Not Found", [("Content-Type", "text/plain")])
        return [b"Not Found"]
