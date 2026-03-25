from format import F
from types import SimpleNamespace
from http_module import req

import json
import util
import main
import requests

from util import _F_string_save, read_s, i2b


class Ctx(dict):
    @property
    def version(self):
        return self.get("version", 0)

context = Ctx(version=3)


# sample data
params = {
    "jumpPower": 50,
    "walkSpeed": 25,
}
mesh = {
    "Name": "ExampleMesh",
    "Visible": True,

    "points": [
        {"id": 1, "v3": [0.0, 0.0, 0.0], "ptype": 1},
        {"id": 2, "v3": [10.0, 0.0, 0.0], "ptype": 1},
        {"id": 3, "v3": [10.0, 0.0, 10.0], "ptype": 1},
        {"id": 4, "v3": [0.0, 0.0, 10.0], "ptype": 1},
    ],

    "surfaces": [
        [1, 2, 3],
        [1, 3, 4]
    ],

    "c_conns": [],
    "barriers": [],
    "connections": []
}

context = Ctx(version=3)
data_chunks = []
util.save(data_chunks, {"params": params, "mesh": mesh}, F.MeshReq, context)
payload_bytes = b"".join(data_chunks)

print("chunks count:", len(data_chunks))
for i, c in enumerate(data_chunks):
    print(i, type(c), len(c))
payload_bytes = b"".join(data_chunks)
print("total bytes:", len(payload_bytes))

print("payload_bytes length:", len(payload_bytes))
print("payload_bytes (hex, first 128 bytes):", payload_bytes[:128].hex())

load_ctx = Ctx(version=3)
loaded_obj, new_index = util.load(payload_bytes, 0, F.MeshReq, {"version": 3})
print(loaded_obj, new_index)
def handler(res: requests.Response, node):
    if res is None:
        print("network error:", node["response"])
        return

    if res.status_code != 200:
        print("Failed:", res.status_code, res.text)
        return

    text = res.text or ""

    # Try JSON first
    try:
        obj = res.json()
        if "mesh" in obj:
            status = obj.get("status")
            mesh = obj.get("mesh")
            print("Server returned JSON mesh response.")
            print("status:", obj.get("status"))
            print("mesh:", json.dumps(mesh, indent=4))
            return
    except Exception:
        pass  # not JSON, fall through to binary handling

    # Binary fallback
    if len(text) <= len(payload_bytes):
        print("Server did not return encoded mesh data.")
        print("Response was:", text)
        return

    encoded_part = text[len(payload_bytes):]

    try:
        raw = util.decode(encoded_part)
    except Exception as exc:
        print("decode failed:", exc)
        print("encoded_part length:", len(encoded_part))
        print("encoded_part (hex, first 128 bytes):", encoded_part[:128].encode().hex())
        return

    try:
        save_obj, _ = util.load(raw, 0, F.MeshSave, {"version": 3})
    except Exception as exc:
        print("load failed:", exc)
        return

    print("received mesh version:", save_obj.get("version"))
    print("node keys:", list(node.keys()))

response = req({
    "Url": "http://127.0.0.1:5000/mesh/generate",
    "Method": "POST",
    "Body": json.dumps(loaded_obj),
    "handler": handler
})

response()

# res = requests.post("http://127.0.0.1:5000/mesh/generate", json=loaded_obj)

# print(res.text)

# if res.ok:
#     raw = res.json()
#     print(raw)