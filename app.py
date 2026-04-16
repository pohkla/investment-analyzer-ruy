from __future__ import annotations

import io
import json
import math
import re
from datetime import datetime
from statistics import median
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from PIL import Image

OCR_AVAILABLE = False
OCR_ERROR = ""

try:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"
    OCR_AVAILABLE = True
except Exception as e:
    pytesseract = None
    OCR_ERROR = str(e)

app = FastAPI(title="Ray Local Investment Analyzer v6")


def run_ocr_from_image(img: np.ndarray) -> str:
    if not OCR_AVAILABLE or pytesseract is None:
        return f"OCR not available on server: {OCR_ERROR}"

    try:
        pil_img = Image.fromarray(img)
        text = pytesseract.image_to_string(pil_img)
        return text.strip()
    except Exception as e:
        return f"OCR failed: {e}"

HTML = r'''<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Ray Local Investment Analyzer v6</title>
  <style>
    :root {
      --bg:#07111f; --panel:#0f1a30; --panel2:#142241; --line:#29406c;
      --text:#edf3ff; --muted:#a9b8de; --accent:#7ca8ff; --accent2:#62e2bc;
      --warn:#ffd66b; --bad:#ff9c9c; --good:#97f1d4; --shadow:0 18px 46px rgba(0,0,0,.28);
      --radius:20px;
    }
    *{box-sizing:border-box}
    body{margin:0;font-family:Inter,system-ui,Segoe UI,Arial,sans-serif;background:linear-gradient(180deg,#07111d,#0a1730 55%,#0c1b34);color:var(--text)}
    .container{max-width:1450px;margin:0 auto;padding:24px}
    .hero,.layout,.stats,.cards2,.cards3{display:grid;gap:18px}
    .hero{grid-template-columns:1.25fr .75fr;margin-bottom:20px}
    .layout{grid-template-columns:420px 1fr}
    .stats{grid-template-columns:repeat(4,minmax(0,1fr));margin-top:18px}
    .cards2{grid-template-columns:1fr 1fr}.cards3{grid-template-columns:repeat(3,minmax(0,1fr))}
    .card{background:linear-gradient(180deg,rgba(18,29,56,.98),rgba(12,21,42,.98));border:1px solid rgba(124,168,255,.14);border-radius:var(--radius);box-shadow:var(--shadow)}
    .p24{padding:24px}.p20{padding:20px}
    h1{margin:0 0 10px;font-size:35px;line-height:1.08} h2{margin:0 0 12px;font-size:24px} h3{margin:0 0 9px;font-size:17px}
    p{margin:0;color:var(--muted);line-height:1.68}
    .chips{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}.chip{padding:8px 12px;border-radius:999px;background:rgba(124,168,255,.08);border:1px solid rgba(124,168,255,.18);font-size:13px}
    .dropzone{border:2px dashed rgba(124,168,255,.32);border-radius:18px;background:rgba(124,168,255,.05);padding:24px;text-align:center;cursor:pointer;transition:.18s}
    .dropzone.drag{border-color:var(--accent2);background:rgba(98,226,188,.07);transform:translateY(-1px)}
    .dropzone .big{font-size:21px;font-weight:800;margin-bottom:8px}.tip{margin-top:12px;padding:12px 14px;border-radius:14px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.06);font-size:13px;line-height:1.6;color:#dce7ff}
    .stack{display:grid;gap:14px;margin-top:16px}
    label{display:block;font-size:14px;font-weight:700;margin-bottom:7px;color:#e3ebff}
    input,select,button,textarea{width:100%;border-radius:14px;border:1px solid rgba(124,168,255,.18);background:rgba(255,255,255,.05);color:var(--text);padding:13px 14px;font-size:15px}
    select option{background:#11203d;color:#eef4ff}
    .row2{display:grid;grid-template-columns:1fr 1fr;gap:12px}.row3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
    button{background:linear-gradient(135deg,var(--accent),#978aff);border:none;font-weight:800;cursor:pointer}.btn-alt{background:rgba(255,255,255,.05)!important;border:1px solid rgba(124,168,255,.18)!important}.btn-good{background:linear-gradient(135deg,#62e2bc,#56b3ff)!important}
    button:hover{transform:translateY(-1px)}
    .preview-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:14px}
    .img-card{padding:10px;border-radius:16px;border:1px solid rgba(255,255,255,.06);background:rgba(255,255,255,.03)} .img-card img{width:100%;height:150px;object-fit:cover;border-radius:12px;border:1px solid rgba(255,255,255,.08)} .img-meta{margin-top:8px;font-size:13px;color:var(--muted);word-break:break-all}
    .signal{padding:10px 14px;border-radius:999px;font-size:13px;font-weight:800;display:inline-block}.buy{background:rgba(151,241,212,.12);color:var(--good);border:1px solid rgba(151,241,212,.25)} .sell{background:rgba(255,156,156,.12);color:var(--bad);border:1px solid rgba(255,156,156,.25)} .wait{background:rgba(255,214,107,.12);color:var(--warn);border:1px solid rgba(255,214,107,.25)}
    .metric{padding:16px;border-radius:16px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.06)} .metric .k{font-size:13px;color:var(--muted);margin-bottom:6px}.metric .v{font-size:24px;font-weight:800}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
    ul{margin:10px 0 0 18px;color:#e4ebff;line-height:1.7}
    .section{margin-top:18px}.hidden{display:none}.small{font-size:12px;color:var(--muted)}
    table{width:100%;border-collapse:collapse;margin-top:10px;font-size:14px} th,td{padding:10px;border-bottom:1px solid rgba(255,255,255,.08);text-align:left;vertical-align:top} th{color:#dbe5ff} td{color:#b9c7ee}
    .result-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;flex-wrap:wrap}
    @media (max-width:1024px){.hero,.layout,.stats,.cards2,.cards3,.row2,.row3{grid-template-columns:1fr}}
  </style>
</head>
<body>
<div class="container">
  <section class="hero">
    <div class="card p24">
      <h1>Ray Local Investment Analyzer v6</h1>
      <p>เวอร์ชันนี้ยกระดับการอ่านภาพกราฟจริงอีกขั้น โดยเน้น <b>candlestick structure</b>, <b>trendline</b>, <b>breakout</b>, <b>liquidity zone</b> และมีปุ่ม <b>Export Report</b> เป็นรายงานสวย ๆ แบบ local ได้ทันที</p>
      <div class="chips">
        <span class="chip">Paste Screenshot</span>
        <span class="chip">OCR Symbol / TF</span>
        <span class="chip">Candlestick Detail</span>
        <span class="chip">Trendline / Breakout</span>
        <span class="chip">Liquidity Zone</span>
        <span class="chip">Export HTML Report</span>
      </div>
    </div>
    <div class="card p24">
      <h2>ภาพที่เหมาะกับระบบ</h2>
      <p>เหมาะกับภาพ screenshot ที่เห็นส่วนหัวกราฟ, ชื่อสินทรัพย์, timeframe, แกนราคา และโซนกราฟจริงชัดเจน เช่น TradingView, MT5 หรือหน้าจอโบรกเกอร์</p>
      <div class="tip">คำแนะนำ: ถ้าเป็นไปได้ ให้ภาพมีทั้งภาพรวมและภาพซูมจุดเข้า เพื่อให้ระบบประเมิน structure, swing, breakout และ TP/SL ได้สมบูรณ์ขึ้น</div>
    </div>
  </section>

  <section class="layout">
    <div class="card p20">
      <div id="dropzone" class="dropzone" tabindex="0">
        <div class="big">ลากรูปมาวาง หรือกดเลือกไฟล์</div>
        <p>รองรับหลายไฟล์ และกด <b>Ctrl + V</b> เพื่อวางภาพจากเครื่องมือแคปหน้าจอได้</p>
      </div>
      <input id="fileInput" type="file" accept="image/*" multiple class="hidden" />

      <div class="stack">
        <div>
          <label for="assetType">ประเภทสินทรัพย์</label>
          <select id="assetType">
            <option value="auto">Auto Detect</option>
            <option value="stock">หุ้น</option>
            <option value="gold">ทองคำ</option>
            <option value="crypto">คริปโต</option>
            <option value="forex">Forex</option>
            <option value="other">อื่น ๆ</option>
          </select>
        </div>
        <div>
          <label for="riskProfile">สไตล์ความเสี่ยง</label>
          <select id="riskProfile">
            <option value="conservative">Conservative</option>
            <option value="balanced" selected>Balanced</option>
            <option value="aggressive">Aggressive</option>
          </select>
        </div>
        <div>
          <label for="currentPrice">ราคาปัจจุบัน (ไม่บังคับ)</label>
          <input id="currentPrice" type="number" step="any" placeholder="ปล่อยว่างได้ ระบบจะพยายามอ่านจากภาพ" />
        </div>
        <div>
          <label for="notes">หมายเหตุเพิ่มเติม</label>
          <textarea id="notes" placeholder="เช่น ภาพแรกคือภาพรวม ภาพสองคือจุดเข้า หรืออยากให้เน้น breakout/retest"></textarea>
        </div>
        <div class="row3">
          <button id="analyzeBtn">วิเคราะห์ทันที</button>
          <button id="exportBtn" class="btn-good" disabled>Export Report</button>
          <button id="clearBtn" class="btn-alt">ล้างรูปทั้งหมด</button>
        </div>
      </div>
    </div>

    <div class="card p20">
      <h2>ภาพที่แนบ</h2>
      <div id="previewGrid" class="preview-grid"></div>
      <div id="emptyState" class="tip" style="margin-top:16px;">ยังไม่มีรูปภาพแนบอยู่</div>
      <div id="loading" class="tip hidden" style="margin-top:16px;">กำลังวิเคราะห์ภาพด้วย OCR + Vision Engine v6...</div>
      <div id="results" class="hidden section"></div>
    </div>
  </section>
</div>

<script>
const filesStore = [];
const previewGrid = document.getElementById('previewGrid');
const fileInput = document.getElementById('fileInput');
const dropzone = document.getElementById('dropzone');
const emptyState = document.getElementById('emptyState');
const results = document.getElementById('results');
const loading = document.getElementById('loading');
const exportBtn = document.getElementById('exportBtn');
let latestResult = null;

function syncEmpty(){ emptyState.style.display = filesStore.length ? 'none' : 'block'; }
function escapeHtml(v){ return String(v ?? '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])); }
function fmt(v){ if(v === null || v === undefined || Number.isNaN(Number(v))) return '-'; return Number(v).toLocaleString('en-US',{maximumFractionDigits:6}); }
function signalClass(signal){ if(signal==='BUY') return 'buy'; if(signal==='SELL') return 'sell'; return 'wait'; }

function renderPreviews(){
  previewGrid.innerHTML='';
  filesStore.forEach((entry, idx) => {
    const card=document.createElement('div');
    card.className='img-card';
    card.innerHTML=`<img src="${entry.url}" alt="preview-${idx}"><div class="img-meta">${escapeHtml(entry.file.name || ('pasted-image-' + (idx+1) + '.png'))}</div>`;
    previewGrid.appendChild(card);
  });
  syncEmpty();
}
function addFiles(fileList){
  Array.from(fileList).forEach((file, idx) => {
    if(!file.type.startsWith('image/')) return;
    filesStore.push({ file, url: URL.createObjectURL(file), id: crypto.randomUUID() + '-' + idx });
  });
  renderPreviews();
}
function clearAll(){
  filesStore.forEach(f => URL.revokeObjectURL(f.url));
  filesStore.length = 0; fileInput.value=''; latestResult=null; exportBtn.disabled=true;
  results.classList.add('hidden'); results.innerHTML=''; renderPreviews();
}
function fileToDataUrl(file){
  return new Promise((resolve,reject)=>{
    const reader=new FileReader();
    reader.onload=()=>resolve(reader.result);
    reader.onerror=reject;
    reader.readAsDataURL(file);
  });
}

dropzone.addEventListener('click', ()=>fileInput.click());
fileInput.addEventListener('change', (e)=>addFiles(e.target.files));
dropzone.addEventListener('dragover', e=>{ e.preventDefault(); dropzone.classList.add('drag'); });
dropzone.addEventListener('dragleave', ()=>dropzone.classList.remove('drag'));
dropzone.addEventListener('drop', e=>{ e.preventDefault(); dropzone.classList.remove('drag'); addFiles(e.dataTransfer.files); });
window.addEventListener('paste', async (e)=>{
  const items=e.clipboardData?.items || []; const pasted=[];
  for(const item of items){ if(item.type.startsWith('image/')){ const blob=item.getAsFile(); if(blob) pasted.push(new File([blob], `pasted-${Date.now()}.png`, {type: blob.type})); }}
  if(pasted.length) addFiles(pasted);
});
document.getElementById('clearBtn').addEventListener('click', clearAll);

function renderResults(data){
  latestResult = data;
  exportBtn.disabled = false;
  const sigClass = signalClass(data.signal);
  const imgRows = data.images.map((img,i)=>`
    <tr>
      <td>${i+1}</td>
      <td>${escapeHtml(img.file_name)}</td>
      <td>${escapeHtml(img.detected_symbol || '-')}</td>
      <td>${escapeHtml(img.detected_timeframe || '-')}</td>
      <td>${fmt(img.detected_price)}</td>
      <td>${escapeHtml(img.trend_label)}</td>
      <td>${escapeHtml(img.breakout_signal || '-')}</td>
      <td>${escapeHtml(img.liquidity_label || '-')}</td>
      <td>${escapeHtml(img.candle_bias || '-')}</td>
    </tr>`).join('');

  results.innerHTML = `
    <div class="result-head">
      <div>
        <h2>ผลการวิเคราะห์</h2>
        <p>${escapeHtml(data.summary)}</p>
      </div>
      <div class="signal ${sigClass}">${escapeHtml(data.signal_label)}</div>
    </div>

    <div class="stats">
      <div class="metric"><div class="k">Symbol</div><div class="v mono">${escapeHtml(data.detected_symbol || '-')}</div></div>
      <div class="metric"><div class="k">Timeframe</div><div class="v mono">${escapeHtml(data.detected_timeframe || '-')}</div></div>
      <div class="metric"><div class="k">ราคาอ้างอิง</div><div class="v mono">${fmt(data.trade_plan.reference_price)}</div></div>
      <div class="metric"><div class="k">Bias</div><div class="v mono">${escapeHtml(data.trade_plan.bias)}</div></div>
    </div>

    <div class="stats">
      <div class="metric"><div class="k">Entry</div><div class="v mono">${fmt(data.trade_plan.entry)}</div></div>
      <div class="metric"><div class="k">Stop Loss</div><div class="v mono">${fmt(data.trade_plan.stop_loss)}</div></div>
      <div class="metric"><div class="k">TP1</div><div class="v mono">${fmt(data.trade_plan.take_profit_1)}</div></div>
      <div class="metric"><div class="k">TP2</div><div class="v mono">${fmt(data.trade_plan.take_profit_2)}</div></div>
    </div>

    <div class="cards3 section">
      <div class="card p20"><h3>Market Structure</h3><ul>
        <li><b>Trend:</b> ${escapeHtml(data.market_structure.trend_label)}</li>
        <li><b>Candlestick:</b> ${escapeHtml(data.market_structure.candle_bias)}</li>
        <li><b>Trendline:</b> ${escapeHtml(data.market_structure.trendline_bias)}</li>
        <li><b>Breakout:</b> ${escapeHtml(data.market_structure.breakout_signal)}</li>
        <li><b>Liquidity:</b> ${escapeHtml(data.market_structure.liquidity_label)}</li>
      </ul></div>
      <div class="card p20"><h3>Levels</h3><ul>
        <li><b>Support:</b> ${fmt(data.trade_plan.support)}</li>
        <li><b>Resistance:</b> ${fmt(data.trade_plan.resistance)}</li>
        <li><b>Swing Low:</b> ${fmt(data.trade_plan.swing_low)}</li>
        <li><b>Swing High:</b> ${fmt(data.trade_plan.swing_high)}</li>
        <li><b>Risk/Reward:</b> ${escapeHtml(data.trade_plan.rr_text)}</li>
      </ul></div>
      <div class="card p20"><h3>Quant Signals</h3><ul>
        <li><b>Direction score:</b> ${data.direction_score}</li>
        <li><b>Volatility score:</b> ${data.volatility_score}</li>
        <li><b>OCR quality:</b> ${data.ocr_quality}</li>
        <li><b>ภาพที่ใช้:</b> ${data.images.length} ไฟล์</li>
      </ul></div>
    </div>

    <div class="cards2 section">
      <div class="card p20"><h3>เหตุผลหลัก</h3><ul>${data.reasons.map(r=>`<li>${escapeHtml(r)}</li>`).join('')}</ul></div>
      <div class="card p20"><h3>ข้อควรระวัง</h3><ul>${data.cautions.map(r=>`<li>${escapeHtml(r)}</li>`).join('')}</ul></div>
    </div>

    <div class="cards2 section">
      <div class="card p20"><h3>Trendline / Breakout / Liquidity</h3><ul>
        <li><b>Trendline summary:</b> ${escapeHtml(data.market_structure.trendline_summary)}</li>
        <li><b>Breakout zone:</b> ${escapeHtml(data.market_structure.breakout_context)}</li>
        <li><b>Liquidity zone:</b> ${escapeHtml(data.market_structure.liquidity_context)}</li>
      </ul></div>
      <div class="card p20"><h3>Candlestick Detail</h3><ul>
        <li><b>Recent pattern:</b> ${escapeHtml(data.market_structure.candlestick_detail.recent_pattern)}</li>
        <li><b>Bullish candles:</b> ${data.market_structure.candlestick_detail.bullish_count}</li>
        <li><b>Bearish candles:</b> ${data.market_structure.candlestick_detail.bearish_count}</li>
        <li><b>Doji / indecision:</b> ${data.market_structure.candlestick_detail.doji_count}</li>
      </ul></div>
    </div>

    <div class="section card p20">
      <h3>รายละเอียดต่อภาพ</h3>
      <table>
        <thead><tr><th>#</th><th>ไฟล์</th><th>Symbol</th><th>TF</th><th>ราคาที่อ่านได้</th><th>Trend</th><th>Breakout</th><th>Liquidity</th><th>Candles</th></tr></thead>
        <tbody>${imgRows}</tbody>
      </table>
    </div>

    <div class="tip section small">v6 เป็น local OCR + heuristic vision engine ที่อ่านภาพลึกขึ้นกว่ารุ่นก่อน แต่ยังไม่ใช่ deep learning model เต็มรูปแบบ จึงควรตรวจยืนยันกับกราฟจริงก่อนเข้าออเดอร์</div>
  `;
  results.classList.remove('hidden');
}

document.getElementById('analyzeBtn').addEventListener('click', async ()=>{
  if(!filesStore.length){ alert('กรุณาแนบภาพอย่างน้อย 1 ภาพ'); return; }
  loading.classList.remove('hidden'); results.classList.add('hidden'); exportBtn.disabled = true;
  const fd = new FormData();
  filesStore.forEach(entry => fd.append('files', entry.file));
  fd.append('asset_type', document.getElementById('assetType').value);
  fd.append('risk_profile', document.getElementById('riskProfile').value);
  fd.append('notes', document.getElementById('notes').value || '');
  fd.append('current_price', document.getElementById('currentPrice').value || '');
  try {
const resp = await fetch('/analyze', { method:'POST', body:fd });

const text = await resp.text();
let data;

try {
  data = JSON.parse(text);
} catch (e) {
  alert("Backend ไม่ได้ส่ง JSON:\n\n" + text);
  return;
}

if (!resp.ok || !data.ok) {
  alert("วิเคราะห์ไม่สำเร็จ:\n" + (data.error || "Unknown error"));
  return;
}

renderResults(data);
    if(!resp.ok) throw new Error(data.detail || 'Analyze failed');
    renderResults(data);
  } catch(err){
    alert('วิเคราะห์ไม่สำเร็จ: ' + err.message);
  } finally { loading.classList.add('hidden'); }
});

exportBtn.addEventListener('click', async ()=>{
  if(!latestResult) return;
  const imageRows = await Promise.all(filesStore.map(async (entry, idx)=>({
    name: entry.file.name || `image-${idx+1}.png`,
    dataUrl: await fileToDataUrl(entry.file)
  })));
  const html = buildReportHtml(latestResult, imageRows);
  const blob = new Blob([html], {type:'text/html;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const ts = new Date().toISOString().replace(/[:.]/g,'-');
  a.href = url; a.download = `ray-analysis-report-${ts}.html`; a.click();
  setTimeout(()=>URL.revokeObjectURL(url), 1000);
});

function buildReportHtml(data, images){
  const reasons = data.reasons.map(r=>`<li>${escapeHtml(r)}</li>`).join('');
  const cautions = data.cautions.map(r=>`<li>${escapeHtml(r)}</li>`).join('');
  const gallery = images.map(img=>`<figure style="margin:0"><img src="${img.dataUrl}" style="width:100%;border-radius:14px;border:1px solid #dce5ff33"><figcaption style="margin-top:8px;color:#5d6f95;font-size:12px">${escapeHtml(img.name)}</figcaption></figure>`).join('');
  const rows = data.images.map((img,i)=>`<tr><td>${i+1}</td><td>${escapeHtml(img.file_name)}</td><td>${escapeHtml(img.detected_symbol || '-')}</td><td>${escapeHtml(img.detected_timeframe || '-')}</td><td>${fmt(img.detected_price)}</td><td>${escapeHtml(img.trend_label)}</td><td>${escapeHtml(img.breakout_signal || '-')}</td><td>${escapeHtml(img.liquidity_label || '-')}</td><td>${escapeHtml(img.candle_bias || '-')}</td></tr>`).join('');
  return `<!DOCTYPE html>
<html lang="th"><head><meta charset="UTF-8"><title>Ray Analysis Report</title><style>
body{font-family:Inter,Arial,sans-serif;background:#f4f7fb;color:#16223b;margin:0} .wrap{max-width:1200px;margin:0 auto;padding:26px}
.hero{background:linear-gradient(135deg,#112345,#1a3b76);color:#fff;border-radius:22px;padding:28px 30px;box-shadow:0 16px 40px rgba(17,35,69,.16)}
.grid4,.grid2,.grid3,.gallery{display:grid;gap:16px}.grid4{grid-template-columns:repeat(4,minmax(0,1fr));margin-top:18px}.grid2{grid-template-columns:1fr 1fr;margin-top:18px}.grid3{grid-template-columns:repeat(3,minmax(0,1fr));margin-top:18px}.gallery{grid-template-columns:repeat(3,minmax(0,1fr));margin-top:18px}
.card{background:#fff;border-radius:18px;padding:20px;box-shadow:0 10px 26px rgba(19,35,71,.08)} .metric .k{font-size:12px;color:#687a9f;margin-bottom:6px}.metric .v{font-size:24px;font-weight:800} .mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
ul{margin:10px 0 0 18px;line-height:1.7} table{width:100%;border-collapse:collapse;font-size:14px} th,td{padding:10px;border-bottom:1px solid #e6edf8;text-align:left;vertical-align:top} th{color:#465b86} .badge{display:inline-block;padding:8px 12px;border-radius:999px;background:#e9f4ef;color:#196746;font-weight:800}
@media print{body{background:#fff}.hero,.card{box-shadow:none;border:1px solid #e4eaf5}} @media(max-width:1024px){.grid4,.grid2,.grid3,.gallery{grid-template-columns:1fr}}
</style></head><body><div class="wrap">
  <section class="hero"><div style="display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:flex-start"><div><h1 style="margin:0 0 8px;font-size:34px">Ray Local Analysis Report v6</h1><div style="opacity:.92;line-height:1.7">${escapeHtml(data.summary)}</div><div style="margin-top:12px;font-size:13px;opacity:.86">สร้างรายงาน: ${escapeHtml(data.generated_at || '')}</div></div><div class="badge">${escapeHtml(data.signal_label)}</div></div></section>
  <section class="grid4">
    <div class="card metric"><div class="k">Symbol</div><div class="v mono">${escapeHtml(data.detected_symbol || '-')}</div></div>
    <div class="card metric"><div class="k">Timeframe</div><div class="v mono">${escapeHtml(data.detected_timeframe || '-')}</div></div>
    <div class="card metric"><div class="k">Reference Price</div><div class="v mono">${fmt(data.trade_plan.reference_price)}</div></div>
    <div class="card metric"><div class="k">Bias</div><div class="v mono">${escapeHtml(data.trade_plan.bias)}</div></div>
  </section>
  <section class="grid4">
    <div class="card metric"><div class="k">Entry</div><div class="v mono">${fmt(data.trade_plan.entry)}</div></div>
    <div class="card metric"><div class="k">Stop Loss</div><div class="v mono">${fmt(data.trade_plan.stop_loss)}</div></div>
    <div class="card metric"><div class="k">TP1</div><div class="v mono">${fmt(data.trade_plan.take_profit_1)}</div></div>
    <div class="card metric"><div class="k">TP2</div><div class="v mono">${fmt(data.trade_plan.take_profit_2)}</div></div>
  </section>
  <section class="grid3">
    <div class="card"><h3 style="margin-top:0">Market Structure</h3><ul><li><b>Trend:</b> ${escapeHtml(data.market_structure.trend_label)}</li><li><b>Candlestick:</b> ${escapeHtml(data.market_structure.candle_bias)}</li><li><b>Trendline:</b> ${escapeHtml(data.market_structure.trendline_bias)}</li><li><b>Breakout:</b> ${escapeHtml(data.market_structure.breakout_signal)}</li><li><b>Liquidity:</b> ${escapeHtml(data.market_structure.liquidity_label)}</li></ul></div>
    <div class="card"><h3 style="margin-top:0">Levels</h3><ul><li><b>Support:</b> ${fmt(data.trade_plan.support)}</li><li><b>Resistance:</b> ${fmt(data.trade_plan.resistance)}</li><li><b>Swing Low:</b> ${fmt(data.trade_plan.swing_low)}</li><li><b>Swing High:</b> ${fmt(data.trade_plan.swing_high)}</li><li><b>Risk/Reward:</b> ${escapeHtml(data.trade_plan.rr_text)}</li></ul></div>
    <div class="card"><h3 style="margin-top:0">Quant Scores</h3><ul><li><b>Direction:</b> ${data.direction_score}</li><li><b>Volatility:</b> ${data.volatility_score}</li><li><b>OCR Quality:</b> ${data.ocr_quality}</li><li><b>Images:</b> ${data.images.length}</li></ul></div>
  </section>
  <section class="grid2"><div class="card"><h3 style="margin-top:0">เหตุผลหลัก</h3><ul>${reasons}</ul></div><div class="card"><h3 style="margin-top:0">ข้อควรระวัง</h3><ul>${cautions}</ul></div></section>
  <section class="grid2"><div class="card"><h3 style="margin-top:0">Trendline / Breakout / Liquidity</h3><ul><li><b>Trendline summary:</b> ${escapeHtml(data.market_structure.trendline_summary)}</li><li><b>Breakout zone:</b> ${escapeHtml(data.market_structure.breakout_context)}</li><li><b>Liquidity zone:</b> ${escapeHtml(data.market_structure.liquidity_context)}</li></ul></div><div class="card"><h3 style="margin-top:0">Candlestick Detail</h3><ul><li><b>Recent pattern:</b> ${escapeHtml(data.market_structure.candlestick_detail.recent_pattern)}</li><li><b>Bullish candles:</b> ${data.market_structure.candlestick_detail.bullish_count}</li><li><b>Bearish candles:</b> ${data.market_structure.candlestick_detail.bearish_count}</li><li><b>Doji / indecision:</b> ${data.market_structure.candlestick_detail.doji_count}</li></ul></div></section>
  <section class="card" style="margin-top:18px"><h3 style="margin-top:0">รายละเอียดต่อภาพ</h3><table><thead><tr><th>#</th><th>ไฟล์</th><th>Symbol</th><th>TF</th><th>ราคาที่อ่านได้</th><th>Trend</th><th>Breakout</th><th>Liquidity</th><th>Candles</th></tr></thead><tbody>${rows}</tbody></table></section>
  <section class="gallery">${gallery}</section>
</div></body></html>`;
}

renderPreviews();
</script>
</body>
</html>'''


