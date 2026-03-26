# main.py
import json
import math
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Tuple, Optional
from enum import Enum
from collections import defaultdict

from expy import expy, Request, Response
from format import F

# ---------------------------
# PTYPES enum (Polaris-compatible)
# ---------------------------
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

V3 = Tuple[float, float, float]

# ---------------------------
# AABB class and helpers
# ---------------------------
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
        mn = (min(start[0], end[0]) - radius, min(start[1], end[1]), min(start[2], end[2]) - radius)
        mx = (max(start[0], end[0]) + radius, max(start[1], end[1]) + height, max(start[2], end[2]) + radius)
        sweep_box = AABB(mn, mx)
        return self.intersects(sweep_box)

# ---------------------------
# Vector helpers
# ---------------------------
def vec_sub(a: V3, b: V3) -> V3:
    return (a[0]-b[0], a[1]-b[1], a[2]-b[2])

def length(a: V3) -> float:
    return math.sqrt(a[0]*a[0] + a[1]*a[1] + a[2]*a[2])

def tri_centroid(a: V3, b: V3, c: V3) -> V3:
    return ((a[0]+b[0]+c[0])/3.0, (a[1]+b[1]+c[1])/3.0, (a[2]+b[2]+c[2])/3.0)

def tri_normal(a: V3, b: V3, c: V3) -> V3:
    u = vec_sub(b, a); v = vec_sub(c, a)
    nx = u[1]*v[2] - u[2]*v[1]
    ny = u[2]*v[0] - u[0]*v[2]
    nz = u[0]*v[1] - u[1]*v[0]
    L = math.sqrt(nx*nx + ny*ny + nz*nz)
    if L == 0:
        return (0.0, 1.0, 0.0)
    return (nx/L, ny/L, nz/L)

# ---------------------------
# Connection dataclass and factory
# ---------------------------
@dataclass
class ConnectionObj:
    action: int
    fromID: int
    toID: int
    i1: int = 0
    i2: int = 0
    j1: int = 0
    j2: int = 0
    t1: float = 0.0
    t2: float = 0.0
    u1: float = 0.0
    u2: float = 0.0

def make_conn(action: int, frm: int, to: int,
              i1: int = 0, i2: int = 0, j1: int = 0, j2: int = 0,
              t1: float = 0.0, t2: float = 0.0, u1: float = 0.0, u2: float = 0.0) -> Dict[str, Any]:
    return asdict(ConnectionObj(action, frm, to, i1, i2, j1, j2, t1, t2, u1, u2))

# ---------------------------
# Jump model and sampling
# ---------------------------
def can_jump(a: V3, b: V3, jumpPower: float, gravity: float, walkSpeed: float,
             radius: float, height: float, barrier_aabbs: List[AABB],
             air_control: float = 1.0, samples: int = 8) -> bool:
    dx = b[0] - a[0]; dz = b[2] - a[2]
    horiz = math.hypot(dx, dz)
    vy = jumpPower
    T = 2.0 * vy / gravity if gravity > 0 else 0.0
    if T <= 0:
        return False
    vx = walkSpeed * air_control
    if horiz > vx * T:
        return False
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

# ---------------------------
# Input normalization and id preservation
# ---------------------------
def normalize_points_preserve(points_raw: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[int,int]]:
    """
    Preserve numeric ids when present. Assign new ids only for missing/None ids.
    Returns normalized list and mapping of assigned ids (old->new) for those that were None.
    """
    normalized = []
    # collect existing numeric ids to avoid collisions
    existing_ids = set()
    for p in points_raw:
        pid = p.get("id")
        try:
            if pid is not None:
                existing_ids.add(int(pid))
        except Exception:
            pass
    # choose next id above max existing
    next_auto = max(existing_ids) + 1 if existing_ids else 1
    assigned_map = {}  # original None index -> assigned id (not used externally except metadata)
    for p in points_raw:
        pid = p.get("id")
        if pid is None:
            pid_int = next_auto
            next_auto += 1
        else:
            try:
                pid_int = int(pid)
            except Exception:
                pid_int = next_auto
                next_auto += 1
        v3 = p.get("v3", (0.0,0.0,0.0))
        if isinstance(v3, (list, tuple)) and len(v3) >= 3:
            v3t = (float(v3[0]), float(v3[1]), float(v3[2]))
        else:
            v3t = (0.0,0.0,0.0)
        ptype = p.get("ptype", PTYPE.INTERIOR.value)
        try:
            ptype = int(ptype)
        except Exception:
            ptype = PTYPE.INTERIOR.value
        normalized.append({"orig": p, "id": pid_int, "v3": v3t, "ptype": ptype})
    return normalized, assigned_map

