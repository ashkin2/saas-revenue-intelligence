"""
ai_insights.py
---------------
LLM-powered analytics layer: turns the SQL KPI output + churn-model results into an executive
narrative and a prioritised retention/growth action plan, with a guardrail against invented numbers.

Pipeline
  1. build_context()     - pulls ONLY verified figures (SQL + model output) into ai/kpi_context.json
  2. generate()          - sends that context to an LLM (Anthropic API) with a strict JSON schema prompt
                           -> ai/ai_insights.json
  3. verify_grounding()  - every number the model cites must be traceable to the context
                           (relative tolerance 1.5%); unsupported figures are flagged, not silently shown

Usage
  python ai/ai_insights.py context      # (re)build ai/kpi_context.json
  python ai/ai_insights.py generate     # call the API (needs ANTHROPIC_API_KEY, `pip install anthropic`)
  python ai/ai_insights.py verify       # run the grounding check on ai/ai_insights.json
"""

import json
import os
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd

DB = "data/saas.db"
CTX_PATH = Path("ai/kpi_context.json")
OUT_PATH = Path("ai/ai_insights.json")
MODEL_RESULTS = Path("python/outputs/model_results.json")
MODEL_ID = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

SYSTEM_PROMPT = """You are a senior SaaS revenue analyst writing for the CFO and CRO.
Use ONLY the figures in the JSON context provided. Never estimate, extrapolate or invent a number.
If you derive a figure (e.g. a difference), show it only if both inputs are in the context.
Be specific, prioritise by revenue impact, and be candid about uncertainty and model limits.
Return a single JSON object, no prose outside JSON, with exactly these keys:
  executive_summary: string (3-4 sentences),
  key_risks: [{title, evidence, so_what}]            (max 3),
  opportunities: [{title, evidence, so_what}]        (max 3),
  recommended_actions: [{priority (1-5), action, owner, success_metric, rationale}]  (max 5),
  caveats: [string]                                  (max 3)"""


def _q(conn, sql):
    return pd.read_sql_query(sql, conn)


def build_context() -> dict:
    conn = sqlite3.connect(DB)
    sql = open("sql/kpi_queries.sql").read()
    stmts = [s.strip() for s in sql.split(";") if "SELECT" in s]
    mrr = _q(conn, stmts[0])
    ret = _q(conn, stmts[1])
    ue = _q(conn, stmts[2])
    seg = _q(conn, stmts[5])
    conc = _q(conn, stmts[6])
    conn.close()

    last, prev = mrr.iloc[-1], mrr.iloc[-2]
    last_r = ret.iloc[-1]
    ttm = mrr.tail(12)
    res = json.load(open(MODEL_RESULTS))
    champ = next(m for m in res["metrics"] if m["selected"])
    hi = next(r for r in res["risk_summary"] if r["risk_tier"] == "High")
    med = next(r for r in res["risk_summary"] if r["risk_tier"] == "Medium")
    low = next(r for r in res["risk_summary"] if r["risk_tier"] == "Low")
    top3_share = float(conc.head(3)["pct_of_mrr"].sum())

    ctx = {
        "as_of_month": last["month"],
        "headline": {
            "ending_mrr": int(last["ending_mrr"]), "arr": int(last["arr"]),
            "mrr_growth_pct_mom": float(last["mrr_growth_pct"]),
            "mrr_prev_month": int(prev["ending_mrr"]),
            "active_customers": int(last["active_customers"]),
            "new_customers_month": int(last["new_customers"]),
            "churned_customers_month": int(last["churned_customers"]),
            "nrr_pct_month": float(last_r["nrr_pct"]), "grr_pct_month": float(last_r["grr_pct"]),
            "logo_churn_pct_month": float(last_r["logo_churn_pct"]),
            "revenue_churn_pct_month": float(last_r["revenue_churn_pct"]),
            "avg_nrr_pct_ttm": round(float(ret.tail(12)["nrr_pct"].mean()), 1),
            "avg_logo_churn_pct_ttm": round(float(ret.tail(12)["logo_churn_pct"].mean()), 1),
            "ttm_new_mrr": int(ttm["new_mrr"].sum()), "ttm_expansion_mrr": int(ttm["expansion_mrr"].sum()),
            "ttm_contraction_mrr": int(ttm["contraction_mrr"].sum()), "ttm_churned_mrr": int(ttm["churned_mrr"].sum()),
        },
        "unit_economics_by_channel": ue.to_dict("records"),
        "plan_region_top_segments": seg.head(5).to_dict("records"),
        "mrr_concentration_top3_deciles_pct": round(top3_share, 1),
        "churn_model": {
            "selected_model": res["selected_model"], "horizon_months": res["horizon_months"],
            "test_roc_auc": champ["roc_auc"], "top_decile_lift": champ["lift_at_top10pct"],
            "top_decile_precision": champ["precision_at_top10pct"], "baseline_3m_churn_rate": champ["baseline_churn_rate"],
            "high_risk_customers": hi["customers"], "high_risk_mrr": hi["mrr"],
            "medium_risk_customers": med["customers"], "medium_risk_mrr": med["mrr"],
            "low_risk_customers": low["customers"], "low_risk_mrr": low["mrr"],
            "expected_3m_mrr_loss_high_tier": hi["expected_loss"],
            "expected_3m_mrr_loss_medium_tier": med["expected_loss"],
            "expected_3m_mrr_loss_low_tier": low["expected_loss"],
            "expected_3m_mrr_loss_total": res["total_expected_mrr_loss_3m"],
            "top_drivers": [d["feature"] for d in res["feature_importance"][:3]],
        },
        "forecast": {"method": res["forecast"]["method"],
                     "implied_monthly_growth_pct": res["forecast"]["implied_monthly_growth_pct"],
                     "mrr_6m_out": res["forecast"]["forecast"][-1]["mrr"],
                     "mrr_6m_low": res["forecast"]["forecast"][-1]["low"],
                     "mrr_6m_high": res["forecast"]["forecast"][-1]["high"],
                     "backtest_6m_mape_pct": res["forecast"]["backtest"][-1]["mape_pct"],
                     "backtest_origins": res["forecast"]["backtest_origins"]},
        "data_note": "Synthetic dataset (1,800 customers, 24 months).",
    }
    CTX_PATH.write_text(json.dumps(ctx, indent=2, default=float))
    print(f"[context] wrote {CTX_PATH}")
    return ctx