def pil_to_cv(image: Image.Image) -> np.ndarray:
    rgb = image.convert("RGB")
    return cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)


def extract_numeric_candidates(text: str) -> list[float]:
    values: list[float] = []
    normalized = text.replace("O", "0").replace("o", "0")
    for raw in re.findall(r"(?<![A-Za-z])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", normalized):
        token = raw.replace(",", "")
        try:
            num = float(token)
        except ValueError:
            continue
        if 0 < num < 10_000_000:
            values.append(num)
    return values


def normalize_symbol(token: str) -> str | None:
    token = re.sub(r"[^A-Za-z0-9:/._-]", "", token.upper())
    if len(token) < 2 or len(token) > 18:
        return None
    bad = {"BUY", "SELL", "LONG", "SHORT", "OPEN", "CLOSE", "VOL", "EMA", "MACD", "RSI", "USD"}
    if token in bad:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", token):
        return None
    patterns = [
        r"^[A-Z]{2,10}$",
        r"^[A-Z]{2,10}[A-Z0-9]{0,4}$",
        r"^[A-Z]{2,10}/[A-Z]{2,10}$",
        r"^[A-Z]{2,10}:[A-Z0-9._-]{1,12}$",
    ]
    if any(re.fullmatch(p, token) for p in patterns):
        return token
    return None


