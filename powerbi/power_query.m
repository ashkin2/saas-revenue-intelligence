// =====================================================================
// Power Query (M) - load the 6 CSV exports produced by etl/etl_pipeline.py and churn_model.py
// Home > Transform data > Advanced Editor. Set the SourceFolder parameter first.
// =====================================================================

// ---- Parameter ----------------------------------------------------------------------------
// SourceFolder  (Text)  e.g.  "C:\Projects\saas-analytics-project\powerbi\data\"


// ---- fact_subscription_monthly ------------------------------------------------------------
let
    Source   = Csv.Document(File.Contents(SourceFolder & "fact_subscription_monthly.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    Typed    = Table.TransformColumnTypes(Promoted, {
                    {"customer_id", type text}, {"month", type text}, {"month_idx", Int64.Type},
                    {"plan", type text}, {"mrr", type number}, {"active_mrr", type number},
                    {"new_mrr", type number}, {"expansion_mrr", type number},
                    {"contraction_mrr", type number}, {"churned_mrr", type number},
                    {"tenure_months", Int64.Type}, {"engagement_score", type number},
                    {"is_new", Int64.Type}, {"is_expansion", Int64.Type},
                    {"is_contraction", Int64.Type}, {"is_churn", Int64.Type}}),
    // first day of month = join key to dim_date
    MonthStart = Table.AddColumn(Typed, "MonthStart", each Date.FromText([month] & "-01"), type date)
in
    MonthStart


// ---- dim_customer -------------------------------------------------------------------------
let
    Source   = Csv.Document(File.Contents(SourceFolder & "dim_customer.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    Typed    = Table.TransformColumnTypes(Promoted, {{"customer_id", type text}, {"signup_month", type text},
                    {"acquisition_channel", type text}, {"region", type text}, {"company_size", type text}}),
    // sort key so company size orders logically in visuals (use "Sort by column")
    SizeOrder = Table.AddColumn(Typed, "company_size_order", each
                    if [company_size] = "1-10" then 1 else if [company_size] = "11-50" then 2
                    else if [company_size] = "51-200" then 3 else if [company_size] = "201-1000" then 4 else 5, Int64.Type)
in
    SizeOrder


// ---- fact_marketing_spend -----------------------------------------------------------------
let
    Source   = Csv.Document(File.Contents(SourceFolder & "fact_marketing_spend.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    Typed    = Table.TransformColumnTypes(Promoted, {{"month", type text}, {"channel", type text}, {"spend", type number}}),
    MonthStart = Table.AddColumn(Typed, "MonthStart", each Date.FromText([month] & "-01"), type date)
in
    MonthStart


// ---- fact_support_tickets -----------------------------------------------------------------
let
    Source   = Csv.Document(File.Contents(SourceFolder & "fact_support_tickets.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    Typed    = Table.TransformColumnTypes(Promoted, {{"customer_id", type text}, {"month", type text}, {"ticket_count", Int64.Type}}),
    MonthStart = Table.AddColumn(Typed, "MonthStart", each Date.FromText([month] & "-01"), type date)
in
    MonthStart


// ---- churn_scores (output of the ML model) ------------------------------------------------
let
    Source   = Csv.Document(File.Contents(SourceFolder & "churn_scores.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    Typed    = Table.TransformColumnTypes(Promoted, {{"customer_id", type text}, {"active_mrr", type number},
                    {"churn_prob_3m", type number}, {"risk_tier", type text}, {"expected_mrr_loss", type number}}),
    // risk tier sort key (High first)
    TierOrder = Table.AddColumn(Typed, "risk_tier_order", each if [risk_tier] = "High" then 1 else if [risk_tier] = "Medium" then 2 else 3, Int64.Type)
in
    TierOrder


// ---- dim_date : continuous DAILY calendar (required for time-intelligence functions) -------
let
    StartDate = #date(2024, 1, 1),
    EndDate   = #date(2026, 6, 30),                      // extends over the 6-month forecast horizon
    DayCount  = Duration.Days(EndDate - StartDate) + 1,
    Dates     = List.Dates(StartDate, DayCount, #duration(1, 0, 0, 0)),
    ToTable   = Table.FromList(Dates, Splitter.SplitByNothing(), {"Date"}, null, ExtraValues.Error),
    Typed     = Table.TransformColumnTypes(ToTable, {{"Date", type date}}),
    Year      = Table.AddColumn(Typed, "Year", each Date.Year([Date]), Int64.Type),
    Quarter   = Table.AddColumn(Year, "Quarter", each "Q" & Text.From(Date.QuarterOfYear([Date])), type text),
    MonthNum  = Table.AddColumn(Quarter, "Month Number", each Date.Month([Date]), Int64.Type),
    MonthName = Table.AddColumn(MonthNum, "Month", each Date.ToText([Date], "MMM yyyy"), type text),
    MonthSort = Table.AddColumn(MonthName, "Month Sort", each Date.Year([Date]) * 100 + Date.Month([Date]), Int64.Type)
in
    MonthSort
