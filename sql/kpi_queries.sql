-- ============================================================
-- kpi_queries.sql  |  SaaS KPI layer (SQLite, star schema)
-- CTEs + window functions for industry-standard SaaS metrics.
-- Identity: Ending MRR = Starting + New + Expansion - Contraction - Churned
-- ============================================================

-- 1. MRR WATERFALL + growth + ARR
WITH m AS (
    SELECT month,
           SUM(active_mrr)      AS ending_mrr,
           SUM(new_mrr)         AS new_mrr,
           SUM(expansion_mrr)   AS expansion_mrr,
           SUM(contraction_mrr) AS contraction_mrr,
           SUM(churned_mrr)     AS churned_mrr,
           SUM(CASE WHEN is_churn = 0 THEN 1 ELSE 0 END) AS active_customers,
           SUM(is_new) AS new_customers,
           SUM(is_churn) AS churned_customers
    FROM fact_subscription_monthly
    GROUP BY month
)
SELECT month,
       COALESCE(LAG(ending_mrr) OVER (ORDER BY month), 0) AS starting_mrr,
       new_mrr, expansion_mrr, contraction_mrr, churned_mrr, ending_mrr,
       ending_mrr * 12 AS arr,
       active_customers, new_customers, churned_customers,
       ROUND(100.0 * (ending_mrr - LAG(ending_mrr) OVER (ORDER BY month))
             / NULLIF(LAG(ending_mrr) OVER (ORDER BY month), 0), 2) AS mrr_growth_pct
FROM m ORDER BY month;


-- 2. REVENUE CHURN, LOGO CHURN, GRR and NRR per month
--    GRR = (Start - Contraction - Churn) / Start        (capped at 100%)
--    NRR = (Start + Expansion - Contraction - Churn) / Start
WITH m AS (
    SELECT month,
           SUM(active_mrr) AS ending_mrr,
           SUM(expansion_mrr) AS exp, SUM(contraction_mrr) AS con, SUM(churned_mrr) AS churn,
           SUM(is_churn) AS churned_customers,
           SUM(CASE WHEN is_churn = 0 THEN 1 ELSE 0 END) AS active_customers
    FROM fact_subscription_monthly GROUP BY month
), s AS (
    SELECT *, LAG(ending_mrr) OVER (ORDER BY month) AS start_mrr,
              LAG(active_customers) OVER (ORDER BY month) AS start_customers
    FROM m
)
SELECT month, start_mrr,
       ROUND(100.0 * churn / start_mrr, 2)                          AS revenue_churn_pct,
       ROUND(100.0 * churned_customers / start_customers, 2)         AS logo_churn_pct,
       ROUND(100.0 * (start_mrr - con - churn) / start_mrr, 2)       AS grr_pct,
       ROUND(100.0 * (start_mrr + exp - con - churn) / start_mrr, 2) AS nrr_pct
FROM s WHERE start_mrr IS NOT NULL AND start_mrr > 0
ORDER BY month;


-- 3. UNIT ECONOMICS BY CHANNEL: ARPA, churn, LTV, CAC, LTV:CAC, CAC payback (months)
--    LTV = ARPA / monthly logo churn      CAC = channel spend / new customers
WITH arpa AS (
    SELECT acquisition_channel, AVG(active_mrr) AS arpa
    FROM fact_subscription_monthly WHERE is_churn = 0 GROUP BY acquisition_channel
), churn AS (
    SELECT acquisition_channel, 1.0 * SUM(is_churn) / COUNT(*) AS churn_rate
    FROM fact_subscription_monthly WHERE is_new = 0 GROUP BY acquisition_channel
), nc AS (
    SELECT acquisition_channel, COUNT(*) AS new_customers
    FROM fact_subscription_monthly WHERE is_new = 1 GROUP BY acquisition_channel
), sp AS (
    SELECT channel AS acquisition_channel, SUM(spend) AS spend
    FROM fact_marketing_spend GROUP BY channel
)
SELECT a.acquisition_channel,
       n.new_customers,
       ROUND(s.spend, 0)                                     AS total_spend,
       ROUND(a.arpa, 2)                                      AS arpa,
       ROUND(100 * c.churn_rate, 2)                          AS monthly_churn_pct,
       ROUND(a.arpa / c.churn_rate, 0)                       AS ltv,
       ROUND(s.spend / n.new_customers, 0)                   AS cac,
       ROUND((a.arpa / c.churn_rate) / (s.spend / n.new_customers), 2) AS ltv_to_cac,
       ROUND((s.spend / n.new_customers) / a.arpa, 1)        AS cac_payback_months
