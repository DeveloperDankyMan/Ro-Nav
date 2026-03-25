# util.py
# Utilities for Polaris-Nav Python port
# - Imports FormatRegistry.F and attaches primitive save/load handlers into F
# - Binary helpers, zero-run encoding, compression, generic save/load engine

from __future__ import annotations
import struct
import zlib
import traceback
from typing import Any, Callable, Dict, List, Tuple, Union

# Import the user's format registry (adjust module name if needed)
from format import F  # <-- change if your file is named differently

# --- Numeric precision constants ------------------------------------------------
prec = 1e-3
prec2 = prec * prec

# compute machine epsilon similar to Lua code
_e = 1.0
while 1.0 + _e != 1.0:
    _e *= 0.5
e = _e

# --- Small helpers --------------------------------------------------------------
def mod1_dec(x: int, m: int) -> int:
    return (x - 2) % m + 1

def mod1_inc(x: int, m: int) -> int:
    return x % m + 1

def bind(f: Callable, obj: Any) -> Callable:
    def _bound(*args, **kwargs):
        return f(obj, *args, **kwargs)
    return _bound

def union_k(*dicts: Dict[Any, Any]) -> Dict[Any, Any]:
    r: Dict[Any, Any] = {}
    for d in dicts:
        r.update(d)
    return r

def union_i(*lists: List[Any]) -> List[Any]:
    r: List[Any] = []
    for lst in lists:
        r.extend(list(lst))
    return r

def validate_bool(txt: str) -> Union[bool, None]:
    if txt is None:
        return None
    s = txt.lower()
    if s in ('true', 't'):
        return True
    if s in ('false', 'f'):
        return False
    return None

def get_trace(msg: str) -> str:
    tb = ''.join(traceback.format_stack())
    return f"{msg}; {tb}"

def pcall(f: Callable, *args, **kwargs) -> Tuple[bool, Any]:
    try:
        return True, f(*args, **kwargs)
    except Exception as exc:
        return False, get_trace(str(exc))

# --- Binary helpers ------------------------------------------------------------
# Endianness: '>' big-endian, '<' little-endian. Default is big-endian.
def i2b(x: int, length: int = 4, endian: str = '>') -> bytes:
    if length == 4:
        return struct.pack(f"{endian}I", x)
    if length == 8:
        return struct.pack(f"{endian}Q", x)
    # generic fallback
    return x.to_bytes(length, byteorder='big' if endian == '>' else 'little')

def b2i(b: bytes, endian: str = '>') -> int:
    ln = len(b)
    if ln == 4:
        return struct.unpack(f"{endian}I", b)[0]
    if ln == 8:
        return struct.unpack(f"{endian}Q", b)[0]
    return int.from_bytes(b, byteorder='big' if endian == '>' else 'little')

def i642b(x: int, endian: str = '>') -> bytes:
    return i2b(x, length=8, endian=endian)

def b2i64(b: bytes, endian: str = '>') -> int:
    return b2i(b, endian=endian)

def d2b(x: float, endian: str = '>') -> bytes:
    return struct.pack(f"{endian}d", x)

def b2d(b: bytes, endian: str = '>') -> float:
    return struct.unpack(f"{endian}d", b)[0]

def v2b(v: Tuple[float, float, float], endian: str = '>') -> bytes:
    return d2b(v[0], endian=endian) + d2b(v[1], endian=endian) + d2b(v[2], endian=endian)

def b2v(b: bytes, endian: str = '>') -> Tuple[float, float, float]:
    if len(b) != 24:
        raise ValueError("Vector bytes must be 24 bytes")
    return (b2d(b[0:8], endian=endian), b2d(b[8:16], endian=endian), b2d(b[16:24], endian=endian))

def s2b(s: str, encoding: str = 'utf-8', endian: str = '>') -> bytes:
    bs = s.encode(encoding)
    return i2b(len(bs), length=4, endian=endian) + bs

