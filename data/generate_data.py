"""
generate_data.py
-----------------
Generates a realistic synthetic SaaS business dataset: customers,
subscriptions (with upgrades/downgrades/churn), monthly recurring
revenue events, support tickets, and marketing spend by channel.

Simulates 24 months of operating history for a B2B SaaS company —
used as the raw input for the ETL pipeline, SQL KPI layer, the churn
prediction model, the Excel executive report, and the dashboard.
"""

import numpy as np
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta

np.random.seed(7)

MONTHS = 24
START = date(2024, 1, 1)
month_list = [START + relativedelta(months=i) for i in range(MONTHS)]

PLANS = {
    "Starter": 49,
    "Growth": 199,
    "Enterprise": 799,
}
PLAN_NAMES = list(PLANS.keys())

CHANNELS = ["Organic Search", "Paid Social", "Paid Search", "Referral", "Outbound Sales", "Content/SEO"]
CHANNEL_WEIGHTS = [0.22, 0.18, 0.20, 0.15, 0.13, 0.12]
REGIONS = ["North America", "Europe", "APAC", "India", "LATAM"]
REGION_WEIGHTS = [0.34, 0.26, 0.18, 0.14, 0.08]
COMPANY_SIZES = ["1-10", "11-50", "51-200", "201-1000", "1000+"]
SIZE_WEIGHTS = [0.30, 0.32, 0.20, 0.12, 0.06]

# ---- 1. Marketing spend by month/channel (drives CAC) ----
spend_rows = []
for m in month_list:
    for ch in CHANNELS:
        # Average monthly spend per channel (content, tooling, ads, partner payouts, SDR cost).
        # Calibrated so blended LTV:CAC lands in a realistic 2.5x-9x band by channel.
        base = {"Organic Search": 29700, "Content/SEO": 19000, "Paid Social": 43000,
                "Paid Search": 62500, "Referral": 17500, "Outbound Sales": 42500}[ch]
        # Spend ramps with the growth curve (budget follows pipeline), mean-normalised to 1
        ramp_w = np.linspace(0.5, 1.6, MONTHS)
        ramp = ramp_w[month_list.index(m)] / ramp_w.mean()
        spend = max(0, np.random.normal(base * ramp, base * 0.10))
        spend_rows.append({"month": m.strftime("%Y-%m"), "channel": ch, "spend": round(spend, 2)})
df_spend = pd.DataFrame(spend_rows)
df_spend.to_csv("data/marketing_spend.csv", index=False)

# ---- 2. Customers with signup month, channel, region, size, plan ----
N_CUSTOMERS = 1800
customers = []
for i in range(N_CUSTOMERS):
    # Signups ramp up over time (growth-stage SaaS pattern)
    signup_weights = np.linspace(0.5, 1.6, MONTHS)
    signup_idx = np.random.choice(range(MONTHS), p=signup_weights / signup_weights.sum())
    signup_month = month_list[signup_idx]

    channel = np.random.choice(CHANNELS, p=CHANNEL_WEIGHTS)
    region = np.random.choice(REGIONS, p=REGION_WEIGHTS)
    size = np.random.choice(COMPANY_SIZES, p=SIZE_WEIGHTS)

    # Larger companies skew toward higher plans
    if size in ["201-1000", "1000+"]:
        plan = np.random.choice(PLAN_NAMES, p=[0.10, 0.35, 0.55])
    elif size in ["51-200"]:
        plan = np.random.choice(PLAN_NAMES, p=[0.25, 0.50, 0.25])
    else:
        plan = np.random.choice(PLAN_NAMES, p=[0.55, 0.38, 0.07])

    # Seat/usage multiplier gives realistic MRR variation within a plan
    seat_mult = float(np.clip(np.random.lognormal(0, 0.35), 0.5, 3.0))

    customers.append({
        "customer_id": f"CUST{10000+i}",
        "seat_mult": round(seat_mult, 2),
        "signup_month_idx": signup_idx,
        "signup_month": signup_month.strftime("%Y-%m"),
        "acquisition_channel": channel,
        "region": region,
        "company_size": size,
        "initial_plan": plan,
    })
