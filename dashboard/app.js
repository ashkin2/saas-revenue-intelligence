/* app.js - renders every dashboard section from window.DASHBOARD_DATA (no framework, no network) */
(function () {
  const D = window.DASHBOARD_DATA;
  const $ = id => document.getElementById(id);
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const C = () => ({ navy: css('--navy'), blue: css('--blue'), green: css('--green'), amber: css('--amber'), red: css('--red'), purple: css('--purple'), teal: css('--teal'), mute: css('--mute') });
  const usd = v => '$' + Math.round(v).toLocaleString('en-US');
  const usdK = v => Math.abs(v) >= 1e6 ? '$' + (v / 1e6).toFixed(1) + 'M' : Math.abs(v) >= 1e3 ? '$' + Math.round(v / 1e3) + 'K' : '$' + Math.round(v);
  const pct = (v, d = 1) => v.toFixed(d) + '%';
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const mon = m => { const [y, mm] = m.split('-'); return ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][+mm - 1] + " '" + y.slice(2); };
  const K = D.kpi;

  $('sub').textContent = `As of ${mon(K.as_of)} | synthetic data: 1,800 customers, 24 months | SQL + Python + Excel + Power BI + ML + LLM`;

  /* ---------------------------------------------------------------- KPI cards */
  const delta = (v, unit, goodUp = true) => {
    const cls = Math.abs(v) < 0.005 ? 'flat' : ((v > 0) === goodUp ? 'up' : 'down');
    const arrow = v > 0 ? '▲' : v < 0 ? '▼' : '●';
    return `<span class="${cls}">${arrow} ${Math.abs(v).toFixed(unit === 'pts' ? 2 : 2)}${unit === 'pts' ? ' pts' : '%'} vs prior month</span>`;
  };
  const kpis = [
    ['Ending MRR', usd(K.ending_mrr), delta(K.mrr_delta_pct, '%'), 'Monthly recurring revenue'],
    ['ARR', usd(K.arr), '<span class="flat">MRR x 12</span>', 'Annualised run-rate'],
    ['Active customers', K.active_customers.toLocaleString(), `<span class="${K.customers_delta >= 0 ? 'up' : 'down'}">${K.customers_delta >= 0 ? '▲' : '▼'} ${Math.abs(K.customers_delta)} net vs prior month</span>`, 'Paying accounts'],
    ['Net revenue retention', pct(K.nrr_month), delta(K.nrr_delta_pts, 'pts'), `TTM average ${pct(K.nrr_ttm)} | benchmark 100%+`],
    ['Gross revenue retention', pct(K.grr_month), delta(K.grr_delta_pts, 'pts'), 'Excludes expansion'],
    ['Logo churn (monthly)', pct(K.logo_churn_month, 2), delta(K.logo_churn_delta_pts, 'pts', false), `TTM average ${pct(K.logo_churn_ttm)}`],
    ['LTV : CAC (blended)', K.ltv_cac_blended.toFixed(2) + 'x', `<span class="${K.ltv_cac_blended >= 3 ? 'up' : 'down'}">${K.ltv_cac_blended >= 3 ? 'At or above' : 'Below'} 3x benchmark</span>`, 'Customer-weighted'],
    ['CAC payback', K.cac_payback_blended.toFixed(1) + ' mo', `<span class="${K.cac_payback_blended <= 12 ? 'up' : 'down'}">${K.cac_payback_blended <= 12 ? 'Within' : 'Over'} 12-month benchmark</span>`, 'Blended CAC / ARPA'],
  ];
  $('kpis').innerHTML = kpis.map(k => `<div class="kpi"><div class="l">${k[0]}</div><div class="v">${k[1]}</div><div class="d">${k[2]}</div><div class="n">${k[3]}</div></div>`).join('');

  /* ---------------------------------------------------------------- AI strip + AI tab */
  const A = D.ai;
  $('aiStrip').innerHTML = `<span class="badge b-ai">AI summary</span>${esc(A.executive_summary)} <span class="note">Every figure was checked against the KPI layer (${A._meta.grounding_check.numbers_checked} checked, ${A._meta.grounding_check.unsupported.length} unsupported).</span>`;
  $('aiSummary').innerHTML = `<p style="margin:6px 0 0">${esc(A.executive_summary)}</p>`;
  $('aiMeta').innerHTML = `
    <div class="flow"><div>SQL KPI layer</div><i>→</i><div>kpi_context.json</div><i>→</i><div>LLM</div><i>→</i><div>Grounding check</div><i>→</i><div>Dashboard</div></div>
    <p style="margin:8px 0 4px"><span class="badge ${A._meta.grounding_check.passed ? 'b-ok' : 'b-red'}">${A._meta.grounding_check.passed ? 'Grounding passed' : 'Grounding failed'}</span>
    ${A._meta.grounding_check.numbers_checked} numeric claims verified against source data, ${A._meta.grounding_check.unsupported.length} unsupported.</p>
    <p class="note" style="margin:4px 0">${esc(A._meta.generated_by)}</p>
    <p class="note" style="margin:4px 0">The checker is unit-aware (a $ figure cannot be validated by a matching percentage) and was tested against fabricated numbers.</p>`;
  const ins = x => `<div class="insight"><h4>${esc(x.title)}</h4><p><b>Evidence:</b> ${esc(x.evidence)}</p><p class="so"><b>So what:</b> ${esc(x.so_what)}</p></div>`;
  $('aiRisks').innerHTML = A.key_risks.map(ins).join('');
  $('aiOpps').innerHTML = A.opportunities.map(ins).join('');
  $('aiActs').innerHTML = A.recommended_actions.map(a => `<div class="act"><div class="pr">${a.priority}</div><div><b>${esc(a.action)}</b>
    <div class="m"><b>Owner:</b> ${esc(a.owner)} &nbsp;|&nbsp; <b>Success metric:</b> ${esc(a.success_metric)}</div><div class="m">${esc(a.rationale)}</div></div></div>`).join('');
  $('aiCav').innerHTML = A.caveats.map(c => `<li style="margin:3px 0;font-size:12.5px">${esc(c)}</li>`).join('');

  /* ---------------------------------------------------------------- tables */
  const tierBadge = t => `<span class="badge ${t === 'High' ? 'b-red' : t === 'Medium' ? 'b-warn' : 'b-ok'}">${t}</span>`;
  function tables() {
    const col = C(), ue = D.unit_economics.slice().sort((a, b) => b.ltv_to_cac - a.ltv_to_cac);
    $('ueTbl').innerHTML = `<thead><tr><th>Channel</th><th class="num">New customers</th><th class="num">Spend</th><th class="num">CAC</th><th class="num">ARPA</th><th class="num">Monthly churn</th><th class="num">LTV</th><th class="num">LTV:CAC</th><th class="num">Payback (mo)</th><th>Verdict</th></tr></thead><tbody>` +
      ue.map(r => {
        const ok = r.ltv_to_cac >= 3 && r.cac_payback_months <= 12;
        return `<tr><td><b>${esc(r.acquisition_channel)}</b></td><td class="num">${r.new_customers.toLocaleString()}</td><td class="num">${usd(r.total_spend)}</td><td class="num">${usd(r.cac)}</td><td class="num">${usd(r.arpa)}</td><td class="num">${pct(r.monthly_churn_pct, 2)}</td><td class="num">${usd(r.ltv)}</td><td class="num"><b>${r.ltv_to_cac.toFixed(2)}x</b></td><td class="num">${r.cac_payback_months.toFixed(1)}</td><td><span class="badge ${ok ? 'b-ok' : r.ltv_to_cac >= 3 ? 'b-warn' : 'b-red'}">${ok ? 'Scale' : r.ltv_to_cac >= 3 ? 'Watch payback' : 'Fix or cut'}</span></td></tr>`;
      }).join('') + '</tbody>';

    const best = ue[0], worst = ue[ue.length - 1];
    $('ueStrip').innerHTML = `<b>Takeaway:</b> ${esc(best.acquisition_channel)} returns ${best.ltv_to_cac.toFixed(2)}x LTV:CAC while ${esc(worst.acquisition_channel)} returns ${worst.ltv_to_cac.toFixed(2)}x. ${ue.filter(r => r.ltv_to_cac < 3).length} of ${ue.length} channels sit below the 3x benchmark.`;

    $('modelTbl').innerHTML = `<thead><tr><th>Model</th><th class="num">Validation AUC</th><th class="num">Test ROC-AUC</th><th class="num">PR-AUC</th><th class="num">Precision @ top 10%</th><th class="num">Lift @ top 10%</th><th class="num">Recall @ top 10%</th><th></th></tr></thead><tbody>` +
      D.model.metrics.map(m => `<tr><td><b>${esc(m.model)}</b></td><td class="num">${m.validation_auc.toFixed(3)}</td><td class="num">${m.roc_auc.toFixed(3)}</td><td class="num">${m.pr_auc.toFixed(3)}</td><td class="num">${m.precision_at_top10pct.toFixed(3)}</td><td class="num">${m.lift_at_top10pct.toFixed(2)}x</td><td class="num">${m.recall_at_top10pct.toFixed(3)}</td><td>${m.selected ? '<span class="badge b-ok">Selected</span>' : ''}</td></tr>`).join('') + '</tbody>';

    const maxL = Math.max(...D.model.top_at_risk.map(r => r.expected_mrr_loss));
    $('riskTbl').innerHTML = `<thead><tr><th>Customer</th><th>Plan</th><th>Region</th><th class="num">MRR</th><th class="num">3-mo churn prob.</th><th>Tier</th><th>Expected MRR loss</th><th>Main drivers</th></tr></thead><tbody>` +
      D.model.top_at_risk.slice(0, 12).map(r => `<tr><td>${esc(r.customer_id)}</td><td>${esc(r.plan)}</td><td>${esc(r.region)}</td><td class="num">${usd(r.active_mrr)}</td><td class="num">${pct(r.churn_prob_3m * 100)}</td><td>${tierBadge(r.risk_tier)}</td>
      <td><span class="bar" style="width:${Math.max(4, r.expected_mrr_loss / maxL * 80)}px"></span> ${usd(r.expected_mrr_loss)}</td><td>${esc(r.primary_drivers)}</td></tr>`).join('') + '</tbody>';

    const M = D.model, rs = M.risk_summary;
    $('modelStrip').innerHTML = `<b>${esc(M.selected)}</b> predicts churn within ${M.horizon} months. Held-out ROC-AUC <b>${M.metrics[0].roc_auc.toFixed(3)}</b>; the top 10% of scored accounts churn at <b>${M.metrics[0].lift_at_top10pct.toFixed(2)}x</b> the base rate. A moderate, honest signal on simulated data: useful for prioritising outreach, not for certainty. Total expected 3-month MRR loss: <b>${usd(M.total_expected_loss)}</b>.`;
    $('tiers').innerHTML = rs.map(t => `<div class="tier"><div class="t">${tierBadge(t.risk_tier)} ${t.risk_tier} risk</div><div class="big">${t.customers.toLocaleString()} accounts</div><small>${usd(t.mrr)} MRR | avg probability ${pct(t.avg_prob * 100)}</small><small>Expected 3-month loss <b>${usd(t.expected_loss)}</b></small></div>`).join('');

    // cohort heat table
    const rows = D.cohort.rows, lo = 40, hi = 100;
    const shade = v => { const t = Math.max(0, Math.min(1, (v - lo) / (hi - lo))); const a = 0.12 + t * 0.78; return `rgba(46,134,222,${a.toFixed(2)})`; };
    $('cohortTbl').innerHTML = `<thead><tr><th>Cohort</th><th class="num">Size</th>${D.cohort.months.map(k => `<th class="num">M${k}</th>`).join('')}</tr></thead><tbody>` +
      rows.map(r => `<tr><td class="h">${mon(r.cohort)}</td><td class="h">${r.size}</td>${r.values.map(v => v == null ? '<td></td>' : `<td style="background:${shade(v)};color:${v > 72 ? '#fff' : 'var(--ink)'}">${v.toFixed(0)}%</td>`).join('')}</tr>`).join('') + '</tbody>';
  }

  /* ---------------------------------------------------------------- charts */
  function charts() {
    const c = C(), months = D.mrr.map(r => mon(r.month));
    MC.chart('cWaterfall', {
      labels: months, yFmt: usdK, y2Fmt: usdK, maxBar: 26, xLabelWidth: 46,
      series: [
        { type: 'bar', stack: 's', name: 'New MRR', color: c.green, data: D.mrr.map(r => r.new_mrr), fmt: usd },
        { type: 'bar', stack: 's', name: 'Expansion', color: c.blue, data: D.mrr.map(r => r.expansion_mrr), fmt: usd },
        { type: 'bar', stack: 's', name: 'Contraction', color: c.amber, data: D.mrr.map(r => -r.contraction_mrr), fmt: usd, rawSign: true },
        { type: 'bar', stack: 's', name: 'Churned', color: c.red, data: D.mrr.map(r => -r.churned_mrr), fmt: usd, rawSign: true },
        { type: 'line', axis: 'right', name: 'Ending MRR', color: c.navy, data: D.mrr.map(r => r.ending_mrr), fmt: usd, points: true },
      ],
    });
    const pm = D.plan_mix;
    MC.chart('cPlan', {
      labels: pm.months.map(mon), yFmt: usdK, maxBar: 26, xLabelWidth: 46,
      series: [['Starter', c.teal], ['Growth', c.blue], ['Enterprise', c.navy]].map(([p, col]) => ({ type: 'bar', stack: 'p', name: p, color: col, data: pm.series[p], fmt: usd })),
    });
    const F = D.forecast, hist = F.history, fc = F.forecast, labs = hist.map(r => r.month).concat(fc.map(r => r.month)), nh = hist.length;
    const pad = a => a.concat(Array(fc.length).fill(null)), lead = a => Array(nh).fill(null).concat(a);
    const join = D.mrr[D.mrr.length - 1].ending_mrr;
    MC.chart('cForecast', {
      labels: labs.map(mon), yFmt: usdK, xLabelWidth: 46, yMin: 0,
      series: [
        { type: 'band', name: '80% interval', color: c.blue, low: Array(nh - 1).fill(null).concat([join], fc.map(r => r.low)), high: Array(nh - 1).fill(null).concat([join], fc.map(r => r.high)), fmt: usd },
        { type: 'line', name: 'Actual MRR', color: c.navy, data: pad(hist.map(r => r.mrr)), fmt: usd },
        { type: 'line', name: 'Forecast', color: c.blue, dash: '6 4', data: Array(nh - 1).fill(null).concat([join], fc.map(r => r.mrr)), fmt: usd, points: true },
      ],
    });
    $('fcDesc').textContent = `${F.method}. 6-month backtest MAPE ${F.backtest[F.backtest.length - 1].mape_pct}%. Interval is optimistic: only ${F.backtest_origins} backtest origins.`;
    MC.hbar('cRegion', { labels: D.region_mrr.map(r => r.region), values: D.region_mrr.map(r => r.mrr), color: c.navy, fmt: usd, tickFmt: usdK, name: 'MRR',
      extra: D.region_mrr.map(r => `<div>Customers: <b>${r.customers.toLocaleString()}</b></div>`) });

    const rt = D.retention, rm = rt.map(r => mon(r.month));
    MC.chart('cNrr', { labels: rm, yFmt: v => v + '%', xLabelWidth: 46, series: [
      { type: 'ref', name: '100% line', color: c.mute, value: 100, label: '100%' },
      { type: 'line', name: 'NRR', color: c.navy, data: rt.map(r => r.nrr_pct), fmt: v => pct(v, 1), points: true },
      { type: 'line', name: 'GRR', color: c.teal, data: rt.map(r => r.grr_pct), fmt: v => pct(v, 1), points: true }] });
    MC.chart('cChurn', { labels: rm, yFmt: v => v + '%', xLabelWidth: 46, zero: true, series: [
      { type: 'line', name: 'Logo churn', color: c.red, data: rt.map(r => r.logo_churn_pct), fmt: v => pct(v, 2), points: true },
      { type: 'line', name: 'Revenue churn', color: c.amber, data: rt.map(r => r.revenue_churn_pct), fmt: v => pct(v, 2), points: true }] });

    const ue = D.unit_economics.slice().sort((a, b) => b.ltv_to_cac - a.ltv_to_cac), ch = ue.map(r => r.acquisition_channel);
    MC.chart('cLtv', { labels: ch, yFmt: v => v + 'x', maxBar: 44, xLabelWidth: 80, series: [
      { type: 'bar', name: 'LTV:CAC', color: c.navy, colors: ue.map(r => r.ltv_to_cac >= 3 ? c.green : c.red), data: ue.map(r => r.ltv_to_cac), fmt: v => v.toFixed(2) + 'x' },
      { type: 'ref', name: '3x benchmark', color: c.mute, value: 3, label: '3x benchmark', legend: false }] });
    MC.chart('cPay', { labels: ch, yFmt: v => v + ' mo', maxBar: 44, xLabelWidth: 80, series: [
      { type: 'bar', name: 'Payback', color: c.navy, colors: ue.map(r => r.cac_payback_months <= 12 ? c.green : c.red), data: ue.map(r => r.cac_payback_months), fmt: v => v.toFixed(1) + ' months' },
      { type: 'ref', name: '12-month benchmark', color: c.mute, value: 12, label: '12-month benchmark', legend: false }] });

    MC.hbar('cFeat', { labels: D.model.feature_importance.map(f => f.feature), values: D.model.feature_importance.map(f => f.importance), color: c.purple, fmt: v => v.toFixed(4), name: 'AUC drop', xTitle: 'Drop in ROC-AUC when shuffled' });
    MC.scatter('cCal', { points: D.model.calibration.map(b => ({ x: b.predicted, y: b.observed })), color: c.blue, fmt: v => (v * 100).toFixed(0) + '%', xTitle: 'Predicted 3-month churn', yTitle: 'Observed' });
  }

  /* ---------------------------------------------------------------- tabs + theme */
  const tabs = [...document.querySelectorAll('#nav button')];
  function show(name) {
    tabs.forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === name)));
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('on', t.id === 'tab-' + name));
    try { history.replaceState(null, '', '#' + name); } catch (e) { }
    requestAnimationFrame(charts);
  }
  tabs.forEach(b => b.addEventListener('click', () => show(b.dataset.tab)));
  $('themeBtn').addEventListener('click', () => {
    const dark = document.documentElement.dataset.theme === 'dark' || (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.dataset.theme = dark ? 'light' : 'dark';
    charts();
  });
  tables();
  const start = (location.hash || '').slice(1);
  show(tabs.some(b => b.dataset.tab === start) ? start : 'overview');
})();