def read_i(data: bytes, i: int, endian: str = '>') -> Tuple[int, int]:
    return b2i(data[i:i+4], endian=endian), i + 4

def read_i64(data: bytes, i: int, endian: str = '>') -> Tuple[int, int]:
    return b2i64(data[i:i+8], endian=endian), i + 8

def read_d(data: bytes, i: int, endian: str = '>') -> Tuple[float, int]:
    return b2d(data[i:i+8], endian=endian), i + 8

def read_v(data: bytes, i: int, endian: str = '>') -> Tuple[Tuple[float, float, float], int]:
    return b2v(data[i:i+24], endian=endian), i + 24

def read_t(data: bytes, i: int) -> Tuple[int, int]:
    return data[i], i + 1

def read_s(data: bytes, i: int, endian: str = '>') -> Tuple[str, int]:
    n, i = read_i(data, i, endian=endian)
    s = data[i:i+n].decode('utf-8')
    return s, i + n

def read_a(data: bytes, i: int, endian: str = '>') -> Tuple[Union[str, float], int]:
    ty, i = read_t(data, i)
    if ty == 0:
        return read_s(data, i, endian=endian)
    if ty == 1:
        return read_d(data, i, endian=endian)
    raise ValueError(f"Unknown Any type tag: {ty}")

# --- Zero-run encoding (zero_encoding.lua port) --------------------------------
_SPECIAL = bytes([255])
_NULL = bytes([0])

def encode_zeros(value: bytes) -> bytes:
    parts: List[bytes] = []
    i = 0
    n = len(value)
    while i < n:
        b = value[i]
        if b == 0:
            m = 1
            while i + 1 < n and m < 254 and value[i + 1] == 0:
                m += 1
                i += 1
            parts.append(_SPECIAL)
            parts.append(bytes([m]))
        elif b == 255:
            parts.append(_SPECIAL)
            parts.append(_SPECIAL)
        else:
            parts.append(bytes([b]))
        i += 1
    return b''.join(parts)

def decode_zeros(value: bytes) -> bytes:
    parts: List[bytes] = []
    i = 0
    n = len(value)
    while i < n:
        b = value[i]
        if b == 255:
            i += 1
            if i >= n:
                raise ValueError("Truncated zero-encoding stream")
            b2 = value[i]
            if b2 == 255:
                parts.append(_SPECIAL)
            else:
                parts.append(_NULL * b2)
        else:
            parts.append(bytes([b]))
        i += 1
    return b''.join(parts)

# --- Compression wrappers ------------------------------------------------------
def encode(value: bytes) -> bytes:
    compressed = zlib.compress(value, level=9)
    return encode_zeros(compressed)

def decode(value: bytes) -> bytes:
    return zlib.decompress(decode_zeros(value))

# --- Attach primitive save/load handlers into the provided F registry ----------
# The FormatRegistry you provided uses dicts for primitives like F.String, F.Int, etc.
# We attach 'save' and 'load' callables into those dicts so other modules can call them.

# Save handlers append bytes to a list of byte chunks

# --- Robust primitive save/load helpers (replace existing ones) ---

def _F_string_save(value: str, data_parts: List[bytes], context: dict = None, endian: str = '>'):
    # Treat None as empty string (4-byte zero length)
    if value is None:
        data_parts.append(i2b(0, length=4, endian=endian))
        return
    data_parts.append(s2b(value, endian=endian))

def _F_string_load(data: bytes, i: int, context: dict = None, endian: str = '>') -> Tuple[str, int]:
    s, i = read_s(data, i, endian=endian)
    # read_s returns "" for zero-length strings
    return s, i

def _F_bool_save(value: bool, data_parts: List[bytes], context: dict = None):
    data_parts.append(b'\x01' if value else b'\x00')

def _F_bool_load(data: bytes, i: int, context: dict = None) -> Tuple[bool, int]:
    return (data[i] == 1), i + 1

