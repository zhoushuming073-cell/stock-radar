const API = "http://127.0.0.1:8765";
const number = new Intl.NumberFormat("zh-CN");
const labels = {
  abnormal_price_jump: "价格大幅跳变",
  missing_trading_session: "缺失交易日",
  no_bars: "无日线数据",
  stale_ticker: "近期无更新",
};
const messages = {
  abnormal_price_jump: "相邻日收盘价变化较大，需核对公司行动",
  missing_trading_session: "中间交易日没有日线记录",
  no_bars: "所选时段无日线数据",
  stale_ticker: "最近多个交易日无日线",
};
const $ = (id) => document.getElementById(id);
let overview = null;
let selected = "AAPL";
let symbolData = null;
let visibleIssueLimit = 200;

function notice(message, error = false) {
  const element = $("notice");
  element.textContent = message;
  element.hidden = !message;
  element.classList.toggle("error", error);
}

async function get(path) {
  const response = await fetch(`${API}${path}`, {
    cache: "no-store", mode: "cors", targetAddressSpace: "loopback",
    signal: AbortSignal.timeout(12000),
  });
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).error || detail; } catch (_) {}
    throw new Error(detail);
  }
  return response.json();
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (match) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[match]);
}

function setDefinition(id, rows) {
  $(id).innerHTML = rows.map(([key, value]) =>
    `<div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd></div>`
  ).join("");
}

function renderOverview() {
  $("asof").textContent = `历史日线 · 截至 ${overview.last || "—"} · 本机只读`;
  $("metric-universe").textContent = number.format(overview.universe.length);
  $("metric-bars").textContent = number.format(overview.bars);
  $("metric-errors").textContent = number.format(overview.errors);
  $("metric-warnings").textContent = number.format(overview.warnings);
  const counts = overview.warning_counts;
  $("count-jump").textContent = number.format(counts.abnormal_price_jump || 0);
  $("count-missing").textContent = number.format(counts.missing_trading_session || 0);
  $("count-empty").textContent = number.format(counts.no_bars || 0);
  $("count-stale").textContent = number.format(counts.stale_ticker || 0);
  if (overview.report_stale) notice("数据库比校验报告更新，请运行每日更新任务后刷新。", false);
  else notice("");
}

function updateSuggestions() {
  if (!overview) return;
  const query = $("symbol").value.trim().toUpperCase();
  const matches = overview.universe.filter(({ symbol, name }) =>
    symbol.startsWith(query) || (query.length > 1 && name.toUpperCase().includes(query))
  ).slice(0, 20);
  $("symbol-options").innerHTML = matches.map(({ symbol, name }) =>
    `<option value="${escapeHtml(symbol)}">${escapeHtml(name)}</option>`
  ).join("");
}

function chartBars() {
  if (!symbolData) return [];
  const range = $("period").value;
  return range === "all" ? symbolData.bars : symbolData.bars.slice(-Number(range));
}