FROM arpa a JOIN churn c USING (acquisition_channel)
            JOIN nc n USING (acquisition_channel)
            JOIN sp s USING (acquisition_channel)
ORDER BY ltv_to_cac DESC;


-- 4. COHORT RETENTION (logo retention by months since signup, first 12 months)
WITH base AS (
    SELECT f.customer_id, d.signup_month AS cohort,
           (CAST(substr(f.month,1,4) AS INT)*12 + CAST(substr(f.month,6,2) AS INT))
         - (CAST(substr(d.signup_month,1,4) AS INT)*12 + CAST(substr(d.signup_month,6,2) AS INT)) AS age,
           f.is_churn
    FROM fact_subscription_monthly f JOIN dim_customer d USING (customer_id)
), sizes AS (
    SELECT cohort, COUNT(DISTINCT customer_id) AS cohort_size FROM base GROUP BY cohort
)
SELECT b.cohort, b.age AS months_since_signup, s.cohort_size,
       COUNT(DISTINCT CASE WHEN b.is_churn = 0 THEN b.customer_id END) AS active_customers,
       ROUND(100.0 * COUNT(DISTINCT CASE WHEN b.is_churn = 0 THEN b.customer_id END) / s.cohort_size, 1) AS retention_pct
FROM base b JOIN sizes s USING (cohort)
WHERE b.age BETWEEN 0 AND 12
GROUP BY b.cohort, b.age ORDER BY b.cohort, b.age;


-- 5. CHURN EARLY-WARNING SIGNALS: engagement and tickets, last 3 months before churn vs healthy
SELECT CASE WHEN f.is_churn = 1 THEN 'Churned (month of churn)' ELSE 'Retained' END AS status,
       COUNT(*) AS customer_months,
       ROUND(AVG(f.engagement_score), 3) AS avg_engagement,
       ROUND(AVG(COALESCE(t.ticket_count, 0)), 2) AS avg_tickets
FROM fact_subscription_monthly f
LEFT JOIN fact_support_tickets t USING (customer_id, month)
GROUP BY status;


-- 6. SEGMENT VIEW (latest month): plan x region MRR, customers, ARPA, share of MRR
WITH latest AS (SELECT MAX(month) AS mo FROM fact_subscription_monthly)
SELECT plan, region,
       COUNT(*) AS customers,
       SUM(active_mrr) AS mrr,
       ROUND(AVG(active_mrr), 1) AS arpa,
       ROUND(100.0 * SUM(active_mrr) / SUM(SUM(active_mrr)) OVER (), 1) AS pct_of_total_mrr
FROM fact_subscription_monthly, latest
WHERE month = latest.mo AND is_churn = 0
GROUP BY plan, region
ORDER BY mrr DESC;


-- 7. MRR CONCENTRATION: top 10% of customers' share of MRR (NTILE window)
WITH latest AS (
    SELECT customer_id, active_mrr FROM fact_subscription_monthly
    WHERE month = (SELECT MAX(month) FROM fact_subscription_monthly) AND is_churn = 0
), ranked AS (SELECT *, NTILE(10) OVER (ORDER BY active_mrr DESC) AS decile FROM latest)
SELECT decile, COUNT(*) AS customers, SUM(active_mrr) AS mrr,
       ROUND(100.0 * SUM(active_mrr) / SUM(SUM(active_mrr)) OVER (), 1) AS pct_of_mrr
FROM ranked GROUP BY decile ORDER BY decile;