def _F_v3_save(value: Tuple[float, float, float], data_parts: List[bytes], context: dict = None, endian: str = '>'):
    if value is None:
        # write three zero doubles
        data_parts.append(d2b(0.0, endian=endian) * 3)
        return
    data_parts.append(v2b(value, endian=endian))

def _F_v3_load(data: bytes, i: int, context: dict = None, endian: str = '>') -> Tuple[Tuple[float, float, float], int]:
    return read_v(data, i, endian=endian)

def _F_byte_save(value: int, data_parts: List[bytes], context: dict = None):
    data_parts.append(bytes([0]) if value is None else bytes([value & 0xFF]))

def _F_byte_load(data: bytes, i: int, context: dict = None) -> Tuple[int, int]:
    return data[i], i + 1

def _F_double_save(value: float, data_parts: List[bytes], context: dict = None, endian: str = '>'):
    data_parts.append(d2b(0.0, endian=endian) if value is None else d2b(float(value), endian=endian))

def _F_double_load(data: bytes, i: int, context: dict = None, endian: str = '>') -> Tuple[float, int]:
    return read_d(data, i, endian=endian)

def _F_int_save(value: int, data_parts: List[bytes], context: dict = None, endian: str = '>'):
    data_parts.append(i2b(0, length=4, endian=endian) if value is None else i2b(int(value), length=4, endian=endian))

def _F_int_load(data: bytes, i: int, context: dict = None, endian: str = '>') -> Tuple[int, int]:
    return read_i(data, i, endian=endian)

def _F_int64_save(value: int, data_parts: List[bytes], context: dict = None, endian: str = '>'):
    data_parts.append(i642b(0, endian=endian) if value is None else i642b(int(value), endian=endian))

def _F_int64_load(data: bytes, i: int, context: dict = None, endian: str = '>') -> Tuple[int, int]:
    return read_i64(data, i, endian=endian)

def _F_any_save(value: Any, data_parts: List[bytes], context: dict = None, endian: str = '>'):
    # Tagging: 0 = string, 1 = double, 2 = None
    if value is None:
        data_parts.append(bytes([2]))
        return
    if isinstance(value, str):
        data_parts.append(bytes([0]) + s2b(value, endian=endian))
        return
    if isinstance(value, (int, float)):
        data_parts.append(bytes([1]) + d2b(float(value), endian=endian))
        return
    raise TypeError("F.Any.save: unsupported type")

def _F_any_load(data: bytes, i: int, context: dict = None, endian: str = '>') -> Tuple[Any, int]:
    tag = data[i]
    i += 1
    if tag == 2:
        return None, i
    if tag == 0:
        return read_s(data, i, endian=endian)
    if tag == 1:
        return read_d(data, i, endian=endian)
    raise ValueError(f"Unknown F.Any tag: {tag}")


# def _F_string_save(value: str, data_parts: List[bytes], context: dict = None, endian: str = '>'):
#     data_parts.append(s2b(value, endian=endian))

# def _F_string_load(data: bytes, i: int, context: dict = None, endian: str = '>') -> Tuple[str, int]:
#     return read_s(data, i, endian=endian)

# def _F_bool_save(value: bool, data_parts: List[bytes], context: dict = None):
#     data_parts.append(b'\x01' if value else b'\x00')

# def _F_bool_load(data: bytes, i: int, context: dict = None) -> Tuple[bool, int]:
#     return (data[i] == 1), i + 1

# def _F_v3_save(value: Tuple[float, float, float], data_parts: List[bytes], context: dict = None, endian: str = '>'):
#     data_parts.append(v2b(value, endian=endian))

# def _F_v3_load(data: bytes, i: int, context: dict = None, endian: str = '>') -> Tuple[Tuple[float, float, float], int]:
#     return read_v(data, i, endian=endian)

# def _F_byte_save(value: int, data_parts: List[bytes], context: dict = None):
#     data_parts.append(bytes([value & 0xFF]))

# def _F_byte_load(data: bytes, i: int, context: dict = None) -> Tuple[int, int]:
#     return data[i], i + 1

