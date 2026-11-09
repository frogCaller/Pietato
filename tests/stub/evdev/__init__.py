# A stand-in for python-evdev where it isn't installed (run.py puts this folder on the path then): its key names
# as numbers, and no devices. Enough for the tests, which make their own controllers.
import collections
import zlib


class _E:
    """Each key name a number of its own, the same every run (Python's own hash() isn't: now and then two names
    came out the same, and a controller's A was another button), and far apart (nothing's a neighbour of another)."""
    def __init__(self):
        self._codes, self._taken = {}, set()

    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        if n not in self._codes:
            v = zlib.crc32(n.encode()) % 100000 * 100
            while v in self._taken:
                v += 100
            self._codes[n] = v
            self._taken.add(v)
        return self._codes[n]


ecodes = _E()
InputDevice = UInput = list_devices = None
AbsInfo = collections.namedtuple("AbsInfo", "value min max fuzz flat resolution")
