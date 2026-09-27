const API = "http://127.0.0.1:8765";
const number = new Intl.NumberFormat("en-US");
const priceNumber = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
const labels = {
  abnormal_price_jump: "Large price jump",
  missing_trading_session: "Missing trading session",
  no_bars: "No daily bars",
  stale_ticker: "No recent update",
};
const messages = {
  abnormal_price_jump: "Large close-to-close move; check corporate actions",
  missing_trading_session: "No daily bar for an intervening trading session",
  no_bars: "No daily bars in the selected period",
  stale_ticker: "No daily bars for several recent sessions",
};
const $ = (id) => document.getElementById(id);
let overview = null;
let selected = "AAPL";
let symbolData = null;
let visibleIssueLimit = 200;
let relayoutHandler = null;
let chartDrawId = 0;
let chartResizeObserver = null;

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
  $("asof").textContent = `Historical daily bars · Through ${overview.last || "—"} · Local read only`;
  $("metric-universe").textContent = number.format(overview.universe.length);
  $("metric-bars").textContent = number.format(overview.bars);
  $("metric-errors").textContent = number.format(overview.errors);
  $("metric-warnings").textContent = number.format(overview.warnings);
  const counts = overview.warning_counts;
  $("count-jump").textContent = number.format(counts.abnormal_price_jump || 0);
  $("count-missing").textContent = number.format(counts.missing_trading_session || 0);
  $("count-empty").textContent = number.format(counts.no_bars || 0);
  $("count-stale").textContent = number.format(counts.stale_ticker || 0);
  if (overview.report_stale) notice("The database is newer than the validation report. Run the daily update, then refresh.", false);
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

function showBarDetails(row) {
  const change = row.close - row.open;
  const changeClass = change >= 0 ? "up" : "down";
  const signedChange = `${change >= 0 ? "+" : ""}${priceNumber.format(change)}`;
  $("chart-hover").innerHTML = `<strong>${escapeHtml(row.date)}</strong>
    <span>Open ${priceNumber.format(row.open)}</span><span>High ${priceNumber.format(row.high)}</span>
    <span>Low ${priceNumber.format(row.low)}</span><span>Close ${priceNumber.format(row.close)}</span>
    <span class="${changeClass}">${signedChange}</span><span>Volume ${number.format(row.volume)}</span>`;
}

function resetChartHover() {
  $("chart-hover").textContent = "Hover over a candle to view daily prices";
  $("price-cursor").hidden = true;
  $("price-guide").hidden = true;
}

function visibleVolumeRange(chart, rows) {
  const range = chart._fullLayout?.xaxis?.range;
  if (!range) return [0, Math.max(1, ...rows.map((row) => row.volume)) * 1.18];
  const first = Math.max(0, Math.ceil(Math.min(...range)));
  const last = Math.min(rows.length - 1, Math.floor(Math.max(...range)));
  const visible = first <= last ? rows.slice(first, last + 1) : rows.slice(Math.max(0, Math.round(range[0])), Math.max(0, Math.round(range[0])) + 1);
  return [0, Math.max(1, ...visible.map((row) => row.volume)) * 1.18];
}

function dateTicks(rows, chartWidth, range = [-.5, rows.length - .5]) {
  const first = Math.max(0, Math.ceil(Math.min(...range)));
  const last = Math.min(rows.length - 1, Math.floor(Math.max(...range)));
  const maxTicks = Math.max(2, Math.min(7, Math.floor(chartWidth / 95)));
  const step = Math.max(1, Math.ceil((last - first + 1) / maxTicks));
  const indices = [];
  for (let index = first; index <= last; index += step) indices.push(index);
  return { "xaxis.tickvals": indices.map((index) => rows[index].date),
    "xaxis.ticktext": indices.map((index) => rows[index].date.slice(5)) };
}

function visibleDateTicks(chart, rows) {
  return dateTicks(rows, chart.clientWidth, chart._fullLayout?.xaxis?.range);
}

function trackChartPointer(event, chart, rows) {
  const layout = chart._fullLayout;
  if (!layout?._size || !layout.xaxis?.range || !layout.yaxis?.range) return;
  const { l, t, w, h } = layout._size;
  const bounds = chart.getBoundingClientRect();
  const x = event.clientX - bounds.left;
  const y = event.clientY - bounds.top;
  if (x < l || x > l + w || y < t || y > t + h) {
    resetChartHover();
    return;
  }
  const xRange = layout.xaxis.range;
  const index = Math.round(xRange[0] + (x - l) / w * (xRange[1] - xRange[0]));
  if (index >= 0 && index < rows.length) showBarDetails(rows[index]);
  else $("chart-hover").textContent = "Hover over a candle to view daily prices";

  const domain = layout.yaxis.domain;
  const top = t + (1 - domain[1]) * h;
  const bottom = t + (1 - domain[0]) * h;
  const marker = $("price-cursor");
  const guide = $("price-guide");
  if (y < top || y > bottom) {
    marker.hidden = true;
    guide.hidden = true;
    return;
  }
  const yRange = layout.yaxis.range;
  marker.textContent = priceNumber.format(yRange[1] - (y - top) / (bottom - top) * (yRange[1] - yRange[0]));
  marker.style.top = `${y}px`;
  marker.hidden = false;
  guide.style.top = `${y}px`;
  guide.style.left = `${l}px`;
  guide.style.width = `${w}px`;
  guide.hidden = false;
}

