"""project：編排 adapter → level.validate gate → tools → quantity → precedence → validator → emit → report。

WP6 落地；WP0 為骨架。資料流不可重排（實作書 §1）。
公開：project_rows(rows, vocab, rs=None)、project_worksheet(session, ws_id)（後者在 export_service 組裝）。
"""
from __future__ import annotations
