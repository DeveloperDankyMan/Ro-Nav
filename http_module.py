# req_module.py
import threading
import time
import traceback
from typing import Any, Dict, Optional

import requests

from promise import Promise, Promise_ctor  # your continuation-style Promise

# linked-list sentinel
class _Sentinel:
    def __init__(self):
        self.next = self
        self.prev = self

LL = _Sentinel()
TIMEOUT = 120.0
_INF = float("inf")

def _traceback():
    
    return "".join(traceback.format_stack())

# exec handler: performs HTTP request, unlinks queue, then calls handler if provided
def _exec(promise: Promise, _args):
    node = promise.state  # node is a dict representing the request
    # enqueue
    node["next"] = LL
    node["prev"] = LL.prev
    LL.prev.next = node
    LL.prev = node

    node["start_t"] = time.time()
    node["success"] = None
    node["response"] = None

    try:
        a = node["args"]
        method = a.get("Method", "GET").upper()
        url = a.get("Url")
        headers = a.get("Headers", {}) or {}
        body = a.get("Body", None)
        timeout = a.get("Timeout", TIMEOUT)

        resp = requests.request(method, url, headers=headers, data=body, timeout=timeout)
        node["response"] = resp
        node["success"] = True
    except Exception as exc:
        node["response"] = exc
        node["success"] = False
    finally:
        node["finish_t"] = time.time()

    # unlink if still active
    if node.get("is_active", True):
        try:
            prev = node.get("prev")
            nxt = node.get("next")
            if prev is not None and nxt is not None:
                prev.next = nxt
                nxt.prev = prev
        except Exception:
            pass
    else:
        # timed out and not accepted late -> raise to trigger Else/default_throw
        if not node["args"].get("accept_late", False):
            raise RuntimeError("Late response and not accepted")

    # call user-provided handler if present (Lua-style: handler(res, node))
    handler = node["args"].get("handler")
    try:
        if callable(handler):
            # pass requests.Response or exception object (Lua checks truthiness)
            resp = node.get("response")
            # In Lua they check `if res then` — pass None on exception to match that pattern
            if isinstance(resp, Exception):
                handler(None, node)
            else:
                handler(resp, node)
    except Exception as h_exc:
        # handler errors should not crash the request flow; log and continue
        print("handler raised:", h_exc)

    # treat non-2xx as error to trigger Else in promise chain
    if node["success"] is True and isinstance(node["response"], requests.Response):
        status = node["response"].status_code
        if 200 <= status < 300:
            return promise.Continue(node)
        else:
            raise RuntimeError(f"HTTP {status}: {node['response'].text}")
    elif node["success"] is True:
        return promise.Continue(node)
    else:
        raise node["response"]

def _default_throw(promise: Promise, args):
    node = promise.state
    if not node.get("is_active", True):
        flight_time = node.get("finish_t", 0.0) - node.get("start_t", 0.0)
        if node.get("success") is None:
            print(f"[WARN] Request timed out at {flight_time:.2f} seconds.")
        else:
            print(f"[WARN] Response arrived late (after {flight_time:.2f} seconds).")

    r = node.get("response")
    if node.get("success") is True:
        print("[WARN] Application-level response error:", getattr(r, "text", r))
    elif node.get("success") is False:
        print("[WARN] Network error:", r)
    else:
        print("[WARN] Request error:", node.get("msg"))

    print("Request created at:")
    print(node.get("traceback"))
    return promise.Continue(args)

# watcher thread to mark timed-out requests and call ThrowAsync
_watcher_stop = False
def _watcher_loop():
    while not _watcher_stop:
        t = time.time()
        cur = LL.next
        while cur is not LL:
            start_t = cur.get("start_t", _INF)
            if t - start_t > TIMEOUT:
                cur["is_active"] = False
                prom = cur.get("promise")
                if prom is not None:
                    try:
                        prom.ThrowAsync(cur)
                    except Exception:
                        pass
                cur = cur.get("next", LL)
            else:
                cur = cur.get("next", LL)
        time.sleep(0.1)

_watcher_thread = threading.Thread(target=_watcher_loop, daemon=True)
_watcher_thread.start()

# Public req function (Lua-style)
def req(args: Dict[str, Any]):
    node = {
        "promise": None,
        "success": None,
        "response": None,
        "args": args,
        "next": None,
        "prev": None,
        "start_t": _INF,
        "finish_t": 0.0,
        "is_active": True,
        "traceback": _traceback(),
    }

    # robust promise constructor
    def _make_promise(state, *handlers):
        ctor = getattr(Promise, "__ctor", None)
        if callable(ctor):
            return ctor(state, *handlers)
        factory = globals().get("make_promise") or globals().get("makePromise")
        if callable(factory):
            return factory(state, *handlers)
        try:
            return Promise(state, *handlers)
        except Exception:
            pass
        for name in ("create", "new"):
            fn = getattr(Promise, name, None)
            if callable(fn):
                return fn(state, *handlers)
        raise RuntimeError("Unable to construct Promise: unsupported Promise API")

    p = Promise_ctor(node)
    p.Then(_exec).Else(_default_throw)
    node["promise"] = p
    return p