function drawChart() {
  if (!symbolData || !window.Plotly) return;
  const rows = chartBars();
  const chart = $("chart");
  if (!rows.length) {
    Plotly.purge(chart);
    chart.textContent = "No daily bars for this symbol in the current database.";
    chart.classList.add("empty");
    resetChartHover();
    return;
  }
  chart.classList.remove("empty");
  const dates = rows.map((row) => row.date);
  const colors = rows.map((row) => row.close >= row.open ? "#159a88" : "#d65d63");
  const ticks = dateTicks(rows, chart.clientWidth);
  const drawId = ++chartDrawId;
  resetChartHover();
  Plotly.react(chart, [
    { type: "candlestick", x: dates, open: rows.map((row) => row.open), high: rows.map((row) => row.high), low: rows.map((row) => row.low), close: rows.map((row) => row.close), increasing: { line: { color: "#159a88" } }, decreasing: { line: { color: "#d65d63" } }, name: "Price", xaxis: "x", yaxis: "y", hoverinfo: "none" },
    { type: "bar", x: dates, y: rows.map((row) => row.volume), marker: { color: colors }, opacity: .62, name: "Volume", xaxis: "x", yaxis: "y2", hoverinfo: "none" },
  ], {
    margin: { l: 52, r: 15, t: 15, b: 40 }, paper_bgcolor: "#fff", plot_bgcolor: "#fff",
    showlegend: false, hovermode: false, dragmode: "pan",
    xaxis: { type: "category", showgrid: true, gridcolor: "#edf1f6", rangeslider: { visible: false }, tickmode: "array", tickvals: ticks["xaxis.tickvals"], ticktext: ticks["xaxis.ticktext"] },
    yaxis: { domain: [.29, 1], showgrid: true, gridcolor: "#edf1f6", title: { text: "Price" }, tickfont: { color: "#687a90" } },
    yaxis2: { domain: [0, .21], range: [0, Math.max(1, ...rows.map((row) => row.volume)) * 1.18], fixedrange: true, showgrid: true, gridcolor: "#edf1f6", title: { text: "Volume" }, tickfont: { color: "#687a90" } },
  }, { responsive: true, displaylogo: false, scrollZoom: true, modeBarButtonsToRemove: ["lasso2d", "select2d"] }).then(() => {
    if (drawId !== chartDrawId) return;
    if (relayoutHandler) chart.removeListener("plotly_relayout", relayoutHandler);
    relayoutHandler = (changes) => {
      if (!Object.keys(changes).some((key) => /^xaxis\.(range|autorange)/.test(key))) return;
      const range = visibleVolumeRange(chart, rows);
      const current = chart.layout.yaxis2.range;
      Plotly.relayout(chart, { ...(current[1] !== range[1] ? { "yaxis2.range": range } : {}), ...visibleDateTicks(chart, rows) });
    };
    chart.on("plotly_relayout", relayoutHandler);
    chart.onpointermove = (event) => trackChartPointer(event, chart, rows);
    chart.onpointerleave = resetChartHover;
    if (chartResizeObserver) chartResizeObserver.disconnect();
    let observedWidth = chart.clientWidth;
    chartResizeObserver = new ResizeObserver(() => {
      if (chart.clientWidth === observedWidth) return;
      observedWidth = chart.clientWidth;
      Plotly.relayout(chart, visibleDateTicks(chart, rows));
    });
    chartResizeObserver.observe(chart);
  });
}

function renderSymbol() {
  const asset = symbolData.asset || {};
  const name = overview.universe.find((row) => row.symbol === selected)?.name || asset.name || "";
  $("chart-title").textContent = `${selected} · ${name}`;
  setDefinition("details", [
    ["Company name", asset.name || name || "—"], ["Exchange", asset.exchange || "—"],
    ["Asset class", asset.asset_class === "us_equity" ? "US equity" : asset.asset_class || "—"],
    ["Trading status", asset.status === "active" ? "Active" : asset.status || "—"],
  ]);
  const bars = symbolData.bars;
  setDefinition("coverage", [
    ["Daily records", number.format(bars.length)], ["First date", bars[0]?.date || "—"],
    ["Last date", bars.at(-1)?.date || "—"],
    ["Research warnings", number.format(overview.issues.filter((issue) => issue.symbol === selected).length)],
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
  $("issue-count").textContent = `${number.format(rows.length)} issues`;
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
    notice(`Symbol ${normalized || "not provided"} was not found in the universe.`, true);
    return;
  }
  selected = normalized;
  $("symbol").value = normalized;
  try {
    symbolData = await get(`/api/symbol?symbol=${encodeURIComponent(normalized)}`);
    notice(overview.report_stale ? "The database is newer than the validation report. Run the daily update, then refresh." : "");
    renderSymbol();
  } catch (error) {
    notice(`Could not load ${normalized}: ${error.message}`, true);
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
    notice("Cannot connect to the local data service. Start Stock Radar on this computer and allow browser access to the local network.", true);
    $("asof").textContent = "Local data disconnected";
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