def map_surface_indices(surf: List[Any], id_list: List[int], normalized_points: List[Dict[str, Any]]) -> List[int]:
    mapped = []
    id_set = set(id_list)
    for entry in surf:
        try:
            e_int = int(entry)
        except Exception:
            e_int = None
        if e_int is not None and e_int in id_set:
            mapped.append(e_int)
            continue
        try:
            idx = int(entry) - 1
            if 0 <= idx < len(normalized_points):
                mapped.append(normalized_points[idx]["id"])
                continue
        except Exception:
            pass
    return mapped

# ---------------------------
# ptype heuristics and adjacency
# ---------------------------
def build_vertex_adjacency(surfaces: List[List[int]]) -> Dict[int, set]:
    adj = {}
    for s in surfaces:
        n = len(s)
        for i in range(n):
            a = s[i]; b = s[(i+1) % n]
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
    return adj

def is_boundary_vertex(vertex_id: int, surfaces: List[List[int]]) -> bool:
    edge_count = {}
    for s in surfaces:
        n = len(s)
        for i in range(n):
            a = s[i]; b = s[(i+1) % n]
            key = tuple(sorted((a,b)))
            edge_count[key] = edge_count.get(key, 0) + 1
    for s in surfaces:
        if vertex_id in s:
            idxs = [i for i,v in enumerate(s) if v == vertex_id]
            for idx in idxs:
                a = s[idx]; b = s[(idx+1) % len(s)]
                if edge_count.get(tuple(sorted((a,b))), 0) == 1:
                    return True
    return False

def point_clearance(point_v3: V3, barrier_aabbs: List[AABB], required_height: float) -> bool:
    x,y,z = point_v3
    for box in barrier_aabbs:
        if (box.min[0] <= x <= box.max[0]) and (box.min[2] <= z <= box.max[2]):
            if box.min[1] <= y + required_height and box.max[1] >= y:
                return False
    return True

def ptype_from_normal(ny: float) -> int:
    if ny >= 0.95:
        return PTYPE.INTERIOR.value
    if ny >= 0.7:
        return PTYPE.MIDEXTERIOR.value
    if ny >= 0.5:
        return PTYPE.EXTERIOR.value
    return PTYPE.BLOCKED.value

