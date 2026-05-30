const el = (id) => document.getElementById(id);
const state = { chart: null, candleSeries: null, ws: null, lastAnalysis: null };

function fmt(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '--';
  return Number(v).toFixed(digits);
}

function logItem(title, body) {
  const node = document.createElement('div');
  node.className = 'live-item';
  node.innerHTML = `<time>${new Date().toLocaleString('th-TH')}</time><strong>${title}</strong><p>${body}</p>`;
  const box = el('liveLog');
  box.prepend(node);
  while (box.children.length > 8) box.removeChild(box.lastChild);
}

function initChart() {
  const container = el('chart');
  state.chart = LightweightCharts.createChart(container, {
    layout: { background: { color: 'transparent' }, textColor: '#cbd5e1' },
    grid: { vertLines: { color: 'rgba(255,255,255,.05)' }, horzLines: { color: 'rgba(255,255,255,.05)' } },
    rightPriceScale: { borderColor: 'rgba(255,255,255,.1)' },
    timeScale: { borderColor: 'rgba(255,255,255,.1)', timeVisible: true, secondsVisible: false },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  });
  state.candleSeries = state.chart.addCandlestickSeries({
    upColor: '#34d399',
    downColor: '#f87171',
    borderUpColor: '#34d399',
    borderDownColor: '#f87171',
    wickUpColor: '#34d399',
    wickDownColor: '#f87171',
  });
  window.addEventListener('resize', () => {
    state.chart.applyOptions({ width: container.clientWidth });
  });
}

async function loadHistory() {
  const res = await fetch('/api/xauusd/history?tf=M1&limit=260');
  const data = await res.json();
  state.candleSeries.setData(data.candles);
  state.chart.timeScale().fitContent();
}

function updateAnalysis(a) {
  if (!a) return;
  state.lastAnalysis = a;
  el('price').textContent = fmt(a.price);
  el('updatedAt').textContent = `Last sync: ${new Date(a.updated_at || Date.now()).toLocaleString('th-TH')}`;
  el('marketMode').textContent = a.market_mode || '--';
  el('action').textContent = a.action || '--';
  el('condition').textContent = a.condition || '--';
  el('recommendedAction').textContent = a.action || '--';
  el('planText').textContent = a.condition || '--';
  el('entry').textContent = fmt(a.entry);
  el('sl').textContent = fmt(a.sl);
  el('tp1').textContent = fmt(a.tp1);
  el('confidence').textContent = `${a.confidence ?? '--'}/100`;
  el('confidenceBar').style.width = `${a.confidence || 0}%`;
  el('h1Bias').textContent = a.timeframes?.H1 || '--';
  el('m15Bias').textContent = a.timeframes?.M15 || '--';
  el('support').textContent = fmt(a.levels?.support);
  el('resistance').textContent = fmt(a.levels?.resistance);
  el('lot').textContent = fmt(a.risk?.suggested_lot, 2);
  if (a.last_webhook) {
    el('apiStatus').textContent = 'Webhook Active';
  }
}

async function loadAnalysis() {
  const balance = el('balance').value || 300;
  const risk = el('riskPercent').value || 1;
  const slp = el('slPoints').value || 55;
  const res = await fetch(`/api/xauusd/analysis?balance=${balance}&risk_percent=${risk}&sl_points=${slp}`);
  const a = await res.json();
  updateAnalysis(a);
  logItem('Manual Analyze', `${a.market_mode} • ${a.action} • Confidence ${a.confidence}/100`);
}

function connectWS() {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
  const url = `${scheme}://${location.host}/ws/xauusd`;
  state.ws = new WebSocket(url);
  state.ws.onopen = () => {
    el('wsStatus').textContent = 'Real-time Online';
    el('wsStatus').className = 'pill';
    state.ws.send('hello');
    logItem('WebSocket Connected', 'ระบบเริ่มรับข้อมูลแบบ Real-time แล้ว');
  };
  state.ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    const a = msg.analysis;
    if (a) updateAnalysis(a);
    if (msg.price) {
      const candle = { time: Math.floor(Date.now() / 1000), open: msg.price, high: msg.price, low: msg.price, close: msg.price };
      // Lightweight Charts update works best when backend candles are bucketed; reload periodically for clean OHLC.
      state.candleSeries.update(candle);
    }
    if (msg.type === 'tradingview_webhook') {
      logItem('TradingView Alert Received', `${msg.signal || 'ALERT'} • ${msg.price} • ${msg.message || ''}`);
      loadHistory();
    }
  };
  state.ws.onclose = () => {
    el('wsStatus').textContent = 'Reconnect...';
    el('wsStatus').className = 'pill warning';
    setTimeout(connectWS, 2500);
  };
  state.ws.onerror = () => {
    el('wsStatus').textContent = 'WS Error';
    el('wsStatus').className = 'pill danger';
  };
}

function setupWebhookSample() {
  const url = `${location.origin}/api/tradingview/webhook`;
  el('webhookUrl').textContent = url;
  el('webhookSample').textContent = JSON.stringify({
    symbol: '{{ticker}}',
    price: '{{close}}',
    time: '{{time}}',
    interval: '{{interval}}',
    signal: 'XAUUSD_ALERT',
    message: 'Price reached key zone',
    secret: 'ใส่ค่า TRADINGVIEW_WEBHOOK_SECRET จาก Render'
  }, null, 2);
}

async function boot() {
  initChart();
  setupWebhookSample();
  await loadHistory();
  await loadAnalysis();
  connectWS();
  setInterval(loadHistory, 30000);
}

el('refreshBtn').addEventListener('click', () => { loadHistory(); loadAnalysis(); });
el('analyzeBtn').addEventListener('click', loadAnalysis);
['balance','riskPercent','slPoints'].forEach((id) => el(id).addEventListener('change', loadAnalysis));

boot().catch((err) => {
  console.error(err);
  logItem('Boot Error', err.message || String(err));
});
