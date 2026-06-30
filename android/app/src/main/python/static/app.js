const fmtUsd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const fmtUsd2 = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

const fmtCompactUsd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
});

const fmtPct = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  const sign = Number(value) > 0 ? "+" : "";
  return `${sign}${Number(value).toFixed(2)}%`;
};

const fmtNum = (value, digits = 2) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toFixed(digits);
};

const fmtInteger = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return new Intl.NumberFormat("en-US").format(Number(value));
};

const marketCapThresholdText = (value) => {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  const yiUsd = number / 100000000;
  return `最低市值 ${fmtNum(yiUsd, yiUsd % 1 === 0 ? 0 : 1)} 亿美元 · `;
};

const $ = (id) => document.getElementById(id);
let refreshTimer = null;

const MONTH_ZH = {
  Jan: "1月",
  Feb: "2月",
  Mar: "3月",
  Apr: "4月",
  May: "5月",
  Jun: "6月",
  Jul: "7月",
  Aug: "8月",
  Sep: "9月",
  Oct: "10月",
  Nov: "11月",
  Dec: "12月",
};

const RATING_ZH = {
  "Strong Buy": "强烈买入",
  Buy: "买入",
  Outperform: "跑赢",
  Overweight: "增持",
  Hold: "持有",
  Neutral: "中性",
  "Market Perform": "跟随大盘",
  Underperform: "跑输",
  Underweight: "减持",
  Sell: "卖出",
};

const ACTION_ZH = {
  Maintains: "维持",
  Reiterates: "重申",
  Initiates: "首次覆盖",
  Upgrades: "上调评级",
  Downgrades: "下调评级",
  Raises: "上调",
  Lowers: "下调",
};

const translateRating = (value) => RATING_ZH[value] || value || "--";
const translateAction = (value) => ACTION_ZH[value] || value || "--";
const translateMonth = (value) => MONTH_ZH[value] || value || "--";
const displayText = (value) => (!value || value === "N/A" ? "暂无" : value);

function setStatus(state, text) {
  const dot = $("sync-dot");
  dot.className = `dot ${state || ""}`.trim();
  $("last-updated").textContent = text;
}

function dayText(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return `${fmtInteger(value)} 天`;
}

function scoreText(value, suffix = "") {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return `${fmtNum(value, Number(value) % 1 === 0 ? 0 : 1)}${suffix}`;
}

function predictionDetailText(prediction) {
  if (!prediction?.averageDays || !prediction?.earliestDate || !prediction?.latestDate) return "--";
  return `均值 ${dayText(prediction.averageDays)}，窗口 ${prediction.earliestDate} 至 ${prediction.latestDate}，样本 ${prediction.sampleCount} 轮`;
}

const FORECAST_WINDOW_STATUS = {
  before_window: "未到窗口",
  in_window: "窗口内",
  after_window: "已过窗口",
};

function averageDistanceText(daysToAverage) {
  if (daysToAverage === null || daysToAverage === undefined || Number.isNaN(Number(daysToAverage))) return "--";
  const days = Number(daysToAverage);
  if (days > 0) return `距均值还有 ${dayText(days)}`;
  if (days < 0) return `已过均值 ${dayText(Math.abs(days))}`;
  return "今天到达均值";
}

function setForecastProgress(id, prediction) {
  const el = $(id);
  if (!prediction?.averageDays || prediction?.progressPct === null || prediction?.progressPct === undefined) {
    el.className = "forecast-progress empty";
    el.textContent = "--";
    return;
  }
  const progressPct = Number(prediction.progressPct);
  const barPct = Math.max(0, Math.min(100, progressPct));
  const status = prediction.windowStatus || "";
  el.className = `forecast-progress ${status} ${progressPct >= 100 ? "over-average" : ""}`.trim();
  el.innerHTML = `
    <div class="forecast-progress-head">
      <span>当前</span>
      <b>${scoreText(progressPct, "%")}</b>
      <em>${FORECAST_WINDOW_STATUS[status] || "观察中"}</em>
    </div>
    <div class="forecast-progress-track" aria-hidden="true">
      <i style="width:${barPct}%"></i>
    </div>
    <small>${dayText(prediction.elapsedDays)} / 均值 ${dayText(prediction.averageDays)} · ${averageDistanceText(prediction.daysToAverage)}</small>
  `;
}