df_customers = pd.DataFrame(customers)

# ---- 3. Monthly subscription/MRR events per customer (lifecycle simulation) ----
events = []
tickets = []

for c in customers:
    cid = c["customer_id"]
    plan = c["initial_plan"]
    plan_rank = PLAN_NAMES.index(plan)
    signup_idx = c["signup_month_idx"]
    is_active = True
    tenure = 0
    # engagement score proxy: drives churn risk & usage; degrades randomly over time
    engagement = np.random.uniform(0.45, 0.95)
    eng_hist = [engagement]

    for m_idx in range(signup_idx, MONTHS):
        if not is_active:
            break
        month = month_list[m_idx]
        tenure += 1

        # engagement drifts
        # Engagement observed at the START of this month (what the CS team could see);
        # churn this month is driven by these lagged values (usage decay precedes cancellation).
        e_lag1 = eng_hist[-1]
        e_lag2 = eng_hist[-2] if len(eng_hist) > 1 else eng_hist[-1]
        # mean-reverting drift around a healthy level of ~0.70, with monthly noise
        engagement = np.clip(engagement + 0.05 * (0.70 - engagement) + np.random.normal(0, 0.07), 0.05, 1.0)
        eng_hist.append(engagement)

        is_new = (m_idx == signup_idx)
        is_expansion = False
        is_contraction = False
        is_churn = False

        # Plan change dynamics (after month 2, low-engagement more likely to downgrade;
        # high-engagement more likely to upgrade)
        if tenure > 2 and np.random.random() < 0.06:
            if engagement > 0.7 and plan_rank < 2:
                plan_rank += 1
                is_expansion = True
            elif engagement < 0.50 and plan_rank > 0:
                plan_rank -= 1
                is_contraction = True

        plan = PLAN_NAMES[plan_rank]

        # Support tickets: more tickets correlates with lower engagement
        n_tickets = np.random.poisson(lam=max(0.1, (1 - engagement) * 3))
        for _ in range(n_tickets):
            tickets.append({"customer_id": cid, "month": month.strftime("%Y-%m")})

        # Churn hazard: higher for low engagement, early tenure (onboarding risk),
        # and Starter plan customers (classic SaaS pattern)
        # Hazard grows with (a) low LAGGED engagement and (b) a recent sharp drop - the leading
        # indicators product/CS teams monitor in practice. Onboarding and plan-tier effects on top.
        base_hazard = 0.006
        base_hazard += 0.40 * max(0.0, 0.65 - e_lag1)
        base_hazard += 0.60 * max(0.0, e_lag2 - e_lag1 - 0.02)
        if tenure <= 2:
            base_hazard += 0.012  # onboarding churn risk
        if plan == "Starter":
            base_hazard += 0.006
        if plan == "Enterprise":
            base_hazard -= 0.003

        churn_roll = np.random.random()
        if churn_roll < max(0.004, base_hazard):
            is_churn = True
            is_active = False

        mrr = int(round(PLANS[plan] * c["seat_mult"]))

        events.append({
            "customer_id": cid,
            "month": month.strftime("%Y-%m"),
            "month_idx": m_idx,
            "plan": plan,
            "mrr": mrr,
            "tenure_months": tenure,
            "engagement_score": round(engagement, 3),
            "is_new": is_new,
            "is_expansion": is_expansion,
            "is_contraction": is_contraction,
            "is_churn": is_churn,
            "region": c["region"],
            "acquisition_channel": c["acquisition_channel"],
            "company_size": c["company_size"],
        })

df_events = pd.DataFrame(events)
df_tickets = pd.DataFrame(tickets)

df_customers.to_csv("data/customers.csv", index=False)
df_events.to_csv("data/subscription_events.csv", index=False)
df_tickets.to_csv("data/support_tickets.csv", index=False)

print(f"Generated {len(df_customers)} customers")
print(f"Generated {len(df_events)} monthly subscription-event rows")
print(f"Generated {len(df_tickets)} support ticket rows")
print(f"Generated {len(df_spend)} marketing spend rows")
print(df_events.head(3).to_string())
