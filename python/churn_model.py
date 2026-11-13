"""
churn_model.py
---------------
Predictive layer for the SaaS analytics project.

1. CHURN PREDICTION  - classifier predicting whether an active customer churns within the NEXT 3 MONTHS
                       from behavioural + commercial features. Logistic Regression and HistGradientBoosting
                       are compared; the winner is chosen on a time-based VALIDATION slice and only then
                       reported on the untouched test period (no random shuffling, no look-ahead leakage).
2. EXPLAINABILITY    - permutation importance on the held-out period; calibration by risk decile.
3. ACTIONABLE OUTPUT - scores every active customer, assigns High/Medium/Low tiers and sizes expected MRR loss.
4. MRR FORECAST      - damped-growth 6-month forecast; 80% band from a rolling-origin backtest.

NOTE: the data is synthetic. Model metrics therefore reflect the data-generating assumptions
(engagement decay precedes churn) and demonstrate the methodology, not real-world performance.

Run: python python/churn_model.py
"""

import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

DB = "data/saas.db"
OUT = Path("python/outputs")
OUT.mkdir(parents=True, exist_ok=True)
HORIZON = 3          # predict churn within next N months
TRAIN_END = 15       # month_idx <= 15 -> train; 16..(23-HORIZON) -> test
SEED = 42

PLAN_ORD = {"Starter": 0, "Growth": 1, "Enterprise": 2}
SIZE_ORD = {"1-10": 0, "11-50": 1, "51-200": 2, "201-1000": 3, "1000+": 4}

# ------------------------------------------------------------------ data
conn = sqlite3.connect(DB)
fact = pd.read_sql_query("SELECT * FROM fact_subscription_monthly", conn)
tix = pd.read_sql_query("SELECT * FROM fact_support_tickets", conn)
conn.close()

fact = fact.merge(tix, on=["customer_id", "month"], how="left")
fact["ticket_count"] = fact["ticket_count"].fillna(0)
fact = fact.sort_values(["customer_id", "month_idx"]).reset_index(drop=True)

# ------------------------------------------------------------------ features
g = fact.groupby("customer_id")
fact["eng_delta_1m"] = fact["engagement_score"] - g["engagement_score"].shift(1)
fact["eng_roll3"] = g["engagement_score"].transform(lambda s: s.rolling(3, min_periods=1).mean())
fact["eng_min3"] = g["engagement_score"].transform(lambda s: s.rolling(3, min_periods=1).min())
fact["tickets_roll3"] = g["ticket_count"].transform(lambda s: s.rolling(3, min_periods=1).sum())
fact["plan_ord"] = fact["plan"].map(PLAN_ORD)
fact["size_ord"] = fact["company_size"].map(SIZE_ORD)
fact["eng_delta_1m"] = fact["eng_delta_1m"].fillna(0)
for col in ["region", "acquisition_channel"]:
    fact[col + "_code"] = fact[col].astype("category").cat.codes

FEATURES = ["tenure_months", "engagement_score", "eng_delta_1m", "eng_roll3", "eng_min3",
            "ticket_count", "tickets_roll3", "active_mrr", "plan_ord", "size_ord",
            "region_code", "acquisition_channel_code"]

# ------------------------------------------------------------------ label: churn within next HORIZON months
churn_idx = fact.loc[fact["is_churn"] == 1].set_index("customer_id")["month_idx"]
fact["churn_month_idx"] = fact["customer_id"].map(churn_idx)
fact["label"] = ((fact["churn_month_idx"] > fact["month_idx"]) &
                 (fact["churn_month_idx"] <= fact["month_idx"] + HORIZON)).astype(int)

snap = fact[fact["is_churn"] == 0]                       # only customers active at snapshot
last_idx = int(fact["month_idx"].max())
labelled = snap[snap["month_idx"] <= last_idx - HORIZON]  # outcome window fully observed
train = labelled[labelled["month_idx"] <= TRAIN_END]
test = labelled[labelled["month_idx"] > TRAIN_END]
print(f"Train rows={len(train):,} (churn rate {train.label.mean():.2%}) | "
      f"Test rows={len(test):,} (churn rate {test.label.mean():.2%})")

# ------------------------------------------------------------------ models
cat_mask = [f.endswith("_code") for f in FEATURES]


def new_gbm():
    return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200,
                                          min_samples_leaf=60, l2_regularization=2.0,
                                          categorical_features=cat_mask, random_state=SEED)


def new_logit():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))


# Model selection on a time-based VALIDATION slice carved from the training period,
# so the held-out test period is never used to pick the model.
VAL_START = 12
fit_df, val_df = train[train["month_idx"] < VAL_START], train[train["month_idx"] >= VAL_START]
val_auc = {}
for name, factory in [("HistGradientBoosting", new_gbm), ("Logistic Regression", new_logit)]:
    mdl = factory().fit(fit_df[FEATURES], fit_df["label"])
    val_auc[name] = roc_auc_score(val_df["label"], mdl.predict_proba(val_df[FEATURES])[:, 1])