def detect_symbol_and_timeframe(image_bgr: np.ndarray) -> tuple[str | None, str | None, dict[str, Any]]:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    rois = {
        "top_left": gray[: max(45, int(h * 0.18)), : max(140, int(w * 0.5))],
        "top_bar": gray[: max(50, int(h * 0.14)), :],
        "left_bar": gray[: max(100, int(h * 0.35)), : max(220, int(w * 0.38))],
    }
    tf_pattern = re.compile(r"\b(?:[1-9]|[1-9]\d)(?:S|M|H|D|W|MO)\b|\b(?:D|W|1D|1W|1M|4H|2H|3H|15M|30M|45M|5M|1H)\b", re.I)
    symbols: list[str] = []
    timeframes: list[str] = []
    raw_texts: dict[str, str] = {}
    for key, roi in rois.items():
        scaled = cv2.resize(roi, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        thr = cv2.adaptiveThreshold(scaled, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 7)
        txt = pytesseract.image_to_string(thr, config="--psm 6")
        raw_texts[key] = txt
        for token in re.split(r"\s+", txt):
            sym = normalize_symbol(token)
            if sym:
                symbols.append(sym)
        for token in re.findall(tf_pattern, txt.upper()):
            token = token.upper()
            if token == "M":
                continue
            timeframes.append(token)
    symbol = max(symbols, key=symbols.count) if symbols else None
    timeframe = max(timeframes, key=timeframes.count) if timeframes else None
    return symbol, timeframe, {"texts": raw_texts, "symbols": symbols, "timeframes": timeframes}


def ocr_prices(image_bgr: np.ndarray) -> tuple[list[float], dict[str, Any]]:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    areas = {
        "full": gray,
        "right_strip": gray[:, int(w * 0.78):],
        "bottom_right": gray[int(h * 0.55):, int(w * 0.68):],
        "right_mid": gray[int(h * 0.15): int(h * 0.85), int(w * 0.80):],
    }
    raw_values: list[float] = []
    raw_texts: dict[str, str] = {}
    for key, area in areas.items():
        scaled = cv2.resize(area, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        thr = cv2.adaptiveThreshold(scaled, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11)
        txt = pytesseract.image_to_string(thr, config="--psm 6 -c tessedit_char_whitelist=0123456789.,")
        raw_texts[key] = txt
        raw_values.extend(extract_numeric_candidates(txt))
    filtered: list[float] = []
    seen = set()
    for value in sorted(raw_values):
        rv = round(value, 6)
        if rv in seen:
            continue
        seen.add(rv)
        filtered.append(rv)
    return filtered, {"texts": raw_texts, "count": len(filtered)}


def get_chart_roi(gray: np.ndarray) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    h, w = gray.shape[:2]
    x1, x2 = int(w * 0.07), int(w * 0.90)
    y1, y2 = int(h * 0.12), int(h * 0.86)
    return gray[y1:y2, x1:x2], (x1, y1, x2, y2)


def extract_price_path(gray: np.ndarray) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    crop, bbox = get_chart_roi(gray)
    blur = cv2.GaussianBlur(crop, (5, 5), 0)
    edges = cv2.Canny(blur, 60, 180)
    ys = np.full(edges.shape[1], np.nan, dtype=float)
    for x in range(edges.shape[1]):
        col = np.where(edges[:, x] > 0)[0]
        if len(col) >= 2:
            ys[x] = float(np.median(col))
    valid = np.where(~np.isnan(ys))[0]
    if len(valid) < max(20, edges.shape[1] * 0.05):
        thr = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 9)
        for x in range(thr.shape[1]):
            col = np.where(thr[:, x] > 0)[0]
            if len(col) >= 2:
                ys[x] = float(np.median(col))
        valid = np.where(~np.isnan(ys))[0]
    if len(valid) >= 3:
        ys_interp = ys.copy()
        xs = np.arange(len(ys))
        ys_interp[np.isnan(ys_interp)] = np.interp(xs[np.isnan(ys_interp)], xs[valid], ys[valid])
        kernel = np.ones(7) / 7.0
        ys_smooth = np.convolve(ys_interp, kernel, mode="same")
        return ys_smooth, bbox
    return ys, bbox


def detect_trend_and_volatility(image_bgr: np.ndarray) -> tuple[float, float, str, np.ndarray, tuple[int, int, int, int]]:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    path, bbox = extract_price_path(gray)
    valid = np.where(~np.isnan(path))[0]
    if len(valid) < 20:
        return 0.0, 0.25, "SIDEWAYS", path, bbox
    xs = valid.astype(float)
    ys = path[valid].astype(float)
    coeffs = np.polyfit(xs, ys, 1)
    slope = float(coeffs[0])
    crop_h = bbox[3] - bbox[1]
    crop_w = bbox[2] - bbox[0]
    trend_score = max(-1.0, min(1.0, -slope / max(1.0, crop_h / max(40.0, crop_w))))
    pred = np.polyval(coeffs, xs)
    residual = np.std(ys - pred) / max(1.0, crop_h)
    volatility = max(0.05, min(1.0, residual * 6.0))
    if trend_score > 0.18:
        label = "UPTREND"
    elif trend_score < -0.18:
        label = "DOWNTREND"
    else:
        label = "SIDEWAYS"
    return round(trend_score, 4), round(volatility, 4), label, path, bbox


def map_y_to_price(y: float, prices: list[float], chart_height: int) -> float | None:
    if not prices or chart_height <= 0 or np.isnan(y):
        return None
    pmin, pmax = min(prices), max(prices)
    if pmax <= pmin:
        return None
    ratio = 1.0 - min(max(y / chart_height, 0.0), 1.0)
    return pmin + ratio * (pmax - pmin)


def detect_swings(path: np.ndarray, prices: list[float], chart_height: int) -> dict[str, Any]:
    valid = np.where(~np.isnan(path))[0]
    if len(valid) < 30:
        return {"swing_high": None, "swing_low": None, "highs": [], "lows": []}
    ys = path
    window = max(4, len(ys) // 35)
    highs: list[tuple[int, float]] = []
    lows: list[tuple[int, float]] = []
    for i in range(window, len(ys) - window):
        seg = ys[i - window:i + window + 1]
        center = ys[i]
        if np.isnan(center) or np.isnan(seg).any():
            continue
        if center <= np.min(seg) and center < np.mean(seg) - np.std(seg) * 0.15:
            price = map_y_to_price(center, prices, chart_height)
            if price is not None:
                highs.append((i, price))
        if center >= np.max(seg) and center > np.mean(seg) + np.std(seg) * 0.15:
            price = map_y_to_price(center, prices, chart_height)
            if price is not None:
                lows.append((i, price))
    swing_high = highs[-1][1] if highs else None
    swing_low = lows[-1][1] if lows else None
    return {
        "swing_high": round(swing_high, 6) if swing_high is not None else None,
        "swing_low": round(swing_low, 6) if swing_low is not None else None,
        "highs": [round(v, 6) for _, v in highs[-8:]],
        "lows": [round(v, 6) for _, v in lows[-8:]],
    }


def detect_candlestick_detail(image_bgr: np.ndarray) -> dict[str, Any]:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    crop, _ = get_chart_roi(gray)
    blur = cv2.GaussianBlur(crop, (3, 3), 0)
    thr = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 6)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    morph = cv2.morphologyEx(thr, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candles = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        area = w * h
        if area < 16 or h < 8:
            continue
        ratio = h / max(1, w)
        if ratio < 1.2 or ratio > 20:
            continue
        if w > crop.shape[1] * 0.09 or h > crop.shape[0] * 0.75:
            continue
        candles.append((x, y, w, h))

    candles.sort(key=lambda b: b[0])
    bullish = bearish = doji = 0
    recent_types: list[str] = []
    for x, y, w, h in candles[-28:]:
        body = morph[y:y+h, x:x+w]
        coords = np.column_stack(np.where(body > 0))
        if len(coords) < 5:
            continue
        y_min, x_min = coords.min(axis=0)
        y_max, x_max = coords.max(axis=0)
        span_y = max(1.0, float(y_max - y_min))
        span_x = max(1.0, float(x_max - x_min))
        body_ratio = span_x / max(1.0, w)
        top_mass = np.sum(coords[:, 0] < (y_min + y_max) / 2.0)
        bottom_mass = np.sum(coords[:, 0] >= (y_min + y_max) / 2.0)
        upper_wick = (y_min + span_y * 0.25) / max(1.0, h)
        lower_wick = (h - y_max + span_y * 0.25) / max(1.0, h)
        if body_ratio < 0.24 or abs(top_mass - bottom_mass) <= max(3, len(coords) * 0.05):
            ctype = "doji"
            doji += 1
        elif bottom_mass > top_mass:
            ctype = "bullish"
            bullish += 1
        else:
            ctype = "bearish"
            bearish += 1
        if ctype == "bullish" and lower_wick > upper_wick * 1.25:
            ctype = "bullish rejection"
        elif ctype == "bearish" and upper_wick > lower_wick * 1.25:
            ctype = "bearish rejection"
        recent_types.append(ctype)

    base_label = "Mixed / neutral candles"
    if bullish > bearish + 2:
        base_label = "Bullish candles dominant"
    elif bearish > bullish + 2:
        base_label = "Bearish candles dominant"
    elif doji >= max(2, bullish, bearish):
        base_label = "Indecision / doji heavy"

    recent_pattern = " / ".join(recent_types[-5:]) if recent_types else "insufficient candle detail"
    return {
        "label": base_label,
        "bullish_count": bullish,
        "bearish_count": bearish,
        "doji_count": doji,
        "candle_count": bullish + bearish + doji,
        "recent_pattern": recent_pattern,
    }


def detect_trendlines(image_bgr: np.ndarray, prices: list[float], bbox: tuple[int, int, int, int]) -> dict[str, Any]:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    x1, y1, x2, y2 = bbox
    crop = gray[y1:y2, x1:x2]
    blur = cv2.GaussianBlur(crop, (5, 5), 0)
    edges = cv2.Canny(blur, 70, 180)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=55, minLineLength=max(30, crop.shape[1] // 5), maxLineGap=18)
    if lines is None:
        return {
            "trendline_bias": "No clear trendline",
            "trendline_summary": "ไม่พบเส้นแนวโน้มเด่นชัดจากภาพชุดนี้",
            "upper_line": None,
            "lower_line": None,
        }
    up_lines = []
    down_lines = []
    for raw in lines[:160]:
        x_a, y_a, x_b, y_b = raw[0]
        dx = x_b - x_a
        if abs(dx) < 18:
            continue
        slope = (y_b - y_a) / dx
        length = math.hypot(dx, y_b - y_a)
        if length < crop.shape[1] * 0.18:
            continue
        mid_y = (y_a + y_b) / 2.0
        item = {"slope": slope, "length": length, "mid_y": mid_y}
        if slope < -0.08:
            up_lines.append(item)
        elif slope > 0.08:
            down_lines.append(item)
    up_strength = round(sum(i["length"] for i in up_lines) / max(1.0, crop.shape[1]), 4)
    down_strength = round(sum(i["length"] for i in down_lines) / max(1.0, crop.shape[1]), 4)
    if up_strength > down_strength * 1.15 and up_strength > 0.45:
        bias = "Ascending structure"
        summary = "พบแนวรับ/โครงสร้างเอียงขึ้นเด่นกว่าฝั่งลง"
    elif down_strength > up_strength * 1.15 and down_strength > 0.45:
        bias = "Descending structure"
        summary = "พบแนวต้าน/โครงสร้างเอียงลงเด่นกว่าฝั่งขึ้น"
    else:
        bias = "Mixed / channel-like"
        summary = "ภาพมีลักษณะใกล้เคียง channel หรือ trendline ไม่เด่นข้างเดียว"
    return {
        "trendline_bias": bias,
        "trendline_summary": summary,
        "upper_line": round(down_strength, 4),
        "lower_line": round(up_strength, 4),
    }


def choose_reference_price(all_prices: list[float], user_price: float | None) -> float | None:
    if user_price and user_price > 0:
        return user_price
    if not all_prices:
        return None
    decimals = [p for p in all_prices if abs(p - round(p)) > 1e-8]
    candidates = decimals if decimals else all_prices
    if len(candidates) >= 3:
        return float(median(candidates[-min(7, len(candidates)):]))
    return float(median(candidates))


def cluster_levels(prices: list[float], width_pct: float = 0.006) -> list[dict[str, Any]]:
    if not prices:
        return []
    vals = sorted(prices)
    clusters: list[list[float]] = [[vals[0]]]
    for p in vals[1:]:
        anchor = median(clusters[-1])
        if abs(p - anchor) / max(1e-9, anchor) <= width_pct:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    levels = []
    for group in clusters:
        levels.append({"price": round(float(median(group)), 6), "touches": len(group), "min": min(group), "max": max(group)})
    return sorted(levels, key=lambda x: (-x["touches"], x["price"]))


def choose_support_resistance(prices: list[float], ref: float, swing_low: float | None, swing_high: float | None) -> tuple[float | None, float | None, list[dict[str, Any]]]:
    if not prices:
        return swing_low, swing_high, []
    levels = cluster_levels(prices)
    below = [lvl["price"] for lvl in levels if lvl["price"] < ref]
    above = [lvl["price"] for lvl in levels if lvl["price"] > ref]
    support = min(below, key=lambda p: abs(ref - p)) if below else None
    resistance = min(above, key=lambda p: abs(ref - p)) if above else None
    if swing_low is not None:
        support = swing_low if support is None else float(median([support, swing_low]))
    if swing_high is not None:
        resistance = swing_high if resistance is None else float(median([resistance, swing_high]))
    support = round(support, 6) if support is not None else None
    resistance = round(resistance, 6) if resistance is not None else None
    return support, resistance, levels[:10]


def detect_breakout_and_liquidity(ref_price: float | None, support: float | None, resistance: float | None, swings: dict[str, Any], trend_score: float, candle_detail: dict[str, Any]) -> dict[str, Any]:
    breakout_signal = "No clear breakout"
    breakout_context = "ราคาในภาพยังไม่หลุดระดับสำคัญอย่างชัดเจน"
    liquidity_label = "No strong liquidity clue"
    liquidity_context = "ยังไม่พบ sweep หรือ equal-high / equal-low เด่นชัด"
    if ref_price is None:
        return {
            "breakout_signal": breakout_signal,
            "breakout_context": breakout_context,
            "liquidity_label": liquidity_label,
            "liquidity_context": liquidity_context,
        }

    tol = max(ref_price * 0.0025, 1e-6)
    highs = swings.get("highs", [])
    lows = swings.get("lows", [])

    if resistance is not None and ref_price > resistance + tol:
        breakout_signal = "Bullish breakout"
        breakout_context = "ราคาปัจจุบันอยู่เหนือแนวต้านใกล้สุด มีโอกาสเป็น breakout หรือ breakout continuation"
    elif support is not None and ref_price < support - tol:
        breakout_signal = "Bearish breakdown"
        breakout_context = "ราคาปัจจุบันอยู่ต่ำกว่าแนวรับใกล้สุด มีโอกาสเป็น bearish breakout / breakdown"
    elif resistance is not None and abs(ref_price - resistance) <= tol:
        breakout_signal = "Retest under resistance"
        breakout_context = "ราคาอยู่ใกล้โซนแนวต้านพอดี ควรดูว่าจะ reject หรือทะลุ"
    elif support is not None and abs(ref_price - support) <= tol:
        breakout_signal = "Retest over support"
        breakout_context = "ราคาอยู่ใกล้โซนแนวรับพอดี ควรดูว่าจะรับอยู่หรือหลุด"

    if len(highs) >= 2:
        recent_highs = highs[-3:]
        if max(recent_highs) - min(recent_highs) <= tol * 1.4 and ref_price > max(recent_highs):
            liquidity_label = "Buy-side liquidity taken"
            liquidity_context = "มีลักษณะคล้ายกวาด high เดิม/ equal highs แล้วทะลุขึ้น"
        elif max(recent_highs) - min(recent_highs) <= tol * 1.4 and ref_price < max(recent_highs):
            liquidity_label = "Liquidity resting above highs"
            liquidity_context = "มี high ใกล้เคียงกันหลายจุด ด้านบนอาจยังมี buy-side liquidity ค้างอยู่"
    if len(lows) >= 2:
        recent_lows = lows[-3:]
        if max(recent_lows) - min(recent_lows) <= tol * 1.4 and ref_price < min(recent_lows):
            liquidity_label = "Sell-side liquidity taken"
            liquidity_context = "มีลักษณะคล้ายกวาด low เดิม/ equal lows แล้วหลุดลง"
        elif max(recent_lows) - min(recent_lows) <= tol * 1.4 and ref_price > min(recent_lows) and liquidity_label == "No strong liquidity clue":
            liquidity_label = "Liquidity resting below lows"
            liquidity_context = "มี low ใกล้เคียงกันหลายจุด ด้านล่างอาจยังมี sell-side liquidity ค้างอยู่"

    if candle_detail.get("doji_count", 0) >= 3 and breakout_signal.startswith("Bullish"):
        breakout_context += " แต่ยังมี doji เยอะ ควรระวัง false breakout"
    if candle_detail.get("doji_count", 0) >= 3 and breakout_signal.startswith("Bearish"):
        breakout_context += " แต่ยังมี doji เยอะ ควรระวัง false breakdown"

    if trend_score > 0.2 and liquidity_label == "No strong liquidity clue":
        liquidity_label = "Upside liquidity path"
        liquidity_context = "โครงสร้างภาพยังเปิดทางขึ้นมากกว่าลง"
    elif trend_score < -0.2 and liquidity_label == "No strong liquidity clue":
        liquidity_label = "Downside liquidity path"
        liquidity_context = "โครงสร้างภาพยังเปิดทางลงมากกว่าขึ้น"

    return {
        "breakout_signal": breakout_signal,
        "breakout_context": breakout_context,
        "liquidity_label": liquidity_label,
        "liquidity_context": liquidity_context,
    }


def risk_params(profile: str) -> tuple[float, float]:
    mapping = {
        "conservative": (0.006, 1.7),
        "balanced": (0.009, 2.1),
        "aggressive": (0.013, 2.8),
    }
    return mapping.get(profile, mapping["balanced"])


def build_trade_plan(ref_price: float | None, trend_score: float, volatility: float, risk_profile: str, support: float | None, resistance: float | None, swing_low: float | None, swing_high: float | None, candle_detail: dict[str, Any], breakout_signal: str, trendline_bias: str) -> dict[str, Any]:
    stop_pct_base, rr_base = risk_params(risk_profile)
    if ref_price is None:
        return {
            "reference_price": None,
            "entry": None,
            "stop_loss": None,
            "take_profit_1": None,
            "take_profit_2": None,
            "bias": "รอข้อมูลราคาเพิ่ม",
            "rr_text": "-",
            "support": support,
            "resistance": resistance,
            "swing_low": swing_low,
            "swing_high": swing_high,
        }
    stop_pct = stop_pct_base * (1 + volatility * 0.8)
    reward_pct = stop_pct * rr_base
    bullish_candles = candle_detail.get("bullish_count", 0) > candle_detail.get("bearish_count", 0)
    bearish_candles = candle_detail.get("bearish_count", 0) > candle_detail.get("bullish_count", 0)

    bullish_case = trend_score > 0.18 or breakout_signal == "Bullish breakout" or (bullish_candles and trendline_bias == "Ascending structure")
    bearish_case = trend_score < -0.18 or breakout_signal == "Bearish breakdown" or (bearish_candles and trendline_bias == "Descending structure")

    if bullish_case and not bearish_case:
        entry = support if support is not None else ref_price * (1 - stop_pct * 0.35)
        stop_anchor = min(v for v in [support, swing_low] if v is not None) if any(v is not None for v in [support, swing_low]) else None
        stop_loss = stop_anchor * (1 - stop_pct * 0.45) if stop_anchor is not None else ref_price * (1 - stop_pct)
        tp1 = resistance if resistance is not None else ref_price * (1 + reward_pct * 0.7)
        tp2 = max(tp1 * (1 + reward_pct * 0.25), ref_price * (1 + reward_pct * 1.25))
        bias = "Long / Buy setup"
    elif bearish_case and not bullish_case:
        entry = resistance if resistance is not None else ref_price * (1 + stop_pct * 0.35)
        stop_anchor = max(v for v in [resistance, swing_high] if v is not None) if any(v is not None for v in [resistance, swing_high]) else None
        stop_loss = stop_anchor * (1 + stop_pct * 0.45) if stop_anchor is not None else ref_price * (1 + stop_pct)
        tp1 = support if support is not None else ref_price * (1 - reward_pct * 0.7)
        tp2 = min(tp1 * (1 - reward_pct * 0.25), ref_price * (1 - reward_pct * 1.25))
        bias = "Short / Sell setup"
    else:
        entry = ref_price
        stop_loss = ref_price * (1 - stop_pct) if bullish_candles else ref_price * (1 + stop_pct)
        tp1 = ref_price * (1 + reward_pct * 0.55) if bullish_candles else ref_price * (1 - reward_pct * 0.55)
        tp2 = ref_price * (1 + reward_pct) if bullish_candles else ref_price * (1 - reward_pct)
        bias = "Wait / Mixed structure"

    risk = abs(entry - stop_loss)
    reward = abs(tp1 - entry)
    rr_text = f"1:{round(reward / risk, 2)}" if risk > 1e-9 else "-"
    return {
        "reference_price": round(ref_price, 6),
        "entry": round(entry, 6),
        "stop_loss": round(stop_loss, 6),
        "take_profit_1": round(tp1, 6),
        "take_profit_2": round(tp2, 6),
        "bias": bias,
        "rr_text": rr_text,
        "support": round(support, 6) if support is not None else None,
        "resistance": round(resistance, 6) if resistance is not None else None,
        "swing_low": swing_low,
        "swing_high": swing_high,
    }


def aggregate_text_choice(values: list[str | None]) -> str | None:
    vals = [v for v in values if v]
    return max(vals, key=vals.count) if vals else None


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return HTML


@app.post("/analyze")
async def analyze(
    files: list[UploadFile] = File(...),
    asset_type: str = Form("auto"),
    risk_profile: str = Form("balanced"),
    current_price: str = Form(""),
    notes: str = Form(""),
):
    try:
        if not files:
            return JSONResponse(status_code=400, content={"ok": False, "error": "No files uploaded"})

        # --- ของเดิมทั้งหมดอยู่ในนี้ ---
        # (ไม่ต้องแก้ logic ข้างใน)

        return JSONResponse({
            "ok": True,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "signal": signal,
            "signal_label": signal_label,
            "summary": summary,
            "detected_symbol": detected_symbol,
            "detected_timeframe": detected_timeframe,
            "direction_score": avg_direction,
            "volatility_score": avg_volatility,
            "ocr_quality": ocr_quality,
            "trade_plan": trade_plan,
            "market_structure": {...},
            "reasons": reasons,
            "cautions": cautions,
            "detected_levels": levels,
            "images": image_details,
        })

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": str(e),
                "type": type(e).__name__
            }
        )

    all_prices: list[float] = []
    symbols: list[str | None] = []
    timeframes: list[str | None] = []
    direction_scores: list[float] = []
    vol_scores: list[float] = []
    swing_highs: list[float] = []
    swing_lows: list[float] = []
    image_details: list[dict[str, Any]] = []
    breakout_signals: list[str] = []
    liquidity_labels: list[str] = []
    trendline_biases: list[str] = []
    candle_labels: list[str] = []
    candle_detail_samples: list[dict[str, Any]] = []

    for file in files:
        raw = await file.read()
        try:
            pil_img = Image.open(io.BytesIO(raw))
        except Exception:
            continue
        image_bgr = pil_to_cv(pil_img)
        detected_symbol, detected_timeframe, sym_meta = detect_symbol_and_timeframe(image_bgr)
        prices, price_meta = ocr_prices(image_bgr)
        trend_score, volatility, trend_label, path, bbox = detect_trend_and_volatility(image_bgr)
        chart_h = max(1, bbox[3] - bbox[1])
        swings = detect_swings(path, prices, chart_h)
        candle_detail = detect_candlestick_detail(image_bgr)
        trendline_info = detect_trendlines(image_bgr, prices, bbox)
        temp_ref = choose_reference_price(prices, None)
        temp_support, temp_resistance, temp_levels = choose_support_resistance(prices, temp_ref, swings.get("swing_low"), swings.get("swing_high")) if temp_ref else (None, None, [])
        breakout_info = detect_breakout_and_liquidity(temp_ref, temp_support, temp_resistance, swings, trend_score, candle_detail)

        all_prices.extend(prices)
        symbols.append(detected_symbol)
        timeframes.append(detected_timeframe)
        direction_scores.append(trend_score)
        vol_scores.append(volatility)
        if swings.get("swing_high") is not None:
            swing_highs.append(swings["swing_high"])
        if swings.get("swing_low") is not None:
            swing_lows.append(swings["swing_low"])
        breakout_signals.append(breakout_info["breakout_signal"])
        liquidity_labels.append(breakout_info["liquidity_label"])
        trendline_biases.append(trendline_info["trendline_bias"])
        candle_labels.append(candle_detail["label"])
        candle_detail_samples.append(candle_detail)

        image_details.append({
            "file_name": file.filename or "uploaded-image.png",
            "detected_symbol": detected_symbol,
            "detected_timeframe": detected_timeframe,
            "detected_price": temp_ref,
            "trend_score": trend_score,
            "volatility": volatility,
            "trend_label": trend_label,
            "swing_summary": f"H {swings.get('swing_high') or '-'} / L {swings.get('swing_low') or '-'}",
            "swing_high": swings.get("swing_high"),
            "swing_low": swings.get("swing_low"),
            "candle_bias": candle_detail["label"],
            "candlestick_detail": candle_detail,
            "trendline_bias": trendline_info["trendline_bias"],
            "breakout_signal": breakout_info["breakout_signal"],
            "liquidity_label": breakout_info["liquidity_label"],
            "ocr_price_count": price_meta["count"],
            "raw_symbol_text": sym_meta["texts"],
            "raw_price_text": price_meta["texts"],
        })

    if not image_details:
        return JSONResponse(status_code=400, content={"detail": "No valid images could be processed"})

    detected_symbol = aggregate_text_choice(symbols)
    detected_timeframe = aggregate_text_choice(timeframes)
    ref_price = choose_reference_price(all_prices, user_price)
    avg_direction = round(float(np.mean(direction_scores)) if direction_scores else 0.0, 4)
    avg_volatility = round(float(np.mean(vol_scores)) if vol_scores else 0.25, 4)
    swing_high = round(float(median(swing_highs)), 6) if swing_highs else None
    swing_low = round(float(median(swing_lows)), 6) if swing_lows else None
    support, resistance, levels = choose_support_resistance(all_prices, ref_price, swing_low, swing_high) if ref_price else (swing_low, swing_high, [])

    dominant_candle = aggregate_text_choice(candle_labels) or "Mixed / neutral candles"
    dominant_trendline = aggregate_text_choice(trendline_biases) or "No clear trendline"
    dominant_breakout = aggregate_text_choice(breakout_signals) or "No clear breakout"
    dominant_liquidity = aggregate_text_choice(liquidity_labels) or "No strong liquidity clue"
    dominant_candle_detail = candle_detail_samples[-1] if candle_detail_samples else {"recent_pattern": "-", "bullish_count": 0, "bearish_count": 0, "doji_count": 0}

    breakout_info = detect_breakout_and_liquidity(ref_price, support, resistance, {"highs": swing_highs[-6:], "lows": swing_lows[-6:]}, avg_direction, dominant_candle_detail)
    trade_plan = build_trade_plan(ref_price, avg_direction, avg_volatility, risk_profile, support, resistance, swing_low, swing_high, dominant_candle_detail, breakout_info["breakout_signal"], dominant_trendline)

    signal = "WAIT"
    signal_label = "WAIT / รอจังหวะยืนยัน"
    if trade_plan["bias"].startswith("Long"):
        signal, signal_label = "BUY", "BUY SETUP / มองจังหวะ Long"
    elif trade_plan["bias"].startswith("Short"):
        signal, signal_label = "SELL", "SELL SETUP / มองจังหวะ Short"

    reasons = [
        f"ภาพรวมโครงสร้างราคาออกแนว {('ขาขึ้น' if avg_direction > 0.18 else 'ขาลง' if avg_direction < -0.18 else 'แกว่งตัว/กลาง ๆ')} จาก direction score = {avg_direction}",
        f"Candlestick detail บ่งชี้ว่า: {dominant_candle}",
        f"Trendline analysis สรุปว่า: {dominant_trendline}",
        f"Breakout context: {breakout_info['breakout_context']}",
        f"Liquidity context: {breakout_info['liquidity_context']}",
    ]
    if support is not None and resistance is not None:
        reasons.append(f"ระบบประเมินแนวรับ/แนวต้านใกล้สุดที่ประมาณ {support} / {resistance}")
    if trade_plan["entry"] is not None:
        reasons.append(f"จุดเข้าแนะนำอยู่แถว {trade_plan['entry']} โดยใช้โครงสร้างราคากับ risk profile แบบ {risk_profile}")

    cautions = [
        "OCR อาจอ่านเลขราคาเพี้ยนได้หากภาพเบลอหรือครอปแกนราคาหาย",
        "การอ่านแท่งเทียนจากภาพเป็น heuristic vision ไม่ใช่การ parse data feed ตรง",
        "ถ้ามี breakout signal แต่ doji เยอะ หรือภาพไม่ชัด ควรรอสัญญาณยืนยันเพิ่ม",
    ]
    if notes.strip():
        cautions.append(f"หมายเหตุจากผู้ใช้: {notes.strip()}")

    summary = "ระบบวิเคราะห์จากภาพกราฟจริงโดยประมวลผล symbol/timeframe, candlestick structure, trendline, breakout และ liquidity zone เพื่อสร้างแผน Entry / SL / TP บนเครื่อง local"
    ocr_quality = min(1.0, round((len(all_prices) / max(1, len(files))) / 18.0, 4))

    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "signal": signal,
        "signal_label": signal_label,
        "summary": summary,
        "detected_symbol": detected_symbol,
        "detected_timeframe": detected_timeframe,
        "direction_score": avg_direction,
        "volatility_score": avg_volatility,
        "ocr_quality": ocr_quality,
        "trade_plan": trade_plan,
        "market_structure": {
            "trend_label": "UPTREND" if avg_direction > 0.18 else "DOWNTREND" if avg_direction < -0.18 else "SIDEWAYS",
            "candle_bias": dominant_candle,
            "trendline_bias": dominant_trendline,
            "trendline_summary": trendline_info["trendline_summary"] if image_details else "-",
            "breakout_signal": breakout_info["breakout_signal"],
            "breakout_context": breakout_info["breakout_context"],
            "liquidity_label": breakout_info["liquidity_label"],
            "liquidity_context": breakout_info["liquidity_context"],
            "candlestick_detail": dominant_candle_detail,
        },
        "reasons": reasons,
        "cautions": cautions,
        "detected_levels": levels,
        "images": image_details,
        "meta": {
            "asset_type": asset_type,
            "risk_profile": risk_profile,
            "notes": notes,
        },
    }
    return JSONResponse(content=json.loads(json.dumps(payload, default=str)))
