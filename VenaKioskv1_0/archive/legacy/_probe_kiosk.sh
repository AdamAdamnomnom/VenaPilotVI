#!/bin/bash
DISPLAY=:0 python3 <<'PY'
from Xlib import display
from Xlib.ext import xfixes
import inspect
d = display.Display()
r = d.screen().root
print("sig", getattr(xfixes.hide_cursor, "__doc__", None), inspect.signature(xfixes.hide_cursor) if hasattr(inspect, "signature") else "")
for call in [
    lambda: xfixes.hide_cursor(r),
    lambda: xfixes.hide_cursor(d, r),
    lambda: getattr(r, "xfixes_hide_cursor", lambda: None)(),
    lambda: getattr(d, "xfixes_hide_cursor", lambda *a: None)(r),
]:
    try:
        call()
        d.sync()
        print("OK", call)
        break
    except Exception as e:
        print("fail", e)
PY