def assign_ptypes_and_flags(out_points: List[Dict[str, Any]], mapped_surfaces: List[List[int]],
                            id_to_v3: Dict[int, V3], barrier_aabbs: List[AABB],
                            radius: float, height: float, adjacency: Optional[Dict[int,set]] = None) -> Dict[int,set]:
    if adjacency is None:
        adjacency = build_vertex_adjacency(mapped_surfaces)
    surf_normals = []
    for s in mapped_surfaces:
        if len(s) < 3:
            surf_normals.append((0.0,1.0,0.0))
            continue
        a = id_to_v3.get(s[0]); b = id_to_v3.get(s[1]); c = id_to_v3.get(s[2])
        if a and b and c:
            surf_normals.append(tri_normal(a,b,c))
        else:
            surf_normals.append((0.0,1.0,0.0))
    vert_normals = {}
    for si, s in enumerate(mapped_surfaces):
        n = surf_normals[si]
        for vid in s:
            vx = vert_normals.setdefault(vid, [0.0,0.0,0.0])
            vx[0] += n[0]; vx[1] += n[1]; vx[2] += n[2]
    for vid, comp in list(vert_normals.items()):
        L = math.sqrt(comp[0]*comp[0] + comp[1]*comp[1] + comp[2]*comp[2])
        if L == 0:
            vert_normals[vid] = (0.0,1.0,0.0)
        else:
            vert_normals[vid] = (comp[0]/L, comp[1]/L, comp[2]/L)
    id_to_point = {p["id"]: p for p in out_points}
    for p in out_points:
        vid = p["id"]
        v3 = tuple(p["v3"])
        orig = p.get("orig") or {}
        if isinstance(orig, dict):
            if orig.get("goal") or orig.get("is_goal"):
                p["ptype"] = PTYPE.GOAL.value
                p["action"] = False; p["reflex"] = False
                continue
            if orig.get("action") or orig.get("is_action"):
                p["ptype"] = PTYPE.ACTION.value
                p["action"] = True; p["reflex"] = False
                continue
        has_clearance = point_clearance(v3, barrier_aabbs, height)
        ny = vert_normals.get(vid, (0.0,1.0,0.0))[1]
        deg = len(adjacency.get(vid, set()))
        boundary = is_boundary_vertex(vid, mapped_surfaces)
        if not has_clearance or deg <= 1:
            p["ptype"] = PTYPE.BLOCKED.value
        elif ny >= 0.95 and not boundary:
            p["ptype"] = PTYPE.INTERIOR.value
        elif ny >= 0.7:
            p["ptype"] = PTYPE.MIDEXTERIOR.value
        elif ny >= 0.5:
            p["ptype"] = PTYPE.EXTERIOR.value
        else:
            p["ptype"] = PTYPE.BLOCKED.value
        p["action"] = False
        p["reflex"] = False
        for box in barrier_aabbs:
            dx = max(box.min[0] - v3[0], 0, v3[0] - box.max[0])
            dz = max(box.min[2] - v3[2], 0, v3[2] - box.max[2])
            horiz_dist = math.hypot(dx, dz)
            if horiz_dist <= radius * 1.5:
                p["reflex"] = True
                break
    return adjacency

# ---------------------------
# find surface indices helper
# ---------------------------
def find_surface_indices_for_pair(from_id: int, to_id: int, mapped_surfaces: List[List[int]]) -> Tuple[int,int,int,int]:
    i1 = i2 = j1 = j2 = 0
    s1 = s2 = None
    for s in mapped_surfaces:
        if from_id in s and s1 is None:
            s1 = s
        if to_id in s and s2 is None:
            s2 = s
        if s1 is not None and s2 is not None:
            break
    if s1 is not None:
        try:
            i1 = s1.index(from_id) + 1
        except ValueError:
            i1 = 0
        i2 = s1.index(to_id) + 1 if to_id in s1 else 0
    if s2 is not None and s2 is not s1:
        j1 = s2.index(from_id) + 1 if from_id in s2 else 0
        try:
            j2 = s2.index(to_id) + 1
        except ValueError:
            j2 = 0
    return i1, i2, j1, j2

