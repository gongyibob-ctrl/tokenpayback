const $ = (s) => document.querySelector(s);

function fmtMoney(v) {
  if (v == null) return "—";
  if (Math.abs(v) >= 1000) return "$" + Math.round(v).toLocaleString();
  return "$" + v.toFixed(2);
}

function fmtROI(r) {
  if (r == null || (typeof r === "number" && !isFinite(r))) return "—";
  if (r >= 100) return r.toFixed(0) + "×";
  if (r >= 10) return r.toFixed(1) + "×";
  if (r < 0) return r.toFixed(2) + "×";
  return r.toFixed(2) + "×";
}

function roiClass(r) {
  if (r == null) return "";
  if (r >= 3) return "roi-good";
  if (r >= 1) return "roi-mid";
  return "roi-bad";
}

function roiVerdict(r, cost) {
  if (r == null) return "no cost data";
  if (cost < 1) return "no cost data";
  if (r >= 10) return "🚀 AI is carrying you";
  if (r >= 3) return "✓ paying off comfortably";
  if (r >= 1) return "↗︎ barely breaking even";
  if (r > 0) return "⚠️ burning more than you ship";
  return "no output this week";
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function load() {
  const r = await fetch("data.json", { cache: "no-cache" });
  if (!r.ok) throw new Error("data.json missing");
  return r.json();
}

function renderHero(latest) {
  // Legacy engineering-ROI hero kept for the weeks chart; not the main hero anymore.
  const w = document.getElementById("latest-week"); if (w) w.textContent = latest.week;
}

function renderOverall(data) {
  const o = data.overall;
  if (!o) return;
  document.getElementById("overall-cost").textContent = fmtMoney(o.totalCostUsd);
  // "Saved vs hiring it out" — prefer analytics.parity (cleanest), fall back to overall
  const parity = data.analytics && data.analytics.parity;
  const savedUsd = parity ? parity.savedUsd : Math.max(0, (o.totalValueUsd || 0) - (o.totalCostUsd || 0));
  const humanEquiv = parity ? parity.humanEquivUsd : (o.totalValueUsd || 0);
  const savedEl = document.getElementById("overall-saved");
  if (savedEl) savedEl.textContent = fmtMoney(savedUsd);
  const savedSub = document.getElementById("overall-saved-sub");
  if (savedSub) savedSub.textContent = `${fmtMoney(humanEquiv)} hired out − ${fmtMoney(o.totalCostUsd)} AI`;
  const hrs = o.humanHoursSaved || 0;
  const days = o.humanDaysSaved || 0;
  document.getElementById("overall-hours").textContent = hrs >= 16
    ? `${days.toFixed(1)} days`
    : `${hrs.toFixed(1)} hrs`;
  const roiEl = document.getElementById("overall-roi");
  roiEl.textContent = fmtROI(o.roiMid);
  roiEl.className = "value roi " + roiClass(o.roiMid);
  const verdict = roiVerdict(o.roiMid, o.totalCostUsd);
  const rangeHint = (o.roiLow && o.roiHigh)
    ? ` · range ${fmtROI(o.roiLow)} — ${fmtROI(o.roiHigh)}`
    : "";
  document.getElementById("overall-roi-verdict").textContent = verdict + rangeHint;
  // Window label
  const sessionCount = (data.sessions || []).length;
  document.getElementById("overall-window").textContent = `across ${sessionCount} sessions`;
  // Benchmark info
  if (data.benchmark && data.benchmark.region) {
    const b = data.benchmark;
    const el = document.getElementById("benchmark-info");
    if (el) el.textContent = `${b.region} / ${b.seniority}`;
  }
}

const VC_LABEL = { VA: "Value-Added", NVA: "Non-Value-Added", BVA: "Business-Value-Added" };
const VC_BLURB = {
  VA:  "you'd pay for it — shipped artifact, fixed bug, useful answer",
  NVA: "burned tokens for nothing — retry / failed / harmful",
  BVA: "necessary overhead — research, scaffolding, context",
};

function renderWaste(data) {
  const nva = data.analytics && data.analytics.nva;
  if (!nva || !nva.byClass || !nva.byClass.length) return;
  document.getElementById("waste-section").hidden = false;
  // Health pill
  const hp = document.getElementById("nva-health");
  if (hp && nva.nvaHealthHint) {
    hp.textContent = nva.nvaHealthHint.label;
    hp.className = "health-pill health-" + nva.nvaHealthHint.band;
  }
  // Stacked bar
  const total = nva.totalCostUsd || 1;
  const bar = document.getElementById("vc-bar");
  bar.innerHTML = nva.byClass.map((c) => {
    const pct = Math.max(0.5, c.pct);
    return `<div class="vc-bar-seg vc-${c.class}" style="flex-basis:${pct}%" title="${c.class} ${c.pct.toFixed(1)}% · ${fmtMoney(c.costUsd)}"></div>`;
  }).join("");
  // Per-class breakdown rows
  const bd = document.getElementById("vc-breakdown");
  bd.innerHTML = nva.byClass.map((c) => `
    <div class="vc-row">
      <span class="vc-tag vc-${c.class}">${c.class}</span>
      <div class="vc-label">
        <div class="vc-label-main">${VC_LABEL[c.class] || c.class} <span class="muted">— ${VC_BLURB[c.class] || ""}</span></div>
        <div class="muted" style="font-size:11px">${c.sessionCount} session${c.sessionCount === 1 ? "" : "s"}</div>
      </div>
      <div class="vc-amount">${fmtMoney(c.costUsd)} <span class="muted">(${c.pct.toFixed(1)}%)</span></div>
    </div>
  `).join("");
  // Internal failure callout
  const fb = document.getElementById("failure-box");
  const fail = nva.internalFailure;
  if (fail && fail.costUsd > 0) {
    fb.hidden = false;
    let harmful = "";
    if (fail.harmfulCount > 0) {
      harmful = ` — including <b class="bad-text">${fail.harmfulCount} harmful session${fail.harmfulCount === 1 ? "" : "s"} (${fmtMoney(fail.harmfulCostUsd)})</b> where the agent made things worse`;
    }
    fb.innerHTML = `
      <div class="fb-label">🚨 Internal Failure Cost</div>
      <div class="fb-body">
        <b>${fmtMoney(fail.costUsd)}</b> burned across <b>${fail.sessionCount}</b> session${fail.sessionCount === 1 ? "" : "s"}
        that produced no usable output (${fail.pct.toFixed(1)}% of your spend)${harmful}.
        From <a href="https://en.wikipedia.org/wiki/Cost_of_poor_quality" target="_blank" rel="noopener">Juran's PAF model</a> —
        these are the sessions where changing your prompt or tool choice has the biggest payback.
      </div>
    `;
  }
}

function renderDrift(data) {
  const v = data.analytics && data.analytics.variance;
  if (!v || !v.signals || !v.signals.length) return;
  document.getElementById("drift-section").hidden = false;
  const weeks = v.weeks || [];
  const period = weeks.length >= 2
    ? `${weeks[weeks.length - 1].week} vs baseline of prior ${Math.min(3, weeks.length - 1)} week${weeks.length > 2 ? "s" : ""}`
    : "needs more data";
  document.getElementById("drift-period").textContent = period;
  const fmtSignalVal = (label, val) => {
    if (val == null) return "—";
    if (label === "Yield Variance") return (val * 100).toFixed(1) + "%";
    if (label === "Rate Variance") return fmtMoney(val);
    if (label === "Efficiency Variance") return Math.round(val).toLocaleString() + " tk";
    return String(val);
  };
  const arrowFor = (sig) => {
    if (sig.verdict === "insufficient" || sig.deltaPct == null) return "·";
    if (sig.deltaPct > 0) return "↑";
    if (sig.deltaPct < 0) return "↓";
    return "→";
  };
  document.getElementById("drift-signals").innerHTML = v.signals.map((s) => {
    if (s.verdict === "insufficient") {
      return `<div class="signal signal-insufficient">
        <div class="sig-label">${s.label}</div>
        <div class="sig-val muted">—</div>
        <div class="sig-why muted">${escapeHtml(s.why || "not enough data yet")}</div>
      </div>`;
    }
    const arr = arrowFor(s);
    const deltaStr = s.deltaPct != null ? `${s.deltaPct > 0 ? "+" : ""}${s.deltaPct.toFixed(1)}%` : "";
    return `<div class="signal signal-${s.verdict}">
      <div class="sig-label">${s.label}</div>
      <div class="sig-val">
        <span class="sig-current">${fmtSignalVal(s.label, s.latest)}</span>
        <span class="sig-arrow">${arr}</span>
        <span class="sig-delta">${deltaStr}</span>
      </div>
      <div class="sig-baseline muted">vs baseline ${fmtSignalVal(s.label, s.baseline)}</div>
      <div class="sig-why">${escapeHtml(s.why)}</div>
    </div>`;
  }).join("");
}

function renderCostSplit(data) {
  const cs = data.analytics && data.analytics.costSplit;
  if (!cs) return;
  document.getElementById("costsplit-section").hidden = false;
  document.getElementById("split-prop").textContent =
    `${fmtMoney(cs.proportionalUsd)} (${cs.proportionalPct.toFixed(1)}%)`;
  document.getElementById("split-fixed").textContent =
    `${fmtMoney(cs.fixedWeeklyUsd)} (${cs.fixedPct.toFixed(1)}%)`;
  const ca = data.analytics.causality || {};
  document.getElementById("split-causality").textContent =
    ca.score != null ? `${ca.score}%` : "—";
  document.getElementById("split-causality-hint").textContent = ca.label || "";
  // Subscriptions
  const subs = cs.subscriptions || [];
  const tbody = document.getElementById("subs-tbody");
  if (!subs.length) {
    tbody.innerHTML = `<tr><td colspan="3" class="muted">no subscriptions configured</td></tr>`;
    return;
  }
  tbody.innerHTML = subs.map((s) => {
    const utilStr = s.utilizationPct == null ? "—" : `${s.utilizationPct.toFixed(0)}%`;
    const days = s.activeDays30d == null ? "—" : `${s.activeDays30d}/30d`;
    const verdictClass = "verdict-" + s.verdict;
    return `
      <tr>
        <td>
          <div><b>${escapeHtml(s.name)}</b> <span class="muted">${fmtMoney(s.monthlyUsd)}/mo</span></div>
          <div class="muted" style="font-size:11px">${escapeHtml(s.hint || "")}</div>
        </td>
        <td class="num">${days}<br><span class="muted" style="font-size:10px">${utilStr} util</span></td>
        <td><span class="verdict-pill ${verdictClass}">${escapeHtml(s.verdict)}</span></td>
      </tr>`;
  }).join("");
}

function renderValueStream(data) {
  const vs = (data.analytics && data.analytics.valueStream) || [];
  if (!vs.length) return;
  document.getElementById("vs-section").hidden = false;
  document.getElementById("vs-tbody").innerHTML = vs.slice(0, 12).map((v) => {
    const nvaCell = v.nvaPct == null ? "—" : (v.nvaPct > 30
      ? `<span class="bad-text">${v.nvaPct.toFixed(0)}%</span>`
      : `${v.nvaPct.toFixed(0)}%`);
    return `
      <tr>
        <td>${escapeHtml(v.project)}</td>
        <td class="num">${v.sessionCount}</td>
        <td><span class="muted" style="font-size:11px">${(v.agents || []).map(escapeHtml).join(" · ")}</span></td>
        <td class="num">${fmtMoney(v.costUsd)}</td>
        <td class="num">${fmtMoney(v.valueUsd)}</td>
        <td class="num ${roiClass(v.roi)}"><b>${fmtROI(v.roi)}</b></td>
        <td class="num">${nvaCell}</td>
      </tr>`;
  }).join("");
}

function renderRedundancy(data) {
  const r = data.analytics && data.analytics.redundancy;
  if (!r || !r.projects || !r.projects.length) return;
  document.getElementById("redundancy-section").hidden = false;
  document.getElementById("red-amount").textContent = fmtMoney(r.totalRecoverableUsd);
  document.getElementById("red-tbody").innerHTML = r.projects.map((p) => {
    const sec = (p.secondaryAgents || []).map((s) =>
      `${escapeHtml(s.agent)} (${fmtMoney(s.costUsd)})`
    ).join(" · ");
    return `
      <tr>
        <td>${escapeHtml(p.project)}</td>
        <td><b>${escapeHtml(p.primaryAgent)}</b></td>
        <td class="num">${fmtMoney(p.primaryCostUsd)}</td>
        <td>${sec}</td>
        <td class="num warn-amount">${fmtMoney(p.recoverableUsd)}</td>
      </tr>`;
  }).join("");
}

function renderFooterMeta(data) {
  const a = data.analytics || {};
  const ca = a.causality;
  const att = a.attended;
  const bits = [];
  if (ca && ca.score != null) {
    bits.push(`<span title="${escapeHtml(ca.label || '')}">causality ${ca.score}%</span>`);
  }
  if (att && att.autonomyRate != null) {
    bits.push(`<span>autonomy rate ${(att.autonomyRate * 100).toFixed(0)}%</span>`);
  }
  if (a.nva && a.nva.byClass) {
    const nvaSeg = a.nva.byClass.find((c) => c.class === "NVA");
    if (nvaSeg) bits.push(`<span>NVA share ${nvaSeg.pct.toFixed(1)}%</span>`);
  }
  const el = document.getElementById("footer-meta");
  if (el && bits.length) {
    el.innerHTML = bits.join(" &nbsp;·&nbsp; ");
  }
}

function renderChart(weeks) {
  const c = $("#bar-chart");
  c.innerHTML = "";
  const maxV = Math.max(...weeks.flatMap((w) => [w.cost_usd, w.value_usd]), 1);
  weeks.forEach((w) => {
    const g = document.createElement("div");
    g.className = "bar-group";
    const bars = document.createElement("div");
    bars.className = "bars";
    const costH = Math.max(2, (w.cost_usd / maxV) * 100);
    const valueH = Math.max(2, (w.value_usd / maxV) * 100);
    bars.innerHTML = `
      <div class="bar" style="height:${costH}%" title="cost: ${fmtMoney(w.cost_usd)}"></div>
      <div class="bar value" style="height:${valueH}%" title="value: ${fmtMoney(w.value_usd)}"></div>
    `;
    g.appendChild(bars);
    const lab = document.createElement("div");
    lab.className = "bar-label";
    lab.textContent = w.week.replace("2026-", "");
    g.appendChild(lab);
    const tip = document.createElement("div");
    tip.className = "bar-tooltip";
    tip.textContent = fmtROI(w.roi);
    g.appendChild(tip);
    c.appendChild(g);
  });
}

function renderTable(weeks) {
  const tbody = $("#weeks-table tbody");
  const latestWeek = weeks[weeks.length - 1]?.week;
  tbody.innerHTML = weeks.map((w) => `
    <tr class="${w.week === latestWeek ? 'latest' : ''}">
      <td>${w.week}</td>
      <td class="num">${fmtMoney(w.cost_usd)}</td>
      <td class="num">${fmtMoney(w.value_usd)}</td>
      <td class="num ${roiClass(w.roi)}"><strong>${fmtROI(w.roi)}</strong></td>
      <td class="num">${w.output.prs_merged}</td>
      <td class="num">${w.output.commits}</td>
      <td class="num">+${w.output.additions.toLocaleString()}</td>
      <td class="num">${w.output.reverts}</td>
    </tr>
  `).join("");
}

function renderBreakdown(latest) {
  const c = latest.cost;
  const v = latest.value_breakdown;
  $("#cost-breakdown").innerHTML = `
    <li><span class="k">Anthropic API</span><span class="v">${fmtMoney(c.anthropic_usd)}</span></li>
    <li><span class="k">OpenAI API</span><span class="v">${fmtMoney(c.openai_usd)}</span></li>
    <li><span class="k">Fixed subs (weekly)</span><span class="v">${fmtMoney(c.fixed_subscriptions_usd)}</span></li>
    <li><span class="k"><strong>Total</strong></span><span class="v"><strong>${fmtMoney(latest.cost_usd)}</strong></span></li>
  `;
  $("#value-breakdown").innerHTML = `
    <li><span class="k">${latest.output.prs_merged} PRs merged</span><span class="v">+${fmtMoney(v.pr_value_usd)}</span></li>
    <li><span class="k">${latest.output.additions.toLocaleString()} lines added</span><span class="v">+${fmtMoney(v.line_value_usd)}</span></li>
    <li><span class="k">${latest.output.reverts} reverts</span><span class="v">-${fmtMoney(v.revert_penalty_usd)}</span></li>
    <li><span class="k"><strong>Net value</strong></span><span class="v"><strong>${fmtMoney(latest.value_usd)}</strong></span></li>
  `;
}

function renderPRs(latest) {
  const list = $("#prs-list");
  const prs = latest.output.prs || [];
  if (!prs.length) {
    list.innerHTML = "<li><em>no PRs merged this week</em></li>";
    return;
  }
  list.innerHTML = prs.map((p) => `
    <li>
      <a href="${p.url}" target="_blank" rel="noopener">${escapeHtml(p.title)}</a>
      <div class="repo">${p.repo}</div>
    </li>
  `).join("");
}

function renderHeuristics(config) {
  $("#heuristics").innerHTML = `
    <li><span class="k">Hourly rate</span><span class="v">$${config.hourly_rate_usd}</span></li>
    <li><span class="k">Value per merged PR</span><span class="v">$${config.value_per_pr_usd}</span></li>
    <li><span class="k">Value per line added</span><span class="v">$${config.value_per_line_committed_usd}</span></li>
    <li><span class="k">GitHub user</span><span class="v">${config.github_username}</span></li>
  `;
}

function renderLosers(data) {
  const sessions = data.sessions || [];
  const QM = {"full-replacement":1.0,"with-edits":0.7,"draft-only":0.4,"failed":0,"harmful":-0.5};
  const losers = sessions.filter((s) => {
    const c = s.classification || {};
    const q = c.replacement_quality;
    const mMid = c.human_minutes_mid, rMid = c.hourly_rate_usd_mid;
    const qm = QM[q];
    if (qm == null) return false;
    if (q === "failed" || q === "harmful") return true;
    if (mMid != null && rMid != null && (s.est_cost_usd || 0) > 0) {
      const v = (mMid/60) * rMid * qm;
      return v / (s.est_cost_usd || 1) < 1;
    }
    return false;
  });
  if (!losers.length) return;
  document.getElementById("losers-section").hidden = false;
  document.getElementById("losers-tbody").innerHTML = losers.slice(0, 20).map((s) => {
    const c = s.classification || {};
    const q = c.replacement_quality || "—";
    const qm = QM[q] ?? null;
    const mMid = c.human_minutes_mid, rMid = c.hourly_rate_usd_mid;
    const cost = s.est_cost_usd || 0;
    let v = null, roi = null;
    if (mMid != null && rMid != null && qm != null) {
      v = (mMid/60) * rMid * qm;
      if (cost > 0) roi = v / cost;
    }
    const date = (s.last_event || "").slice(0, 10);
    return `
      <tr>
        <td>${date}</td>
        <td><span class="cat-tag">${escapeHtml(s.agent || "?")}</span></td>
        <td>${escapeHtml(c.project || "?")}</td>
        <td><span class="cat-tag cat-${escapeHtml(c.category || "")}">${escapeHtml(c.category || "?")}</span></td>
        <td>${escapeHtml(c.summary || "")}</td>
        <td><span class="cat-tag" style="color:#ff6b6b;border-color:#ff6b6b">${escapeHtml(q)} ${qm != null ? "×" + qm : ""}</span></td>
        <td class="num">${fmtMoney(cost)}</td>
        <td class="num">${v != null ? fmtMoney(v) : "—"}</td>
        <td class="num roi-bad"><strong>${fmtROI(roi)}</strong></td>
      </tr>`;
  }).join("");
}

function renderActivityHero(data) {
  const cats = data.byCategory || [];
  const grid = document.getElementById("activity-grid");
  if (!cats.length) { grid.innerHTML = "<div class=\"muted\">no sessions yet — run <code>tokenpayback</code> first</div>"; return; }
  grid.innerHTML = cats.map((c) => {
    const rangeTitle = `value range: ${fmtMoney(c.value_low_usd)} — ${fmtMoney(c.value_high_usd)} · ROI range: ${fmtROI(c.roi_low)} — ${fmtROI(c.roi_high)}`;
    const hrs = c.human_minutes_total != null ? (c.human_minutes_total / 60).toFixed(1) : null;
    return `
    <div class="activity-cell" title="${escapeHtml(rangeTitle)}">
      <div class="a-icon">${c.icon || "•"}</div>
      <div class="a-label">${escapeHtml(c.label || c.category)}</div>
      <div class="a-count">${c.count} <span class="muted" style="font-size:13px">session${c.count===1?"":"s"}</span></div>
      <div class="a-foot">
        <span>spent <b>${fmtMoney(c.cost_usd)}</b></span>
        <span>value <b>${fmtMoney(c.value_usd)}</b></span>
        <span class="a-roi ${roiClass(c.roi)}">${fmtROI(c.roi)}</span>
      </div>
      ${hrs ? `<div class="muted" style="font-size:11px;margin-top:4px">${hrs}h human time · range ${fmtMoney(c.value_low_usd)} — ${fmtMoney(c.value_high_usd)}</div>` : ""}
    </div>
  `;}).join("");
}

function renderAgents(data) {
  const agents = data.byAgent || [];
  if (!agents.length) return;
  document.getElementById("agents-section").hidden = false;
  const labels = {
    "claude-code": "Claude Code",
    "codex": "Codex CLI",
    "hermes": "Hermes",
    "openclaw": "OpenClaw 🦞",
    "openhuman": "OpenHuman",
    "cursor": "Cursor",
    "proxy": "Local Proxy",
  };
  const expand = (a) => {
    if ((a || "").startsWith("proxy:")) {
      return "Proxy / via " + a.slice("proxy:".length);
    }
    return labels[a] || a;
  };
  document.getElementById("agents-tbody").innerHTML = agents.map((a) => `
    <tr>
      <td>${escapeHtml(expand(a.agent))}</td>
      <td class="num">${a.count}</td>
      <td class="num">${fmtMoney(a.cost_usd)}</td>
      <td class="num">${fmtMoney(a.value_usd)}</td>
      <td class="num ${roiClass(a.roi)}"><strong>${fmtROI(a.roi)}</strong></td>
    </tr>
  `).join("");
}

function renderSessions(data) {
  const sessions = data.sessions || [];
  if (!sessions.length) return;
  document.getElementById("sessions-section").hidden = false;
  const agentLabel = {"claude-code": "Claude Code", "codex": "Codex", "hermes": "Hermes", "openclaw": "OpenClaw 🦞", "openhuman": "OpenHuman", "cursor": "Cursor", "proxy": "Proxy"};
  const sourceLabel = (s) => {
    if ((s.agent || "").startsWith("proxy:")) {
      const tool = s.agent.slice("proxy:".length);
      const upstream = (s.raw && s.raw.upstreams) ? Object.keys(s.raw.upstreams)[0] : "?";
      return { agent: "Proxy", via: tool + " → " + upstream };
    }
    return { agent: agentLabel[s.agent] || s.agent || "?", via: "—" };
  };
  const fmtMinutes = (m) => {
    if (m == null) return "—";
    if (m < 60) return `${Math.round(m)}m`;
    return `${(m/60).toFixed(1)}h`;
  };
  const QM = {"full-replacement":1.0,"with-edits":0.7,"draft-only":0.4,"failed":0};
  document.getElementById("sessions-tbody").innerHTML = sessions.slice(0, 60).map((s) => {
    const c = s.classification || {};
    const date = (s.last_event || "").slice(0, 10);
    const lbls = sourceLabel(s);
    const role = c.equivalent_role || "—";
    const mLow = c.human_minutes_low, mMid = c.human_minutes_mid, mHigh = c.human_minutes_high;
    const rLow = c.hourly_rate_usd_low, rMid = c.hourly_rate_usd_mid, rHigh = c.hourly_rate_usd_high;
    const timeCell = (mMid != null)
      ? `<span class="muted">${fmtMinutes(mLow)}</span> · <b>${fmtMinutes(mMid)}</b> · <span class="muted">${fmtMinutes(mHigh)}</span>`
      : "—";
    const rateCell = (rMid != null)
      ? `<span class="muted">$${rLow}</span> · <b>$${rMid}</b> · <span class="muted">$${rHigh}</span><span class="muted"> /hr</span>`
      : "—";
    const quality = c.replacement_quality || "—";
    const qm = QM[quality];
    const qmStr = qm != null ? qm.toFixed(qm === 1 ? 1 : 1) : "—";
    const qualityCell = `<span class="cat-tag">${escapeHtml(quality)}</span> <span class="muted">×${qmStr}</span>`;
    const cost = s.est_cost_usd || 0;
    let vLow = null, vMid = null, vHigh = null, roiLow = null, roiMid = null, roiHigh = null;
    if (mMid != null && rMid != null && qm != null) {
      vLow  = (mLow  / 60) * rLow  * qm;
      vMid  = (mMid  / 60) * rMid  * qm;
      vHigh = (mHigh / 60) * rHigh * qm;
      if (cost > 0) {
        roiLow  = vLow  / cost;
        roiMid  = vMid  / cost;
        roiHigh = vHigh / cost;
      }
    }
    const valueCell = vMid != null
      ? `<span class="muted">${fmtMoney(vLow)}</span> · <b>${fmtMoney(vMid)}</b> · <span class="muted">${fmtMoney(vHigh)}</span>`
      : "—";
    const roiCell = roiMid != null
      ? `<span class="muted">${fmtROI(roiLow)}</span> · <strong class="${roiClass(roiMid)}">${fmtROI(roiMid)}</strong> · <span class="muted">${fmtROI(roiHigh)}</span>`
      : "—";
    return `
      <tr>
        <td>${date}</td>
        <td><span class="cat-tag">${escapeHtml(lbls.agent)}</span></td>
        <td><span class="cat-tag">${escapeHtml(lbls.via)}</span></td>
        <td><span class="cat-tag cat-${escapeHtml(c.category || "")}">${escapeHtml(c.category || "?")}</span></td>
        <td>${escapeHtml(c.project || "?")}</td>
        <td>${escapeHtml(role)}</td>
        <td class="num">${timeCell}</td>
        <td class="num">${rateCell}</td>
        <td>${qualityCell}</td>
        <td class="num">${fmtMoney(cost)}</td>
        <td class="num">${valueCell}</td>
        <td class="num">${roiCell}</td>
      </tr>
    `;
  }).join("");
}

function renderValueModelTable() {
  const tbody = document.getElementById("value-model-tbody");
  if (!tbody) return;
  const rows = [
    ["🚢", "new-feature", "Code shipped — $50 baseline + $600/PR + $0.30/line"],
    ["➕", "extend-feature", "Code extended — $30 baseline + $400/PR"],
    ["🐛", "bug-fix", "Bug fixed — $80 baseline + $700/PR (high stakes)"],
    ["🔍", "debug", "Bug understood — $40 baseline (root cause is value, even without fix)"],
    ["🧹", "refactor", "Code cleaned — $30 baseline"],
    ["⚙️", "config-ops", "Infra changed — $60 baseline ('the deploy works now' is real)"],
    ["📚", "research", "Info gathered — $25 baseline (an answered question IS value)"],
    ["💡", "brainstorm", "Ideas explored — $20 baseline"],
    ["🎯", "personal-task", "Life shipped — $30 baseline + $0.20/file modified"],
    ["❓", "chat-misc", "Question answered — $5 baseline"],
  ];
  tbody.innerHTML = rows.map(([i, k, v]) => `<tr><td>${i}</td><td class="key">${k}</td><td>${v}</td></tr>`).join("");
}

async function main() {
  try {
    const data = await load();
    const weeks = data.weeks || [];
    $("#meta").textContent = `generated ${new Date(data.generatedAt).toLocaleString()}`;
    // Overall + activity work regardless of weeks data
    renderOverall(data);
    renderWaste(data);
    renderDrift(data);
    renderCostSplit(data);
    renderValueStream(data);
    renderRedundancy(data);
    renderActivityHero(data);
    renderLosers(data);
    renderAgents(data);
    renderSessions(data);
    renderFooterMeta(data);
    // Engineering output card only renders when weeks data is present
    if (weeks.length) {
      const latest = weeks[weeks.length - 1];
      renderHero(latest);
      renderChart(weeks);
      renderTable(weeks);
    } else {
      // Hide the engineering-output card entirely when no GitHub data
      const wkTable = document.getElementById("weeks-table");
      if (wkTable) {
        const card = wkTable.closest(".card");
        if (card) card.hidden = true;
      }
    }
  } catch (e) {
    console.error(e);
    document.body.insertAdjacentHTML("beforeend",
      `<div class="card" style="border-color:#ff6b6b">render error: ${escapeHtml(e.message || String(e))}<pre style="font-size:11px;overflow:auto">${escapeHtml((e.stack||"").slice(0,1500))}</pre></div>`);
  }
}

main();
