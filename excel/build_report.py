"""
build_report.py
----------------
Builds the SaaS Executive Report workbook (Excel) from the SQL warehouse + model outputs.

Design rules (what a finance reviewer expects):
  * Source data pasted as values (blue), everything derived is a LIVE FORMULA (black)
  * MRR waterfall rebuilt in-sheet and reconciled against the warehouse (check column)
  * Inputs for what-if analysis are isolated, colour-coded cells on the Scenario sheet
  * Conditional formatting + charts for exec readability; no merged-cell tricks in data areas

Run: python excel/build_report.py   ->   excel/SaaS_Executive_Report.xlsx
"""

import json
import sqlite3

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.formatting.rule import CellIsRule, ColorScaleRule, DataBarRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L
from openpyxl.workbook.properties import CalcProperties

NAVY, MID, LIGHT, GRID = "1F3864", "2E5090", "EAF0FA", "D9DEE8"
F_IN = Font(name="Calibri", size=10, color="0000FF")              # hard-coded source data
F_CALC = Font(name="Calibri", size=10, color="000000")            # formulas
F_B = Font(name="Calibri", size=10, bold=True)
F_H = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
F_T = Font(name="Calibri", size=16, bold=True, color=NAVY)
F_SUB = Font(name="Calibri", size=10, italic=True, color="666666")
FILL_H = PatternFill("solid", fgColor=NAVY)
FILL_L = PatternFill("solid", fgColor=LIGHT)
FILL_IN = PatternFill("solid", fgColor="FFF2CC")
THIN = Side(style="thin", color=GRID)
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
USD, USD2, PCT, INT = '"$"#,##0', '"$"#,##0.00', "0.0%", "#,##0"

conn = sqlite3.connect("data/saas.db")
stmts = [s.strip() for s in open("sql/kpi_queries.sql").read().split(";") if "SELECT" in s]
mrr = pd.read_sql_query(stmts[0], conn)
ue = pd.read_sql_query(stmts[2], conn)
coh = pd.read_sql_query(stmts[3], conn)
conn.close()
scores = pd.read_csv("python/outputs/churn_scores_current.csv")
res = json.load(open("python/outputs/model_results.json"))

wb = Workbook()
wb.calculation = CalcProperties(fullCalcOnLoad=True)


def header(ws, row, labels, col=1):
    for i, t in enumerate(labels):
        c = ws.cell(row=row, column=col + i, value=t)
        c.font, c.fill, c.border = F_H, FILL_H, BOX
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 32


def title(ws, text, sub):
    ws["A1"], ws["A1"].font = text, F_T
    ws["A2"], ws["A2"].font = sub, F_SUB
    ws.sheet_view.showGridLines = False


# =============================================================== MRR Waterfall
w = wb.active
w.title = "MRR Waterfall"
title(w, "MRR Waterfall & Retention", "Source: warehouse (blue = data, black = formula). Ending MRR is rebuilt by formula and reconciled to the warehouse.")
cols = ["Month", "Starting MRR", "New MRR", "Expansion MRR", "Contraction MRR", "Churned MRR",
        "Ending MRR (calc)", "Ending MRR (warehouse)", "Recon. diff", "ARR", "MoM growth",
        "Net new MRR", "GRR", "NRR", "Active customers", "New customers", "Churned customers",
        "Logo churn", "Contraction (chart)", "Churned (chart)"]
