"""
build_dashboard_data.py
------------------------
Single export that feeds the HTML dashboard: SQL KPI layer + ML model results + LLM insights
(with its grounding-check report) -> dashboard/dashboard_data.json

Run: python dashboard/build_dashboard_data.py
"""

import json
import sqlite3

import pandas as pd

conn = sqlite3.connect("data/saas.db")
stmts = [s.strip() for s in open("sql/kpi_queries.sql").read().split(";") if "SELECT" in s]
q = lambda sql: pd.read_sql_query(sql, conn)

mrr = q(stmts[0])
ret = q(stmts[1])
ue = q(stmts[2])
coh = q(stmts[3])
seg = q(stmts[5])
plan_mix = q("""SELECT month, plan, SUM(active_mrr) AS mrr FROM fact_subscription_monthly
                WHERE is_churn = 0 GROUP BY month, plan ORDER BY month""")
region_mrr = q("""SELECT region, SUM(active_mrr) AS mrr, COUNT(*) AS customers
                  FROM fact_subscription_monthly
                  WHERE is_churn = 0 AND month = (SELECT MAX(month) FROM fact_subscription_monthly)
                  GROUP BY region ORDER BY mrr DESC""")
conn.close()

res = json.load(open("python/outputs/model_results.json"))
ai = json.load(open("ai/ai_insights.json"))

last, prev = mrr.iloc[-1], mrr.iloc[-2]
rl, rp = ret.iloc[-1], ret.iloc[-2]
blended_ltv = (ue["ltv"] * ue["new_customers"]).sum() / ue["new_customers"].sum()
blended_cac = ue["total_spend"].sum() / ue["new_customers"].sum()
blended_arpa = (ue["arpa"] * ue["new_customers"]).sum() / ue["new_customers"].sum()

kpi = {
    "as_of": last["month"],
    "ending_mrr": float(last["ending_mrr"]), "mrr_delta_pct": float(last["mrr_growth_pct"]),
    "arr": float(last["arr"]),
    "active_customers": int(last["active_customers"]),
    "customers_delta": int(last["active_customers"] - prev["active_customers"]),
    "nrr_ttm": round(float(ret.tail(12)["nrr_pct"].mean()), 1),
    "nrr_month": float(rl["nrr_pct"]), "nrr_delta_pts": round(float(rl["nrr_pct"] - rp["nrr_pct"]), 2),
    "grr_month": float(rl["grr_pct"]), "grr_delta_pts": round(float(rl["grr_pct"] - rp["grr_pct"]), 2),
    "logo_churn_month": float(rl["logo_churn_pct"]), "logo_churn_delta_pts": round(float(rl["logo_churn_pct"] - rp["logo_churn_pct"]), 2),
    "logo_churn_ttm": round(float(ret.tail(12)["logo_churn_pct"].mean()), 1),
    "ltv_cac_blended": round(float(blended_ltv / blended_cac), 2),
    "cac_payback_blended": round(float(blended_cac / blended_arpa), 1),
}

piv = coh.pivot(index="cohort", columns="months_since_signup", values="retention_pct")
cohort = {"months": list(range(0, 13)),
          "rows": [{"cohort": c, "size": int(coh[coh.cohort == c].cohort_size.iloc[0]),
                    "values": [None if pd.isna(piv.loc[c].get(k)) else float(piv.loc[c].get(k)) for k in range(0, 13)]}
                   for c in piv.index]}

plans = {p: plan_mix[plan_mix.plan == p].sort_values("month")["mrr"].astype(float).tolist()
         for p in ["Starter", "Growth", "Enterprise"]}

model = {
    "selected": res["selected_model"], "horizon": res["horizon_months"], "split": res["split"],
    "metrics": res["metrics"], "calibration": res["calibration"],
    "feature_importance": res["feature_importance"][:8], "risk_summary": res["risk_summary"],
    "total_expected_loss": res["total_expected_mrr_loss_3m"], "top_at_risk": res["top_at_risk"],
}

out = {
    "kpi": kpi,
    "mrr": mrr.to_dict("records"),
    "retention": ret.to_dict("records"),
    "unit_economics": ue.to_dict("records"),
    "cohort": cohort,
    "plan_mix": {"months": sorted(plan_mix["month"].unique().tolist()), "series": plans},
    "region_mrr": region_mrr.to_dict("records"),
    "segments": seg.head(8).to_dict("records"),
    "model": model,
    "forecast": res["forecast"],
    "ai": ai,
}
payload = json.dumps(out, default=float).replace("NaN", "null")  # strict JSON
with open("dashboard/dashboard_data.json", "w") as f:
    f.write(payload)
# .js twin so index.html also works when opened directly from disk (file:// blocks fetch())
with open("dashboard/dashboard_data.js", "w") as f:
    f.write("window.DASHBOARD_DATA = " + payload + ";\n")
print("saved dashboard/dashboard_data.json |", len(json.dumps(out, default=float)) // 1024, "KB")
print("grounding:", ai["_meta"].get("grounding_check"))
