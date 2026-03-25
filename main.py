from expy import expy, Request, Response
from typing import Dict, Any, List, Literal, Tuple
from enum import Enum
from format import F

import util
import json
import math

# ---------------------------------------------------------
# POINT TYPE ENUMS
# ---------------------------------------------------------

PTYPES = (
    "UNKNOWN",
    "INTERIOR",
    "MIDEXTERIOR",
    "EXTERIOR",
    "INTER",
    "ACTION",
    "GOAL",
    "BLOCKED"
)

PTYPE = Enum("PTYPE", {name: i for i, name in enumerate(PTYPES)})
PTYPE_NAME = {member.value: member.name for member in PTYPE}

# ---------------------------------------------------------
# V3 (Vector3)
# ---------------------------------------------------------

V3 = Tuple[float, float, float]

class AABB:
    __slots__ = ("min", "max")
    def __init__(self, mn: V3, mx: V3):
        self.min = (min(mn[0], mx[0]), min(mn[1], mx[1]), min(mn[2], mx[2]))
        self.max = (max(mn[0], mx[0]), max(mn[1], mx[1]), max(mn[2], mx[2]))
    def contains_point(self, p: V3) -> bool:
        return (self.min[0] <= p[0] <= self.max[0] and
                self.min[1] <= p[1] <= self.max[1] and
                self.min[2] <= p[2] <= self.max[2])
    def intersects(self, other: "AABB") -> bool:
        return (self.min[0] < other.max[0] and self.max[0] > other.min[0] and
                self.min[1] < other.max[1] and self.max[1] > other.min[1] and
                self.min[2] < other.max[2] and self.max[2] > other.min[2])
    def expand(self, margin: float) -> "AABB":
        return AABB((self.min[0]-margin, self.min[1]-margin, self.min[2]-margin),
                    (self.max[0]+margin, self.max[1]+margin, self.max[2]+margin))
    def swept_aabb(self, start: V3, end: V3, radius: float, height: float) -> bool:
        mn = (min(start[0], end[0]) - radius, min(start[1], end[1]) - 0.0, min(start[2], end[2]) - radius)
        mx = (max(start[0], end[0]) + radius, max(start[1], end[1]) + height, max(start[2], end[2]) + radius)
        sweep_box = AABB(mn, mx)
        return self.intersects(sweep_box)

# small vector helpers
def vec_sub(a: V3, b: V3) -> V3: return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def length(a: V3) -> float: return math.sqrt(a[0]*a[0] + a[1]*a[1] + a[2]*a[2])
def tri_centroid(a: V3, b: V3, c: V3) -> V3: return ((a[0]+b[0]+c[0])/3.0, (a[1]+b[1]+c[1])/3.0, (a[2]+b[2]+c[2])/3.0)
def tri_normal(a: V3, b: V3, c: V3) -> V3:
    u = vec_sub(b, a); v = vec_sub(c, a)
    nx = u[1]*v[2] - u[2]*v[1]; ny = u[2]*v[0] - u[0]*v[2]; nz = u[0]*v[1] - u[1]*v[0]
    L = math.sqrt(nx*nx + ny*ny + nz*nz)
    if L == 0: return (0.0, 1.0, 0.0)
    return (nx/L, ny/L, nz/L)

# physics: airtime and conservative jump check with sampling
def max_jump_range(jumpPower: float, gravity: float, horizontal_speed: float) -> float:
    if gravity <= 0: return 0.0
    T = 2.0 * jumpPower / gravity
    return max(0.0, horizontal_speed * T)