# ---------------------------
# synthesize c_conns (grouped by fromID and type)
# ---------------------------
def synthesize_c_conns_grouped(out_connections: List[Dict[str, Any]],
                               out_points: List[Dict[str, Any]],
                               existing_c_conns: List[Dict[str, Any]],
                               walk_threshold: float) -> Tuple[List[Dict[str, Any]], bool]:
    if existing_c_conns:
        return list(existing_c_conns), False
    id_to_v3 = {p["id"]: tuple(p["v3"]) for p in out_points}
    groups: Dict[Tuple[int,int], List[int]] = {}  # (action, fromID) -> [toIDs]
    conn_set = set((c["fromID"], c["toID"], c.get("action", 0)) for c in out_connections)
    for c in out_connections:
        a = c["fromID"]; b = c["toID"]; action = c.get("action", 0)
        if action == 1:
            key = (action, a)
            groups.setdefault(key, []).append(b)
            continue
        pa = id_to_v3.get(a); pb = id_to_v3.get(b)
        if pa is None or pb is None:
            continue
        dist = math.hypot(pa[0]-pb[0], pa[2]-pb[2])
        if dist >= walk_threshold:
            key = (action, a)
            groups.setdefault(key, []).append(b)
    generated = []
    for (action, frm), tos in groups.items():
        # build at/to maps
        at_map = {frm: True}
        to_map = {tid: True for tid in tos}
        ctype = "jump" if action == 1 else "walk_long"
        # determine bidirectionality: if any to has reverse edge, mark bidirectional True
        bidir = any((t, frm, action) in conn_set for t in tos)
        cconn = {
            "type": ctype,
            "bidirectional": bidir,
            "at": at_map,
            "to": to_map,
            "generated": True
        }
        generated.append(cconn)
    return generated, True

