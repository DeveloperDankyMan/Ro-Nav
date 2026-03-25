import traceback
import threading

# ------------------------------------------------------------
# Dispatch Table (Option 3)
# ------------------------------------------------------------

DISPATCH_TABLE = {}

def register_action(name):
    def wrapper(fn):
        DISPATCH_TABLE[name] = fn
        return fn
    return wrapper

def dispatch(action):
    action_type = action.get("type")
    if action_type not in DISPATCH_TABLE:
        raise RuntimeError(f"No handler for action type '{action_type}'")
    return DISPATCH_TABLE[action_type](action)


# ------------------------------------------------------------
# Control Codes
# ------------------------------------------------------------

class OP:
    NONE = object()
    CONTINUE = object()
    THROW = object()
    REPEAT = object()
    RESUME = object()


# ------------------------------------------------------------
# Promise Implementation
# ------------------------------------------------------------

def get_trace(err):
    return "".join(traceback.format_exception(type(err), err, err.__traceback__))


class Promise:
    def __init__(self, state=None, *callbacks):
        self.state = state or {}
        self._callbacks = list(callbacks)

        self.i = 1
        self.is_running = False
        self.after = OP.NONE
        self.after_args = None

        self.on_error = None
        self.predecessor = None
        self.caller = None
        self.silent = False
        self.msg = None

    # ------------------------------------------------------------
    # Promise chaining
    # ------------------------------------------------------------

    def Then(self, callback):
        self._callbacks.append(callback)
        return self

    def Else(self, callback):
        self.OnError().Then(callback)
        return self

    def OnError(self):
        if self.on_error is None:
            self.on_error = Promise(self.state)
            self.on_error.predecessor = self
        return self.on_error

    def Silent(self):
        self.silent = True
        return self

    # ------------------------------------------------------------
    # Core dispatch loop
    # ------------------------------------------------------------

    def _Dispatch(self, op, args=None, msg=None):
        if msg is not None:
            self.msg = msg

        if self.is_running:
            self.after = op
            self.after_args = args
            return

        if op == OP.RESUME:
            op = self.after
            if self.after_args is not None:
                args = self.after_args

        while op is not OP.NONE:
            self.after = OP.CONTINUE
            self.after_args = None

            if op == OP.THROW:
                if not self.silent and isinstance(self.msg, str):
                    print(self.msg)

                if self.on_error:
                    return self.on_error._Dispatch(OP.CONTINUE, args, self.msg)

            if op == OP.REPEAT:
                index = self.i - 1
            else:
                index = self.i
                self.i = index + 1

            action = self._get_action(index)

            if action is not None:
                if callable(action):
                    self.is_running = True
                    try:
                        value = action(self, args)
                        success = True
                    except Exception as err:
                        success = False
                        value = get_trace(err)
                    finally:
                        self.is_running = False

                    if not success:
                        self.after = OP.THROW
                        self.after_args = args
                        self.msg = value
                    elif isinstance(value, Promise):
                        value.caller = self
                        return value._Dispatch(OP.CONTINUE)

                else:
                    dispatch(action)

            else:
                self.i = 1
                self.after = OP.NONE

                if self.predecessor and self.predecessor.caller:
                    self.predecessor.caller.ThrowAsync(args, self.msg)

                if self.caller:
                    self.caller.ResumeAsync(args)

                return args

            op = self.after
            args = self.after_args

    def _get_action(self, index):
        if 1 <= index <= len(self._callbacks):
            return self._callbacks[index - 1]
        return None

    # ------------------------------------------------------------
    # Control helpers
    # ------------------------------------------------------------

    def _spawn(self, op, args):
        t = threading.Thread(target=self._Dispatch, args=(op, args))
        t.daemon = True
        t.start()
        return t

    def Continue(self, *args):
        return self._Dispatch(OP.CONTINUE, args)

    def ContinueAsync(self, *args):
        return self._spawn(OP.CONTINUE, args)

    def Throw(self, *args):
        return self._Dispatch(OP.THROW, args)

    def ThrowAsync(self, *args):
        return self._spawn(OP.THROW, args)

    def Repeat(self, *args):
        return self._Dispatch(OP.REPEAT, args)

    def RepeatAsync(self, *args):
        return self._spawn(OP.REPEAT, args)

    def Resume(self, *args):
        return self._Dispatch(OP.RESUME, args)

    def ResumeAsync(self, *args):
        return self._spawn(OP.RESUME, args)

    def ReturnAsync(self, *args):
        if self.caller:
            return self.caller.ResumeAsync(*args)

    def EscalateAsync(self, args):
        if self.predecessor and self.predecessor.caller:
            return self.predecessor.caller.ThrowAsync(args, self.msg)

    def Reset(self):
        self.i = 1

    def Stop(self):
        self.after = OP.NONE
        self.Reset()

    def RetryAsync(self, *args):
        if self.predecessor:
            self.predecessor.Reset()
            return self.predecessor.ContinueAsync(*args)

    # ------------------------------------------------------------
    # Lua-like syntactic sugar
    # ------------------------------------------------------------

    def __call__(self, *args):
        return self.Continue(*args)

    def __getattr__(self, key):
        if key in self.state:
            return self.state[key]
        raise AttributeError(key)

    def __setattr__(self, key, value):
        if key in {
            "state", "_callbacks", "i", "is_running", "after", "after_args",
            "on_error", "predecessor", "caller", "silent", "msg"
        } or key.startswith("_"):
            super().__setattr__(key, value)
        else:
            self.state[key] = value


# Factory function
def Promise_ctor(state=None, *callbacks):
    return Promise(state or {}, *callbacks)
