"""PrecedenceProjector：層範圍、chain、傳遞縮減、Kahn 編號（Spec §5）。

WP5 落地；WP0 為骨架。
鐵則（實作書 §6#4）：不得沿用 level.build_output().precedence_edges；層間邊＝ hi_Y < lo_X 偏序的
傳遞縮減，由 Y 的 sink 連 X 的 source。巢狀 cub 區塊位置以成員最小 seq_no 定（Spec §5.3）。
`a/b` 離散跳號拒收（E_LEVEL_DISCRETE_UNSUPPORTED）。
"""
from __future__ import annotations