# ---------------------------
# Full generator (Polaris-like)
# ---------------------------
def generate_navmesh_polaris(mesh_data: Dict[str, Any],
                             params: Dict[str, Any],
                             options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if options is None:
        options = {}
    sample_midpoints = options.get("sample_midpoints", True)
    sample_centroids = options.get("sample_centroids", True)
    air_control = options.get("air_control", 1.0)
    jump_samples = int(options.get("jump_samples", 8))

    name = mesh_data.get("Name", mesh_data.get("name", "generated_mesh"))
    visible = mesh_data.get("Visible", mesh_data.get("visible", True))

    points_raw = mesh_data.get("points", []) or []
    surfaces_raw = mesh_data.get("surfaces", []) or []
    barriers_raw = mesh_data.get("barriers", []) or []
    c_conns_in = mesh_data.get("c_conns", []) or []

    normalized, assigned_map = normalize_points_preserve(points_raw)
    id_to_v3 = {item["id"]: item["v3"] for item in normalized}

    # build barrier AABBs: per-object and per-triangle (if polygon)
    barrier_aabbs: List[AABB] = []
    for bar in barriers_raw:
        coords = []
        if isinstance(bar, dict) and "min" in bar and "max" in bar:
            try:
                barrier_aabbs.append(AABB(tuple(bar["min"]), tuple(bar["max"])))
                continue
            except Exception:
                pass
        for v in bar:
            if isinstance(v, (list, tuple)) and len(v) == 3:
                coords.append(tuple(v))
            elif isinstance(v, int) and v in id_to_v3:
                coords.append(id_to_v3[v])
        if coords:
            xs = [c[0] for c in coords]; ys = [c[1] for c in coords]; zs = [c[2] for c in coords]
            barrier_aabbs.append(AABB((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))))

    gravity = float(params.get("gravity", 196.2))
    jumpPower = float(params.get("jumpPower", 50))
    walkSpeed = float(params.get("walkSpeed", 16))
    radius = float(params.get("radius", 2))
    height = float(params.get("height", 5))

    # Build out_points preserving original ids
    out_points: List[Dict[str, Any]] = []
    for item in normalized:
        out_points.append({"id": item["id"], "v3": item["v3"], "ptype": item["ptype"], "orig": item["orig"]})

    # Keep surfaces as provided (do not overwrite). Also produce mapped_surfaces referencing preserved ids.
    mapped_surfaces: List[List[int]] = []
    id_list = list(id_to_v3.keys())
    for surf in surfaces_raw:
        if isinstance(surf, dict):
            # struct surface: preserve as-is (it may contain id and c_conns)
            # For connectivity we skip struct surfaces unless they include a list form; keep them in output surfaces unchanged.
            # Represent struct surfaces in mapped_surfaces only if they include a 'points' list (non-standard fallback).
            if "points" in surf and isinstance(surf["points"], (list, tuple)):
                mapped = map_surface_indices(surf["points"], id_list, normalized)
                if mapped:
                    mapped_surfaces.append(mapped)
            continue
        if not isinstance(surf, (list, tuple)):
            continue
        mapped = map_surface_indices(surf, id_list, normalized)
        if mapped:
            mapped_surfaces.append(mapped)

    # sampling: add centroids and midpoints (mark generated points)
    centroid_ids: List[int] = []
    midpoint_ids: List[int] = []
    next_generated_id = max(id_list) + 1 if id_list else 1
    def add_generated_point(v: V3, ptype: int = PTYPE.INTERIOR.value) -> int:
        nonlocal next_generated_id
        nid = next_generated_id
        out_points.append({"id": nid, "v3": v, "ptype": ptype, "generated": True})
        next_generated_id += 1
        return nid

    if sample_centroids or sample_midpoints:
        for surf in surfaces_raw:
            if not isinstance(surf, (list, tuple)) or len(surf) < 3:
                continue
            verts = []
            for entry in surf:
                try:
                    e_int = int(entry)
                except Exception:
                    e_int = None
                if e_int is not None and e_int in id_to_v3:
                    verts.append(id_to_v3[e_int])
            if len(verts) < 3:
                continue
            a, b, c = verts[0], verts[1], verts[2]
            n = tri_normal(a, b, c)
            up_dot = n[1]
            ptype = ptype_from_normal(up_dot)
            if sample_centroids:
                centroid = tri_centroid(a, b, c)
                centroid_ids.append(add_generated_point(centroid, ptype))
            if sample_midpoints:
                for i in range(len(verts)):
                    v1 = verts[i]; v2 = verts[(i+1) % len(verts)]
                    mid = ((v1[0]+v2[0])/2.0, (v1[1]+v2[1])/2.0, (v1[2]+v2[2])/2.0)
                    midpoint_ids.append(add_generated_point(mid, ptype))

    # connectivity candidates and spatial hash
    candidates = out_points[:]
    max_walk_dist = max(1.0, radius * 4.0)
    cell = max(4.0, radius * 4.0)
    grid: Dict[Tuple[int,int], List[Dict[str,Any]]] = {}
    def cell_key(p: V3) -> Tuple[int,int]:
        return (int(p[0] // cell), int(p[2] // cell))
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

    # assign ptypes and flags using mapped_surfaces and barrier AABBs
    adjacency = build_vertex_adjacency(mapped_surfaces)
    assign_ptypes_and_flags(out_points, mapped_surfaces, id_to_v3, barrier_aabbs, radius, height, adjacency=adjacency)

    # build connections (walk + jump) with adjacency indices
    out_connections: List[Dict[str, Any]] = []
    conn_set = set()
    for pa in candidates:
        a_v = tuple(pa["v3"])
        for pb in nearby_points(pa):
            if pb["id"] <= pa["id"]:
                continue
            b_v = tuple(pb["v3"])
            dist = length(vec_sub(a_v, b_v))
            if dist <= max_walk_dist and pa.get("ptype", PTYPE.INTERIOR.value) != PTYPE.BLOCKED.value and pb.get("ptype", PTYPE.INTERIOR.value) != PTYPE.BLOCKED.value:
                blocked = any(box.swept_aabb(a_v, b_v, radius, height) for box in barrier_aabbs)
                if not blocked:
                    i1, i2, j1, j2 = find_surface_indices_for_pair(pa["id"], pb["id"], mapped_surfaces)
                    conn = make_conn(0, pa["id"], pb["id"], i1=i1, i2=i2, j1=j1, j2=j2)
                    out_connections.append(conn)
                    conn_set.add((pa["id"], pb["id"], 0))
                    continue
            if can_jump(a_v, b_v, jumpPower, gravity, walkSpeed, radius, height, barrier_aabbs, air_control, jump_samples):
                i1, i2, j1, j2 = find_surface_indices_for_pair(pa["id"], pb["id"], mapped_surfaces)
                conn = make_conn(1, pa["id"], pb["id"], i1=i1, i2=i2, j1=j1, j2=j2)
                out_connections.append(conn)
                conn_set.add((pa["id"], pb["id"], 1))

    # mark action flag for points that are jump origins
    id_to_point = {p["id"]: p for p in out_points}
    out_by_from = defaultdict(list)
    for c in out_connections:
        out_by_from[c["fromID"]].append(c)
    for pid, conns in out_by_from.items():
        for c in conns:
            if c["action"] == 1:
                if pid in id_to_point:
                    id_to_point[pid]["action"] = True
                break

    # synthesize c_conns grouped by (action, fromID) when input empty
    walk_threshold = float(options.get("walk_threshold", max(4.0, radius * 2.0)))
    out_c_conns, generated_flag = synthesize_c_conns_grouped(out_connections, out_points, c_conns_in, walk_threshold)

    # final mesh: preserve original surfaces as provided (do not overwrite)
    mesh_out = {
        "Name": name,
        "Visible": visible,
        "points": out_points,
        "c_conns": out_c_conns,
        "surfaces": surfaces_raw,   # preserve original surface representation exactly
        "barriers": barriers_raw,
        "connections": out_connections
    }

    # metadata: only include assigned_map if we created new ids for missing points
    meta = {
        "assigned_ids": assigned_map,  # often empty; kept for compatibility
        "generated_c_conns": generated_flag,
        "sampled_centroid_ids": centroid_ids,
        "sampled_midpoint_ids": midpoint_ids
    }

    return {"mesh": mesh_out, "meta": meta}

# ---------------------------
# Web app and routes
# ---------------------------
app = expy(__name__)

def json_parser(req: Request, res: Response, next):
    if req.get_method() in ("POST", "PUT", "PATCH") and req.body:
        try:
            req.json = json.loads(req.body)
        except Exception:
            req.json = {}
    else:
        req.json = {}
    next()

def logger(req: Request, res: Response, next):
    body_json = getattr(req, "json", "N/A")

    print("----- REQUEST DEBUG -----")
    print(f"Method: {req.get_method()}")
    print(f"Path:   {getattr(req, 'path', req.get_path() if hasattr(req, 'get_path') else '')}")
    print(f"Full URL: {getattr(req, 'full_url', '')}")
    print(f"Body JSON: {json.dumps(body_json, indent=4)}")
    print("-------------------------")
    next()

app.use(json_parser)
app.use(logger)

def home(req: Request, res: Response):
    return res.render("index.html", {"title": "Welcome", "name": "Donovan"})

def mesh_generate(req: Request, res: Response):
    body = getattr(req, "json", {}) or {}
    try:
        params = body.get("params", {})
        mesh_data = body.get("mesh", {})
    except Exception as exc:
        return res.json({"error": str(exc)})

    _gravity = params.get("gravity", 196.2)
    _jumpPower = params.get("jumpPower", 50)
    _walkSpeed = params.get("walkSpeed", 16)
    _radius = params.get("radius", 2)
    _height = params.get("height", 5)

    options = {
        "sample_midpoints": True,
        "sample_centroids": True,
        "air_control": 1.0,
        "jump_samples": 8,
        "walk_threshold": max(4.0, _radius * 2.0)
    }

    try:
        result = generate_navmesh_polaris(mesh_data, {
            "gravity": _gravity,
            "jumpPower": _jumpPower,
            "walkSpeed": _walkSpeed,
            "radius": _radius,
            "height": _height
        }, options)
    except Exception as exc:
        return res.json({"status": "error", "error": str(exc)})

    mesh_out = result.get("mesh")
    meta = result.get("meta", {})

    print(json.dumps(mesh_out, indent=4))

    return res.json({
        "status": "ok",
        "mesh": mesh_out,
        "meta": meta
    })

def biological_intelligence(req: Request, res: Response):
    pass

app.get("/", home)
app.post("/mesh/generate", mesh_generate)
app.post("/biological/intelligence", biological_intelligence)

if __name__ == "__main__":
    try: 
        app.run(port=5000)
    except KeyboardInterrupt:
        pass
