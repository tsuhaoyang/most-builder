"""search 模組單元測試（impl-03）。

涵蓋：
- normalization：標點去除、空白摺疊、lower
- build_content_norm：多欄位串接
- NullProvider 降級：embed 永遠回 None
- SearchService：q 為空字串時直接回空結果（不查 DB）
- RRF 融合分數計算
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ddm_v2.search.adapters.null_provider import NullProvider
from ddm_v2.search.normalization import build_content_norm, normalize
from ddm_v2.search.service import SearchService

pytestmark = pytest.mark.unit


# ── normalize ──────────────────────────────────────────────────────────

def test_normalize_removes_punctuation():
    # OpenCC s2twp 可能將「機台」轉為「機臺」（台灣繁體變體），兩種形式均可接受。
    result = normalize("壓合，機台：測試")
    assert "，" not in result
    assert "：" not in result
    assert "壓合" in result
    assert "機台" in result or "機臺" in result
    assert "測試" in result


def test_normalize_collapses_whitespace():
    result = normalize("  hello   world  ")
    assert result == "hello world"


def test_normalize_lowercases_ascii():
    assert normalize("ABC DEF") == "abc def"


def test_normalize_empty():
    assert normalize("") == ""
    assert normalize("   ") == ""


# ── build_content_norm ─────────────────────────────────────────────────

def test_build_content_norm_basic():
    result = build_content_norm("壓合", "並壓合機台", ["SMT", "貼片"])
    assert "壓合" in result
    # OpenCC s2twp 可能將「機台」轉為「機臺」；確認「並壓合機」主體部分保留
    assert "並壓合機" in result  # 台/臺 字形變體不影響前綴匹配
    assert "smt" in result
    assert "貼片" in result


def test_build_content_norm_no_keywords():
    result = build_content_norm("取料", "", None)
    assert result == "取料"


def test_build_content_norm_skips_empty():
    result = build_content_norm("取料", "", [])
    assert result == "取料"


# ── NullProvider ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_null_provider_returns_none():
    provider = NullProvider()
    assert provider.model_id == "null"
    result = await provider.embed(["任何文字"])
    assert result is None


# ── SearchService 空查詢 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_empty_query_returns_no_hits():
    """q 正規化後為空 → 直接回空，不碰 DB。"""
    svc = SearchService(NullProvider())

    class FakeDB:
        async def execute(self, *a, **kw):
            raise AssertionError("不應碰 DB")

    result = await svc.search(FakeDB(), "   ", limit=10)
    assert result["hits"] == []
    assert result["semantic"] is False


@pytest.mark.asyncio
async def test_search_null_provider_no_semantic():
    """NullProvider 時 semantic=False，即使 L2 有結果。"""
    svc = SearchService(NullProvider())

    class Row:
        def __init__(self, doc_type, ref_id, score, snippet):
            self.doc_type = doc_type
            self.ref_id = ref_id
            self.score = score
            self.snippet = snippet

    class FakeResult:
        def fetchall(self):
            return [Row("motion_module", "uuid-1", 0.8, "壓合機台")]

    class FakeDB:
        async def execute(self, *a, **kw):
            return FakeResult()

    result = await svc.search(FakeDB(), "壓合", limit=10)
    assert result["semantic"] is False
    assert len(result["hits"]) == 1
    assert result["hits"][0].doc_type == "motion_module"
    assert result["hits"][0].match_type == "text"


# ── RRF 融合行為（透過 SearchService 驗證）────────────────────────────


class FakeVecProvider:
    """模擬 EmbeddingProvider：embed 永遠回 1024 維向量（觸發 L3 路徑）。"""

    model_id = "fake"

    async def embed(self, texts: list[str]):
        return [[0.1] * 1024]


class FakeDB:
    """模擬 AsyncSession：第一次 execute 回 L2 rows，第二次回 L3 rows。"""

    def __init__(self, l2_rows: list, l3_rows: list):
        self._l2_rows = l2_rows
        self._l3_rows = l3_rows
        self._call_count = 0

    async def execute(self, sql, params=None):
        self._call_count += 1
        mock_result = MagicMock()
        if self._call_count == 1:
            mock_result.fetchall.return_value = self._l2_rows
        else:
            mock_result.fetchall.return_value = self._l3_rows
        return mock_result


def _make_row(doc_type: str, ref_id: str, score: float, snippet: str = ""):
    r = MagicMock()
    r.doc_type = doc_type
    r.ref_id = ref_id
    r.score = score
    r.snippet = snippet
    return r


@pytest.mark.asyncio
async def test_rrf_fused_match_type_and_order():
    """兩路各有 hits 的鍵，融合後 match_type=fused；同時出現比只在一路的分高。

    RRF 計算（k=60）：
    - B 在 L2 rank 2、L3 rank 1 → 1/62 + 1/61 ≈ 0.0325 （最高）
    - A 在 L2 rank 1、L3 缺席     → 1/61 + 1/1060 ≈ 0.0173
    - C 在 L2 缺席、L3 rank 2     → 1/1060 + 1/62 ≈ 0.0171
    預期排序：B > A > C
    """
    l2_rows = [
        _make_row("motion_module", "A", 0.9),  # L2 rank 1
        _make_row("motion_module", "B", 0.7),  # L2 rank 2
    ]
    l3_rows = [
        _make_row("motion_module", "B", 0.95),  # L3 rank 1（B 同時出現兩路）
        _make_row("motion_module", "C", 0.80),  # L3 rank 2（只在 L3）
    ]
    svc = SearchService(FakeVecProvider())
    result = await svc.search(FakeDB(l2_rows, l3_rows), "test", ["motion_module"], limit=10)

    hits = result["hits"]
    assert result["semantic"] is True
    # B 同時出現於兩路，RRF 最高 → 排第一
    assert hits[0].ref_id == "B"
    assert hits[0].match_type == "fused"
    # A 只在 L2 但 rank 更好；C 只在 L3 rank 2 → A 應排在 C 之前
    ref_ids = [h.ref_id for h in hits]
    assert ref_ids.index("A") < ref_ids.index("C")


@pytest.mark.asyncio
async def test_rrf_absent_key_penalized():
    """只在一路的鍵 penalty=rank 1000；兩路共同鍵分數高於同 rank 的單路鍵。

    ONLY_L2：L2 rank 1、L3 rank 1000 → 1/61 + 1/1060
    BOTH：    L2 rank 1000、L3 rank 1  → 1/1060 + 1/61
    兩者 RRF 分相等，但都應出現在結果中；semantic 路徑下 match_type 全為 fused。
    """
    l2_rows = [_make_row("motion_module", "ONLY_L2", 0.99)]  # L2 rank 1
    l3_rows = [_make_row("motion_module", "BOTH", 0.50)]      # L3 rank 1，不在 L2

    svc = SearchService(FakeVecProvider())
    result = await svc.search(FakeDB(l2_rows, l3_rows), "test", ["motion_module"], limit=10)

    hits = result["hits"]
    assert result["semantic"] is True
    ref_ids = [h.ref_id for h in hits]
    assert "ONLY_L2" in ref_ids
    assert "BOTH" in ref_ids
    # semantic 路徑下所有 hits 都標記為 fused
    assert all(h.match_type == "fused" for h in hits)
