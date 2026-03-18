# lib/application.py
from wsgiref.simple_server import make_server
from urllib.request import Request as UrlRequest
from urllib.response import addinfourl

from .router.view import ViewEngine
from .router import Router, request_proto, response_proto

class Application:
    def __init__(self):
        self.router = Router()
        self.request = request_proto
        self.response = response_proto
        self.settings = {}
        self.locals = {}
        self.view_engine = ViewEngine("views")
        self.middleware = []

    def __call__(self, environ, start_response):
        req = self._make_request(environ)
        res = self._make_response()

        req.__class__ = self.request
        res.__class__ = self.response

        req.app = self
        res.app = self

        middleware = self.middleware
        index = 0

        def run_middleware():
            nonlocal index

            if index < len(middleware):
                fn = middleware[index]
                index += 1
                fn(req, res, run_middleware)   # ← DO NOT return this
            else:
                # All middleware done → run router
                return self.router.handle(req, res, environ, start_response)

        result = run_middleware()

        # If middleware didn’t return router result, return it now
        if result is not None:
            return result

        # Router result will be returned by router.handle
        # but if middleware chain swallowed it, force return
        return [res.body]


    # def __call__(self, environ, start_response):
    #     req = self._make_request(environ)
    #     res = self._make_response()

    #     # attach prototypes (Express-style)
    #     req.__class__ = self.request
    #     res.__class__ = self.response

    #     req.app = self
    #     res.app = self

    #     return self.router.handle(req, res, environ, start_response)

    def _make_request(self, environ):
        scheme = environ.get("wsgi.url_scheme", "http")
        host = environ.get("HTTP_HOST", "localhost")
        path = environ.get("PATH_INFO", "/")
        query = environ.get("QUERY_STRING", "")

        # Build full URL
        if query:
            url = f"{scheme}://{host}{path}?{query}"
        else:
            url = f"{scheme}://{host}{path}"

        method = environ["REQUEST_METHOD"]
        headers = {
            k[5:].replace("_", "-"): v
            for k, v in environ.items()
            if k.startswith("HTTP_")
        }

        req = UrlRequest(url, method=method, headers=headers)

        # Read body
        length = int(environ.get("CONTENT_LENGTH", 0) or 0)
        req.body = environ["wsgi.input"].read(length) if length > 0 else b""
        req.json = {}
        return req


    # def _make_request(self, environ):
    #     url = environ["PATH_INFO"]
    #     method = environ["REQUEST_METHOD"]
    #     headers = {k[5:].replace("_", "-"): v for k, v in environ.items() if k.startswith("HTTP_")}

    #     req = UrlRequest(url, method=method, headers=headers)
    #     req.body = environ["wsgi.input"].read(int(environ.get("CONTENT_LENGTH", 0) or 0))
    #     return req

    def _make_response(self):
        # urllib has no server response, so we create a dummy one
        return addinfourl(fp=None, headers={}, url="", code=200)

    def get(self, path, handler=None):
        # Direct call: app.get("/path", handler)
        if handler is not None:
            self.router.add("GET", path, handler)
            return handler

        # Decorator call: @app.get("/path")
        def wrapper(fn):
            self.router.add("GET", path, fn)
            return fn
        return wrapper

    def post(self, path, handler=None):
        if handler is not None:
            self.router.add("POST", path, handler)
            return handler

        def wrapper(fn):
            self.router.add("POST", path, fn)
            return fn
        return wrapper
        
    def use(self, fn):
        self.middleware.append(fn)
        return self


    def run(self, host="127.0.0.1", port=3000):
        server = make_server(host, port, self)
        print(f"expy running at http://{host}:{port}")
        server.serve_forever()