async function loadBtc() {
  const response = await fetch("/api/btc");
  if (!response.ok) throw new Error("BTC 数据获取失败");
  const data = await response.json();

  $("btc-action").textContent = data.action || "--";
  $("btc-price").textContent = fmtUsd2.format(data.price || 0);
  $("btc-change").textContent = fmtPct(data.change24hPct);
  $("btc-change").className = Number(data.change24hPct) >= 0 ? "positive" : "negative";
  $("btc-days").textContent = `${data.daysSinceHalving ?? "--"} 天`;
  $("btc-halving-countdown").textContent = dayText(data.daysToNextHalving);
  $("btc-halving-detail").textContent = data.nextHalvingEstimate
    ? `预计 ${data.nextHalvingEstimate}${
        data.remainingBlocks !== null && data.remainingBlocks !== undefined
          ? `，剩余 ${fmtInteger(data.remainingBlocks)} 区块`
          : ""
      }`
    : "--";
  $("btc-fng-value").textContent = data.fearGreed?.value !== null && data.fearGreed?.value !== undefined
    ? `${data.fearGreed.value}/100`
    : "--";
  $("btc-fng-detail").textContent = data.fearGreed?.classificationZh || data.fearGreed?.classification || "--";
  $("btc-detail").textContent = data.actionDetail || "";
  renderBtcRhythm(data.cycleRhythm);
  renderBtcForecast(data.cycleRhythm?.predictions);
}

function renderBtcRhythm(rhythm) {
  const topBottom = rhythm?.topToBottom || {};
  const bottomTop = rhythm?.bottomToTop || {};
  const current = rhythm?.current || {};

  $("btc-top-bottom-days").textContent = dayText(topBottom.averageDays);
  $("btc-top-bottom-detail").textContent =
    topBottom.sampleCount && topBottom.minDays && topBottom.maxDays
      ? `${topBottom.sampleCount} 轮样本，历史范围 ${dayText(topBottom.minDays)} - ${dayText(topBottom.maxDays)}`
      : "--";

  $("btc-bottom-top-days").textContent = dayText(bottomTop.averageDays);
  $("btc-bottom-top-detail").textContent =
    bottomTop.sampleCount && bottomTop.minDays && bottomTop.maxDays
      ? `${bottomTop.sampleCount} 轮样本，历史范围 ${dayText(bottomTop.minDays)} - ${dayText(bottomTop.maxDays)}`
      : "--";

  $("btc-current-cycle-days").textContent = dayText(current.daysFromBottomToCurrentHigh);
  if (current.currentHighDate) {
    const progress = current.progressVsAverageBottomToTopPct
      ? `，约为历史均值 ${current.progressVsAverageBottomToTopPct}%`
      : "";
    const coolingWindow = Array.isArray(current.estimatedCoolingLowWindow)
      ? `；若按历史见顶后见底节奏，冷却窗口约 ${current.estimatedCoolingLowWindow[0]} 至 ${current.estimatedCoolingLowWindow[1]}${
          current.estimatedCoolingLowAverageDate ? `，均值日 ${current.estimatedCoolingLowAverageDate}` : ""
        }`
      : "";
    $("btc-current-cycle-detail").textContent =
      `${current.cycleBottomDate} 至 ${current.currentHighDate} 动态高点，距该高点 ${dayText(current.daysSinceCurrentHigh)}${progress}${coolingWindow}`;
  } else {
    $("btc-current-cycle-detail").textContent = current.method || "--";
  }
}

function renderBtcForecast(predictions) {
  const fromHalving = predictions?.fromHalving || {};
  const fromBottom = predictions?.fromBottom || {};
  const fromTop = predictions?.fromTop || {};

  $("btc-forecast-method").textContent = predictions?.method
    ? "样本：2012 / 2016 / 2020 三轮减半周期"
    : "--";

  $("btc-halving-top-date").textContent = fromHalving.top?.averageDate || "--";
  setForecastProgress("btc-halving-top-progress", fromHalving.top);
  $("btc-halving-top-detail").textContent = fromHalving.anchorDate
    ? `锚点 ${fromHalving.anchorDate}；${predictionDetailText(fromHalving.top)}`
    : "--";

  $("btc-halving-bottom-date").textContent = fromHalving.bottom?.averageDate || "--";
  setForecastProgress("btc-halving-bottom-progress", fromHalving.bottom);
  $("btc-halving-bottom-detail").textContent = fromHalving.anchorDate
    ? `锚点 ${fromHalving.anchorDate}；${predictionDetailText(fromHalving.bottom)}`
    : "--";

  $("btc-bottom-top-date").textContent = fromBottom.top?.averageDate || "--";
  setForecastProgress("btc-bottom-top-progress", fromBottom.top);
  $("btc-bottom-top-date-detail").textContent = fromBottom.anchorDate
    ? `锚点 ${fromBottom.anchorDate}；${predictionDetailText(fromBottom.top)}`
    : "--";

  $("btc-top-bottom-date").textContent = fromTop.bottom?.averageDate || "--";
  setForecastProgress("btc-top-bottom-progress", fromTop.bottom);
  $("btc-top-bottom-date-detail").textContent = fromTop.anchorDate
    ? `锚点 ${fromTop.anchorDate}；${predictionDetailText(fromTop.bottom)}`
    : "等待本轮动态高点数据";
}

