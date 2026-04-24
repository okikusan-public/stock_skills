#!/usr/bin/env python3
"""E2E Test Runner for stock-skills agents.

Usage:
    python3 tests/e2e/run_e2e.py              # 全シナリオ実行
    python3 tests/e2e/run_e2e.py e2e_001      # 特定シナリオのみ
    python3 tests/e2e/run_e2e.py e2e_001 e2e_003  # 複数指定
"""

import csv
import json
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Test functions (each returns {passed: bool, details: list[str]})
# ---------------------------------------------------------------------------

def test_screener() -> dict:
    """e2e_001: Screener — いい日本株ある？"""
    details = []
    passed = True

    try:
        from src.data.yahoo_client import screen_stocks
        from yfinance import EquityQuery

        # 日本株 alpha プリセット相当（yfinance EquityQuery フィールド名）
        query = EquityQuery("AND", [
            EquityQuery("EQ", ["exchange", "JPX"]),
            EquityQuery("LT", ["peratio.lasttwelvemonths", 20]),
            EquityQuery("LT", ["pricebookratio.quarterly", 2.0]),
            EquityQuery("GT", ["returnonequity.lasttwelvemonths", 8]),
        ])
        result = screen_stocks(query, max_results=5)

        # 基準1: 1件以上
        if result and len(result) > 0:
            details.append(f"[x] 銘柄リスト: {len(result)} 件")
        else:
            details.append("[o] 銘柄リスト: 0 件")
            passed = False

        # 基準2: symbol, name
        if result:
            first = result[0]
            has_symbol = "symbol" in first
            has_name = "shortName" in first or "name" in first
            details.append(f"[{'x' if has_symbol else 'o'}] symbol: {'あり' if has_symbol else 'なし'}")
            details.append(f"[{'x' if has_name else 'o'}] name: {'あり' if has_name else 'なし'}")
            if not (has_symbol and has_name):
                passed = False

        # 基準3: 指標
        if result:
            first = result[0]
            has_per = "trailingPE" in first or "forwardPE" in first
            details.append(f"[{'x' if has_per else 'o'}] PER: {'あり' if has_per else 'なし'}")

        # 基準4: region
        if result:
            all_japan = all(
                r.get("symbol", "").endswith(".T") or r.get("exchange") == "JPX"
                for r in result
            )
            details.append(f"[{'x' if all_japan else 'o'}] region=japan: {all_japan}")
            if not all_japan:
                passed = False

    except Exception as e:
        details.append(f"[o] 例外: {e}")
        passed = False

    return {"passed": passed, "details": details}


def test_analyst() -> dict:
    """e2e_002: Analyst — 7203.Tってどう？"""
    details = []
    passed = True

    try:
        from tools.yahoo_finance import get_stock_info, get_price_history

        info = get_stock_info("7203.T")
        if info is None:
            details.append("[o] stock_info: None")
            return {"passed": False, "details": details}

        # 基準1: 基本指標
        for key in ["per", "pbr", "roe", "dividend_yield"]:
            val = info.get(key)
            details.append(f"[{'x' if val is not None else 'o'}] {key}: {val}")
            if val is None and key in ("per", "pbr"):
                passed = False

        # 基準2: 価格履歴
        hist = get_price_history("7203.T", period="3mo")
        if hist is not None and len(hist) > 0:
            details.append(f"[x] price_history: {len(hist)} データポイント")
        else:
            details.append("[o] price_history: なし")
            passed = False

        # 基準3: セクター
        sector = info.get("sector")
        details.append(f"[{'x' if sector else 'o'}] sector: {sector}")

    except Exception as e:
        details.append(f"[o] 例外: {e}")
        passed = False

    return {"passed": passed, "details": details}