HR, R0 = 4, 5
header(w, HR, cols)
n = len(mrr)
for i, r in mrr.iterrows():
    row = R0 + i
    w.cell(row, 1, r["month"]).font = F_IN
    w.cell(row, 2, 0 if i == 0 else f"=G{row-1}").font = F_CALC
    for c, k in [(3, "new_mrr"), (4, "expansion_mrr"), (5, "contraction_mrr"), (6, "churned_mrr")]:
        w.cell(row, c, float(r[k])).font = F_IN
    w.cell(row, 7, f"=B{row}+C{row}+D{row}-E{row}-F{row}")
    w.cell(row, 8, float(r["ending_mrr"])).font = F_IN
    w.cell(row, 9, f"=G{row}-H{row}")
    w.cell(row, 10, f"=G{row}*12")
    w.cell(row, 11, f'=IF(B{row}=0,"",G{row}/B{row}-1)')
    w.cell(row, 12, f"=C{row}+D{row}-E{row}-F{row}")
    w.cell(row, 13, f'=IF(B{row}=0,"",(B{row}-E{row}-F{row})/B{row})')
    w.cell(row, 14, f'=IF(B{row}=0,"",(B{row}+D{row}-E{row}-F{row})/B{row})')
    w.cell(row, 15, int(r["active_customers"])).font = F_IN
    w.cell(row, 16, int(r["new_customers"])).font = F_IN
    w.cell(row, 17, int(r["churned_customers"])).font = F_IN
    w.cell(row, 18, "" if i == 0 else f"=Q{row}/O{row-1}")
    w.cell(row, 19, f"=-E{row}")
    w.cell(row, 20, f"=-F{row}")
    for c in range(1, 21):
        cell = w.cell(row, c)
        cell.border = BOX
        if cell.font != F_IN:
            cell.font = F_CALC
    for c in (2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 19, 20):
        w.cell(row, c).number_format = USD
    for c in (11, 13, 14, 18):
        w.cell(row, c).number_format = PCT
    for c in (15, 16, 17):
        w.cell(row, c).number_format = INT
RL = R0 + n - 1
w.freeze_panes = "B5"
for c in range(1, 21):
    w.column_dimensions[L(c)].width = 14
w.column_dimensions["A"].width = 10
w.conditional_formatting.add(f"N{R0+1}:N{RL}", CellIsRule(operator="lessThan", formula=["1"], font=Font(color="C00000", bold=True)))
w.conditional_formatting.add(f"I{R0}:I{RL}", CellIsRule(operator="notBetween", formula=["-0.5", "0.5"], fill=PatternFill("solid", bgColor="FFC7CE")))
w.conditional_formatting.add(f"K{R0+1}:K{RL}", DataBarRule(start_type="min", end_type="max", color="5B9BD5"))

# =============================================================== Unit Economics
u = wb.create_sheet("Unit Economics")
title(u, "Unit Economics by Acquisition Channel", "LTV = ARPA / monthly logo churn.  CAC = channel spend / new customers.  Benchmark: LTV:CAC >= 3x, payback < 12 months.")
header(u, 4, ["Channel", "New customers", "Total spend", "ARPA (monthly)", "Monthly churn", "LTV", "CAC",
              "LTV : CAC", "CAC payback (months)", "Status"])
for i, r in ue.iterrows():
    row = 5 + i
    u.cell(row, 1, r["acquisition_channel"]).font = F_IN
    u.cell(row, 2, int(r["new_customers"])).font = F_IN
    u.cell(row, 3, float(r["total_spend"])).font = F_IN
    u.cell(row, 4, float(r["arpa"])).font = F_IN
    u.cell(row, 5, float(r["monthly_churn_pct"]) / 100).font = F_IN
    u.cell(row, 6, f"=D{row}/E{row}")
    u.cell(row, 7, f"=C{row}/B{row}")
    u.cell(row, 8, f"=F{row}/G{row}")
    u.cell(row, 9, f"=G{row}/D{row}")
    u.cell(row, 10, f'=IF(AND(H{row}>=3,I{row}<12),"Healthy",IF(H{row}>=3,"Slow payback","Below 3x"))')
    for c in range(1, 11):
        u.cell(row, c).border = BOX
        if u.cell(row, c).font != F_IN:
            u.cell(row, c).font = F_CALC
    for c, f in [(2, INT), (3, USD), (4, USD2), (5, "0.00%"), (6, USD), (7, USD), (8, '0.00"x"'), (9, "0.0")]:
        u.cell(row, c).number_format = f