let analystRequestId = 0;

const moneyPlain = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toFixed(2);
};

const moneyTarget = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toFixed(0);
};

const shortDate = (value) => {
  if (!value) return "--";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("zh-CN", { year: "numeric", month: "numeric", day: "numeric" });
};

function resetAnalystCards(row) {
  $("target-symbol").textContent = row?.symbol || "--";
  $("top-analyst-firm").textContent = "加载中";
  $("top-analyst-name").textContent = row ? `${row.symbol} · ${row.label}` : "--";
  $("top-analyst-score").textContent = "--/100";
  $("top-analyst-score-bar").style.width = "0%";
  $("top-analyst-rating").textContent = translateRating(row?.consensusRating);
  $("top-analyst-rating").className = `rating-badge ${ratingClass(row?.consensusRating)}`;
  renderTargetAxis(row, null);
  renderRecommendationBars([]);
  renderLatestRating(null);
}

async function setTargetModule(row) {
  resetAnalystCards(row);
  if (!row?.symbol) return;
  const requestId = ++analystRequestId;
  try {
    const response = await fetch(`/api/analyst?symbol=${encodeURIComponent(row.symbol)}`);
    if (!response.ok) throw new Error("机构详情获取失败");
    const detail = await response.json();
    if (requestId !== analystRequestId) return;
    renderAnalystDetail(row, detail);
  } catch (error) {
    console.error(error);
  }
}

function renderAnalystDetail(row, detail) {
  const top = detail.topAnalyst || {};
  const score = Number(top.score);
  $("top-analyst-firm").textContent = top.firm || top.analyst || detail.target?.sourceName || "--";
  $("top-analyst-name").textContent = top.analyst && top.analyst !== top.firm ? top.analyst : detail.ratingsSummary || "";
  $("top-analyst-score").textContent = Number.isFinite(score) ? `${score}/100` : "--/100";
  $("top-analyst-score-bar").style.width = Number.isFinite(score) ? `${Math.max(0, Math.min(100, score))}%` : "0%";
  const topRating = top.rating || row.consensusRating;
  $("top-analyst-rating").textContent = translateRating(topRating);
  $("top-analyst-rating").className = `rating-badge ${ratingClass(topRating)}`;

  renderTargetAxis(row, detail.target);
  renderRecommendationBars(detail.historicalRecommendations || []);
  renderLatestRating(detail.latestRating);
}

function renderTargetAxis(row, target) {
  const low = Number(target?.low ?? row?.targetLowPrice);
  const average = Number(target?.average ?? row?.targetMeanPrice);
  const high = Number(target?.high ?? row?.targetHighPrice);
  const current = Number(row?.price);
  $("target-low").textContent = moneyPlain(low);
  $("target-high").textContent = moneyPlain(high);
  $("target-average-bubble").innerHTML = `${moneyPlain(average)}<small>平均</small>`;
  $("target-current-bubble").innerHTML = `${moneyPlain(current)}<small>现价</small>`;

  const hasRange = Number.isFinite(low) && Number.isFinite(high) && high > low;
  setAxisPoint("axis-average-dot", "target-average-bubble", hasRange ? ((average - low) / (high - low)) * 100 : null);
  setAxisPoint("axis-current-dot", "target-current-bubble", hasRange ? ((current - low) / (high - low)) * 100 : null);
}

function setAxisPoint(dotId, bubbleId, pct) {
  const dot = $(dotId);
  const bubble = $(bubbleId);
  bubble.classList.remove("edge-left", "edge-right");
  if (pct === null || pct === undefined || Number.isNaN(Number(pct))) {
    dot.style.display = "none";
    bubble.style.display = "none";
    return;
  }
  const left = Math.max(0, Math.min(100, pct));
  dot.style.display = "block";
  bubble.style.display = "block";
  dot.style.left = `${left}%`;
  bubble.style.left = `${left}%`;
  if (left < 12) {
    bubble.classList.add("edge-left");
  } else if (left > 88) {
    bubble.classList.add("edge-right");
  }
}