# def _F_double_save(value: float, data_parts: List[bytes], context: dict = None, endian: str = '>'):
#     data_parts.append(d2b(value, endian=endian))

# def _F_double_load(data: bytes, i: int, context: dict = None, endian: str = '>') -> Tuple[float, int]:
#     return read_d(data, i, endian=endian)

# def _F_int_save(value: int, data_parts: List[bytes], context: dict = None, endian: str = '>'):
#     data_parts.append(i2b(value, length=4, endian=endian))

# def _F_int_load(data: bytes, i: int, context: dict = None, endian: str = '>') -> Tuple[int, int]:
#     return read_i(data, i, endian=endian)

# def _F_int64_save(value: int, data_parts: List[bytes], context: dict = None, endian: str = '>'):
#     data_parts.append(i642b(value, endian=endian))

# def _F_int64_load(data: bytes, i: int, context: dict = None, endian: str = '>') -> Tuple[int, int]:
#     return read_i64(data, i, endian=endian)

# def _F_any_save(value: Any, data_parts: List[bytes], context: dict = None, endian: str = '>'):
#     if isinstance(value, str):
#         data_parts.append(bytes([0]) + s2b(value, endian=endian))
#     elif isinstance(value, (int, float)):
#         data_parts.append(bytes([1]) + d2b(float(value), endian=endian))
#     else:
#         raise TypeError("F.Any.save: unsupported type")

# def _F_any_load(data: bytes, i: int, context: dict = None, endian: str = '>') -> Tuple[Any, int]:
#     return read_a(data, i, endian=endian)

F.String['save'] = _F_string_save
F.String['load'] = _F_string_load
F.Bool['save']   = _F_bool_save
F.Bool['load']   = _F_bool_load
F.V3['save']     = _F_v3_save
F.V3['load']     = _F_v3_load
F.Byte['save']   = _F_byte_save
F.Byte['load']   = _F_byte_load
F.Double['save'] = _F_double_save
F.Double['load'] = _F_double_load
F.Int['save']    = _F_int_save
F.Int['load']    = _F_int_load
F.Int64['save']  = _F_int64_save
F.Int64['load']  = _F_int64_load
F.Any['save']    = _F_any_save
F.Any['load']    = _F_any_load


# --- Generic save/load engine compatible with your FormatRegistry ----------------
# The engine expects format descriptors exactly like those produced by FormatRegistry methods.

def save(data_parts: List[bytes], obj: Any, fmt: Dict, context: Dict = None, endian: str = '>'):
    if context is None:
        context = {}
    if fmt is None:
        return
    t = fmt.get("type")
    
    # --- inside save(...) ---

    # ref branch (robust)
    if t == "ref":
        # Accept: None, int id, dict with 'id', or object with .id
        if obj is None:
            id_val = 0
        elif isinstance(obj, int):
            id_val = obj
        elif isinstance(obj, dict) and "id" in obj:
            id_val = int(obj["id"])
        elif hasattr(obj, "id"):
            id_val = int(getattr(obj, "id"))
        else:
            raise TypeError(f"Cannot serialize ref: unexpected type {type(obj)} for format {fmt}")
        data_parts.append(i2b(id_val, length=4, endian=endian))
        return
    # if t == "ref":
    #     # write id as 4-byte int; caller must ensure obj has .id
    #     data_parts.append(i2b(getattr(obj, "id"), length=4, endian=endian))
    #     return
    if t == "konst":
        if fmt.get("is_serialized"):
            save(data_parts, fmt["value"], fmt["v_format"], context, endian=endian)
        return
    if t == "save":
        save(data_parts, obj, fmt["v_format"], context, endian=endian)
        return
    if t == "enable_if":
        # cond is a callable that returns True/False given context
        if fmt["cond"](context):
            save(data_parts, obj, fmt["v_format"], context, endian=endian)
        return
    # Replace existing union branch in save(...) with this:

    if t == "union":
        options = fmt.get("options", [])
        # Quick type-based selection
        for opt in options:
            opt_type = opt.get("type")
            # If option is a list format and obj is a list-like, use it
            if opt_type == "list" and isinstance(obj, (list, tuple)):
                save(data_parts, obj, opt, context, endian=endian)
                return
            # If option is a struct and obj is mapping-like, use it
            if opt_type == "struct" and isinstance(obj, dict):
                save(data_parts, obj, opt, context, endian=endian)
                return
            # If option is a konst that serializes a scalar and obj is scalar, use it
            if opt_type == "konst" and not isinstance(obj, (list, dict)):
                save(data_parts, obj, opt, context, endian=endian)
                return
        # Fallback: try each option and accept the first that doesn't raise
        for opt in options:
            try:
                # Use a temporary list to test serialization without mutating main data_parts
                test_parts: List[bytes] = []
                save(test_parts, obj, opt, context, endian=endian)
                # If succeeded, append test_parts to real data_parts and return
                data_parts.extend(test_parts)
                return
            except Exception:
                continue
        # If none matched, raise to surface the mismatch
        raise TypeError(f"union.save: no matching option for object of type {type(obj)}")

    # if t == "union":
    #     # try each option in order
    #     for opt in fmt.get("options", []):
    #         save(data_parts, obj, opt, context, endian=endian)
    #     return