print("Validation ROC-AUC:", {k: round(v, 3) for k, v in val_auc.items()})
selected = max(val_auc, key=val_auc.get)
print(f"Selected model (by validation AUC): {selected}")

# Refit both on the full training window; the selected one drives scoring downstream.
gbm = new_gbm().fit(train[FEATURES], train["label"])
logit = new_logit().fit(train[FEATURES], train["label"])
champion = gbm if selected == "HistGradientBoosting" else logit


def evaluate(model, name):
    p = model.predict_proba(test[FEATURES])[:, 1]
    k = int(len(test) * 0.10)
    top = test.assign(p=p).nlargest(k, "p")
    base = test["label"].mean()
    res = {
        "model": name,
        "roc_auc": round(roc_auc_score(test["label"], p), 3),
        "pr_auc": round(average_precision_score(test["label"], p), 3),
        "baseline_churn_rate": round(base, 4),
        "precision_at_top10pct": round(top["label"].mean(), 3),
        "lift_at_top10pct": round(top["label"].mean() / base, 2),
        "recall_at_top10pct": round(top["label"].sum() / test["label"].sum(), 3),
    }
    return res, p


m_gbm, p_gbm_all = evaluate(gbm, "HistGradientBoosting")
m_log, p_log_all = evaluate(logit, "Logistic Regression")
m_gbm["validation_auc"] = round(val_auc["HistGradientBoosting"], 3)
m_log["validation_auc"] = round(val_auc["Logistic Regression"], 3)
m_gbm["selected"] = selected == "HistGradientBoosting"
m_log["selected"] = selected == "Logistic Regression"
p_gbm = p_gbm_all if selected == "HistGradientBoosting" else p_log_all  # champion test probs
print(json.dumps([m_log, m_gbm], indent=2))

# calibration on test (decile of predicted risk vs observed rate)
cal = test.assign(p=p_gbm)
cal["bin"] = pd.qcut(cal["p"], 10, labels=False, duplicates="drop")
calibration = (cal.groupby("bin").agg(predicted=("p", "mean"), observed=("label", "mean"),
                                       n=("label", "size")).round(4).reset_index().to_dict("records"))

# permutation importance (held-out)
pi = permutation_importance(champion, test[FEATURES], test["label"], scoring="roc_auc",
                            n_repeats=8, random_state=SEED)
LABELS = {"tenure_months": "Tenure (months)", "engagement_score": "Engagement score",
          "eng_delta_1m": "Engagement change (1m)", "eng_roll3": "Engagement (3m avg)",
          "eng_min3": "Engagement (3m min)", "ticket_count": "Support tickets (month)",
          "tickets_roll3": "Support tickets (3m)", "active_mrr": "Account MRR",
          "plan_ord": "Plan tier", "size_ord": "Company size", "region_code": "Region",
          "acquisition_channel_code": "Acquisition channel"}
importance = (pd.DataFrame({"feature": [LABELS[f] for f in FEATURES],
                            "importance": pi.importances_mean.round(4)})
              .sort_values("importance", ascending=False).to_dict("records"))

# ------------------------------------------------------------------ score current customers
current = fact[(fact["month_idx"] == last_idx) & (fact["is_churn"] == 0)].copy()
current["churn_prob_3m"] = champion.predict_proba(current[FEATURES])[:, 1]
q_hi, q_med = current["churn_prob_3m"].quantile([0.90, 0.70])
current["risk_tier"] = np.where(current["churn_prob_3m"] >= q_hi, "High",
                         np.where(current["churn_prob_3m"] >= q_med, "Medium", "Low"))


def driver(r):
    """Plain-language top risk driver per account (rule-based reason code from model features)."""
    reasons = []
    if r["eng_delta_1m"] <= -0.10:
        reasons.append("sharp engagement drop")
    if r["eng_roll3"] < 0.50:
        reasons.append("low 3-month engagement")
    if r["tickets_roll3"] >= 5:
        reasons.append("high support load")
    if r["tenure_months"] <= 3:
        reasons.append("early-tenure onboarding risk")
    if r["plan_ord"] == 0:
        reasons.append("entry plan")
    return "; ".join(reasons[:2]) if reasons else "model-detected combined signals"


current["primary_drivers"] = current.apply(driver, axis=1)
current["expected_mrr_loss"] = (current["churn_prob_3m"] * current["active_mrr"]).round(2)

risk_summary = (current.groupby("risk_tier")
                .agg(customers=("customer_id", "count"), mrr=("active_mrr", "sum"),
                     avg_prob=("churn_prob_3m", "mean"), expected_loss=("expected_mrr_loss", "sum"))
                .round(3).reindex(["High", "Medium", "Low"]).reset_index().to_dict("records"))

at_risk = (current.sort_values("expected_mrr_loss", ascending=False)
           [["customer_id", "plan", "region", "company_size", "acquisition_channel", "active_mrr",
             "engagement_score", "eng_delta_1m", "tickets_roll3", "tenure_months",
             "churn_prob_3m", "risk_tier", "primary_drivers", "expected_mrr_loss"]]
           .round(3))