function renderRecommendationBars(history) {
  const wrap = $("recommendation-bars");
  wrap.innerHTML = "";
  const rows = history.slice(-4);
  if (!rows.length) {
    wrap.innerHTML = '<span class="chart-empty">暂无评级历史</span>';
    return;
  }
  const maxTotal = Math.max(...rows.map((item) => Number(item.buy || 0) + Number(item.hold || 0) + Number(item.sell || 0)), 1);
  for (const item of rows) {
    const buy = Number(item.buy || 0);
    const hold = Number(item.hold || 0);
    const sell = Number(item.sell || 0);
    const total = buy + hold + sell;
    const scale = total / maxTotal;
    const bar = document.createElement("div");
    bar.className = "rec-bar-wrap";
    bar.innerHTML = `
      <b>${total || "--"}</b>
      <div class="rec-bar" style="height:${Math.max(18, 86 * scale)}px">
        <span class="rec-sell" style="height:${segmentHeight(sell, total)}%"></span>
        <span class="rec-hold" style="height:${segmentHeight(hold, total)}%"></span>
        <span class="rec-buy" style="height:${segmentHeight(buy, total)}%"><em>${buy || ""}</em></span>
      </div>
      <small>${translateMonth(item.month)}</small>
    `;
    wrap.appendChild(bar);
  }
}

function segmentHeight(value, total) {
  if (!total) return 0;
  return Math.max(0, (Number(value || 0) / total) * 100);
}

function renderLatestRating(latest) {
  $("latest-rating-date").textContent = shortDate(latest?.date);
  $("latest-rating-analyst").textContent = latest?.firm || latest?.analyst || "--";
  $("latest-rating-action").textContent = translateAction(latest?.ratingAction);
  $("latest-rating-value").textContent = translateRating(latest?.rating);
  $("latest-price-action").textContent = translateAction(latest?.priceAction);
  $("latest-price-action").className = priceActionClass(latest?.priceAction);
  const previous = moneyTarget(latest?.previousPriceTarget);
  const current = moneyTarget(latest?.priceTarget);
  $("latest-price-target").textContent = previous !== "--" && current !== "--" ? `${previous} -> ${current}` : current;
}

function ratingClass(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized.includes("buy") || normalized.includes("outperform")) return "rating-positive";
  if (normalized.includes("sell") || normalized.includes("under")) return "rating-negative";
  return "rating-neutral";
}

function priceActionClass(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized.includes("raise")) return "positive";
  if (normalized.includes("lower")) return "negative";
  return "";
}

function renderStocks(data) {
  const body = $("stocks-body");
  body.innerHTML = "";
  $("stock-source").textContent = data.source || "";
  const threshold = marketCapThresholdText(data.minMarketCap);
  $("pool-count").textContent =
    data.universeCount !== undefined
      ? `${threshold}${fmtInteger(data.universeCount)} 只，扫描 ${fmtInteger(data.analyzedCount)} 只`
      : `${fmtInteger(data.count)} 只`;
  $("excluded-count").textContent =
    data.excludedChinaRelated !== undefined ? `${fmtInteger(data.excludedChinaRelated)} 只` : "--";

  if (!data.rows?.length) {
    body.innerHTML = '<tr><td colspan="9" class="empty">没有取到股票数据，请检查代码或网络。</td></tr>';
    setTargetModule(null);
    return;
  }

  setTargetModule(data.rows[0]);

  for (const row of data.rows) {
    const tr = document.createElement("tr");
    tr.tabIndex = 0;
    tr.className = "stock-row";
    tr.addEventListener("click", () => {
      document.querySelectorAll(".stock-row.selected").forEach((el) => el.classList.remove("selected"));
      tr.classList.add("selected");
      setTargetModule(row);
    });
    tr.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        tr.click();
      }
    });
    const risks = row.risks?.length ? ` · ${row.risks.join("、")}` : "";
    tr.innerHTML = `
      <td><strong>${row.symbol}</strong><span class="muted">${displayText(row.sector)}</span></td>
      <td><strong>${row.name || row.symbol}</strong><span class="muted">${displayText(row.industry)}</span></td>
      <td>${fmtUsd2.format(row.price || 0)}</td>
      <td>${row.marketCap ? fmtCompactUsd.format(row.marketCap) : "--"}</td>
      <td>${row.targetPrice ? fmtUsd2.format(row.targetPrice) : "--"}</td>
      <td class="${Number(row.upsidePct) >= 0 ? "positive" : "negative"}">${fmtPct(row.upsidePct)}</td>
      <td><span class="score">${fmtNum(row.score, 1)}</span></td>
      <td>${displayText(row.industry || row.sector)}</td>
      <td><strong>${row.label}</strong><span class="muted">${displayText(row.recommendation)}${risks}</span></td>
    `;
    body.appendChild(tr);
  }
  body.querySelector(".stock-row")?.classList.add("selected");
}