def generate():
    try:
        import anthropic
    except ImportError:
        sys.exit("pip install anthropic  (and set ANTHROPIC_API_KEY) to call the API")
    ctx = json.loads(CTX_PATH.read_text())
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=MODEL_ID, max_tokens=2000, system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": "Context JSON:\n" + json.dumps(ctx, indent=2)}],
    )
    text = msg.content[0].text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    out = json.loads(text)
    out["_meta"] = {"generated_by": f"{MODEL_ID} via Anthropic API", "context_file": str(CTX_PATH)}
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"[generate] wrote {OUT_PATH}")
    verify()


# ----------------------------------------------------------------- grounding guardrail
NUM_RE = re.compile(r"\$?\d[\d,]*\.?\d*(?:[kKmM](?![A-Za-z]))?%?")  # suffix must be adjacent, not start a word


def _flatten_numbers(obj, acc):
    if isinstance(obj, dict):
        for v in obj.values():
            _flatten_numbers(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _flatten_numbers(v, acc)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        acc.add(float(obj))
    return acc


def _parse(tok):
    """Return (value, kind) where kind in {'pct','usd_k','usd_m','num'}."""
    t = tok.strip().lower().replace("$", "").replace(",", "")
    kind = "num"
    if t.endswith("%"):
        kind, t = "pct", t[:-1]
    elif t.endswith("k"):
        kind, t = "usd_k", t[:-1]
    elif t.endswith("m"):
        kind, t = "usd_m", t[:-1]
    try:
        return float(t), kind
    except ValueError:
        return None, None


def _supported(x, kind, ctx_nums, tol=0.015):
    """A cited figure must match a context figure under ONE unit rule determined by its own notation:
       '37%'   -> a context value as-is OR as a ratio (x100)      e.g. 0.283 -> 28.3%
       '$12k'  -> context value / 1,000;  '$1.2M' -> / 1,000,000
       others  -> context value as-is (no rescaling, so a made-up dollar amount cannot match by luck)."""
    if kind == "pct":
        cands = [c for n in ctx_nums for c in (n, n * 100)]
    elif kind == "usd_k":
        cands = [n / 1e3 for n in ctx_nums]
    elif kind == "usd_m":
        cands = [n / 1e6 for n in ctx_nums]
    else:
        cands = list(ctx_nums)
    return any(abs(x - v) <= tol * abs(v) + 0.051 for v in cands)


def verify_grounding(insights: dict, ctx: dict) -> dict:
    ctx_nums = _flatten_numbers(ctx, set())
    # months/years in text such as "6-month" or "3 months" are structural constants
    structural = {1, 2, 3, 4, 5, 6, 12, 24, 10, 90, 2024, 2025, 2026}
    text_fields = []
    for k, v in insights.items():
        if k.startswith("_"):
            continue
        text_fields.append(json.dumps(v))
    corpus = " ".join(text_fields)
    unsupported, checked = [], 0
    for tok in NUM_RE.findall(corpus):
        x, kind = _parse(tok)
        if x is None or (kind == "num" and x in structural):
            continue
        checked += 1
        if not _supported(x, kind, ctx_nums):
            unsupported.append(tok.strip())
    return {"numbers_checked": checked, "unsupported": sorted(set(unsupported)),
            "passed": len(set(unsupported)) == 0}


def verify():
    ctx = json.loads(CTX_PATH.read_text())
    ins = json.loads(OUT_PATH.read_text())
    rep = verify_grounding(ins, ctx)
    ins["_meta"]["grounding_check"] = rep
    OUT_PATH.write_text(json.dumps(ins, indent=2))
    print("[verify]", json.dumps(rep))
    return rep


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "context"
    {"context": build_context, "generate": generate, "verify": verify}[cmd]()