def can_jump(a: V3, b: V3, jumpPower: float, gravity: float, walkSpeed: float,
             radius: float, height: float, barrier_aabbs: List[AABB],
             air_control: float = 1.0, samples: int = 8) -> bool:
    dx = b[0] - a[0]; dz = b[2] - a[2]
    horiz = math.hypot(dx, dz)
    vy = jumpPower
    T = 2.0 * vy / gravity if gravity > 0 else 0.0
    if T <= 0: return False
    vx = walkSpeed * air_control
    if horiz > vx * T: return False
    # sample along parabola; conservative swept AABB at each sample
    for s in range(1, samples+1):
        t = (s / samples) * T
        frac = t / T
        x = a[0] + dx * frac
        z = a[2] + dz * frac
        y = a[1] + vy * t - 0.5 * gravity * t * t
        sample_pt = (x, y, z)
        for box in barrier_aabbs:
            if box.swept_aabb(sample_pt, sample_pt, radius, height):
                return False
    return True

def build_barrier_aabbs(barriers_raw: List[Any], id_to_v3: Dict[int, V3]) -> List[AABB]:
    boxes = []
    for bar in barriers_raw:
        coords = []
        if isinstance(bar, dict) and "min" in bar and "max" in bar:
            boxes.append(AABB(tuple(bar["min"]), tuple(bar["max"])))
            continue
        for v in bar:
            if isinstance(v, (list, tuple)) and len(v) == 3:
                coords.append(tuple(v))
            elif isinstance(v, int):
                if v in id_to_v3: coords.append(id_to_v3[v])
        if coords:
            xs = [c[0] for c in coords]; ys = [c[1] for c in coords]; zs = [c[2] for c in coords]
            boxes.append(AABB((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))))
    return boxes

def synthesize_c_conns(out_connections, out_points, existing_c_conns, walk_threshold=4.0):
    """
    - out_connections: list of connection dicts with keys 'action','fromID','toID'
    - out_points: list of point dicts with 'id' and 'v3'
    - existing_c_conns: list (if non-empty, we preserve and return it)
    - walk_threshold: distance threshold above which walk edges become c_conns
    """
    if existing_c_conns:
        return list(existing_c_conns)  # preserve provided c_conns

    # map id -> v3 for distance lookups
    id_to_v3 = {p["id"]: tuple(p["v3"]) for p in out_points}

    # index connections for quick reverse lookup
    conn_set = set((c["fromID"], c["toID"], c["action"]) for c in out_connections)

    generated = []
    for c in out_connections:
        a = c["fromID"]; b = c["toID"]; action = c.get("action", 0)
        # decide whether to synthesize
        if action == 1:
            ctype = "jump"
        else:
            # walk: only synthesize if distance >= threshold
            pa = id_to_v3.get(a); pb = id_to_v3.get(b)
            if pa is None or pb is None:
                continue
            dist = math.hypot(pa[0]-pb[0], pa[2]-pb[2])
            if dist < walk_threshold:
                continue
            ctype = "walk_long"

        # determine bidirectionality
        bidir = (b, a, action) in conn_set

        # build maps: keys are point ids, values True (matches F.konst True)
        at_map = {a: True}
        to_map = {b: True}

        cconn = {
            "type": ctype,
            "bidirectional": bidir,
            "at": at_map,
            "to": to_map
        }
        generated.append(cconn)

    return generated

# ---------------------------------------------------------
# FORMATS
# ---------------------------------------------------------

Surface = F.union(
    F.list(F.Ref.Points),
    F.struct([
        {"id": F.ID},
        {"c_conns": F.map(F.Ref.Points, F.Ref.CConns)}
    ])
)
F.format("Surface", Surface)

Connection = F.struct([
    {"action": F.Int},
    {"fromID": F.Int},
    {"toID": F.Int},
    {"i1": F.Int},
    {"i2": F.Int},
    {"j1": F.Int},
    {"j2": F.Int},
    {"t1": F.Double},
    {"t2": F.Double},
    {"u1": F.Double},
    {"u2": F.Double},
])
F.format("Connection", Connection)

CConnection = F.struct([
    {"type": F.String},
    {"bidirectional": F.Bool},
    {"at": F.map(F.Ref.Points, F.konst(True, F.Bool, False))},
    {"to": F.map(F.Ref.Points, F.konst(True, F.Bool, False))},
])
F.format("CConnection", CConnection)