function probabilityCell(stats) {
  if (!stats || stats.positivePct === null || stats.positivePct === undefined) {
    return "--";
  }
  return `${scoreText(stats.positivePct, "%")}<span class="muted">均 ${fmtPct(stats.avgReturnPct)}</span>`;
}

function renderMarketSentiment(data) {
  const vix = data?.vix || {};
  const fearGreed = data?.fearGreed || {};
  const currentStats = vix.currentStats || {};

  $("vix-level").textContent = vix.value ? fmtNum(vix.value, 2) : "--";
  $("vix-detail").textContent =
    vix.value !== null && vix.value !== undefined
      ? `${vix.bandLabel || "--"} · ${vix.date || "--"} · 近10年分位 ${scoreText(vix.percentile10y, "%")}`
      : "--";
  $("us-fng-score").textContent =
    fearGreed.score !== null && fearGreed.score !== undefined ? `${scoreText(fearGreed.score)}/100` : "--";
  $("us-fng-detail").textContent =
    `${fearGreed.ratingZh || fearGreed.rating || "--"} · ${fearGreed.sourceName || "--"}`;
  $("vix-advice").textContent = vix.recommendation || "--";
  $("vix-advice-detail").textContent = currentStats.threeMonth
    ? `当前区间 ${currentStats.range || "--"}，SPY 3月上涨概率 ${scoreText(currentStats.threeMonth.positivePct, "%")}，6月均收益 ${fmtPct(currentStats.sixMonth?.avgReturnPct)}`
    : "--";
  $("market-sentiment-source").textContent = data?.source || "";

  const body = $("vix-prob-body");
  body.innerHTML = "";
  const rows = vix.table || [];
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty">没有取到 VIX 历史数据。</td></tr>';
    return;
  }

  for (const row of rows) {
    const tr = document.createElement("tr");
    if (row.key === vix.band) tr.className = "vix-row-current";
    tr.innerHTML = `
      <td><strong>${row.range}</strong><span class="muted">${row.label}</span></td>
      <td>${fmtInteger(row.sampleCount)}</td>
      <td>${probabilityCell(row.oneMonth)}</td>
      <td>${probabilityCell(row.threeMonth)}</td>
      <td>${probabilityCell(row.sixMonth)}</td>
      <td><strong>${row.recommendation || "--"}</strong></td>
    `;
    body.appendChild(tr);
  }
}

async function loadMarketSentiment() {
  const response = await fetch("/api/market-sentiment");
  if (!response.ok) throw new Error("美股情绪数据获取失败");
  renderMarketSentiment(await response.json());
}

async function loadStocks() {
  const symbols = $("symbols").value.trim();
  const params = new URLSearchParams();
  if (symbols) {
    params.set("symbols", symbols);
  } else {
    params.set("scan_limit", $("scan-limit").value || "500");
    params.set("min_market_cap_billion", $("min-market-cap").value || "100");
  }
  const response = await fetch(`/api/stocks?${params.toString()}`);
  if (!response.ok) throw new Error("股票数据获取失败");
  renderStocks(await response.json());
}

async function refreshAll() {
  try {
    setStatus("", "正在刷新真实数据...");
    await Promise.all([loadBtc(), loadStocks(), loadMarketSentiment()]);
    setStatus("ok", `已更新 ${new Date().toLocaleString()}`);
  } catch (error) {
    console.error(error);
    setStatus("error", error.message || "刷新失败");
  }
}

function scheduleRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  const interval = Number($("refresh-interval").value);
  if (interval > 0) {
    refreshTimer = setInterval(refreshAll, interval);
  }
}

$("refresh-now").addEventListener("click", refreshAll);
$("refresh-interval").addEventListener("change", scheduleRefresh);
$("symbols").addEventListener("change", refreshAll);
$("min-market-cap").addEventListener("change", refreshAll);
$("scan-limit").addEventListener("change", refreshAll);

scheduleRefresh();
refreshAll();
