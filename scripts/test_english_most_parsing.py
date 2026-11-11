"""端到端測試：英文語句 → LLM planner → MOST sequence 參數對應驗證。

重點：檢查可解析的語句有沒有正確對應到對的 MOST sequence 參數。
"""
import asyncio

from ddm_v2.nlp.llm_client import OpenAICompatClient
from ddm_v2.nlp.llm_planner import LLMPlannerAdapter
from ddm_v2.nlp.contracts import ParseContext

# MOST action_type → sequence + 核心參數對應 (from most_compiler/policies.py)
SEQ_BY_ACTION = {
    "acquire": "GM",
    "move_place": "GM",
    "release_return": "GM",
    "controlled_move": "CM",
    "process": "CM",
    "inspect": "CM",
}
CORE_PARAM_BY_ACTION = {
    "acquire": "G",         # Get control
    "move_place": "P",      # Place
    "controlled_move": "M", # Move controlled
    "process": "X",         # Process time
    "inspect": "I",         # Inspect
    "release_return": "P",
}


async def parse_one(planner, ctx, text, expected_type=None, expected_roles=None):
    print(f"\n{'='*70}")
    print(f"輸入: {text}")
    if expected_type:
        print(f"預期 action_type: {expected_type}")
    try:
        output, raw = await planner.plan(text, ctx)
        print(f"檢測語言: {output.language}")
        print(f"動作數量: {len(output.actions)}")
        for i, a in enumerate(output.actions, 1):
            seq = SEQ_BY_ACTION.get(a.action_type, "?")
            core = CORE_PARAM_BY_ACTION.get(a.action_type, "?")
            print(f"  [{i}] action_type: {a.action_type}  → MOST seq: {seq}, 核心參數: {core}")
            for k, v in a.roles.items():
                print(f"      role[{k}] = \"{v.text}\"")
            # 依賴關係
        if output.dependencies:
            for d in output.dependencies:
                print(f"  dependency: {d.from_action} → {d.to_action} ({d.type})")
        if output.unresolved:
            print(f"  unresolved: {output.unresolved}")

        # 驗證
        if expected_type and output.actions:
            got = output.actions[0].action_type
            mark = "✅" if got == expected_type else "❌"
            print(f"  {mark} action_type 驗證: 預期={expected_type}, 實際={got}")
        return output
    except Exception as e:
        print(f"  ❌ 解析失敗: {type(e).__name__}: {e}")
        return None


async def main():
    client = OpenAICompatClient(
        base_url="http://127.0.0.1:11434",
        model="qwen2.5:14b",
        api_key=None,
        response_format_mode="json_object",
    )
    planner = LLMPlannerAdapter(client, timeout_s=120.0)
    ctx = ParseContext(rule_set_code="default", available_tools=[], available_locations=[])

    # 測試案例：涵蓋各種 action_type
    test_cases = [
        # (輸入, 預期 action_type)
        ("Pick up the screw", "acquire"),
        ("Take the circuit board and place it on the test fixture", "move_place"),
        ("Push the connector into the socket", "controlled_move"),
        ("Fasten the screw with an electric screwdriver", "process"),
        ("Inspect the solder joints", "inspect"),
        ("Left hand grasps a screw from the parts box", "acquire"),
    ]

    print("="*70)
    print("英文語句 → MOST sequence 參數對應測試")
    print("模型: qwen2.5:14b (本地 Ollama)")
    print("="*70)

    results = []
    for text, expected in test_cases:
        out = await parse_one(planner, ctx, text, expected_type=expected)
        results.append((text, expected, out))

    # 總結
    print(f"\n{'='*70}")
    print("測試總結")
    print("="*70)
    correct = 0
    for text, expected, out in results:
        if out and out.actions:
            got = out.actions[0].action_type
            ok = got == expected
            correct += ok
            print(f"{'✅' if ok else '❌'} \"{text[:45]}\" → {got} (預期 {expected})")
        else:
            print(f"❌ \"{text[:45]}\" → 解析失敗")
    print(f"\n正確率: {correct}/{len(test_cases)} ({correct*100//len(test_cases)}%)")


if __name__ == "__main__":
    asyncio.run(main())