UE_L = 4 + len(ue)
tr = UE_L + 1   # blended row (weights = new customers)
u.cell(tr, 1, "Blended (weighted)").font = F_B
u.cell(tr, 2, f"=SUM(B5:B{UE_L})")
u.cell(tr, 3, f"=SUM(C5:C{UE_L})")
u.cell(tr, 4, f"=SUMPRODUCT(D5:D{UE_L},B5:B{UE_L})/B{tr}")
u.cell(tr, 5, f"=SUMPRODUCT(E5:E{UE_L},B5:B{UE_L})/B{tr}")
u.cell(tr, 6, f"=SUMPRODUCT(F5:F{UE_L},B5:B{UE_L})/B{tr}")   # customer-weighted LTV (same definition as Scenario sheet)
u.cell(tr, 7, f"=C{tr}/B{tr}")
u.cell(tr, 8, f"=F{tr}/G{tr}")
u.cell(tr, 9, f"=G{tr}/D{tr}")
for c, f in [(2, INT), (3, USD), (4, USD2), (5, "0.00%"), (6, USD), (7, USD), (8, '0.00"x"'), (9, "0.0")]:
    u.cell(tr, c).number_format = f
for c in range(1, 11):
    u.cell(tr, c).font, u.cell(tr, c).fill, u.cell(tr, c).border = F_B, FILL_L, BOX
u.conditional_formatting.add(f"H5:H{UE_L}", CellIsRule(operator="lessThan", formula=["3"], fill=PatternFill("solid", bgColor="FFC7CE"), font=Font(color="9C0006")))
u.conditional_formatting.add(f"H5:H{UE_L}", CellIsRule(operator="greaterThanOrEqual", formula=["3"], fill=PatternFill("solid", bgColor="C6EFCE"), font=Font(color="006100")))
u.conditional_formatting.add(f"I5:I{UE_L}", CellIsRule(operator="greaterThanOrEqual", formula=["12"], font=Font(color="C00000", bold=True)))
for c, wd in zip("ABCDEFGHIJ", [20, 14, 14, 14, 13, 12, 12, 11, 14, 14]):
    u.column_dimensions[c].width = wd
ch = BarChart()
ch.type, ch.title, ch.style = "bar", "LTV : CAC by channel (target >= 3x)", 10
ch.add_data(Reference(u, min_col=8, min_row=4, max_row=UE_L), titles_from_data=True)
ch.set_categories(Reference(u, min_col=1, min_row=5, max_row=UE_L))
ch.legend, ch.height, ch.width = None, 8, 16
u.add_chart(ch, f"A{tr+3}")

# =============================================================== Cohort Retention
c = wb.create_sheet("Cohort Retention")
title(c, "Logo Retention by Signup Cohort", "% of each signup cohort still active N months after signup (blank = not yet observable).")
piv = coh.pivot(index="cohort", columns="months_since_signup", values="retention_pct")
sizes = coh.drop_duplicates("cohort").set_index("cohort")["cohort_size"]
header(c, 4, ["Cohort", "Cohort size"] + [f"M{k}" for k in range(0, 13)])
for i, (coh_m, row_vals) in enumerate(piv.iterrows()):
    row = 5 + i
    c.cell(row, 1, coh_m).font = F_IN
    c.cell(row, 2, int(sizes[coh_m])).font = F_IN
    for k in range(0, 13):
        v = row_vals.get(k)
        cell = c.cell(row, 3 + k, None if pd.isna(v) else float(v) / 100)
        cell.number_format, cell.font, cell.border = "0%", F_IN, BOX
        cell.alignment = Alignment(horizontal="center")
CL = 4 + len(piv)
c.conditional_formatting.add(f"C5:O{CL}", ColorScaleRule(start_type="num", start_value=0.4, start_color="F8696B",
                                                      mid_type="num", mid_value=0.75, mid_color="FFEB84",
                                                      end_type="num", end_value=1, end_color="63BE7B"))
avg_r = CL + 1
c.cell(avg_r, 1, "Average").font = F_B
for k in range(0, 13):
    col = L(3 + k)
    cell = c.cell(avg_r, 3 + k, f'=IFERROR(AVERAGE({col}5:{col}{CL}),"")')
    cell.number_format, cell.font, cell.fill, cell.border = "0%", F_B, FILL_L, BOX
    cell.alignment = Alignment(horizontal="center")
c.column_dimensions["A"].width, c.column_dimensions["B"].width = 11, 12
c.freeze_panes = "C5"