at_risk.to_csv(OUT / "churn_scores_current.csv", index=False)
current[["customer_id", "active_mrr", "churn_prob_3m", "risk_tier", "expected_mrr_loss"]].round(4) \
    .to_csv("powerbi/data/churn_scores.csv", index=False)

# ------------------------------------------------------------------ MRR forecast
# Damped-growth model: recent MoM growth decays geometrically (growth rarely persists forever).
# Prediction intervals come from a rolling-origin BACKTEST on this very series, not from a
# fitted-residual formula - so the band reflects real out-of-sample forecast error.
mrr = fact.groupby("month_idx")["active_mrr"].sum().sort_index()
months = sorted(fact["month"].unique())
series = mrr.values.astype(float)
H, PHI, K = 6, 0.85, 3


def damped_forecast(hist, h=H, phi=PHI, k=K):
    g = float(np.mean(hist[-k:] / hist[-k - 1:-1] - 1))
    level, out = hist[-1], []
    for _ in range(h):
        g *= phi
        level *= 1 + g
        out.append(level)
    return np.array(out), g


def backtest(phi, k):
    errs = {h: [] for h in range(1, H + 1)}
    for origin in range(12, len(series) - H):
        fc_bt, _ = damped_forecast(series[: origin + 1], phi=phi, k=k)
        for h in range(1, H + 1):
            actual = series[origin + h]
            errs[h].append((fc_bt[h - 1] - actual) / actual)
    return errs


# Tune (phi, k) by mean backtest MAPE across horizons. NOTE: with only ~6 origins this is a
# small-sample selection, and the interval below is therefore somewhat optimistic - flagged in caveats.
grid = [(phi, k) for phi in (0.80, 0.85, 0.90, 0.95, 1.00) for k in (3, 6)]
scores = {(phi, k): np.mean([np.mean(np.abs(v)) for v in backtest(phi, k).values()]) for phi, k in grid}
PHI, K = min(scores, key=scores.get)
errs = backtest(PHI, K)
n_origins = len(errs[1])
bt = [{"horizon": h, "mape_pct": round(100 * float(np.mean(np.abs(errs[h]))), 2),
       "bias_pct": round(100 * float(np.mean(errs[h])), 2),
       "p80_abs_err_pct": round(100 * float(np.quantile(np.abs(errs[h]), 0.8)), 2)} for h in errs]
print(f"Forecast tuned on backtest: phi={PHI}, k={K}; 6m MAPE={bt[-1]['mape_pct']}% bias={bt[-1]['bias_pct']}%")

fc, g_first = damped_forecast(series, phi=PHI, k=K)
y_last, m_last = months[-1].split("-")
fc_months = pd.period_range(start=f"{y_last}-{m_last}", periods=H + 1, freq="M")[1:].astype(str).tolist()
# widen by the backtest p80 abs error (floor of 1% so a lucky short backtest never gives a zero-width band)
forecast = {
    "method": f"Damped growth (phi={PHI}) from trailing {K}-month MoM growth; 80% band = backtest p80 abs error "
              f"over {n_origins} rolling origins",
    "implied_monthly_growth_pct": round(g_first * 100, 2),
    "backtest": bt,
    "backtest_origins": n_origins,
    "history": [{"month": m, "mrr": float(v)} for m, v in zip(months[-12:], series[-12:])],
    "forecast": [{"month": m, "mrr": round(float(v), 0),
                  "low": round(float(v * (1 - max(0.01, bt[i]["p80_abs_err_pct"] / 100))), 0),
                  "high": round(float(v * (1 + max(0.01, bt[i]["p80_abs_err_pct"] / 100))), 0)}
                 for i, (m, v) in enumerate(zip(fc_months, fc))],
}

# ------------------------------------------------------------------ persist
result = {
    "horizon_months": HORIZON,
    "split": {"train_through_month_idx": TRAIN_END, "train_rows": int(len(train)),
              "test_rows": int(len(test))},
    "selected_model": selected,
    "metrics": [m_log, m_gbm],
    "calibration": calibration,
    "feature_importance": importance,
    "risk_summary": risk_summary,
    "thresholds": {"high": round(float(q_hi), 4), "medium": round(float(q_med), 4)},
    "total_expected_mrr_loss_3m": round(float(current["expected_mrr_loss"].sum()), 0),
    "top_at_risk": at_risk.head(15).to_dict("records"),
    "forecast": forecast,
}
with open(OUT / "model_results.json", "w") as f:
    json.dump(result, f, indent=2, default=float)
print(f"\nHigh-risk tier: {risk_summary[0]['customers']} customers, "
      f"MRR ${risk_summary[0]['mrr']:,.0f}")
print(f"Forecast first-month growth {forecast['implied_monthly_growth_pct']}% (damped) -> "
      f"{forecast['forecast'][-1]['month']}: ${forecast['forecast'][-1]['mrr']:,.0f}")
print("Saved -> python/outputs/model_results.json, churn_scores_current.csv")
