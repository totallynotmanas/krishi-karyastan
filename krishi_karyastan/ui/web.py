"""FastAPI Web Dashboard for real-time visualization of multi-agent precision farming."""

from __future__ import annotations
import os
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

from krishi_karyastan.core.models import Coordinates
from krishi_karyastan.simulation.scenarios import build_case_study_scenario

app = FastAPI(title="Krishi-Karyastan Dashboard", description="Smart Farming Cooperative Multi-Agent Monitor")

# Global simulation instance
current_engine = build_case_study_scenario()


class AnomalyRequest(BaseModel):
    x: int
    y: int
    moisture: float = 16.0
    nitrogen: float = 35.0


class StepRequest(BaseModel):
    ticks: int = 1


@app.get("/api/state")
def get_state():
    """Returns current real-time telemetry of the farm, agents, and knowledge base."""
    return current_engine.get_telemetry()


@app.post("/api/step")
def step_simulation(req: StepRequest):
    """Advances simulation by requested ticks."""
    for _ in range(max(1, min(50, req.ticks))):
        current_engine.step()
    return current_engine.get_telemetry()


@app.post("/api/reset")
def reset_simulation():
    """Resets the benchmark scenario to initial conditions."""
    global current_engine
    current_engine = build_case_study_scenario()
    return current_engine.get_telemetry()


@app.post("/api/trigger_anomaly")
def trigger_anomaly(req: AnomalyRequest):
    """Manually triggers a dry and nutrient-poor patch at (x, y)."""
    coords = Coordinates(x=req.x, y=req.y)
    if not current_engine.env.is_valid_coordinate(coords):
        raise HTTPException(status_code=400, detail="Coordinates outside farm boundaries")
    current_engine.env.set_anomalous_patch(
        coords=coords,
        moisture_pct=req.moisture,
        nitrogen_ppm=req.nitrogen,
    )
    return {"status": "anomaly_induced", "coords": [req.x, req.y]}


@app.get("/", response_class=HTMLResponse)
def index_page():
    """Returns the single-page rich responsive web dashboard."""
    return HTMLResponse(content=DASHBOARD_HTML)