# struct branch (mapping-aware)
    if t == "struct":
        for field in fmt.get("fields", []):
            for k, vfmt in field.items():
                if isinstance(obj, dict):
                    val = obj.get(k)
                else:
                    val = getattr(obj, k, None)
                save(data_parts, val, vfmt, context, endian=endian)
        return
    # if t == "struct":
    #     for field in fmt.get("fields", []):
    #         for k, vfmt in field.items():
    #             save(data_parts, getattr(obj, k, None), vfmt, context, endian=endian)
    #     return
    if t == "list":
        vfmt = fmt["v_format"]
        n = len(obj) if obj is not None else 0
        data_parts.append(i2b(n, length=4, endian=endian))
        for item in (obj or []):
            save(data_parts, item, vfmt, context, endian=endian)
        return
    if t == "map":
        kfmt = fmt["k_format"]
        vfmt = fmt["v_format"]
        n = len(obj) if obj is not None else 0
        data_parts.append(i2b(n, length=4, endian=endian))
        for k, v in (obj or {}).items():
            save(data_parts, k, kfmt, context, endian=endian)
            save(data_parts, v, vfmt, context, endian=endian)
        return
    if t == "array":
        vfmt = fmt["v_format"]
        length = fmt["len"]
        for i in range(length):
            save(data_parts, obj[i], vfmt, context, endian=endian)
        return
    if t == "compat":
        # compat.func returns a format or a callable; call it with context
        res = fmt["func"](context)
        if isinstance(res, dict):
            save(data_parts, obj, res, context, endian=endian)
        return
    # primitive: expect fmt dict to have 'save' callable
    save_fn = fmt.get("save")
    if callable(save_fn):
        # many of our save functions accept (value, data_parts, context, endian)
        try:
            save_fn(obj, data_parts, context, endian)
        except TypeError:
            # fallback for older signature (value, data_parts)
            save_fn(obj, data_parts)
    else:
        # unknown format: no-op
        return

