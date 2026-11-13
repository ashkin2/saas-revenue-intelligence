"""
etl_pipeline.py
----------------
ETL pipeline for the SaaS Business Analytics project.

Extract  : raw CSVs (customers, subscription events, support tickets, marketing spend)
Transform: data-quality checks + MRR movement logic (new / expansion / contraction /
           churn) so the MRR waterfall reconciles exactly, then a star schema
Load     : SQLite warehouse (data/saas.db) + CSV exports for Power BI / Excel

Reconciliation identity enforced and asserted:
    Ending MRR = Starting MRR + New + Expansion - Contraction - Churned

Run: python etl/etl_pipeline.py
"""

import sqlite3
from pathlib import Path

import pandas as pd

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "saas.db"
PBI_DIR = Path("powerbi/data")


def extract():
    customers = pd.read_csv(DATA_DIR / "customers.csv")
    events = pd.read_csv(DATA_DIR / "subscription_events.csv")
    tickets = pd.read_csv(DATA_DIR / "support_tickets.csv")
    spend = pd.read_csv(DATA_DIR / "marketing_spend.csv")
    print(f"[EXTRACT] customers={len(customers)} events={len(events)} "
          f"tickets={len(tickets)} spend={len(spend)}")
    return customers, events, tickets, spend


def build_mrr_movements(events: pd.DataFrame) -> pd.DataFrame:
    """Derive per-customer-month MRR movement columns."""
    ev = events.sort_values(["customer_id", "month_idx"]).copy()
    ev["prev_mrr"] = ev.groupby("customer_id")["mrr"].shift(1).fillna(0)

    # A churn row means the customer is lost in that month -> contributes 0 active MRR
    ev["active_mrr"] = ev["mrr"].where(~ev["is_churn"], 0)
    ev["new_mrr"] = ev["active_mrr"].where(ev["is_new"], 0)
    ev["expansion_mrr"] = (ev["mrr"] - ev["prev_mrr"]).where(ev["is_expansion"] & ~ev["is_churn"], 0)
    ev["contraction_mrr"] = (ev["prev_mrr"] - ev["mrr"]).where(ev["is_contraction"] & ~ev["is_churn"], 0)
    ev["churned_mrr"] = ev["prev_mrr"].where(ev["is_churn"] & ~ev["is_new"], 0)

    for c in ["is_new", "is_expansion", "is_contraction", "is_churn"]:
        ev[c] = ev[c].astype(int)
    return ev


def validate_waterfall(ev: pd.DataFrame):
    m = ev.groupby("month_idx")[["active_mrr", "new_mrr", "expansion_mrr",
                                  "contraction_mrr", "churned_mrr"]].sum().sort_index()
    m["starting"] = m["active_mrr"].shift(1).fillna(0)
    m["expected_end"] = m["starting"] + m["new_mrr"] + m["expansion_mrr"] - m["contraction_mrr"] - m["churned_mrr"]
    diff = (m["expected_end"] - m["active_mrr"]).abs().max()
    assert diff < 1e-6, f"MRR waterfall does not reconcile (max diff {diff})"
    print(f"[VALIDATE] MRR waterfall reconciles for all {len(m)} months (max diff = {diff:.6f})")


def transform(customers, events, tickets, spend):
    before = len(events)
    events = events.dropna(subset=["customer_id", "month", "mrr"])
    events = events[events["mrr"] >= 0].drop_duplicates(subset=["customer_id", "month"])
    print(f"[TRANSFORM] events after DQ checks: {before} -> {len(events)}")

    fact = build_mrr_movements(events)
    validate_waterfall(fact)

    dim_customer = customers[["customer_id", "signup_month", "acquisition_channel",
                              "region", "company_size"]].drop_duplicates("customer_id")

    dim_date = pd.DataFrame({"month": sorted(fact["month"].unique())})
    dim_date["year"] = dim_date["month"].str[:4].astype(int)
    dim_date["month_num"] = dim_date["month"].str[5:7].astype(int)
    dim_date["quarter"] = "Q" + ((dim_date["month_num"] - 1) // 3 + 1).astype(str)

    fact_support = tickets.groupby(["customer_id", "month"]).size().reset_index(name="ticket_count")
    return dim_customer, dim_date, fact, fact_support, spend


def load(dim_customer, dim_date, fact, fact_support, spend):
    conn = sqlite3.connect(DB_PATH)
    dim_customer.to_sql("dim_customer", conn, if_exists="replace", index=False)
    dim_date.to_sql("dim_date", conn, if_exists="replace", index=False)
    fact.to_sql("fact_subscription_monthly", conn, if_exists="replace", index=False)
    fact_support.to_sql("fact_support_tickets", conn, if_exists="replace", index=False)
    spend.to_sql("fact_marketing_spend", conn, if_exists="replace", index=False)
    for tbl, col in [("fact_subscription_monthly", "customer_id"),
                     ("fact_subscription_monthly", "month"),
                     ("fact_support_tickets", "customer_id"),
                     ("fact_marketing_spend", "month"),
                     ("dim_customer", "customer_id")]:
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{tbl}_{col} ON {tbl}({col})")
    conn.commit()
    conn.close()
    print(f"[LOAD] Star schema written to {DB_PATH}")

    # CSV exports so the Power BI model can be rebuilt by simply importing these files
    PBI_DIR.mkdir(parents=True, exist_ok=True)
    dim_customer.to_csv(PBI_DIR / "dim_customer.csv", index=False)
    dim_date.to_csv(PBI_DIR / "dim_date.csv", index=False)
    fact.to_csv(PBI_DIR / "fact_subscription_monthly.csv", index=False)
    fact_support.to_csv(PBI_DIR / "fact_support_tickets.csv", index=False)
    spend.to_csv(PBI_DIR / "fact_marketing_spend.csv", index=False)
    print(f"[LOAD] CSV exports for Power BI -> {PBI_DIR}")


def main():
    parts = transform(*extract())
    load(*parts)
    print("[DONE] ETL pipeline completed successfully.")


if __name__ == "__main__":
    main()
