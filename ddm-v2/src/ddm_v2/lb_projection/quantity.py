"""QuantityProjector：兩個乘數的投影矩陣（Spec §3.2，唯一權威）。

WP6 落地；WP0 為骨架。
frequency＝整 motion 乘數（非持工具→Q=F cyclic）；repeat_count＝持工具 use 段 cyclic 乘數
（use 列 Q=N cyclic、acquire/release 為 setup）。持工具×兩乘數多為拒絕碼（§3.2 矩陣）。
"""
from __future__ import annotations