# =============================================================== Churn Risk
k = wb.create_sheet("Churn Risk")
cm = [m for m in res["metrics"] if m["selected"]][0]
title(k, "Churn Risk - Account Scoring", f"Model: {res['selected_model']} | 3-month horizon | held-out ROC-AUC {cm['roc_auc']} | top-decile lift {cm['lift_at_top10pct']}x. Synthetic data.")
header(k, 4, ["Risk tier", "Customers", "MRR", "Expected 3m MRR loss", "% of expected loss"])
T0 = 12                       # data table header row
DL = T0 + len(scores)
for i, tier in enumerate(["High", "Medium", "Low"]):
    r = 5 + i
    k.cell(r, 1, tier).font = F_B
    k.cell(r, 2, f'=COUNTIF($L${T0+1}:$L${DL},A{r})')
    k.cell(r, 3, f'=SUMIF($L${T0+1}:$L${DL},A{r},$F${T0+1}:$F${DL})')
    k.cell(r, 4, f'=SUMIF($L${T0+1}:$L${DL},A{r},$N${T0+1}:$N${DL})')
    k.cell(r, 5, f"=D{r}/D$8")
    for cc, f in [(2, INT), (3, USD), (4, USD), (5, PCT)]:
        k.cell(r, cc).number_format = f
for cc in range(1, 6):
    k.cell(8, cc).font, k.cell(8, cc).fill = F_B, FILL_L
k.cell(8, 1, "Total")
for cc, col in [(2, "B"), (3, "C"), (4, "D")]:
    k.cell(8, cc, f"=SUM({col}5:{col}7)").number_format = USD if cc > 2 else INT
k.cell(8, 5, "=SUM(E5:E7)").number_format = PCT
for r in range(5, 9):
    for cc in range(1, 6):
        k.cell(r, cc).border = BOX
k.cell(10, 1, "All active accounts, sorted by expected MRR loss (probability x MRR). Tiers = top 10% / next 20% / rest by score.").font = F_SUB
hdr = ["Customer", "Plan", "Region", "Company size", "Channel", "MRR", "Engagement", "Engagement chg (1m)",
       "Tickets (3m)", "Tenure (m)", "Churn prob (3m)", "Risk tier", "Primary drivers", "Expected loss"]
header(k, T0, hdr)
for i, r in scores.reset_index(drop=True).iterrows():
    row = T0 + 1 + i
    vals = [r.customer_id, r.plan, r.region, r.company_size, r.acquisition_channel, r.active_mrr,
            r.engagement_score, r.eng_delta_1m, r.tickets_roll3, r.tenure_months, r.churn_prob_3m,
            r.risk_tier, r.primary_drivers, r.expected_mrr_loss]
    for j, v in enumerate(vals):
        cell = k.cell(row, 1 + j, v)
        cell.font = F_IN
    k.cell(row, 6).number_format = USD
    k.cell(row, 7).number_format = "0.00"
    k.cell(row, 8).number_format = "+0.00;-0.00;0.00"
    k.cell(row, 11).number_format = PCT
    k.cell(row, 14).number_format = USD2
k.auto_filter.ref = f"A{T0}:N{DL}"
k.freeze_panes = f"B{T0+1}"
k.conditional_formatting.add(f"K{T0+1}:K{DL}", DataBarRule(start_type="num", start_value=0, end_type="max", color="E57373"))
k.conditional_formatting.add(f"L{T0+1}:L{DL}", FormulaRule(formula=[f'$L{T0+1}="High"'], fill=PatternFill("solid", bgColor="FFC7CE"), font=Font(color="9C0006", bold=True)))
k.conditional_formatting.add(f"L{T0+1}:L{DL}", FormulaRule(formula=[f'$L{T0+1}="Medium"'], fill=PatternFill("solid", bgColor="FFEB9C")))
for col, wd in zip("ABCDEFGHIJKLMN", [12, 11, 14, 12, 16, 10, 11, 12, 10, 9, 13, 10, 40, 13]):
    k.column_dimensions[col].width = wd

