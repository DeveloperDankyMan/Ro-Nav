import re

from urllib.request import Request as UrlRequest

def make_urllib_request(environ):
    url = environ.get("RAW_URI") or environ.get("REQUEST_URI") or environ["PATH_INFO"]

    req = UrlRequest(
        url=url,
        method=environ["REQUEST_METHOD"],
        headers={
            k[5:].replace("_", "-"): v
            for k, v in environ.items()
            if k.startswith("HTTP_")
        }
    )

    # Attach body manually (urllib normally reads from network)
    try:
        length = int(environ.get("CONTENT_LENGTH", 0))
    except ValueError:
        length = 0

    req.body = environ["wsgi.input"].read(length) if length > 0 else b""

    return req


def compile_path(path):
    keys = []

    # Convert "/:id/search?" into regex
    pattern = path

    # Optional segments
    pattern = pattern.replace("?", "?")

    # Params
    def repl(match):
        keys.append(match.group(1))
        return "([^/]+)"

    pattern = re.sub(r":(\w+)", repl, pattern)

    regex = re.compile(f"^{pattern}$")
    return regex, keys
