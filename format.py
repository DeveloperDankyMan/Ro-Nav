# Polaris-Nav format system (Python translation)

class Ref:
    """Lazy reference type container."""
    def __init__(self):
        self._cache = {}

    def __getattr__(self, name):
        if name not in self._cache:
            self._cache[name] = {
                "type": "ref",
                "of": name
            }
        return self._cache[name]


class FormatRegistry:
    def __init__(self):
        self._formats = {}
        self.Ref = Ref()

        # Built‑in primitive formats
        self.ID = {}
        self.V3 = {}
        self.Byte = {}
        self.Double = {}
        self.Int = {}
        self.Int64 = {}
        self.String = {}
        self.Any = {}
        self.Bool = {}

    # ----------------------------------------------------
    # Format constructors
    # ----------------------------------------------------

    def map(self, k_format, v_format):
        return {
            "type": "map",
            "k_format": k_format,
            "v_format": v_format
        }

    def list(self, v_format, key=None):
        return {
            "type": "list",
            "v_format": v_format,
            "key": key
        }

    def array(self, length, v_format, key=None):
        return {
            "type": "array",
            "len": length,
            "v_format": v_format,
            "key": key
        }

    def union(self, *args):
        return {
            "type": "union",
            "options": list(args)
        }

    def struct(self, fields):
        return {
            "type": "struct",
            "fields": fields
        }

    def konst(self, value, v_format=None, is_serialized=False):
        return {
            "type": "konst",
            "value": value,
            "v_format": v_format,
            "is_serialized": is_serialized
        }

    def save(self, name, v_format):
        return {
            "type": "save",
            "name": name,
            "v_format": v_format
        }

    def compat(self, func):
        return {
            "type": "compat",
            "func": func
        }

    def enable_if(self, cond, v_format):
        return {
            "type": "enable_if",
            "cond": cond,
            "v_format": v_format
        }

    # ----------------------------------------------------
    # Registry helpers
    # ----------------------------------------------------

    def format(self, name, t):
        t["name"] = name
        self._formats[name] = t

    def new(self, name, t):
        t["name"] = name
        setattr(self, name, t)

    # Version helper
    def GE_VER(self, ver, on_true, on_false):
        def compat_fn(ctx):
            return on_true if ctx.version >= ver else on_false
        return self.compat(compat_fn)


# --------------------------------------------------------
# Instantiate registry
# --------------------------------------------------------

F = FormatRegistry()

# --------------------------------------------------------
# Define formats (translated from Lua)
# --------------------------------------------------------

F.new("Vector3", F.struct([
    {"x", F.Int},
    {"y": F.Int},
    {"z": F.Int}
]))

F.new("Challenge", F.struct([
    {"signature": F.array(16, F.Byte)},
    {"issued": F.Int64},
    {"difficulty": F.Byte},
    {"K00": F.Int},
    {"K01": F.Int},
    {"K10": F.Int},
    {"K11": F.Int},
]))

F.new("Solution", F.struct([
    {"x": F.Int},
    {"y": F.Int},
]))

# Export
__all__ = ["F"]