# =============================================================== Scenario Model
s = wb.create_sheet("Scenario Model")
title(s, "What-if: Retention & Acquisition Efficiency", "Change the yellow input cells. All outputs recalculate from 'Unit Economics'.")
s["A4"], s["A4"].font = "INPUTS", F_B
s["A5"], s["B5"] = "Reduction in monthly logo churn (relative)", 0.10
s["A6"], s["B6"] = "CAC reduction on channels below 3x LTV:CAC", 0.10
for r in (5, 6):
    s.cell(r, 2).fill, s.cell(r, 2).font, s.cell(r, 2).number_format, s.cell(r, 2).border = FILL_IN, Font(name="Calibri", size=11, bold=True, color="0000FF"), "0%", BOX
header(s, 9, ["Channel", "New customers", "Base LTV", "Base CAC", "Base LTV:CAC", "Scenario churn",
              "Scenario LTV", "Scenario CAC", "Scenario LTV:CAC", "Change (x)"])
for i in range(len(ue)):
    r, src = 10 + i, 5 + i
    s.cell(r, 1, f"='Unit Economics'!A{src}")
    s.cell(r, 2, f"='Unit Economics'!B{src}")
    s.cell(r, 3, f"='Unit Economics'!F{src}")
    s.cell(r, 4, f"='Unit Economics'!G{src}")
    s.cell(r, 5, f"='Unit Economics'!H{src}")
    s.cell(r, 6, f"='Unit Economics'!E{src}*(1-$B$5)")
    s.cell(r, 7, f"='Unit Economics'!D{src}/F{r}")
    s.cell(r, 8, f"=IF(E{r}<3,D{r}*(1-$B$6),D{r})")
    s.cell(r, 9, f"=G{r}/H{r}")
    s.cell(r, 10, f"=I{r}-E{r}")
    for cc, f in [(2, INT), (3, USD), (4, USD), (5, '0.00"x"'), (6, "0.00%"), (7, USD), (8, USD), (9, '0.00"x"'), (10, '+0.00"x";-0.00"x"')]:
        s.cell(r, cc).number_format = f
    for cc in range(1, 11):
        s.cell(r, cc).border, s.cell(r, cc).font = BOX, F_CALC
SL = 9 + len(ue)
b = SL + 1
s.cell(b, 1, "Blended (weighted by new customers)")
s.cell(b, 2, f"=SUM(B10:B{SL})")
s.cell(b, 3, f"=SUMPRODUCT(C10:C{SL},B10:B{SL})/B{b}")
s.cell(b, 4, f"=SUMPRODUCT(D10:D{SL},B10:B{SL})/B{b}")
s.cell(b, 5, f"=C{b}/D{b}")
s.cell(b, 7, f"=SUMPRODUCT(G10:G{SL},B10:B{SL})/B{b}")
s.cell(b, 8, f"=SUMPRODUCT(H10:H{SL},B10:B{SL})/B{b}")
s.cell(b, 9, f"=G{b}/H{b}")
s.cell(b, 10, f"=I{b}-E{b}")
for cc, f in [(2, INT), (3, USD), (4, USD), (5, '0.00"x"'), (7, USD), (8, USD), (9, '0.00"x"'), (10, '+0.00"x";-0.00"x"')]:
    s.cell(b, cc).number_format = f
for cc in range(1, 11):
    s.cell(b, cc).font, s.cell(b, cc).fill, s.cell(b, cc).border = F_B, FILL_L, BOX
s.conditional_formatting.add(f"I10:I{SL}", CellIsRule(operator="lessThan", formula=["3"], font=Font(color="C00000", bold=True)))
s.cell(b + 2, 1, "Note: a relative churn reduction raises LTV on every channel; the CAC lever applies only to channels currently below 3x. "
                 "Channel-level elasticities are assumptions, not estimates from this data.").font = F_SUB
for col, wd in zip("ABCDEFGHIJ", [40, 14, 12, 12, 13, 14, 13, 13, 15, 12]):
    s.column_dimensions[col].width = wd

