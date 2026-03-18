from expy import expy, Request, Response
from typing import Dict, Any, List
import json
import math

# ---------------------------------------------------------
# POINT TYPE ENUMS
# ---------------------------------------------------------

PTYPE = {
    "UNKNOWN": 0,
    "INTERIOR": 1,
    "MIDEXTERIOR": 2,
    "EXTERIOR": 3,
    "REFLEX": 4,
    "INTER": 5,
    "ACTION": 6,
    "GOAL": 7,
    "BLOCKED": 8,
}

PTYPE_NAME = {v: k for k, v in PTYPE.items()}

# ---------------------------------------------------------
# APP SETUP
# ---------------------------------------------------------

app = expy(__name__)

# ---------------------------------------------------------
# MIDDLEWARE
# ---------------------------------------------------------

def json_parser(req: Request, res: Response, next):
    if req.get_method() in ("POST", "PUT", "PATCH") and req.body:
        try:
            req.json = json.loads(req.body)
        except:
            req.json = {}
    else:
        req.json = {}
    next()



def logger(req: Request, res: Response, next):
    """Updated logger for urllib Request objects."""
    print("----- REQUEST DEBUG -----")
    print(f"Method: {req.get_method()}")
    print(f"Path:   {req.path}")  # Custom attribute we add in constructor
    print(f"Full URL: {req.full_url}")
    print(f"Data: {req.data}")
    print(f"Body JSON: {getattr(req, 'json', 'N/A')}")
    print("-------------------------")
    next()

app.use(json_parser)
app.use(logger)

# ---------------------------------------------------------
# VALIDATOR
# ---------------------------------------------------------

def validate_mesh_req(body: dict):
    if not isinstance(body, dict):
        return False, "Body must be a JSON object"

    if "params" not in body or "mesh" not in body:
        return False, "Missing 'params' or 'mesh'"

    params = body["params"]
    mesh = body["mesh"]

    if not isinstance(params, dict):
        return False, "'params' must be an object"

    if not isinstance(mesh, dict):
        return False, "'mesh' must be an object"

    required_mesh_keys = ["Name", "Visible", "points", "surfaces"]
    for k in required_mesh_keys:
        if k not in mesh:
            return False, f"Mesh missing required field '{k}'"

    if not isinstance(mesh["points"], list):
        return False, "'points' must be a list"

    if not isinstance(mesh["surfaces"], list):
        return False, "'surfaces' must be a list"

    return True, None

# ---------------------------------------------------------
# TRIANGULATION
# ---------------------------------------------------------

def triangulate_surface(point_ids):
    tris = []
    if len(point_ids) < 3:
        return tris
    p0 = point_ids[0]
    for i in range(1, len(point_ids) - 1):
        tris.append((p0, point_ids[i], point_ids[i+1]))
    return tris


def triangulate_surfaces(surfaces):
    all_tris = []
    for surf in surfaces:
        if isinstance(surf, list):
            ids = surf
        else:
            ids = surf.get("id") or surf.get("points") or []
        tris = triangulate_surface(ids)
        all_tris.extend(tris)
    return all_tris

# ---------------------------------------------------------
# CCONNECTION LOGIC
# ---------------------------------------------------------

def build_cconnection_edges(c_conns, points):
    edges = []
    for cc in c_conns:
        at_map = cc.get("at", {})
        to_map = cc.get("to", {})
        bidir = cc.get("bidirectional", True)

        at_ids = [pid for pid, v in at_map.items() if v]
        to_ids = [pid for pid, v in to_map.items() if v]

        for a in at_ids:
            for t in to_ids:
                edges.append({"from": a, "to": t})
                if bidir:
                    edges.append({"from": t, "to": a})
    return edges

# ---------------------------------------------------------
# MESH HELPERS
# ---------------------------------------------------------

def normalize_points(points):
    out = []
    for p in points:
        ptype = p.get("ptype", 0)
        out.append({
            "id": p["id"],
            "v3": p["v3"],
            "ptype": ptype,
            "ptype_name": PTYPE_NAME.get(ptype, "UNKNOWN")
        })
    return out