Point = F.struct([
    {"id": F.ID},
    {"v3": F.V3},
    {"ptype": F.Byte}
])
F.format("Point", Point)

Barrier = F.union(
    Surface,
    F.struct([
        {"is_barrier": F.konst(True, F.Bool, False)}
    ])
)

F.new("PointSight", F.map(F.Ref.Points, F.Double))

Mesh = F.struct([
    {"Name": F.String},
    {"Visible": F.Bool},
    {"points": F.list(Point, "Points")},
    {"c_conns": F.GE_VER(2, F.list(CConnection, "CConns"), None)},
    {"surfaces": F.list(Surface, "Surfaces")},
    {"barriers": F.GE_VER(3, F.list(Barrier, "Barriers"), None)},
    {"connections": F.list(Connection)},
])
F.format("Mesh", Mesh)

F.new("MeshSave", F.struct([
    {
        "version": F.save(
            "version",
            F.konst(F._VERSION, F.Int, True)
        )
    },
    {"mesh": Mesh}
]))


MeshReq = F.struct([
    {
        "version": F.save(
            "version",
            F.konst(F._VERSION, F.Int, True)
        )
    },
    {"params": F.map(F.String, F.Any)},
    {"mesh": Mesh}
])
F.new("MeshReq", MeshReq)

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
# HELPERS
# --------------------------------------------------------

