#!/usr/bin/env python3
"""
NISA 全自動 AI アドバイザー
- nisa-holdings.json + snapshot.json + analysis.json から判断
- 各銘柄: SELL_ALL / SELL_HALF / TRIM_HALF / HOLD / WATCH
- 売却で得る資金 → STOCKS_MAIN tier S/A の推奨銘柄へ
- 全シナリオの予想プラス額算出
- data/advisor.json に出力 (15分毎自動更新)
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
JST = timezone(timedelta(hours=9))


def load_json(name):
    try:
        with open(DATA_DIR / name, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[err] {name}: {e}", file=sys.stderr)
        return None


def judge_holding(item, current_price):
    """各銘柄の SELL/HOLD/TRIM 判定"""
    if current_price is None or current_price <= 0:
        return {
            "action": "DATA_NA",
            "label": "❓ データ無し",
            "priority": 99,
            "reason": "価格データ取得不可",
            "color": "gray",
        }

    avg = item["avg_price"]
    pl_per_share = current_price - avg
    pl_pct = (pl_per_share / avg * 100) if avg else 0
    pl_total = pl_per_share * item["shares"]
    cost_total = avg * item["shares"]
    value_total = current_price * item["shares"]
    recovery_to_breakeven = ((avg - current_price) / current_price * 100) if current_price else 0

    if pl_pct <= -35:
        return {
            "action": "SELL_ALL",
            "label": "🚨 即損切り (全株)",
            "priority": 1,
            "reason": f"{pl_pct:+.1f}%。元本回復に+{recovery_to_breakeven:.0f}%必要 (現実的不可能)。塩漬け脱出して資金転換",
            "recover_amt": value_total,
            "color": "red",
            "pl_total": pl_total,
            "pl_pct": pl_pct,
        }
    elif pl_pct <= -20:
        return {
            "action": "SELL_HALF",
            "label": "⚠️ 半分損切り",
            "priority": 2,
            "reason": f"{pl_pct:+.1f}%。リスク半減し残り資金を別銘柄へ",
            "recover_amt": value_total / 2,
            "color": "orange",
            "pl_total": pl_total,
            "pl_pct": pl_pct,
        }
    elif pl_pct >= 30:
        return {
            "action": "TRIM_HALF",
            "label": "💰 半分利確",
            "priority": 3,
            "reason": f"{pl_pct:+.1f}%。NISA非課税利益を半分確定。残りで伸ばす",
            "recover_amt": value_total / 2,
            "color": "green",
            "pl_total": pl_total,
            "pl_pct": pl_pct,
        }
    elif pl_pct >= 15:
        return {
            "action": "HOLD_WATCH",
            "label": "👀 保有・利確待ち",
            "priority": 5,
            "reason": f"{pl_pct:+.1f}%。+30%到達でTRIM",
            "color": "blue",
            "pl_total": pl_total,
            "pl_pct": pl_pct,
        }
    elif pl_pct >= -15:
        return {
            "action": "HOLD",
            "label": "✋ 保有継続",
            "priority": 6,
            "reason": f"{pl_pct:+.1f}%。レンジ内、判断保留",
            "color": "gray",
            "pl_total": pl_total,
            "pl_pct": pl_pct,
        }
    else:
        return {
            "action": "WATCH_DROP",
            "label": "🔻 損切り検討",
            "priority": 4,
            "reason": f"{pl_pct:+.1f}%。-20%到達したら半分損切り",
            "color": "yellow",
            "pl_total": pl_total,
            "pl_pct": pl_pct,
        }


def recommend_buys(analysis):
    """tier S/A銘柄から3ヶ月後中央予想が高い順にtop6"""
    candidates = []
    for code, s in (analysis.get("stocks", {}) or {}).items():
        cat = s.get("category", "")
        tier = s.get("tier", "")
        if cat not in ("STOCKS_MAIN", "STOCKS_UNDER3000") or tier not in ("S", "A"):
            continue
        forecast = s.get("forecast", []) or []
        # 3ヶ月後 (60d) の中央予想 %
        f3m = next((f for f in forecast if f["days"] == 60), None)
        if not f3m:
            continue
        candidates.append({
            "code": code,
            "name": s.get("name", code),
            "tier": tier,
            "category": cat,
            "current": s.get("current"),
            "forecast_3m_mid": f3m["mid"],
            "forecast_3m_pct": f3m["mid_pct"],
            "forecast_3m_high": f3m["high"],
            "forecast_3m_high_pct": f3m["high_pct"],
            "tags": s.get("tags", []),
            "summary": s.get("rationale", {}).get("summary", ""),
        })
    # 中央予想 % 降順
    candidates.sort(key=lambda x: -x["forecast_3m_pct"])
    return candidates[:6]


def calc_health_score(judgments):
    """0-100点 ポートフォリオ健全度"""
    if not judgments:
        return 50
    score = 100
    for j in judgments:
        a = j.get("action")
        if a == "SELL_ALL":
            score -= 20
        elif a == "SELL_HALF":
            score -= 10
        elif a == "WATCH_DROP":
            score -= 5
        elif a == "TRIM_HALF":
            score += 5
    return max(0, min(100, score))


def main():
    holdings = load_json("nisa-holdings.json") or {}
    snapshot = load_json("snapshot.json") or {}
    analysis = load_json("analysis.json") or {}
    stocks_map = snapshot.get("stocks", {})

    judgments = []
    total_cost = 0
    total_value = 0
    total_recovery = 0  # 売却で取り戻せる予想額

    for item in holdings.get("holdings", []):
        cur = stocks_map.get(item["code"], {}).get("p")
        j = judge_holding(item, cur)
        item_full = {
            "code": item["code"],
            "name": item["name"],
            "avg_price": item["avg_price"],
            "shares": item["shares"],
            "current": cur,
            "cost_total": item["avg_price"] * item["shares"],
            "value_total": (cur or 0) * item["shares"],
            **j,
        }
        judgments.append(item_full)
        total_cost += item_full["cost_total"]
        total_value += item_full["value_total"]
        if "recover_amt" in j:
            total_recovery += j["recover_amt"]

    judgments.sort(key=lambda x: x["priority"])

    recommended = recommend_buys(analysis)

    # 推奨資金分配シナリオ
    if total_recovery > 0 and recommended:
        per_stock = total_recovery / min(4, len(recommended))
        allocation = []
        for r in recommended[:4]:
            shares = int(per_stock / r["current"]) if r["current"] else 0
            invest = shares * (r["current"] or 0)
            est_3m = shares * r["forecast_3m_mid"]
            est_3m_high = shares * r["forecast_3m_high"]
            allocation.append({
                **r,
                "buy_shares": shares,
                "invest_amt": invest,
                "estimated_3m_value": est_3m,
                "estimated_3m_value_high": est_3m_high,
                "expected_gain_3m": est_3m - invest,
                "expected_gain_3m_high": est_3m_high - invest,
            })
    else:
        allocation = []

    expected_total_gain_3m = sum(a.get("expected_gain_3m", 0) for a in allocation)
    expected_total_gain_3m_high = sum(a.get("expected_gain_3m_high", 0) for a in allocation)

    out = {
        "generated_at": datetime.now(JST).isoformat(),
        "summary": {
            "total_cost": round(total_cost, 0),
            "total_value": round(total_value, 0),
            "total_pl": round(total_value - total_cost, 0),
            "total_pl_pct": round((total_value - total_cost) / total_cost * 100, 2) if total_cost else 0,
            "health_score": calc_health_score(judgments),
            "total_recovery_if_sell": round(total_recovery, 0),
            "expected_gain_3m": round(expected_total_gain_3m, 0),
            "expected_gain_3m_high": round(expected_total_gain_3m_high, 0),
        },
        "judgments": judgments,
        "recommended_buys": allocation,
        "strategy": (
            "1. 損切り推奨銘柄を全部売却 → 約{:,.0f}円回収. "
            "2. 推奨tier S/A銘柄に分散投資. "
            "3. 3ヶ月後中央予想で約{:+,.0f}円の利益期待. "
            "高値ケースなら最大+{:,.0f}円."
        ).format(total_recovery, expected_total_gain_3m, expected_total_gain_3m_high),
    }

    out_path = DATA_DIR / "advisor.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[done] {out_path} ({out_path.stat().st_size} bytes)")
    print(f"  health: {out['summary']['health_score']}/100")
    print(f"  recovery: {out['summary']['total_recovery_if_sell']:,.0f}円")
    print(f"  expected gain (3m mid): {out['summary']['expected_gain_3m']:+,.0f}円")
    print(f"  expected gain (3m high): {out['summary']['expected_gain_3m_high']:+,.0f}円")


if __name__ == "__main__":
    main()