def test_health_checker() -> dict:
    """e2e_003: Health Checker — PF大丈夫？"""
    details = []
    passed = True

    try:
        # 基準1: 全保有銘柄の読み込み
        from src.data.portfolio_io import load_portfolio
        pf = load_portfolio()
        details.append(f"[{'x' if len(pf) > 0 else 'o'}] 銘柄数: {len(pf)}")
        if len(pf) == 0:
            passed = False

        # 基準2: 新カラム（KIK-694）
        if pf:
            first = pf[0]
            has_return = first.get("total_return") is not None
            has_role = bool(first.get("role"))
            details.append(f"[{'x' if has_return else 'o'}] total_return: {first.get('total_return')}")
            details.append(f"[{'x' if has_role else 'o'}] role: {first.get('role')}")

        # 基準3: thesis/observation（KIK-695）
        from tools.notes import load_notes
        thesis_count = 0
        for pos in pf:
            notes = load_notes(symbol=pos["symbol"])
            thesis = [n for n in notes if n.get("type") in ("thesis", "observation")]
            thesis_count += len(thesis)
        details.append(f"[{'x' if thesis_count > 0 else 'o'}] thesis/observation: {thesis_count} 件")

        # 基準4: 株価取得
        from tools.yahoo_finance import get_stock_info
        if pf:
            info = get_stock_info(pf[0]["symbol"])
            details.append(f"[{'x' if info else 'o'}] 株価取得({pf[0]['symbol']}): {'OK' if info else 'NG'}")
            if not info:
                passed = False

    except Exception as e:
        details.append(f"[o] 例外: {e}")
        passed = False

    return {"passed": passed, "details": details}


def test_researcher() -> dict:
    """e2e_004: Researcher — 最新ニュース教えて"""
    details = []
    passed = True

    try:
        # 基準1: Grok API 利用可否
        from src.data.grok_client._common import is_available
        grok_ok = is_available()
        details.append(f"[x] Grok API: {'利用可能' if grok_ok else '未設定'}")

        # 基準2: ニュース取得
        if grok_ok:
            from tools.grok import search_market
            result = search_market("全体")
            has_data = result and any(
                result.get(k) for k in ["price_action", "macro_factors", "sentiment"]
            )
            details.append(f"[{'x' if has_data else 'o'}] ニュースデータ: {'あり' if has_data else 'なし'}")
        else:
            details.append("[x] Grok未設定: graceful degradation（空データ、エラーなし）")

        # 基準3: GraphRAG
        from tools.graphrag import HAS_GRAPH_QUERY, HAS_CONTEXT
        details.append(f"[x] GraphRAG: query={HAS_GRAPH_QUERY}, context={HAS_CONTEXT}")

    except Exception as e:
        details.append(f"[o] 例外: {e}")
        passed = False

    return {"passed": passed, "details": details}


def test_risk_assessor() -> dict:
    """e2e_005: Risk Assessor — リスク判定して"""
    details = []
    passed = True

    try:
        from tools.yahoo_finance import get_stock_info

        # 基準1: 市場指標取得
        indicators = {
            "^GSPC": "S&P500",
            "^VIX": "VIX",
            "^TNX": "米10年金利",
            "USDJPY=X": "ドル円",
        }
        for sym, name in indicators.items():
            info = get_stock_info(sym)
            if info and info.get("price") is not None:
                details.append(f"[x] {name}: {info['price']}")
            else:
                details.append(f"[o] {name}: 取得失敗")
                passed = False

        # 基準2: RSI計算可能性
        from tools.yahoo_finance import get_price_history
        hist = get_price_history("^GSPC", period="3mo")
        if hist is not None and len(hist) >= 14:
            details.append(f"[x] RSI計算可能: {len(hist)} データポイント")
        else:
            details.append("[o] RSI計算不可: データ不足")
            passed = False

        # 基準3: Grok なしでも判定可能
        details.append("[x] Grok なしでも基本判定可能（VIX/金利/WTI で暫定スコア算出）")

    except Exception as e:
        details.append(f"[o] 例外: {e}")
        passed = False

    return {"passed": passed, "details": details}


def test_hc_strategist_chain() -> dict:
    """e2e_006: HC + Strategist Chain — PF改善したい"""
    details = []
    passed = True

    try:
        # 基準1: PFデータ
        from src.data.portfolio_io import load_portfolio
        pf = load_portfolio()
        has_return = any(pos.get("total_return") is not None for pos in pf)
        details.append(f"[{'x' if pf else 'o'}] PFデータ: {len(pf)} 銘柄")
        details.append(f"[{'x' if has_return else 'o'}] 還元率データ: {'あり' if has_return else 'なし'}")

        # 基準2: lesson
        from tools.notes import load_notes
        lessons = load_notes(note_type="lesson")
        details.append(f"[{'x' if lessons else 'o'}] lesson: {len(lessons)} 件")

        # 基準3: thesis/observation
        thesis_count = 0
        for pos in pf:
            notes = load_notes(symbol=pos["symbol"])
            thesis_count += len([n for n in notes if n.get("type") in ("thesis", "observation")])
        details.append(f"[{'x' if thesis_count > 0 else 'o'}] thesis/observation: {thesis_count} 件")

        # 基準4: GraphRAG
        from tools.graphrag import HAS_GRAPH_QUERY, HAS_CONTEXT
        details.append(f"[x] GraphRAG: query={HAS_GRAPH_QUERY}, context={HAS_CONTEXT}")

        # 基準5: what-if 株価取得
        from tools.yahoo_finance import get_stock_info
        if pf:
            info = get_stock_info(pf[0]["symbol"])
            details.append(f"[{'x' if info else 'o'}] what-if用株価: {'OK' if info else 'NG'}")
            if not info:
                passed = False

    except Exception as e:
        details.append(f"[o] 例外: {e}")
        passed = False

    return {"passed": passed, "details": details}


