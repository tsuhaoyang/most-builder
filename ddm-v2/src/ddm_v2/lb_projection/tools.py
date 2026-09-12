"""ToolLifecycleResolver：chain 內工具事件與 held 狀態機（Spec §4）。

WP4 落地；WP0 為骨架。判準唯一訊號＝ vocab kind='tool'（不猜敘事，實作書 §6#2）。
Pattern A（object=tool 的取/用/放）與 Pattern B（tool_vocab 隱含取得，拆 3 或 2 列，§4.3）。
"""
from __future__ import annotations
