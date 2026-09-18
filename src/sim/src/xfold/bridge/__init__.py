"""HTTP bridge: append-only journal + REST commands + SSE live feed.

Keep schemas in sync with ``@xfold/protocol`` (see docs/BRIDGE.md).
"""

from __future__ import annotations

__all__ = ["create_app", "main"]

from xfold.bridge.app import create_app, main