def build_adjacency(points, surfaces):
    adjacency = []
    for surf in surfaces:
        if isinstance(surf, list):
            ids = surf
        else:
            ids = surf.get("id")

        for i in range(len(ids) - 1):
            adjacency.append({
                "from": ids[i],
                "to": ids[i+1]
            })
    return adjacency


def slope_ok(v1, v2, max_slope):
    dx = v2[0] - v1[0]
    dy = v2[1] - v1[1]
    dz = v2[2] - v1[2]

    horizontal = math.sqrt(dx*dx + dz*dz)
    if horizontal == 0:
        return True

    slope_deg = abs(math.degrees(math.atan(dy / horizontal)))
    return slope_deg <= max_slope


def apply_constraints(connections, points, params):
    filtered = []
    point_map = {p["id"]: p for p in points}

    max_slope = params.get("maxSlope", 45)
    indoors_only = params.get("indoors_only", False)

    for c in connections:
        p1 = point_map[c["from"]]
        p2 = point_map[c["to"]]

        if p1["ptype"] == PTYPE["BLOCKED"] or p2["ptype"] == PTYPE["BLOCKED"]:
            continue

        if indoors_only:
            if p1["ptype"] == PTYPE["EXTERIOR"] or p2["ptype"] == PTYPE["EXTERIOR"]:
                continue

        if not slope_ok(p1["v3"], p2["v3"], max_slope):
            continue

        filtered.append({
            "from": c["from"],
            "to": c["to"],
            "from_ptype": p1["ptype"],
            "to_ptype": p2["ptype"]
        })

    return filtered

# ---------------------------------------------------------
# MESH SAVE SERIALIZER
# ---------------------------------------------------------

MESH_VERSION = 3

def serialize_mesh_save(mesh: dict) -> dict:
    return {
        "version": MESH_VERSION,
        "mesh": mesh
    }

# ---------------------------------------------------------
# MESH GENERATOR
# ---------------------------------------------------------

def generate_mesh(params: dict, mesh: dict) -> dict:
    points = mesh.get("points", [])
    surfaces = mesh.get("surfaces", [])
    barriers = mesh.get("barriers", [])
    c_conns = mesh.get("c_conns", [])

    normalized_points = normalize_points(points)
    triangles = triangulate_surfaces(surfaces)
    adjacency = build_adjacency(normalized_points, surfaces)
    cconn_edges = build_cconnection_edges(c_conns, normalized_points)
    adjacency.extend(cconn_edges)
    filtered_connections = apply_constraints(adjacency, normalized_points, params)

    return {
        "Name": mesh.get("Name", "GeneratedMesh"),
        "Visible": True,
        "points": normalized_points,
        "surfaces": surfaces,
        "triangles": triangles,
        "connections": filtered_connections,
        "barriers": barriers,
        "c_conns": c_conns,
    }

# ---------------------------------------------------------
# ROUTES
# ---------------------------------------------------------

def home(req: Request, res: Response):
    return res.render("index.html", {
        "title": "Welcome",
        "name": "Donovan"
    })


def mesh_generate(req: Request, res: Response):
    body = req.json

    ok, err = validate_mesh_req(body)
    if not ok:
        return res.json({"error": err})

    params = body["params"]
    mesh_data = body["mesh"]

    generated = generate_mesh(params, mesh_data)
    mesh_save = serialize_mesh_save(generated)

    print("----- GENERATED MESH OUTPUT -----")
    print(json.dumps(generated, indent=4))
    print("----- MESH SAVE OUTPUT -----")
    print(json.dumps(mesh_save, indent=4))
    print("----------------------------------")

    return res.json({
        "status": "ok",
        "mesh": generated,
        "save": mesh_save
    })

# ---------------------------------------------------------
# ROUTE REGISTRATION
# ---------------------------------------------------------

app.get("/", home)
app.post("/mesh/generate", mesh_generate)

# ---------------------------------------------------------
# SERVER
# ---------------------------------------------------------

if __name__ == "__main__":
    try:
        app.run(port=5000)
    except KeyboardInterrupt:
        pass