def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Entry point to launch the web server."""
    uvicorn.run("krishi_karyastan.ui.web:app", host=host, port=port, reload=False)


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>🌾 Krishi-Karyastan | Smart Farming Cooperative MAS</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-dark: #0b0f17;
      --bg-card: rgba(18, 24, 38, 0.85);
      --bg-card-border: rgba(45, 62, 80, 0.6);
      --accent-green: #10b981;
      --accent-cyan: #06b6d4;
      --accent-amber: #f59e0b;
      --accent-red: #ef4444;
      --accent-purple: #8b5cf6;
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --glass-blur: blur(14px);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
      background: radial-gradient(circle at top right, #13271d 0%, #0b0f17 50%, #06090e 100%);
      color: var(--text-main);
      min-height: 100vh;
      overflow-x: hidden;
      padding: 24px;
    }

    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--bg-card-border);
    }
    .logo-container { display: flex; align-items: center; gap: 14px; }
    .logo-icon {
      font-size: 2.2rem;
      background: linear-gradient(135deg, #10b981, #06b6d4);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .logo-title h1 { font-size: 1.6rem; font-weight: 700; letter-spacing: -0.5px; }
    .logo-title p { font-size: 0.85rem; color: var(--text-muted); }

    .control-bar { display: flex; align-items: center; gap: 12px; }
    .btn {
      padding: 9px 18px;
      border-radius: 8px;
      font-family: inherit;
      font-weight: 600;
      font-size: 0.88rem;
      border: 1px solid transparent;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s ease;
    }
    .btn-primary { background: linear-gradient(135deg, #10b981, #059669); color: white; box-shadow: 0 4px 14px rgba(16, 185, 129, 0.3); }
    .btn-primary:hover { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(16, 185, 129, 0.45); }
    .btn-secondary { background: rgba(30, 41, 59, 0.8); border: 1px solid var(--bg-card-border); color: var(--text-main); }
    .btn-secondary:hover { background: rgba(45, 62, 80, 0.9); }
    .btn-danger { background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4); color: #fca5a5; }
    .btn-danger:hover { background: rgba(239, 68, 68, 0.3); }

    .tick-badge {
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.3);
      color: #34d399;
      padding: 6px 14px;
      border-radius: 20px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.9rem;
      font-weight: 600;
    }

    .main-grid {
      display: grid;
      grid-template-columns: 1fr 380px;
      gap: 24px;
    }

    .card {
      background: var(--bg-card);
      backdrop-filter: var(--glass-blur);
      border: 1px solid var(--bg-card-border);
      border-radius: 14px;
      padding: 20px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
    }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }
    .card-header h2 { font-size: 1.1rem; font-weight: 600; }

    /* Farm Grid Visual */
    .farm-canvas-container {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 16px;
    }
    .view-toggle {
      display: flex;
      gap: 8px;
      background: rgba(15, 23, 42, 0.6);
      padding: 4px;
      border-radius: 8px;
      border: 1px solid var(--bg-card-border);
    }
    .view-btn {
      padding: 5px 12px;
      border-radius: 6px;
      font-size: 0.8rem;
      font-weight: 500;
      background: transparent;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
    }
    .view-btn.active { background: #1e293b; color: #10b981; font-weight: 600; }

    .grid-board {
      display: grid;
      grid-template-columns: repeat(8, 1fr);
      gap: 6px;
      width: 100%;
      max-width: 680px;
      aspect-ratio: 1 / 1;
      padding: 10px;
      background: rgba(11, 15, 23, 0.6);
      border-radius: 12px;
      border: 1px solid var(--bg-card-border);
    }

    .sector-cell {
      position: relative;
      border-radius: 8px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      transition: all 0.25s ease;
      cursor: pointer;
      user-select: none;
    }
    .sector-cell:hover {
      transform: scale(1.05);
      border-color: #38bdf8;
      z-index: 10;
      box-shadow: 0 4px 16px rgba(56, 189, 248, 0.4);
    }
    .sector-coord {
      position: absolute;
      top: 4px;
      left: 4px;
      font-size: 0.65rem;
      font-family: 'JetBrains Mono', monospace;
      color: rgba(255, 255, 255, 0.4);
    }
    .sector-val {
      font-size: 0.95rem;
      font-weight: 700;
      font-family: 'JetBrains Mono', monospace;
    }
    .sector-sub {
      font-size: 0.68rem;
      color: rgba(255, 255, 255, 0.7);
    }
    .agent-marker {
      position: absolute;
      bottom: 4px;
      display: flex;
      gap: 2px;
    }
    .marker-badge {
      width: 18px;
      height: 18px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.7rem;
      border: 1px solid white;
      box-shadow: 0 2px 6px rgba(0,0,0,0.5);
    }

    /* Right Sidebar Widgets */
    .sidebar { display: flex; flex-direction: column; gap: 20px; }

    .agent-card-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 14px;
      border-radius: 8px;
      background: rgba(30, 41, 59, 0.4);
      border: 1px solid rgba(51, 65, 85, 0.5);
      margin-bottom: 8px;
    }
    .agent-info-left { display: flex; align-items: center; gap: 10px; }
    .agent-avatar {
      width: 32px;
      height: 32px;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.1rem;
    }
    .status-pill {
      font-size: 0.72rem;
      padding: 3px 8px;
      border-radius: 12px;
      font-weight: 600;
    }

    .msg-list {
      max-height: 280px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding-right: 4px;
    }
    .msg-bubble {
      padding: 8px 12px;
      border-radius: 8px;
      background: rgba(15, 23, 42, 0.7);
      border-left: 3px solid #10b981;
      font-size: 0.8rem;
    }
    .msg-top {
      display: flex;
      justify-content: space-between;
      margin-bottom: 4px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
    }
    .msg-perf {
      font-weight: 700;
      color: #fbbf24;
    }

    .gauge-container {
      background: rgba(15, 23, 42, 0.8);
      border-radius: 8px;
      padding: 14px;
      border: 1px solid var(--bg-card-border);
    }
    .gauge-bar-bg {
      height: 12px;
      background: #1e293b;
      border-radius: 6px;
      overflow: hidden;
      margin: 8px 0;
      position: relative;
    }
    .gauge-bar-fill {
      height: 100%;
      background: linear-gradient(90deg, #10b981, #06b6d4 70%, #ef4444 95%);
      width: 0%;
      transition: width 0.3s ease;
    }
  </style>
</head>
<body>

  <header>
    <div class="logo-container">
      <div class="logo-icon">🌾</div>
      <div class="logo-title">
        <h1>Krishi-Karyastan</h1>
        <p>Smart Farming Cooperative: Precision Agriculture Multi-Agent System</p>
      </div>
    </div>
    <div class="control-bar">
      <div class="tick-badge" id="tickDisplay">Tick: 0</div>
      <button class="btn btn-secondary" id="stepBtn" onclick="stepSim(1)">▶ Step</button>
      <button class="btn btn-primary" id="playBtn" onclick="togglePlay()">Auto Play</button>
      <button class="btn btn-secondary" onclick="resetSim()">↺ Reset</button>
      <button class="btn btn-danger" onclick="triggerPatchDeficit()">⚡ Induce Anomaly (3,4)</button>
    </div>
  </header>

  <div class="main-grid">
    <!-- Left Column: Interactive Farm Grid & Coordination Monitor -->
    <div style="display: flex; flex-direction: column; gap: 24px;">
      <div class="card">
        <div class="card-header">
          <h2>🌾 Spatial Farm Sectors (Partial Observability Grid)</h2>
          <div class="view-toggle">
            <button class="view-btn active" id="btnMoist" onclick="setView('moisture')">Moisture %</button>
            <button class="view-btn" id="btnNitro" onclick="setView('nitrogen')">Nitrogen (ppm)</button>
          </div>
        </div>

        <div class="farm-canvas-container">
          <div class="grid-board" id="gridBoard"></div>
          <div style="font-size: 0.82rem; color: var(--text-muted); display: flex; gap: 20px;">
            <span>🔍 <b>SMA</b>: Soil Monitor</span>
            <span>💧 <b>IRR</b>: Irrigation Agent</span>
            <span>🌱 <b>FRT</b>: Fertilizer Agent</span>
            <span>🐛 <b>PST</b>: Pest Scout</span>
            <span>🌾 <b>HAR</b>: Harvester</span>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h2>⚖️ Agronomic Saturation & Collision Governor</h2>
        </div>
        <div class="gauge-container">
          <div style="display: flex; justify-content: space-between; font-size: 0.85rem;">
            <span>Target Sector (3, 4) Joint Moisture: <b id="jointMoistVal">--</b></span>
            <span>Field Capacity Limit: <b>65.0%</b></span>
          </div>
          <div class="gauge-bar-bg">
            <div class="gauge-bar-fill" id="moistGauge"></div>
          </div>
          <p id="governorStatusText" style="font-size: 0.8rem; color: #34d399;">
            ✓ Safe Non-Saturated: Joint water addition is within safe agronomic boundaries. Zero hardware collisions.
          </p>
        </div>
      </div>
    </div>

    <!-- Right Column: Agents Telemetry & FIPA-ACL Message Stream -->
    <div class="sidebar">
      <div class="card">
        <div class="card-header">
          <h2>🤖 Autonomous Field Agents</h2>
        </div>
        <div id="agentsList"></div>
      </div>

      <div class="card">
        <div class="card-header">
          <h2>📨 FIPA-ACL Message Bus Feed</h2>
        </div>
        <div class="msg-list" id="msgList">
          <p style="color: var(--text-muted); font-size: 0.8rem;">Listening for agent performatives...</p>
        </div>
      </div>
    </div>
  </div>

  <script>
    let currentView = 'moisture';
    let isPlaying = false;
    let playInterval = null;

    const AGENT_META = {
      'SoilMonitor_Alpha': { icon: '🔍', color: '#38bdf8', name: 'Soil Monitor' },
      'Irrigator_Unit_1': { icon: '💧', color: '#06b6d4', name: 'Irrigation Unit' },
      'Fertilizer_Unit_1': { icon: '🌱', color: '#10b981', name: 'Fertilizer Unit' },
      'PestScout_Beta': { icon: '🐛', color: '#f59e0b', name: 'Pest Scout' },
      'Harvester_Gamma': { icon: '🌾', color: '#a855f7', name: 'Harvester' }
    };

    function setView(view) {
      currentView = view;
      document.getElementById('btnMoist').classList.toggle('active', view === 'moisture');
      document.getElementById('btnNitro').classList.toggle('active', view === 'nitrogen');
      fetchState();
    }

    async function fetchState() {
      try {
        const res = await fetch('/api/state');
        const data = await res.json();
        renderDashboard(data);
      } catch (err) {
        console.error('Fetch error:', err);
      }
    }

    async function stepSim(ticks = 1) {
      try {
        const res = await fetch('/api/step', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ticks})
        });
        const data = await res.json();
        renderDashboard(data);
      } catch (err) {
        console.error('Step error:', err);
      }
    }

    async function resetSim() {
      if (isPlaying) togglePlay();
      const res = await fetch('/api/reset', { method: 'POST' });
      const data = await res.json();
      renderDashboard(data);
    }

    async function triggerPatchDeficit() {
      await fetch('/api/trigger_anomaly', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({x: 3, y: 4, moisture: 16.0, nitrogen: 35.0})
      });
      fetchState();
    }

    function togglePlay() {
      isPlaying = !isPlaying;
      const playBtn = document.getElementById('playBtn');
      if (isPlaying) {
        playBtn.innerText = '⏸ Pause';
        playBtn.classList.replace('btn-primary', 'btn-secondary');
        playInterval = setInterval(() => stepSim(1), 500);
      } else {
        playBtn.innerText = 'Auto Play';
        playBtn.classList.replace('btn-secondary', 'btn-primary');
        clearInterval(playInterval);
      }
    }

    function renderDashboard(data) {
      document.getElementById('tickDisplay').innerText = `Tick: ${data.tick}`;

      // Build agent position map
      const agentPosMap = {};
      for (const [id, a] of Object.entries(data.agents)) {
        const key = `${a.position[0]},${a.position[1]}`;
        if (!agentPosMap[key]) agentPosMap[key] = [];
        agentPosMap[key].push({ id, ...a });
      }

      // Render Grid
      const board = document.getElementById('gridBoard');
      board.innerHTML = '';

      for (let y = 0; y < 8; y++) {
        for (let x = 0; x < 8; x++) {
          const sector = data.sectors[y][x];
          const cell = document.createElement('div');
          cell.className = 'sector-cell';

          let valText = '';
          let bgColor = '';

          if (currentView === 'moisture') {
            const m = sector.moisture;
            valText = `${m.toFixed(0)}%`;
            if (m < 22) bgColor = 'rgba(239, 68, 68, 0.45)'; // Critical dry
            else if (m < 32) bgColor = 'rgba(245, 158, 11, 0.35)'; // Dry
            else bgColor = 'rgba(16, 185, 129, 0.2)'; // Healthy
          } else {
            const n = sector.nitrogen;
            valText = `${n.toFixed(0)}`;
            if (n < 50) bgColor = 'rgba(239, 68, 68, 0.45)';
            else if (n < 80) bgColor = 'rgba(245, 158, 11, 0.35)';
            else bgColor = 'rgba(56, 189, 248, 0.2)';
          }

          cell.style.background = bgColor;
          cell.innerHTML = `
            <div class="sector-coord">${x},${y}</div>
            <div class="sector-val">${valText}</div>
            <div class="sector-sub">${currentView === 'moisture' ? 'Moist' : 'N ppm'}</div>
          `;

          // Agent markers
          const key = `${x},${y}`;
          if (agentPosMap[key]) {
            const mContainer = document.createElement('div');
            mContainer.className = 'agent-marker';
            for (const ag of agentPosMap[key]) {
              const meta = AGENT_META[ag.id] || { icon: '🤖', color: '#999' };
              const badge = document.createElement('div');
              badge.className = 'marker-badge';
              badge.style.background = meta.color;
              badge.innerText = meta.icon;
              mContainer.appendChild(badge);
            }
            cell.appendChild(mContainer);
          }

          board.appendChild(cell);
        }
      }

      // Render Agents list
      const agentList = document.getElementById('agentsList');
      agentList.innerHTML = '';
      for (const [id, a] of Object.entries(data.agents)) {
        const meta = AGENT_META[id] || { icon: '🤖', color: '#64748b', name: id };
        const item = document.createElement('div');
        item.className = 'agent-card-item';
        item.innerHTML = `
          <div class="agent-info-left">
            <div class="agent-avatar" style="background: ${meta.color}22; border: 1px solid ${meta.color}66;">
              ${meta.icon}
            </div>
            <div>
              <div style="font-weight: 600; font-size: 0.88rem;">${meta.name}</div>
              <div style="font-size: 0.75rem; color: var(--text-muted); font-family: 'JetBrains Mono', monospace;">
                Pos: (${a.position[0]}, ${a.position[1]}) | Bat: ${a.battery.toFixed(0)}%
              </div>
            </div>
          </div>
          <span class="status-pill" style="background: ${getStatusColor(a.status)}22; color: ${getStatusColor(a.status)}; border: 1px solid ${getStatusColor(a.status)}44;">
            ${a.status}
          </span>
        `;
        agentList.appendChild(item);
      }

      // Render Messages
      const msgList = document.getElementById('msgList');
      if (data.recent_messages && data.recent_messages.length > 0) {
        msgList.innerHTML = '';
        for (const m of [...data.recent_messages].reverse()) {
          const b = document.createElement('div');
          b.className = 'msg-bubble';
          b.innerHTML = `
            <div class="msg-top">
              <span class="msg-perf">${m.performative}</span>
              <span style="color: var(--text-muted);">T:${m.tick}</span>
            </div>
            <div><span style="color: var(--accent-cyan);">${m.sender}</span> ➔ <span style="color: var(--accent-purple);">${m.receiver}</span></div>
          `;
          msgList.appendChild(b);
        }
      }

      // Target Patch (3,4) Saturation Gauge
      const targetSector = data.sectors[4][3]; // row 4, col 3 = (3,4)
      if (targetSector) {
        document.getElementById('jointMoistVal').innerText = `${targetSector.moisture.toFixed(1)}%`;
        const pct = Math.min(100, Math.max(0, (targetSector.moisture / 75.0) * 100));
        document.getElementById('moistGauge').style.width = `${pct}%`;
      }
    }

    function getStatusColor(status) {
      switch(status) {
        case 'ACTUATING': return '#10b981';
        case 'NAVIGATING': return '#38bdf8';
        case 'SENSING': return '#818cf8';
        case 'NEGOTIATING': return '#f59e0b';
        default: return '#94a3b8';
      }
    }

    // Initial fetch
    fetchState();
  </script>
</body>
</html>
"""
