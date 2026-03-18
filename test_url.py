import requests
import json

payload = {
    "params": {
        "maxSlope": 45,
        "indoors_only": False
    },
    "mesh": {
        "Name": "TestMesh",
        "Visible": True,
        "points": [
            {"id": 1, "v3": [0,0,0], "ptype": 1},
            {"id": 2, "v3": [1,0,0], "ptype": 1},
            {"id": 3, "v3": [1,0,1], "ptype": 1}
        ],
        "surfaces": [
            [1,2,3]
        ]
    }
}

res = requests.post("http://127.0.0.1:5000/mesh/generate", json=payload)
print(res.json())
