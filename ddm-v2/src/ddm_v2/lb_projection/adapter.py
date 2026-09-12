"""adapter：read_worksheet() dict + vocab → list[ProjectionRow]；load_fixture(path)。

WP2 落地；WP0 為骨架。adapter 只吃 dict，不碰 DB（load_vocab 留在 export_service）。
出處：Spec §1；實作書 WP2。
"""
from __future__ import annotations
