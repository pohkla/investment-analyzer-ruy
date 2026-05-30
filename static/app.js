const el = (id) => document.getElementById(id);
const state = { ws: null, lastAnalysis: null, uploadedImage: null };

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
  if (a.feed?.last_webhook || a.last_webhook) {
    el('apiStatus').textContent = 'Webhook Active';
  }
}

async function loadAnalysis(log = true) {
  const balance = el('balance').value || 300;
  const risk = el('riskPercent').value || 1;
  const slp = el('slPoints').value || 55;
  const res = await fetch(`/api/xauusd/analysis?balance=${balance}&risk_percent=${risk}&sl_points=${slp}`);
  const a = await res.json();
  updateAnalysis(a);
  if (log) logItem('Manual Analyze', `${a.market_mode} • ${a.action} • Confidence ${a.confidence}/100`);
}

function connectWS() {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
  const url = `${scheme}://${location.host}/ws/xauusd`;
  state.ws = new WebSocket(url);
  state.ws.onopen = () => {
    el('wsStatus').textContent = 'Real-time Online';
    el('wsStatus').className = 'pill';
    state.ws.send('hello');
    logItem('WebSocket Connected', 'ระบบเริ่มรับข้อมูลราคาแบบ Real-time แล้ว');
  };
  state.ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.analysis) updateAnalysis(msg.analysis);
    if (msg.type === 'tradingview_webhook') {
      logItem('TradingView Alert Received', `${msg.signal || 'ALERT'} • ${msg.price} • ${msg.message || ''}`);
    }
    if (msg.type === 'chart_image_uploaded') {
      logItem('Chart Image Uploaded', msg.filename || 'ได้รับภาพกราฟแล้ว');
    }
    if (msg.type === 'feed_error') {
      logItem('Live Feed Error', msg.error || 'ไม่สามารถดึงราคาจริงได้');
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

function setUploadPreview(file, previewUrl) {
  el('uploadEmpty').classList.add('hidden');
  el('uploadPreviewWrap').classList.remove('hidden');
  el('chartPreview').src = previewUrl;
  el('imageStatus').textContent = `เลือกไฟล์แล้ว: ${file.name}`;
  el('imageSummary').textContent = 'กด Analyze Image เพื่อส่งภาพเข้า Backend และบันทึกเป็นบริบทสำหรับการวิเคราะห์ร่วมกับราคาจริง';
}

async function uploadChartImage(file) {
  if (!file) return;
  if (!file.type.startsWith('image/')) {
    logItem('Upload Error', 'กรุณาเลือกไฟล์รูปภาพเท่านั้น');
    return;
  }
  if (file.size > 8 * 1024 * 1024) {
    logItem('Upload Error', 'ไฟล์ใหญ่เกิน 8MB');
    return;
  }

  setUploadPreview(file, URL.createObjectURL(file));
  el('imageStatus').textContent = 'กำลังอัปโหลดภาพกราฟ...';

  const form = new FormData();
  form.append('file', file);
  form.append('note', el('commandInput').value || 'Analyze uploaded XAUUSD chart image');

  try {
    const res = await fetch('/api/chart-image/upload', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.detail || data.message || 'Upload failed');
    state.uploadedImage = data;
    el('chartPreview').src = data.image_url;
    el('imageStatus').textContent = data.status || 'ได้รับภาพกราฟแล้ว';
    el('imageSummary').textContent = data.summary || 'ระบบได้รับภาพกราฟแล้ว และพร้อมใช้ประกอบการวิเคราะห์';
    el('recommendedAction').textContent = data.analysis_hint?.action || 'IMAGE_READY';
    el('planText').textContent = data.analysis_hint?.condition || 'ใช้ภาพกราฟร่วมกับราคา Real-time และ Risk Guard เพื่อประกอบการตัดสินใจ';
    logItem('Chart Image Uploaded', `${data.filename} • ${data.analysis_hint?.action || 'IMAGE_READY'}`);
  } catch (err) {
    el('imageStatus').textContent = 'อัปโหลดไม่สำเร็จ';
    el('imageSummary').textContent = err.message || String(err);
    logItem('Upload Error', err.message || String(err));
  }
}

function setupImageUpload() {
  const input = el('chartImageInput');
  const zone = el('uploadZone');
  const choose = el('chooseImageBtn');
  const replace = el('replaceImageBtn');
  const analyze = el('analyzeImageBtn');

  [choose, replace].forEach((btn) => btn?.addEventListener('click', () => input.click()));
  analyze?.addEventListener('click', () => input.files?.[0] ? uploadChartImage(input.files[0]) : input.click());
  input.addEventListener('change', () => uploadChartImage(input.files?.[0]));

  zone.addEventListener('dragover', (e) => {
    e.preventDefault();
    zone.classList.add('dragging');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragging'));
  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('dragging');
    const file = e.dataTransfer.files?.[0];
    if (file) uploadChartImage(file);
  });

  zone.addEventListener('click', (e) => {
    if (e.target.closest('button')) return;
    if (el('uploadEmpty') && !el('uploadEmpty').classList.contains('hidden')) input.click();
  });
}

async function boot() {
  setupWebhookSample();
  setupImageUpload();
  await loadAnalysis(false);
  connectWS();
}

el('refreshBtn').addEventListener('click', () => loadAnalysis());
el('analyzeBtn').addEventListener('click', loadAnalysis);
['balance','riskPercent','slPoints'].forEach((id) => el(id).addEventListener('change', () => loadAnalysis(false)));

boot().catch((err) => {
  console.error(err);
  logItem('Boot Error', err.message || String(err));
});