# =============================================================== Executive Summary (first sheet)
e = wb.create_sheet("Executive Summary", 0)
title(e, "SaaS Executive Summary", f"As of {mrr.iloc[-1]['month']}  |  all KPIs link to the 'MRR Waterfall' and 'Unit Economics' sheets  |  synthetic dataset")
M = "'MRR Waterfall'!"
kpis = [
    ("Ending MRR", f"={M}G{RL}", USD), ("ARR", f"={M}J{RL}", USD), ("MoM growth", f"={M}K{RL}", PCT),
    ("Active customers", f"={M}O{RL}", INT), ("NRR (month)", f"={M}N{RL}", PCT), ("GRR (month)", f"={M}M{RL}", PCT),
    ("NRR (TTM avg)", f"=AVERAGE({M}N{RL-11}:N{RL})", PCT), ("Logo churn (TTM avg)", f"=AVERAGE({M}R{RL-11}:R{RL})", PCT),
    ("Blended LTV : CAC", f"='Unit Economics'!H{tr}", '0.00"x"'), ("Blended CAC payback (mo)", f"='Unit Economics'!I{tr}", "0.0"),
    ("TTM new MRR", f"=SUM({M}C{RL-11}:C{RL})", USD), ("TTM expansion MRR", f"=SUM({M}D{RL-11}:D{RL})", USD),
]
for i, (lab, f, nf) in enumerate(kpis):
    r, cc = 4 + (i // 4) * 3, 1 + (i % 4) * 2
    e.cell(r, cc, lab).font = Font(name="Calibri", size=9, color="666666")
    e.cell(r, cc).alignment = Alignment(horizontal="center")
    v = e.cell(r + 1, cc, f)
    v.font, v.number_format = Font(name="Calibri", size=18, bold=True, color=NAVY), nf
    v.alignment = Alignment(horizontal="center")
    for rr in (r, r + 1):
        e.cell(rr, cc).fill = FILL_L
        e.cell(rr, cc + 1).fill = FILL_L
    e.merge_cells(start_row=r, start_column=cc, end_row=r, end_column=cc + 1)
    e.merge_cells(start_row=r + 1, start_column=cc, end_row=r + 1, end_column=cc + 1)
for col in "ABCDEFGH":
    e.column_dimensions[col].width = 15
e["A14"], e["A14"].font = "Data integrity", F_B
e["A15"] = f'=IF(SUMPRODUCT(ABS({M}I{R0}:I{RL}))<0.5,"PASS - rebuilt MRR waterfall reconciles to the warehouse in all {n} months","CHECK - reconciliation difference detected")'
e["A15"].font = Font(name="Calibri", size=10, bold=True, color="006100")
e["A17"], e["A17"].font = "Reading guide", F_B
for i, t in enumerate([
    "MRR Waterfall: starting + new + expansion - contraction - churned = ending; NRR/GRR derived by formula.",
    "Unit Economics: LTV:CAC and payback by channel, flagged against the 3x / 12-month benchmarks.",
    "Cohort Retention: retention heat-map by signup month.   Churn Risk: scored accounts (filterable).",
    "Scenario Model: change the yellow cells to test churn and CAC improvements.",
]):
    e.cell(18 + i, 1, t).font = Font(name="Calibri", size=10)

# charts on summary
bc = BarChart()
bc.type, bc.grouping, bc.overlap, bc.title, bc.style = "col", "stacked", 100, "MRR movements (monthly)", 10
for col in (3, 4, 19, 20):
    bc.add_data(Reference(w, min_col=col, min_row=HR, max_row=RL), titles_from_data=True)
bc.set_categories(Reference(w, min_col=1, min_row=R0, max_row=RL))
bc.height, bc.width = 8.5, 17
e.add_chart(bc, "A24")
lc = LineChart()
lc.title, lc.style, lc.height, lc.width = "Ending MRR", 12, 8.5, 14
lc.add_data(Reference(w, min_col=7, min_row=HR, max_row=RL), titles_from_data=True)
lc.set_categories(Reference(w, min_col=1, min_row=R0, max_row=RL))
lc.legend = None
e.add_chart(lc, "F24")

for ws in wb.worksheets:
    ws.page_setup.orientation, ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = "landscape", 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True

wb.save("excel/SaaS_Executive_Report.xlsx")
print("saved excel/SaaS_Executive_Report.xlsx")