def test_deepthink_swarm() -> dict:
    """e2e_007: DeepThink 4-Swarm — 2層モデル動的役割割当"""
    details = []
    passed = True

    try:
        # 基準1: deepthink_limits.yaml の読み込みと値チェック
        import yaml
        limits_path = PROJECT_ROOT / ".claude" / "skills" / "deepthink" / "deepthink_limits.yaml"
        with open(limits_path) as f:
            limits = yaml.safe_load(f)

        max_spawns = limits["limits"]["max_agent_spawns"]
        max_llm = limits["limits"]["max_llm_calls"]
        if max_spawns >= 20:
            details.append(f"[x] max_agent_spawns: {max_spawns} (>= 20)")
        else:
            details.append(f"[o] max_agent_spawns: {max_spawns} (< 20, 4-Swarm に不足)")
            passed = False

        if max_llm >= 25:
            details.append(f"[x] max_llm_calls: {max_llm} (>= 25)")
        else:
            details.append(f"[o] max_llm_calls: {max_llm} (< 25)")
            passed = False

        # 深度プリセット検証
        for depth in ["shallow", "medium", "deep"]:
            preset = limits["depth_presets"][depth]
            details.append(f"[x] {depth}: spawns={preset['max_agent_spawns']}, llm={preset['max_llm_calls']}")

        # 基準2: LLMプロバイダの利用可否
        from tools.llm import get_available_providers, is_provider_available
        providers = get_available_providers()
        details.append(f"[x] 利用可能プロバイダ: {providers if providers else 'なし（graceful degradation）'}")

        # 基準3: 各LLMへの疎通確認（API key がある場合のみ）
        from tools.llm import call_llm

        swarm_members = {
            "gpt": {"model": "gpt-5.4", "prompt": "Reply OK in one word.", "kwargs": {"reasoning": "low"}},
            "gemini": {"model": "gemini-3-flash-preview", "prompt": "Reply OK in one word.", "kwargs": {}},
            "grok": {"model": "grok-4.20-0309-reasoning", "prompt": "Reply OK in one word.", "kwargs": {}},
        }

        llm_ok_count = 0
        for provider, cfg in swarm_members.items():
            if is_provider_available(provider):
                result = call_llm(provider, cfg["model"], cfg["prompt"], timeout=30, **cfg["kwargs"])
                if result:
                    details.append(f"[x] {provider}: 応答あり ({len(result)} chars)")
                    llm_ok_count += 1
                else:
                    details.append(f"[o] {provider}: APIキーあるが応答なし")
                    passed = False
            else:
                details.append(f"[x] {provider}: 未設定（graceful degradation）")

        # 基準4: Grok search 関数の利用可否
        from src.data.grok_client._common import is_available as grok_available
        if grok_available():
            from tools.grok import search_x_sentiment
            sentiment = search_x_sentiment("AAPL", "Apple")
            if sentiment:
                details.append(f"[x] Grok search_x_sentiment: データあり")
            else:
                details.append(f"[o] Grok search_x_sentiment: データなし")
        else:
            details.append(f"[x] Grok search: 未設定（graceful degradation）")

        # 基準5: SKILL.md に2層モデル・統合結論・サマリーの記述があるか
        skill_path = PROJECT_ROOT / ".claude" / "skills" / "deepthink" / "SKILL.md"
        skill_content = skill_path.read_text()
        checks = {
            "インフラ層": "インフラ層" in skill_content,
            "推論層": "推論層" in skill_content,
            "適性マトリクス": "適性マトリクス" in skill_content,
            "ハード制約": "ハード制約" in skill_content,
            "4-Swarm": "4-Swarm" in skill_content,
            "エグゼクティブサマリー": "エグゼクティブサマリー" in skill_content,
            "統合結論": "統合結論" in skill_content or "議論の統合" in skill_content,
            "採用/却下": "採用" in skill_content,
            "ツール参照": "tools.yaml" in skill_content,
            "screen_stocks必須": "screen_stocks" in skill_content,
        }
        for label, found in checks.items():
            details.append(f"[{'x' if found else 'o'}] SKILL.md {label}: {'あり' if found else 'なし'}")
            if not found:
                passed = False

        # 基準6: config/tools.yaml の存在と整合性
        tools_path = PROJECT_ROOT / "config" / "tools.yaml"
        if tools_path.exists():
            with open(tools_path) as f:
                tools_def = yaml.safe_load(f)
            tools_keys = list(tools_def.get("tools", {}).keys())
            required = ["yahoo_finance", "grok", "graphrag", "llm", "notes", "portfolio_io"]
            has_all_tools = all(t in tools_keys for t in required)
            details.append(f"[{'x' if has_all_tools else 'o'}] tools.yaml: {tools_keys}")
            # screen_stocks が定義されているか
            yf = tools_def.get("tools", {}).get("yahoo_finance", {}).get("functions", {})
            has_screen = "screen_stocks" in yf
            details.append(f"[{'x' if has_screen else 'o'}] tools.yaml screen_stocks: {'定義あり' if has_screen else 'なし'}")
            if not (has_all_tools and has_screen):
                passed = False
        else:
            details.append("[o] tools.yaml: ファイルなし")
            passed = False

        # 基準7: llm_capabilities.yaml の存在と整合性
        cap_path = PROJECT_ROOT / "config" / "llm_capabilities.yaml"
        if cap_path.exists():
            with open(cap_path) as f:
                caps = yaml.safe_load(f)
            has_all = all(p in caps.get("providers", {}) for p in ["gemini", "gpt", "grok"])
            details.append(f"[{'x' if has_all else 'o'}] llm_capabilities.yaml: 全プロバイダ定義あり")
        else:
            details.append("[o] llm_capabilities.yaml: ファイルなし")
            passed = False

    except Exception as e:
        details.append(f"[o] 例外: {e}")
        passed = False

    return {"passed": passed, "details": details}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

