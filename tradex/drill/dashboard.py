from __future__ import annotations

# ruff: noqa: E501
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from tradex.auto.engine import default_engine

router = APIRouter()


class HaltRequest(BaseModel):
    confirmation: str
    reason: str = "dashboard emergency halt"


@router.get("/api/drill/status")
def drill_status() -> dict:
    engine = default_engine()
    active_run_id = getattr(engine, "active_run_id", engine.store.latest_drill_id)
    drill_id = active_run_id()
    if drill_id is None:
        raise HTTPException(status_code=404, detail="No drill has been created")
    return engine.status(drill_id)


@router.post("/api/drill/halt")
def halt_drill(request: HaltRequest) -> dict:
    if request.confirmation != "HALT":
        raise HTTPException(status_code=400, detail="confirmation must be HALT")
    engine = default_engine()
    active_run_id = getattr(engine, "active_run_id", engine.store.latest_drill_id)
    drill_id = active_run_id()
    if drill_id is None:
        raise HTTPException(status_code=404, detail="No drill has been created")
    engine.halt(drill_id, request.reason)
    return {"drill_id": drill_id, "status": "HALTED"}


@router.get("/drill", response_class=HTMLResponse)
def drill_dashboard() -> str:
    return _DASHBOARD


_DASHBOARD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TradeX Paper Drill</title>
<style>
:root{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,sans-serif}
body{margin:0;background:#07111f;color:#e5edf7}.wrap{max-width:1280px;margin:auto;padding:24px}
header{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}
h1{margin:0;color:#7dd3fc}.muted{color:#91a4b7}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin:20px 0}
.card{background:#0f1d2e;border:1px solid #20344a;border-radius:14px;padding:18px;box-shadow:0 12px 30px #0004}
.metric{font-size:1.7rem;font-weight:700}.positive{color:#4ade80}.negative{color:#fb7185}
table{width:100%;border-collapse:collapse;font-size:.9rem}th,td{text-align:left;padding:9px;border-bottom:1px solid #20344a}
th{color:#7dd3fc}.pill{display:inline-block;padding:3px 8px;border-radius:999px;background:#20344a}
button{background:#dc2626;color:white;border:0;border-radius:8px;padding:10px 14px;font-weight:700;cursor:pointer}
.scroll{overflow:auto;max-height:330px}.bar{height:8px;background:#1e293b;border-radius:9px;overflow:hidden;margin-top:8px}
.bar span{display:block;height:100%;background:#38bdf8}.error{padding:16px;background:#3f1520;border-radius:10px}
</style>
</head>
<body><div class="wrap">
<header><div><h1>TradeX One-Day Paper Drill</h1><div id="session" class="muted">Loading...</div></div>
<button onclick="haltDrill()">Emergency halt</button></header>
<div id="error"></div><div id="portfolios" class="grid"></div>
<section class="card"><h2>Equity Curve</h2><svg id="curve" viewBox="0 0 1000 220"
preserveAspectRatio="none" style="width:100%;height:220px"></svg></section>
<div class="grid"><section class="card"><h2>Open Positions</h2><div class="scroll"><table><thead><tr><th>Book</th><th>Symbol</th><th>Qty</th><th>Entry</th><th>Stop</th><th>Target</th></tr></thead><tbody id="positions"></tbody></table></div></section>
<section class="card"><h2>Model Preparation</h2><div class="scroll"><table><thead><tr><th>Book</th><th>Symbol</th><th>Source</th><th>Status</th></tr></thead><tbody id="preparations"></tbody></table></div></section></div>
<div class="grid"><section class="card"><h2>Signals and Rejections</h2><div class="scroll"><table><thead><tr><th>Time</th><th>Book</th><th>Symbol</th><th>Signal</th><th>Source</th><th>Reason</th></tr></thead><tbody id="signals"></tbody></table></div></section>
<section class="card"><h2>Health and Events</h2><div id="events" class="scroll"></div></section></div>
<section class="card"><h2>Market Data Provenance</h2><div class="scroll"><table><thead><tr><th>Captured</th><th>Book</th><th>Symbol</th><th>Price</th><th>Provider</th><th>Source timestamp</th></tr></thead><tbody id="prices"></tbody></table></div></section>
</div>
<script>
const money=n=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(n||0);
const pct=n=>`${((n||0)*100).toFixed(2)}%`; const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function refresh(){
 try{const r=await fetch('/api/auto/status',{cache:'no-store'});if(!r.ok)throw new Error(await r.text());const d=await r.json();
 document.getElementById('error').innerHTML='';document.getElementById('session').textContent=`${d.drill.session_date} | ${d.drill.status} | ${d.profile.name} ${d.profile.version} | ${d.profile.execution_mode} | phase ${d.scheduler_health.market_phase} | heartbeat ${esc(d.scheduler_health.scheduler_heartbeat_at||'none')} | policy ${d.drill.config.decision_policy_version} | refreshes every 5 seconds`;
 document.getElementById('portfolios').innerHTML=d.portfolios.map(p=>{const ret=(p.equity-5000)/5000;return `<section class="card"><h2>${esc(p.kind)}</h2><div class="metric ${ret>=0?'positive':'negative'}">${money(p.equity)}</div><p>Return ${pct(ret)} | Cash ${money(p.cash)}</p><p>Realized ${money(p.realized_pnl)} | Unrealized ${money(p.unrealized_pnl)}</p><p>Fees ${money(p.fees)} | Slippage ${money(p.slippage)}</p><p>Open ${p.open_positions} | Data failures ${p.data_failures} | ${p.halted?'HALTED':'ACTIVE'}</p><div class="bar"><span style="width:${Math.max(0,Math.min(100,ret/0.05*100))}%"></span></div><small class="muted">Progress toward informational 5% benchmark</small></section>`}).join('');
 document.getElementById('positions').innerHTML=d.positions.map(p=>`<tr><td>${esc(p.portfolio)}</td><td>${esc(p.symbol)}</td><td>${Number(p.quantity).toFixed(6)}</td><td>${money(p.entry_price)}</td><td>${money(p.stop_price)}</td><td>${money(p.take_profit_price)}</td></tr>`).join('')||'<tr><td colspan="6">No open positions</td></tr>';
 document.getElementById('preparations').innerHTML=d.preparations.map(p=>`<tr><td>${esc(p.portfolio)}</td><td>${esc(p.symbol)}</td><td>${esc(p.source)}</td><td><span class="pill">${p.approved?'APPROVED':'TA FALLBACK'}</span></td></tr>`).join('');
 document.getElementById('signals').innerHTML=d.signals.slice().reverse().map(s=>`<tr><td>${new Date(s.decided_at).toLocaleTimeString()}</td><td>${esc(s.portfolio)}</td><td>${esc(s.symbol)}</td><td>${esc(s.signal)}</td><td>${esc(s.source)}</td><td>${esc(s.reason)} | policy ${esc(s.policy_version)}</td></tr>`).join('')||'<tr><td colspan="6">Signals not evaluated yet</td></tr>';
 document.getElementById('events').innerHTML=d.events.slice().reverse().map(e=>`<p><span class="pill">${esc(e.level)}</span> <strong>${esc(e.category)}</strong> ${esc(e.message)}<br><small class="muted">${new Date(e.occurred_at).toLocaleString()}</small></p>`).join('');
 document.getElementById('prices').innerHTML=d.prices.slice().reverse().map(p=>`<tr><td>${new Date(p.captured_at).toLocaleTimeString()}</td><td>${esc(p.portfolio)}</td><td>${esc(p.symbol)}</td><td>${money(p.price)}</td><td>${esc(p.source)}</td><td>${new Date(p.period_start).toLocaleTimeString()}-${new Date(p.period_end).toLocaleTimeString()}</td></tr>`).join('')||'<tr><td colspan="6">No market data captured</td></tr>';
 drawCurve(d.equity_curve);
 }catch(e){document.getElementById('error').innerHTML=`<p class="error">${esc(e.message)}</p>`}
}
function drawCurve(points){const svg=document.getElementById('curve');svg.innerHTML='';const books=['STOCK','CRYPTO'];const colors=['#38bdf8','#f59e0b'];books.forEach((book,index)=>{const p=points.filter(x=>x.portfolio===book);if(!p.length)return;const values=p.map(x=>x.equity);const min=Math.min(4900,...values),max=Math.max(5100,...values);const coords=p.map((x,i)=>`${p.length===1?0:i/(p.length-1)*1000},${210-(x.equity-min)/(max-min)*200}`).join(' ');const line=document.createElementNS('http://www.w3.org/2000/svg','polyline');line.setAttribute('points',coords);line.setAttribute('fill','none');line.setAttribute('stroke',colors[index]);line.setAttribute('stroke-width','4');svg.appendChild(line)})}
async function haltDrill(){if(prompt('Type HALT to stop all new drill activity')!=='HALT')return;await fetch('/api/drill/halt',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirmation:'HALT'})});refresh()}
refresh();setInterval(refresh,5000);
</script></body></html>"""