def load(data: bytes, i: int, fmt: Dict, context: Dict = None, endian: str = '>') -> Tuple[Any, int]:
    if context is None:
        context = {}
    if fmt is None:
        return None, i
    t = fmt.get("type")
    if t == "ref":
        id_val, i = read_i(data, i, endian=endian)
        # context must provide mapping for 'of'
        of = fmt.get("of")
        if of is None:
            return id_val, i
        return context.get(of, {}).get(id_val), i
    if t == "konst":
        if fmt.get("is_serialized"):
            return load(data, i, fmt["v_format"], context, endian=endian)
        return fmt["value"], i
    if t == "save":
        obj, i = load(data, i, fmt["v_format"], context, endian=endian)
        context[fmt["name"]] = obj
        return obj, i
    if t == "enable_if":
        if fmt["cond"](context):
            return load(data, i, fmt["v_format"], context, endian=endian)
        return None, i
    # --- robust union branch for load(...) ---
    if t == "union":
        # Start with a neutral accumulator. Use None until first non-None value appears.
        acc = None
        for opt in fmt.get("options", []):
            context['obj'] = acc
            val, i = load(data, i, opt, context, endian=endian)
            if val is None:
                continue
            # If accumulator is None, adopt the first non-None value
            if acc is None:
                # Make a shallow copy for mutable types to avoid aliasing issues
                if isinstance(val, dict):
                    acc = dict(val)
                elif isinstance(val, list):
                    acc = list(val)
                else:
                    acc = val
                continue
            # Both are dicts -> merge keys
            if isinstance(acc, dict) and isinstance(val, dict):
                acc.update(val)
                continue
            # Both are lists -> concatenate
            if isinstance(acc, list) and isinstance(val, list):
                acc.extend(val)
                continue
            # Mixed types: prefer the new non-empty value (replace)
            # If you prefer the first value to win, swap the assignment below.
            acc = val
        return acc, i

    # if t == "union":
    #     # load each option into same object context
    #     obj = {}
    #     for opt in fmt.get("options", []):
    #         context['obj'] = obj
    #         val, i = load(data, i, opt, context, endian=endian)
    #         if val is not None:
    #             # merge or set
    #             if isinstance(val, dict):
    #                 print(obj)
    #                 obj.update(val)
    #             else:
    #                 obj = val
    #     return obj, i
    # --- inside load(...) ---
    if t == "struct":
        obj_out = {}
        for field in fmt.get("fields", []):
            for k, vfmt in field.items():
                val, i = load(data, i, vfmt, context, endian=endian)
                obj_out[k] = val
        return obj_out, i
    # if t == "struct":
    #     obj = {}
    #     for field in fmt.get("fields", []):
    #         for k, vfmt in field.items():
    #             val, i = load(data, i, vfmt, context, endian=endian)
    #             obj[k] = val
    #     return obj, i
    if t == "list":
        vfmt = fmt["v_format"]
        n, i = read_i(data, i, endian=endian)
        arr = []
        for _ in range(n):
            val, i = load(data, i, vfmt, context, endian=endian)
            arr.append(val)
        return arr, i
    if t == "map":
        kfmt = fmt["k_format"]
        vfmt = fmt["v_format"]
        n, i = read_i(data, i, endian=endian)
        mp = {}
        for _ in range(n):
            k, i = load(data, i, kfmt, context, endian=endian)
            if k is not None:
                v, i = load(data, i, vfmt, context, endian=endian)
                mp[k] = v
        return mp, i
    if t == "array":
        vfmt = fmt["v_format"]
        length = fmt["len"]
        arr = []
        for _ in range(length):
            val, i = load(data, i, vfmt, context, endian=endian)
            arr.append(val)
        return arr, i
    if t == "compat":
        res = fmt["func"](context)
        if isinstance(res, dict):
            return load(data, i, res, context, endian=endian)
        return None, i
    # primitive: expect fmt dict to have 'load' callable
    load_fn = fmt.get("load")
    if callable(load_fn):
        try:
            return load_fn(data, i, context, endian)
        except TypeError:
            return load_fn(data, i)
    return None, i

# --- Exports -------------------------------------------------------------------
__all__ = [
    "prec", "prec2", "e",
    "mod1_dec", "mod1_inc", "bind",
    "union_k", "union_i", "validate_bool",
    "get_trace", "pcall",
    "i2b", "b2i", "i642b", "b2i64",
    "d2b", "b2d", "v2b", "b2v",
    "s2b", "read_i", "read_i64", "read_d", "read_v", "read_t", "read_s", "read_a",
    "encode_zeros", "decode_zeros", "encode", "decode",
    "F", "save", "load"
]