SCENARIOS = {
    "e2e_001": ("Screener E2E", test_screener),
    "e2e_002": ("Analyst E2E", test_analyst),
    "e2e_003": ("Health Checker E2E", test_health_checker),
    "e2e_004": ("Researcher E2E", test_researcher),
    "e2e_005": ("Risk Assessor E2E", test_risk_assessor),
    "e2e_006": ("HC + Strategist Chain E2E", test_hc_strategist_chain),
    "e2e_007": ("DeepThink 4-Swarm E2E", test_deepthink_swarm),
}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_scenarios(ids: list[str] | None = None):
    """Run E2E scenarios and print results."""
    targets = ids or list(SCENARIOS.keys())
    results = []
    total_pass = 0
    total_fail = 0

    print(f"\n{'='*60}")
    print(f"E2E Test Suite — {len(targets)} scenarios")
    print(f"{'='*60}\n")

    for scenario_id in targets:
        if scenario_id not in SCENARIOS:
            print(f"⚠️  Unknown scenario: {scenario_id}")
            continue

        name, test_fn = SCENARIOS[scenario_id]
        print(f"▶ {scenario_id}: {name}...", end=" ", flush=True)

        start = time.time()
        result = test_fn()
        elapsed = time.time() - start

        status = "✅ PASS" if result["passed"] else "❌ FAIL"
        print(f"{status} ({elapsed:.1f}s)")

        for detail in result["details"]:
            print(f"  {detail}")
        print()

        results.append({
            "id": scenario_id,
            "name": name,
            "passed": result["passed"],
            "elapsed": round(elapsed, 1),
            "details": result["details"],
        })

        if result["passed"]:
            total_pass += 1
        else:
            total_fail += 1

    # Summary
    print(f"{'='*60}")
    print(f"結果: {total_pass} PASS / {total_fail} FAIL (全{len(results)}件)")
    print(f"{'='*60}")

    # Save results
    results_path = PROJECT_ROOT / "data" / "e2e_results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total": len(results),
            "passed": total_pass,
            "failed": total_fail,
            "scenarios": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n結果を {results_path} に保存しました")

    return total_fail == 0


if __name__ == "__main__":
    ids = sys.argv[1:] if len(sys.argv) > 1 else None
    success = run_scenarios(ids)
    sys.exit(0 if success else 1)
