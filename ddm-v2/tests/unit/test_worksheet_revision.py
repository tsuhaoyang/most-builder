"""worksheet_revision unit（無 DB）。"""
from __future__ import annotations

from ddm_v2.services.v2.worksheet_revision import content_hash_from_read, sha256_hex


def test_content_hash_stable_order():
    a = {"allowance_percent": 10, "rows": [{"wi_row_id": "b", "seq_no": 2}, {"wi_row_id": "a", "seq_no": 1}]}
    b = {"allowance_percent": 10, "rows": [{"wi_row_id": "b", "seq_no": 2}, {"wi_row_id": "a", "seq_no": 1}]}
    assert content_hash_from_read(a) == content_hash_from_read(b)
    assert len(content_hash_from_read(a)) == 64
    assert content_hash_from_read(a) == sha256_hex(
        __import__("json").dumps(
            {
                "allowance_percent": 10,
                "rows": [
                    {
                        "wi_row_id": "b",
                        "seq_no": 2,
                        "hand": None,
                        "sub_activity": None,
                        "key_parts": None,
                        "object_vocab_id": None,
                        "from_vocab_id": None,
                        "to_vocab_id": None,
                        "tool_vocab_id": None,
                        "frequency": None,
                        "simo_group_id": None,
                        "cycle": None,
                        "level": None,
                    },
                    {
                        "wi_row_id": "a",
                        "seq_no": 1,
                        "hand": None,
                        "sub_activity": None,
                        "key_parts": None,
                        "object_vocab_id": None,
                        "from_vocab_id": None,
                        "to_vocab_id": None,
                        "tool_vocab_id": None,
                        "frequency": None,
                        "simo_group_id": None,
                        "cycle": None,
                        "level": None,
                    },
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
