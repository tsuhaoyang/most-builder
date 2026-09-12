"""TmuDecomposer：單次工時分解（Spec §3.3）。

WP3 落地；WP0 為骨架。
鐵則（實作書 §6#1）：投影層不做 TMU 加減乘除以外的推導；單次工時由引擎 compute_cycle 重算
或 fixture 靜態值；斷言 acquire + N×use_once + release == total_tmu（|Δ|≤1e-6）否則 E_TMU_DECOMPOSITION。
"""
from __future__ import annotations
