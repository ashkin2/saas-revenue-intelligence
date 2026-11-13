# Power BI build guide

Files: `power_query.m` (loaders), `measures.dax` (measures), `theme.json` (View > Themes > Browse for themes), `data/*.csv` (exports from the ETL).
Status: written against the exported schema, **not yet run in Power BI Desktop** - verify visuals after import.

## Import
1. Home > Transform data > Manage parameters: add `SourceFolder` (Text) = full path to `powerbi/data/` with trailing `\`.
2. For each query block in `power_query.m`: New Source > Blank Query > Advanced Editor > paste. Name queries exactly as the comments say.
3. Close & Apply. Then import `measures.dax` into a table called `_Measures` (Enter Data, then add each measure).
4. Mark `dim_date` as a date table on `Date`. Sort `Month` by `Month Sort`; `company_size` by `company_size_order`; `risk_tier` by `risk_tier_order`.

## Model (star schema)
| From (many) | To (one) | Key |
|---|---|---|
| fact_subscription_monthly[customer_id] | dim_customer[customer_id] | many-to-one |
| fact_subscription_monthly[MonthStart] | dim_date[Date] | many-to-one |
| fact_marketing_spend[MonthStart] | dim_date[Date] | many-to-one |
| fact_support_tickets[customer_id] | dim_customer[customer_id] | many-to-one |
| churn_scores[customer_id] | dim_customer[customer_id] | many-to-one |
Single-direction filters. Marketing spend joins to channel through `dim_customer[acquisition_channel]` only via a shared channel slicer (use a small `dim_channel` table if you want cross-filtering).

## Report pages
1. **Executive overview** - cards: MRR, ARR, NRR, GRR, Logo churn, LTV:CAC; MRR waterfall; MRR by plan; month slicer.
2. **Retention & cohorts** - NRR/GRR line with 100% constant line; cohort matrix (rows = signup month, columns = months since signup, conditional colour).
3. **Unit economics** - LTV:CAC and CAC payback by channel with 3x / 12-month reference lines; channel scorecard table.
4. **Churn risk** - tier cards, expected MRR loss by tier, top-accounts table from `churn_scores`; drill-through to customer.
5. **Segments** - plan x region matrix, MRR concentration, region map.
Apply `theme.json`; keep one accent colour for "bad" (red) and use it only for values past a benchmark.