# main generator: preserves mesh name/visible and existing surfaces; returns new mesh dict
def generate_navmesh(mesh_data: Dict, params: Dict) -> Dict:
    # preserve name/visible
    name = mesh_data.get("Name", "Mesh")
    visible = mesh_data.get("Visible", mesh_data.get("visible", True))

    points_raw = mesh_data.get("points", [])
    surfaces_raw = mesh_data.get("surfaces", [])
    barriers_raw = mesh_data.get("barriers", [])
    c_conns_in = mesh_data.get("c_conns", []) or []

    # build id->v3 map from input points
    id_to_v3 = {}
    for p in points_raw:
        pid = int(p.get("id", 0))
        v3 = tuple(p.get("v3", (0.0,0.0,0.0)))
        id_to_v3[pid] = v3

    gravity = float(params.get("gravity", 196.2))
    jumpPower = float(params.get("jumpPower", 50))
    walkSpeed = float(params.get("walkSpeed", 16))
    radius = float(params.get("radius", 2))
    height = float(params.get("height", 5))

    barrier_aabbs = build_barrier_aabbs(barriers_raw, id_to_v3)

    # Start output points with originals (preserve ids by remapping to new contiguous ids)
    out_points = []
    next_id = 1
    orig_to_new = {}
    for orig_id, v in id_to_v3.items():
        orig_to_new[orig_id] = next_id
        out_points.append({"id": next_id, "v3": v, "ptype": 1})
        next_id += 1

    # Add centroid + edge-midpoint sampling per surface (configurable)
    centroid_ids = []
    midpoint_ids = []
    for surf in surfaces_raw:
        if len(surf) < 3: continue
        # gather vertex coords for this surface
        verts = [id_to_v3[i] for i in surf if i in id_to_v3]
        if len(verts) < 3: continue
        a,b,c = verts[0], verts[1], verts[2]
        centroid = tri_centroid(a,b,c)
        n = tri_normal(a,b,c)
        up_dot = n[1]
        ptype = 1 if up_dot >= 0.6 else 0
        out_points.append({"id": next_id, "v3": centroid, "ptype": ptype})
        centroid_ids.append(next_id)
        centroid_id = next_id
        next_id += 1
        # edge midpoints
        for i in range(len(verts)):
            v1 = verts[i]; v2 = verts[(i+1)%len(verts)]
            mid = ((v1[0]+v2[0])/2.0, (v1[1]+v2[1])/2.0, (v1[2]+v2[2])/2.0)
            out_points.append({"id": next_id, "v3": mid, "ptype": ptype})
            midpoint_ids.append(next_id)
            next_id += 1

    # Build surfaces referencing new ids: map original vertex ids to new ids, but keep original surface lists unchanged
    # We do NOT edit surfaces; we only create a parallel list for internal connectivity if needed.
    out_surfaces = []
    for surf in surfaces_raw:
        mapped = [orig_to_new[i] for i in surf if i in orig_to_new]
        if mapped:
            out_surfaces.append(mapped)

    # Build connections:
    out_connections = []
    # candidate points list for pairwise tests
    candidates = out_points[:]  # list of dicts with id,v3,ptype
    max_walk_dist = max(1.0, radius * 4.0)
    # spatial pruning: simple grid hash to avoid O(n^2) for large point sets
    cell = max(4.0, radius * 4.0)
    grid = {}
    def cell_key(p):
        return (int(p[0]//cell), int(p[2]//cell))
    for p in candidates:
        k = cell_key(p["v3"])
        grid.setdefault(k, []).append(p)
    def nearby_points(p):
        kx, kz = cell_key(p["v3"])
        for dx in (-1,0,1):
            for dz in (-1,0,1):
                for q in grid.get((kx+dx, kz+dz), []):
                    if q["id"] != p["id"]:
                        yield q

    for pa in candidates:
        a_v = tuple(pa["v3"])
        for pb in nearby_points(pa):
            if pb["id"] <= pa["id"]:
                continue
            b_v = tuple(pb["v3"])
            dist = length(vec_sub(a_v, b_v))
            # walk connection
            if dist <= max_walk_dist and pa["ptype"] == 1 and pb["ptype"] == 1:
                blocked = any(box.swept_aabb(a_v, b_v, radius, height) for box in barrier_aabbs)
                if not blocked:
                    out_connections.append({"action":0, "fromID":pa["id"], "toID":pb["id"]}) # out_connections.append({"action":0, "fromID":pa["id"], "toID":pb["id"], **_conn_defaults()})
                    continue
            # jump connection
            if can_jump(a_v, b_v, jumpPower, gravity, walkSpeed, radius, height, barrier_aabbs):
                out_connections.append({"action":1, "fromID":pa["id"], "toID":pb["id"]}) # out_connections.append({"action":1, "fromID":pa["id"], "toID":pb["id"], **_conn_defaults()})

    # c_conns: preserve input c_conns and also expose empty list if none
    out_c_conns = synthesize_c_conns(out_connections, out_points, c_conns_in, radius * 2)

    # barriers: keep original barrier geometry and also expose AABB list if needed
    out_barriers = barriers_raw or []

    mesh_out = {
        "Name": name,
        "Visible": visible,
        "points": out_points,
        "c_conns": out_c_conns,
        "surfaces": out_surfaces,   # surfaces preserved (mapped to new point ids)
        "barriers": out_barriers,
        "connections": out_connections
    }
    return mesh_out
# ---------------------------------------------------------
# ROUTES
# ---------------------------------------------------------

def home(req: Request, res: Response):
    return res.render("index.html", {
        "title": "Welcome",
        "name": "Donovan"
    })


def mesh_generate(req: Request, res: Response):
    print(req.data)
    body = req.json

    ok, err = util.pcall(lambda: body)
    if not ok:
        return res.json({"error": err})

    params = body.get("params", {})
    mesh_data = body.get("mesh", {})

    _gravity = params.get("gravity", 196.2)
    _jumpPower = params.get("jumpPower", 50)
    _walkSpeed = params.get("walkSpeed", 16)
    _radius = params.get("radius", 2)
    _height = params.get("height", 5)

    generated = None

    name = mesh_data.get("Name", "Mesh")
    points_raw = mesh_data.get("points", [])
    surfaces_raw = mesh_data.get("surfaces", [])
    barriers_raw = mesh_data.get("barriers", [])
    c_conns_raw = mesh_data.get("c_conns", [])

    generated = generate_navmesh(mesh_data, params)

    print("----- GENERATED MESH OUTPUT -----")
    print(json.dumps(generated, indent=4))
    print("----------------------------------")

    return res.json({
        "status": "ok",
        "mesh": generated
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
