"""mappers：group / atomic / offline / station / general / action_type / duration_ms。

WP6 落地；WP0 為骨架。
duration_ms：Decimal(str(tmu)) * 36 以 ROUND_HALF_UP 取整（Spec §6 duration）。
action_type：Spec 附錄 A。role_type：x_seconds≥1 → machine（Spec §6、D17）。
"""
from __future__ import annotations