function drawChart() {
  if (!symbolData || !window.Plotly) return;
  const rows = chartBars();
  const chart = $("chart");
  if (!rows.length) {
    Plotly.purge(chart);
    chart.textContent = "这个标的在当前数据库中没有日线数据。";
    chart.classList.add("empty");
    return;
  }
  chart.classList.remove("empty");
  const dates = rows.map((row) => row.date);
  const colors = rows.map((row) => row.close >= row.open ? "#159a88" : "#d65d63");
  Plotly.react(chart, [
    { type: "candlestick", x: dates, open: rows.map((row) => row.open), high: rows.map((row) => row.high), low: rows.map((row) => row.low), close: rows.map((row) => row.close), increasing: { line: { color: "#159a88" } }, decreasing: { line: { color: "#d65d63" } }, name: "价格", xaxis: "x", yaxis: "y" },
    { type: "bar", x: dates, y: rows.map((row) => row.volume), marker: { color: colors }, opacity: .62, name: "成交量", xaxis: "x", yaxis: "y2" },
  ], {
    margin: { l: 52, r: 15, t: 15, b: 40 }, paper_bgcolor: "#fff", plot_bgcolor: "#fff",
    showlegend: false, hovermode: "x unified", dragmode: "pan",
    xaxis: { type: "date", showgrid: true, gridcolor: "#edf1f6", rangeslider: { visible: false }, tickformat: "%Y-%m" },
    yaxis: { domain: [.29, 1], showgrid: true, gridcolor: "#edf1f6", title: { text: "价格" }, tickfont: { color: "#687a90" } },
    yaxis2: { domain: [0, .21], showgrid: true, gridcolor: "#edf1f6", title: { text: "成交量" }, tickfont: { color: "#687a90" } },
  }, { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d"] });
}

function renderSymbol() {
  const asset = symbolData.asset || {};
  const name = overview.universe.find((row) => row.symbol === selected)?.name || asset.name || "";
  $("chart-title").textContent = `${selected} · ${name}`;
  setDefinition("details", [
    ["公司名称", asset.name || name || "—"], ["交易所", asset.exchange || "—"],
    ["资产类型", asset.asset_class === "us_equity" ? "美股权益" : asset.asset_class || "—"],
    ["交易状态", asset.status === "active" ? "活跃" : asset.status || "—"],
  ]);
  const bars = symbolData.bars;
  setDefinition("coverage", [
    ["日线记录", number.format(bars.length)], ["最早日期", bars[0]?.date || "—"],
    ["最近日期", bars.at(-1)?.date || "—"],
    ["研究警告", number.format(overview.issues.filter((issue) => issue.symbol === selected).length)],
  ]);
  drawChart();
  renderIssues();
}

function renderIssues() {
  if (!overview) return;
  const kind = $("issue-type").value;
  const scope = $("issue-scope").value;
  const rows = overview.issues.filter((issue) =>
    (kind === "all" || issue.code === kind) && (scope === "all" || issue.symbol === selected)
  );
  $("issue-count").textContent = `共 ${number.format(rows.length)} 条`;
  $("issues").innerHTML = rows.slice(0, visibleIssueLimit).map((issue) => `<tr>
    <td>${escapeHtml(issue.symbol || "")}</td><td>${escapeHtml(issue.date || "")}</td>
    <td>${escapeHtml(labels[issue.code] || issue.code)}</td>
    <td>${escapeHtml(messages[issue.code] || issue.message || "")}</td></tr>`).join("");
  $("show-more").hidden = rows.length <= visibleIssueLimit;
}

async function selectSymbol(symbol) {
  if (!overview) return;
  const normalized = symbol.trim().toUpperCase();
  if (!overview.universe.some((row) => row.symbol === normalized)) {
    notice(`股票池中找不到 ${normalized || "该代码"}。`, true);
    return;
  }
  selected = normalized;
  $("symbol").value = normalized;
  try {
    symbolData = await get(`/api/symbol?symbol=${encodeURIComponent(normalized)}`);
    notice(overview.report_stale ? "数据库比校验报告更新，请运行每日更新任务后刷新。" : "");
    renderSymbol();
  } catch (error) {
    notice(`读取 ${normalized} 失败：${error.message}`, true);
  }
}

async function refresh() {
  $("refresh").disabled = true;
  try {
    overview = await get("/api/overview");
    renderOverview();
    updateSuggestions();
    await selectSymbol(overview.universe.some((row) => row.symbol === selected) ? selected : overview.universe[0]?.symbol || "AAPL");
  } catch (error) {
    notice("无法连接本机数据服务。请在这台电脑上启动 Stock Radar 本地服务，并允许浏览器访问本地网络。", true);
    $("asof").textContent = "本机数据未连接";
  } finally {
    $("refresh").disabled = false;
  }
}

$("refresh").addEventListener("click", refresh);
$("symbol").addEventListener("input", updateSuggestions);
$("symbol").addEventListener("change", () => selectSymbol($("symbol").value));
$("symbol").addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); selectSymbol($("symbol").value); } });
$("period").addEventListener("change", drawChart);
$("issue-type").addEventListener("change", () => { visibleIssueLimit = 200; renderIssues(); });
$("issue-scope").addEventListener("change", () => { visibleIssueLimit = 200; renderIssues(); });
$("show-more").addEventListener("click", () => { visibleIssueLimit += 200; renderIssues(); });
refresh();
