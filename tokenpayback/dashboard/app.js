const $ = (s) => document.querySelector(s);

function fmtMoney(v) {
  if (v == null) return "—";
  if (Math.abs(v) >= 1000) return "$" + Math.round(v).toLocaleString();
  return "$" + v.toFixed(2);
}

function fmtROI(r) {
  if (r == null) return "—";
  if (r >= 100) return r.toFixed(0) + "×";
  if (r >= 10) return r.toFixed(1) + "×";
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
  $("#latest-week").textContent = latest.week;
  $("#latest-cost").textContent = fmtMoney(latest.cost_usd);
  $("#latest-value").textContent = fmtMoney(latest.value_usd);
  const roiEl = $("#latest-roi");
  roiEl.textContent = fmtROI(latest.roi);
  roiEl.className = "value roi " + roiClass(latest.roi);
  $("#roi-verdict").textContent = roiVerdict(latest.roi, latest.cost_usd);
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

function renderSessions(data) {
  const sessions = data.sessions || [];
  const totals = data.sessionsTotals;
  if (!sessions.length || !totals) return;
  document.getElementById("sessions-section").hidden = false;

  const renderBars = (containerId, items, colorClass = "") => {
    const max = Math.max(...items.map((x) => x.cost), 1);
    const html = items.map((it) => `
      <div class="hbar">
        <div class="lbl">${escapeHtml(it.key)}</div>
        <div class="meter"><div class="fill ${colorClass}" style="width:${(it.cost / max * 100).toFixed(1)}%"></div></div>
        <div class="amt">${fmtMoney(it.cost)}<span class="cnt"> · ${it.count}</span></div>
      </div>
    `).join("");
    document.getElementById(containerId).innerHTML = html;
  };
  renderBars("bars-category", totals.byCategory, "meter-cost");
  renderBars("bars-project", totals.byProject.slice(0, 10), "meter-cost");

  const rowHtml = sessions.slice(0, 30).map((s) => {
    const c = s.classification || {};
    const date = (s.last_event || "").slice(0, 10);
    return `
      <tr>
        <td>${date}</td>
        <td><span class="cat-tag cat-${escapeHtml(c.category || "")}">${escapeHtml(c.category || "?")}</span></td>
        <td>${escapeHtml(c.project || "?")}</td>
        <td class="num">${fmtMoney(s.est_cost_usd)}</td>
        <td>${escapeHtml(c.summary || "")}</td>
      </tr>
    `;
  }).join("");
  document.getElementById("sessions-tbody").innerHTML = rowHtml;
}

async function main() {
  try {
    const data = await load();
    const weeks = data.weeks || [];
    if (!weeks.length) throw new Error("no weeks in data.json");
    const latest = weeks[weeks.length - 1];
    $("#meta").textContent = `generated ${new Date(data.generatedAt).toLocaleString()}`;
    renderHero(latest);
    renderChart(weeks);
    renderTable(weeks);
    renderBreakdown(latest);
    renderPRs(latest);
    renderSessions(data);
    renderHeuristics(data.config);
  } catch (e) {
    document.body.insertAdjacentHTML("beforeend", `<div class="card">error: ${e.message}</div>`);
  }
}

main();
