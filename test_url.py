from http_module import req
import json
import requests

# ---------------------------------------------------------
# Biological Mind Test Payload
# ---------------------------------------------------------

payload = {
    "brain": {
        "neurons": [
            {"id": 1, "activation": 0.0, "bias": 0.0, "plasticity": 0.1, "trace": 0.0, "type": "sensory"},
            {"id": 2, "activation": 0.0, "bias": 0.1, "plasticity": 0.1, "trace": 0.0, "type": "hidden"},
            {"id": 3, "activation": 0.0, "bias": 0.0, "plasticity": 0.1, "trace": 0.0, "type": "motor"}
        ],

        "synapses": [
            {"from": 1, "to": 2, "weight": 0.8, "eligibility": 0.0, "plasticity": 0.05},
            {"from": 2, "to": 3, "weight": 1.2, "eligibility": 0.0, "plasticity": 0.05}
        ],

        "hippocampus": {
            "episodes": [],
            "max_size": 2000
        },

        "modulators": {
            "dopamine": 0.0,
            "acetylcholine": 0.6,
            "norepinephrine": 0.1
        }
    },

    "inputs": {
        "1": 1.0
    },

    "dt": 1.0
}

# ---------------------------------------------------------
# Response handler (same style as your mesh handler)
# ---------------------------------------------------------

def handler(res: requests.Response, node):
    if res is None:
        print("network error:", node["response"])
        return

    if res.status_code != 200:
        print("Failed:", res.status_code, res.text)
        return

    # Try JSON
    try:
        obj = res.json()
        if "brain" in obj:
            print("Biological Mind Response:")
            print(json.dumps(obj, indent=4))
            return
    except Exception:
        pass

    print("Unexpected response:", res.text)


# ---------------------------------------------------------
# Send request using your req() wrapper
# ---------------------------------------------------------

response = req({
    "Url": "http://127.0.0.1:5000/biological/neural",
    "Method": "POST",
    "Body": json.dumps(payload),
    "handler": handler
})

response()
