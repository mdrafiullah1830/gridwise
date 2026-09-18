/* ── State ─────────────────────────────────────────────── */
let currentResponse = null;
let charts = {};
let loadingAnim = null;
let compareSlots = [];
let demoRunning = false;

/* ── Init ─────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', async () => {
    initHourlyTable();
    loadSamples();
    loadTemplates();
    loadHistory();
    checkHealth();
    setInterval(checkHealth, 30000);
    document.addEventListener('keydown', handleKeys);
    document.addEventListener('keydown', handleNoteCount);
    document.getElementById('sampleSelect').addEventListener('change', loadSample);
    const saved = localStorage.getItem('gridwise-theme');
    if (saved) document.documentElement.setAttribute('data-theme', saved);
    restoreURLState();
    addCompareSlot();
    addCompareSlot();
});

/* ── Tab Navigation ───────────────────────────────────── */
function switchTab(name) {
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelector(`.nav-tab[onclick="switchTab('${name}')"]`).classList.add('active');
    document.getElementById(`tab-${name}`).classList.add('active');
    if (name === 'history') loadHistory();
    updateURLState();
}

/* ── Health Check ─────────────────────────────────────── */
async function checkHealth() {
    const badge = document.getElementById('statusBadge');
    try {
        const r = await fetch('/health'); await r.json();
        badge.className = 'status-badge ok';
        badge.querySelector('span:last-child').textContent = 'API Online';
    } catch {
        badge.className = 'status-badge err';
        badge.querySelector('span:last-child').textContent = 'API Offline';
    }
}

/* ── Hourly Table ─────────────────────────────────────── */
function initHourlyTable() {
    const tbody = document.getElementById('hourlyBody');
    const defaults = [
        [0.01,0,3.20],[0.01,0,3.20],[0.01,0,3.20],[0.01,0,3.20],
        [0.02,0,3.20],[0.02,0,3.20],[0.02,2,3.20],[0.03,10,3.20],
        [0.04,30,3.20],[0.04,65,3.20],[0.05,130,3.20],[0.05,182,3.20],
        [0.05,210,3.20],[0.05,194,3.20],[0.05,130,3.20],[0.04,65,3.20],
        [0.04,30,3.20],[0.03,10,3.20],[0.02,2,3.20],[0.02,0,3.20],
        [0.01,0,3.20],[0.01,0,3.20],[0.01,0,3.20],[0.01,0,3.20]
    ];
    let html = '';
    for (let h = 0; h < 24; h++) {
        const [d,s,t] = defaults[h];
        html += `<tr><td>${String(h).padStart(2,'0')}:00</td><td><input type="number" value="${d}" step="0.01" min="0" data-hr="${h}" data-field="demand"></td><td><input type="number" value="${s}" step="0.1" min="0" data-hr="${h}" data-field="solar"></td><td><input type="number" value="${t}" step="0.01" min="0" data-hr="${h}" data-field="tariff"></td></tr>`;
    }
    tbody.innerHTML = html;
}

function getHourlyData() {
    const data = { demand: [], solar: [], tariff: [] };
    for (let h = 0; h < 24; h++) {
        data.demand.push(parseFloat(document.querySelector(`[data-hr="${h}"][data-field="demand"]`)?.value) || 0);
        data.solar.push(parseFloat(document.querySelector(`[data-hr="${h}"][data-field="solar"]`)?.value) || 0);
        data.tariff.push(parseFloat(document.querySelector(`[data-hr="${h}"][data-field="tariff"]`)?.value) || 0);
    }
    return data;
}

function setHourlyData(demand, solar, tariff) {
    for (let h = 0; h < 24; h++) {
        const d = document.querySelector(`[data-hr="${h}"][data-field="demand"]`);
        const s = document.querySelector(`[data-hr="${h}"][data-field="solar"]`);
        const t = document.querySelector(`[data-hr="${h}"][data-field="tariff"]`);
        if (d) d.value = demand[h] ?? 0;
        if (s) s.value = solar[h] ?? 0;
        if (t) t.value = tariff[h] ?? 0;
    }
}

function randomiseHourlyData() {
    const demand = Array.from({length:24}, () => +(Math.random()*50+200).toFixed(3));
    const solar = Array.from({length:24}, (_,i) => i<6||i>19?0:+((i-5)*35).toFixed(1));
    const tariff = Array.from({length:24}, () => +(Math.random()*3+2).toFixed(2));
    setHourlyData(demand, solar, tariff);
    toast('Randomised hourly data', 'info');
}
function clearHourlyData() { setHourlyData(Array(24).fill(0),Array(24).fill(0),Array(24).fill(0)); }

/* ── Notes ────────────────────────────────────────────── */
function getNotes() { return Array.from(document.querySelectorAll('#notesContainer input[data-note]')).map(i=>i.value.trim()).filter(Boolean); }
function addNote() {
    const inputs = document.querySelectorAll('#notesContainer input[data-note]');
    if (inputs.length >= 3) { toast('Max 3 notes','error'); return; }
    const c = document.getElementById('notesContainer');
    const idx = inputs.length;
    const row = document.createElement('div'); row.className='note-row';
    row.innerHTML=`<span class="note-index">${idx}</span><input type="text" class="input" placeholder="e.g. Keep battery above 30%..." data-note="${idx}"><button class="btn btn-icon btn-danger" onclick="removeNote(this)"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>`;
    c.appendChild(row); row.querySelector('input').focus();
}
function removeNote(btn) {
    if (document.querySelectorAll('#notesContainer .note-row').length<=1) { toast('At least 1 note','error'); return; }
    btn.closest('.note-row').remove(); reindexNotes();
}
function reindexNotes() { document.querySelectorAll('#notesContainer .note-row').forEach((r,i)=>{r.querySelector('.note-index').textContent=i;r.querySelector('input').dataset.note=i;}); }
function handleNoteCount(e) { if(e.key==='Tab'&&e.target.closest('#notesContainer')){const inputs=document.querySelectorAll('#notesContainer input[data-note]');if(e.target===inputs[inputs.length-1]&&!e.shiftKey&&inputs.length<3)addNote();} }

/* ── Samples & Templates ──────────────────────────────── */
async function loadSamples() {
    try {
        const r = await fetch('/scenarios'); const d = await r.json();
        const sel = document.getElementById('sampleSelect');
        sel.innerHTML = '<option value="">Load sample case...</option>';
        d.samples.forEach(s => { const o=document.createElement('option'); o.value=JSON.stringify(s); o.textContent=`${s.id} — ${(s.notes[0]||'').substring(0,50)}...`; sel.appendChild(o); });
    } catch { toast('Failed to load samples','error'); }
}

async function loadTemplates() {
    try {
        const r = await fetch('/templates'); const d = await r.json();
        const sel = document.getElementById('templateSelect');
        sel.innerHTML = '<option value="">Load template...</option>';
        d.templates.forEach(t => { const o=document.createElement('option'); o.value=JSON.stringify(t); o.textContent=`${t.name} — ${t.description.substring(0,40)}...`; sel.appendChild(o); });
    } catch {}
}

function loadSample() {
    const sel = document.getElementById('sampleSelect'); if (!sel.value) return;
    try {
        const s = JSON.parse(sel.value);
        applyScenarioData(s.id, s.notes, s.hours, s.battery);
        toast(`Loaded ${s.id}`, 'success');
    } catch { toast('Invalid sample','error'); }
}

function loadTemplate() {
    const sel = document.getElementById('templateSelect'); if (!sel.value) return;
    try {
        const t = JSON.parse(sel.value);
        applyScenarioData(t.id, t.notes, t.hours, t.battery);
        toast(`Loaded template: ${t.name}`, 'success');
    } catch { toast('Invalid template','error'); }
}

function applyScenarioData(id, notes, hours, battery) {
    document.getElementById('scenarioId').value = id;
    if (battery) {
        document.getElementById('batteryCapacity').value = battery.capacity_kwh;
        document.getElementById('batteryInitial').value = battery.initial_energy_kwh;
        document.getElementById('batteryMin').value = battery.minimum_energy_kwh;
        document.getElementById('batteryChargeRate').value = battery.max_charge_kwh_per_hour;
        document.getElementById('batteryDischargeRate').value = battery.max_discharge_kwh_per_hour;
    }
    if (hours && hours.length === 24) {
        setHourlyData(hours.map(h=>h.demand_kwh), hours.map(h=>h.solar_kwh), hours.map(h=>h.tariff_bdt_per_kwh));
    }
    const c = document.getElementById('notesContainer'); c.innerHTML = '';
    (notes||[]).forEach((note,i) => {
        const row = document.createElement('div'); row.className='note-row';
        row.innerHTML=`<span class="note-index">${i}</span><input type="text" class="input" value="${note}" data-note="${i}"><button class="btn btn-icon btn-danger" onclick="removeNote(this)"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>`;
        c.appendChild(row);
    });
    updateURLState();
}

function randomScenario() {
    const notes=["Solar panels will be washed from noon until 2 PM","Battery should stay above 30% overnight for emergencies","Please avoid charging during peak hours 17:00 to 21:00","Grid import should not exceed 60 kWh at any hour","Keep battery reserve at least 40 kWh from 01:00 to 06:00","Battery should be fully charged by 11:00"];
    const rand=[]; const count=Math.floor(Math.random()*3)+1; const used=new Set();
    while(rand.length<count){const idx=Math.floor(Math.random()*notes.length);if(!used.has(idx)){used.add(idx);rand.push(notes[idx]);}}
    const c=document.getElementById('notesContainer'); c.innerHTML='';
    rand.forEach((note,i)=>{const row=document.createElement('div');row.className='note-row';row.innerHTML=`<span class="note-index">${i}</span><input type="text" class="input" value="${note}" data-note="${i}"><button class="btn btn-icon btn-danger" onclick="removeNote(this)"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>`;c.appendChild(row);});
    toast('Random scenario loaded','info');
}

/* ── Build Payload ────────────────────────────────────── */
function buildPayload() {
    const notes = getNotes();
    if (!notes.length) { toast('Add at least 1 note','error'); return null; }
    const hourly = getHourlyData();
    return {
        scenario_id: document.getElementById('scenarioId').value || `SCENARIO-${Date.now()}`,
        operator_notes: notes,
        hours: Array.from({length:24}, (_,h) => ({hour:h, demand_kwh:hourly.demand[h], solar_kwh:hourly.solar[h], tariff_bdt_per_kwh:hourly.tariff[h]})),
        battery: {
            capacity_kwh: parseFloat(document.getElementById('batteryCapacity').value)||220,
            initial_energy_kwh: parseFloat(document.getElementById('batteryInitial').value)||110,
            minimum_energy_kwh: parseFloat(document.getElementById('batteryMin').value)||40,
            max_charge_kwh_per_hour: parseFloat(document.getElementById('batteryChargeRate').value)||50,
            max_discharge_kwh_per_hour: parseFloat(document.getElementById('batteryDischargeRate').value)||50,
        }
    };
}

/* ── Optimise ─────────────────────────────────────────── */
async function runOptimization() {
    const payload = buildPayload(); if (!payload) return;
    const btn = document.getElementById('optimizeBtn'); const btnText = document.getElementById('optimizeBtnText');
    btn.disabled = true; btnText.textContent = 'Processing...';
    showLoading('Interpreting operator notes with LLM...');
    try {
        const res = await fetch('/optimize-energy', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
        const data = await res.json(); hideLoading();
        if (!res.ok) { toast(data.detail||'Optimisation failed','error'); return; }
        currentResponse = data;
        renderResults(data);
        saveToHistory(payload, data);
        toast(`Optimised — BDT ${data.total_cost_bdt}`, 'success');
    } catch (err) { hideLoading(); toast(`Failed: ${err.message}`,'error'); }
    finally { btn.disabled=false; btnText.textContent='Optimise Schedule'; }
}

async function runBaseline() {
    const payload = buildPayload(); if (!payload) return;
    showLoading('Running baseline comparison...');
    try {
        const res = await fetch('/optimize-energy/baseline', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
        const data = await res.json(); hideLoading();
        if (!res.ok) { toast(data.detail||'Baseline failed','error'); return; }
        renderBaseline(data);
        toast(`Savings: BDT ${data.savings_bdt} (${data.savings_pct}%)`, 'success');
    } catch (err) { hideLoading(); toast(`Failed: ${err.message}`,'error'); }
}

/* ── Compare ──────────────────────────────────────────── */
function addCompareSlot() {
    if (compareSlots.length >= 5) { toast('Max 5 scenarios','error'); return; }
    const id = compareSlots.length;
    compareSlots.push({ notes: '', demand: '', solar: '', tariff: '', cap: 220, init: 110, min: 40, ch: 50, dch: 50 });
    const c = document.getElementById('compareScenarios');
    const div = document.createElement('div');
    div.className = 'compare-slot'; div.id = `compare-slot-${id}`;
    div.innerHTML = `<div class="compare-slot-header"><span class="note-index">${id+1}</span><strong>Scenario ${id+1}</strong><button class="btn btn-icon btn-danger btn-sm" onclick="removeCompareSlot(${id})"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button></div>
    <div class="input-grid compact">
        <div class="input-group" style="grid-column:1/-1"><label>Operator Notes</label><input type="text" class="input" placeholder="e.g. Solar panels washed from noon to 2 PM" data-cid="${id}" data-cfield="notes"></div>
        <div class="input-group"><label>Battery Cap</label><input type="number" class="input" value="220" data-cid="${id}" data-cfield="cap"></div>
        <div class="input-group"><label>Initial</label><input type="number" class="input" value="110" data-cid="${id}" data-cfield="init"></div>
        <div class="input-group"><label>Min Res</label><input type="number" class="input" value="40" data-cid="${id}" data-cfield="min"></div>
    </div>`;
    c.appendChild(div);
}

function removeCompareSlot(id) {
    const el = document.getElementById(`compare-slot-${id}`); if (el) el.remove();
    compareSlots = compareSlots.filter((_,i) => i !== id);
}

function readCompareSlots() {
    const scenarios = [];
    document.querySelectorAll('.compare-slot').forEach((slot, i) => {
        const notes = slot.querySelector(`[data-cfield="notes"]`)?.value?.trim();
        if (!notes) return;
        const cap = parseFloat(slot.querySelector(`[data-cfield="cap"]`)?.value)||220;
        const init = parseFloat(slot.querySelector(`[data-cfield="init"]`)?.value)||110;
        const min = parseFloat(slot.querySelector(`[data-cfield="min"]`)?.value)||40;
        const hourly = getHourlyData();
        scenarios.push({
            scenario_id: `COMPARE-${i+1}`, operator_notes: [notes],
            hours: Array.from({length:24}, (_,h) => ({hour:h, demand_kwh:hourly.demand[h], solar_kwh:hourly.solar[h], tariff_bdt_per_kwh:hourly.tariff[h]})),
            battery: { capacity_kwh:cap, initial_energy_kwh:init, minimum_energy_kwh:min, max_charge_kwh_per_hour:50, max_discharge_kwh_per_hour:50 }
        });
    });
    return scenarios;
}

async function runCompare() {
    const scenarios = readCompareSlots();
    if (scenarios.length < 2) { toast('Need at least 2 scenarios with notes','error'); return; }
    showLoading('Comparing scenarios...');
    try {
        const res = await fetch('/compare', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({scenarios}) });
        const data = await res.json(); hideLoading();
        if (!res.ok) { toast(data.detail||'Compare failed','error'); return; }
        renderCompareResults(data);
        toast(`Best: ${data.best_scenario_id} — saves BDT ${data.cost_difference_bdt}`, 'success');
    } catch (err) { hideLoading(); toast(`Failed: ${err.message}`,'error'); }
}

/* ── What-If ──────────────────────────────────────────── */
async function runWhatIf() {
    const payload = buildPayload(); if (!payload) return;
    const param = document.getElementById('whatIfParam').value;
    const from = parseFloat(document.getElementById('whatIfFrom').value);
    const to = parseFloat(document.getElementById('whatIfTo').value);
    const steps = parseInt(document.getElementById('whatIfSteps').value)||6;
    const values = Array.from({length:steps}, (_,i) => +(from + (to-from)*(i/(steps-1))).toFixed(1));
    showLoading('Running what-if analysis...');
    try {
        const res = await fetch('/what-if', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({...payload, param, values}) });
        const data = await res.json(); hideLoading();
        if (!res.ok) { toast(data.detail||'What-if failed','error'); return; }
        renderWhatIf(data);
        toast(`What-if complete — ${data.points.length} points`, 'success');
    } catch (err) { hideLoading(); toast(`Failed: ${err.message}`,'error'); }
}

/* ── Carbon ───────────────────────────────────────────── */
async function runCarbon() {
    const payload = buildPayload(); if (!payload) return;
    payload.carbon_factor_kg_per_kwh = parseFloat(document.getElementById('carbonFactor').value)||0.5;
    payload.cost_weight = parseFloat(document.getElementById('costWeight').value)||0.7;
    payload.carbon_weight = parseFloat(document.getElementById('carbonWeight').value)||0.3;
    showLoading('Running carbon-aware optimisation...');
    try {
        const res = await fetch('/optimize-carbon', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
        const data = await res.json(); hideLoading();
        if (!res.ok) { toast(data.detail||'Carbon failed','error'); return; }
        renderCarbonResults(data);
        toast(`Carbon: ${data.total_carbon_kg} kg CO₂`, 'success');
    } catch (err) { hideLoading(); toast(`Failed: ${err.message}`,'error'); }
}

/* ── History ──────────────────────────────────────────── */
async function loadHistory() {
    try {
        const r = await fetch('/history'); const d = await r.json();
        const c = document.getElementById('historyList');
        if (!d.runs.length) { c.innerHTML = '<p class="hint">No runs yet. Run an optimisation to see history here.</p>'; return; }
        c.innerHTML = d.runs.map(run => `
            <div class="history-item" onclick="viewHistoryRun(${run.id})">
                <div class="history-meta"><span class="history-id">#${run.id}</span><span class="history-scenario">${run.scenario_id}</span><span class="history-time">${run.created_at||'—'}</span></div>
                <div class="history-notes">${(JSON.parse(run.notes)||[]).map(n=>`<span class="history-note">${n.substring(0,60)}...</span>`).join('')}</div>
            </div>`).join('');
    } catch {}
}

async function viewHistoryRun(id) {
    try {
        const r = await fetch(`/history/${id}`); const d = await r.json();
        if (d.response) { currentResponse = d.response; renderResults(d.response); switchTab('optimise'); toast(`Loaded run #${id}`,'success'); }
    } catch { toast('Failed to load run','error'); }
}

async function saveToHistory(payload, response) {
    try { await fetch('/history/save', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({scenario_id:payload.scenario_id, notes:payload.operator_notes, response}) }); } catch {}
}

/* ── Live Demo ────────────────────────────────────────── */
async function runDemo() {
    if (demoRunning) { demoRunning = false; document.getElementById('demoBtn').innerHTML='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>Start Demo'; return; }
    demoRunning = true;
    const btn = document.getElementById('demoBtn');
    btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>Stop';
    const prog = document.getElementById('demoProgress'); prog.style.display='flex';
    const results = document.getElementById('demoResults'); results.innerHTML='';
    let data;
    try { const r = await fetch('/scenarios'); data = await r.json(); } catch { toast('Failed to load scenarios','error'); demoRunning=false; return; }
    for (let i = 0; i < data.samples.length && demoRunning; i++) {
        const s = data.samples[i];
        document.getElementById('demoBar').style.width = `${((i+1)/data.samples.length)*100}%`;
        document.getElementById('demoStatus').textContent = `Running ${s.id} (${i+1}/${data.samples.length})...`;
        try {
            const payload = {
                scenario_id: s.id, operator_notes: s.notes, hours: s.hours,
                battery: { capacity_kwh:s.battery.capacity_kwh, initial_energy_kwh:s.battery.initial_energy_kwh, minimum_energy_kwh:s.battery.minimum_energy_kwh, max_charge_kwh_per_hour:s.battery.max_charge_kwh_per_hour, max_discharge_kwh_per_hour:s.battery.max_discharge_kwh_per_hour }
            };
            const res = await fetch('/optimize-energy', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
            const r = await res.json();
            results.innerHTML += `<div class="demo-card ${i===data.samples.length-1?'demo-last':''}"><div class="demo-card-header"><span class="demo-badge">${s.id}</span><span class="demo-cost">BDT ${r.total_cost_bdt}</span><span class="demo-grid">${r.total_grid_kwh} kWh grid</span></div><div class="demo-notes">${s.notes[0]?.substring(0,80)}...</div></div>`;
        } catch { results.innerHTML += `<div class="demo-card error"><span class="demo-badge">${s.id}</span> — Failed</div>`; }
        await new Promise(r => setTimeout(r, 300));
    }
    document.getElementById('demoStatus').textContent = demoRunning ? 'All 10 cases complete!' : 'Stopped';
    document.getElementById('demoBar').style.width = '100%';
    demoRunning = false;
    btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>Start Demo';
}

/* ── Render Results ───────────────────────────────────── */
function renderResults(data) {
    const sec = document.getElementById('resultsSection'); sec.style.display='block';
    const cap = parseFloat(document.getElementById('batteryCapacity').value)||220;
    sec.innerHTML = `
        <div class="summary-grid">
            <div class="summary-card"><div class="summary-icon blue"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg></div><div class="summary-data"><span class="summary-value">${data.total_cost_bdt.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}</span><span class="summary-label">Total Cost (BDT)</span></div></div>
            <div class="summary-card"><div class="summary-icon green"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg></div><div class="summary-data"><span class="summary-value">${data.total_grid_kwh.toFixed(1)}</span><span class="summary-label">Grid Total (kWh)</span></div></div>
            <div class="summary-card"><div class="summary-icon orange"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg></div><div class="summary-data"><span class="summary-value">${data.peak_grid_kwh.toFixed(1)}</span><span class="summary-label">Peak Grid (kWh)</span></div></div>
            <div class="summary-card"><div class="summary-icon purple"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg></div><div class="summary-data"><span class="summary-value">${data.solver_status||'Optimal'}</span><span class="summary-label">Solver Status</span></div></div>
        </div>
        <div class="card"><div class="card-header"><h2>LLM Directive Interpretation</h2><button class="btn btn-ghost btn-sm" onclick="copyDirectives()">Copy</button></div><div id="directiveList">${renderDirectivesHTML(data.directive_interpretation)}</div></div>
        <div class="charts-grid">
            <div class="card"><div class="card-header"><h2>Grid vs Solar</h2></div><div class="chart-container"><canvas id="gridSolarChart"></canvas></div></div>
            <div class="card"><div class="card-header"><h2>Battery SOC</h2></div><div class="chart-container"><canvas id="batteryChart"></canvas></div></div>
            <div class="card"><div class="card-header"><h2>Cost per Hour</h2></div><div class="chart-container"><canvas id="costChart"></canvas></div></div>
            <div class="card"><div class="card-header"><h2>Tariff vs Action</h2></div><div class="chart-container"><canvas id="tariffChart"></canvas></div></div>
        </div>
        <div class="card"><div class="card-header"><h2>24-Hour Schedule</h2><button class="btn btn-ghost btn-sm" onclick="exportCSV()">Export CSV</button></div>
            <div class="table-wrapper scrollable"><table class="data-table schedule-table"><thead><tr><th>Hr</th><th>Grid</th><th>Solar</th><th>Action</th><th>Batt kWh</th><th>SOC</th><th>Cost</th></tr></thead><tbody>${renderScheduleHTML(data.hourly_plan, cap)}</tbody></table></div></div>
        <div class="card"><div class="card-header"><h2>Raw JSON</h2><div class="card-actions"><button class="btn btn-ghost btn-sm" onclick="copyJSON()">Copy</button><button class="btn btn-ghost btn-sm" onclick="toggleJSON()">Show</button></div></div><pre class="json-viewer" id="jsonViewer" style="display:none;">${JSON.stringify(data,null,2)}</pre></div>
        <div class="card"><div class="card-header"><h2>Plan Summary</h2></div><p class="plan-summary">${data.plan_summary}</p></div>`;
    renderCharts(data.hourly_plan, cap);
    setTimeout(()=>sec.scrollIntoView({behavior:'smooth',block:'start'}),100);
}

function renderDirectivesHTML(directives) {
    const names={solar_reduction:'Solar Reduction',minimum_battery_reserve:'Min Reserve',no_charge_window:'No Charge',no_discharge_window:'No Discharge',max_grid_window:'Max Grid',no_op:'No Operation'};
    const badges={solar_reduction:'badge-solar',minimum_battery_reserve:'badge-reserve',no_charge_window:'badge-nocharge',no_discharge_window:'badge-nodischarge',max_grid_window:'badge-maxgrid',no_op:'badge-noop'};
    return directives.map(d=>{
        const adj=d.structured_adjustment; let detail='';
        if(d.directive_type==='solar_reduction'&&adj)detail=`Factor: ${adj.factor}`;
        else if(d.directive_type==='minimum_battery_reserve'&&adj)detail=`Reserve: ${adj.minimum_energy_kwh} kWh`;
        else if(d.directive_type.includes('window')&&adj)detail=`Hours: ${adj.hours?.[0]}:00 → ${adj.hours?.[adj.hours.length-1]}:00`;
        else if(d.directive_type==='max_grid_window'&&adj)detail=`Max: ${adj.max_grid_kwh} kWh`;
        else if(d.directive_type==='no_op')detail='No optimisation needed';
        return `<div class="directive-item ${d.directive_type==='no_op'?'noop':''}"><span class="directive-badge ${badges[d.directive_type]||''}">${names[d.directive_type]||d.directive_type}</span><div><div class="directive-text">${d.explanation||''}</div><div class="directive-detail">${detail}</div></div></div>`;
    }).join('');
}

function renderScheduleHTML(schedule, cap) {
    return schedule.map(h=>{
        const socPct=(h.battery_energy_after_kwh/cap)*100;
        const barW=Math.max(2,socPct*0.6);
        const cls=h.battery_action==='charge'?'action-charge':h.battery_action==='discharge'?'action-discharge':'action-idle';
        return `<tr><td>${String(h.hour).padStart(2,'0')}:00</td><td>${h.grid_kwh.toFixed(1)}</td><td>${h.solar_used_kwh.toFixed(1)}</td><td><span class="action-badge ${cls}">${h.battery_action.toUpperCase()}</span></td><td>${h.battery_kwh.toFixed(1)}</td><td><span class="soc-bar" style="width:${barW}px"></span>${socPct.toFixed(0)}%</td><td>${(h.grid_kwh*(currentResponse?.hourly_plan?3.2:3.2)).toFixed(2)}</td></tr>`;
    }).join('');
}

/* ── Render Baseline ──────────────────────────────────── */
function renderBaseline(data) {
    const sec = document.getElementById('resultsSection'); sec.style.display='block';
    sec.innerHTML = `
        <div class="summary-grid">
            <div class="summary-card"><div class="summary-icon blue"><div class="summary-data"><span class="summary-value">${data.baseline_cost_bdt.toLocaleString('en-US',{minimumFractionDigits:2})}</span><span class="summary-label">Baseline Cost (BDT)</span></div></div></div>
            <div class="summary-card"><div class="summary-icon green"><div class="summary-data"><span class="summary-value">${data.optimised_cost_bdt.toLocaleString('en-US',{minimumFractionDigits:2})}</span><span class="summary-label">Optimised Cost (BDT)</span></div></div></div>
            <div class="summary-card"><div class="summary-icon orange"><div class="summary-data"><span class="summary-value">${data.savings_bdt.toLocaleString('en-US',{minimumFractionDigits:2})}</span><span class="summary-label">Savings (BDT)</span></div></div></div>
            <div class="summary-card"><div class="summary-icon purple"><div class="summary-data"><span class="summary-value">${data.savings_pct.toFixed(1)}%</span><span class="summary-label">Savings (%)</span></div></div></div>
        </div>
        <div class="charts-grid">
            <div class="card"><div class="card-header"><h2>Baseline vs Optimised Cost</h2></div><div class="chart-container"><canvas id="baselineChart"></canvas></div></div>
            <div class="card"><div class="card-header"><h2>Grid Usage Comparison</h2></div><div class="chart-container"><canvas id="baselineGridChart"></canvas></div></div>
        </div>`;
    const isDark = document.documentElement.getAttribute('data-theme')!=='light';
    const textColor = isDark?'#94a3b8':'#475569';
    const gridColor = isDark?'rgba(148,163,184,0.1)':'rgba(15,23,42,0.06)';
    if(charts.baseline)charts.baseline.destroy();
    charts.baseline = new Chart(document.getElementById('baselineChart'),{
        type:'bar',
        data:{labels:['Baseline','Optimised'],datasets:[{label:'Cost (BDT)',data:[data.baseline_cost_bdt,data.optimised_cost_bdt],backgroundColor:['rgba(248,113,113,0.6)','rgba(52,211,153,0.6)'],borderRadius:6}]},
        options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{color:textColor}},y:{ticks:{color:textColor},grid:{color:gridColor},beginAtZero:true}}}
    });
    if(charts.baselineGrid)charts.baselineGrid.destroy();
    charts.baselineGrid = new Chart(document.getElementById('baselineGridChart'),{
        type:'bar',
        data:{labels:['Baseline','Optimised'],datasets:[{label:'Grid (kWh)',data:[data.baseline_grid_kwh,data.optimised_grid_kwh],backgroundColor:['rgba(96,165,250,0.6)','rgba(34,211,238,0.6)'],borderRadius:6}]},
        options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{color:textColor}},y:{ticks:{color:textColor},grid:{color:gridColor},beginAtZero:true}}}
    });
    setTimeout(()=>sec.scrollIntoView({behavior:'smooth',block:'start'}),100);
}

/* ── Render Compare ───────────────────────────────────── */
function renderCompareResults(data) {
    const sec = document.getElementById('compareResults'); sec.style.display='block';
    const rows = data.scenarios.map(s=>`<tr class="${s.scenario_id===data.best_scenario_id?'best-row':''}"><td><span class="demo-badge">${s.scenario_id}</span></td><td>${s.total_cost_bdt.toLocaleString('en-US',{minimumFractionDigits:2})}</td><td>${s.total_grid_kwh.toFixed(1)}</td><td>${s.peak_grid_kwh.toFixed(1)}</td><td>${s.savings_bdt.toFixed(2)}</td><td>${s.savings_pct.toFixed(1)}%</td><td>${s.directive_count}</td></tr>`).join('');
    sec.innerHTML = `<section class="card"><div class="card-header"><h2>Comparison Results</h2><span class="hint">Best: ${data.best_scenario_id} — saves BDT ${data.cost_difference_bdt}</span></div><div class="table-wrapper"><table class="data-table"><thead><tr><th>Scenario</th><th>Cost (BDT)</th><th>Grid (kWh)</th><th>Peak (kWh)</th><th>Savings (BDT)</th><th>Savings %</th><th>Directives</th></tr></thead><tbody>${rows}</tbody></table></div></section>
    <div class="charts-grid"><div class="card"><div class="card-header"><h2>Cost Comparison</h2></div><div class="chart-container"><canvas id="compareChart"></canvas></div></div></div>`;
    const isDark=document.documentElement.getAttribute('data-theme')!=='light';
    const textColor=isDark?'#94a3b8':'#475569';
    const gridColor=isDark?'rgba(148,163,184,0.1)':'rgba(15,23,42,0.06)';
    if(charts.compare)charts.compare.destroy();
    charts.compare=new Chart(document.getElementById('compareChart'),{type:'bar',data:{labels:data.scenarios.map(s=>s.scenario_id),datasets:[{label:'Cost (BDT)',data:data.scenarios.map(s=>s.total_cost_bdt),backgroundColor:data.scenarios.map(s=>s.scenario_id===data.best_scenario_id?'rgba(52,211,153,0.7)':'rgba(96,165,250,0.5)'),borderRadius:6}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{color:textColor}},y:{ticks:{color:textColor},grid:{color:gridColor},beginAtZero:true}}}});
    setTimeout(()=>sec.scrollIntoView({behavior:'smooth',block:'start'}),100);
}

/* ── Render What-If ───────────────────────────────────── */
function renderWhatIf(data) {
    const sec = document.getElementById('whatIfResults'); sec.style.display='block';
    const paramNames={capacity_kwh:'Battery Capacity',initial_energy_kwh:'Initial Energy',minimum_energy_kwh:'Min Reserve',max_charge_kwh_per_hour:'Max Charge Rate',max_discharge_kwh_per_hour:'Max Discharge Rate'};
    const rows=data.points.map(p=>`<tr><td>${p.value}</td><td>${p.total_cost_bdt.toLocaleString('en-US',{minimumFractionDigits:2})}</td><td>${p.total_grid_kwh.toFixed(1)}</td><td>${p.peak_grid_kwh.toFixed(1)}</td></tr>`).join('');
    sec.innerHTML = `<section class="card"><div class="card-header"><h2>What-If: ${paramNames[data.param]||data.param}</h2></div><div class="table-wrapper"><table class="data-table"><thead><tr><th>Value</th><th>Cost (BDT)</th><th>Grid (kWh)</th><th>Peak (kWh)</th></tr></thead><tbody>${rows}</tbody></table></div></section>
    <div class="charts-grid"><div class="card"><div class="card-header"><h2>Cost vs ${paramNames[data.param]||data.param}</h2></div><div class="chart-container"><canvas id="whatIfChart"></canvas></div></div></div>`;
    const isDark=document.documentElement.getAttribute('data-theme')!=='light';
    const textColor=isDark?'#94a3b8':'#475569';
    const gridColor=isDark?'rgba(148,163,184,0.1)':'rgba(15,23,42,0.06)';
    if(charts.whatIf)charts.whatIf.destroy();
    charts.whatIf=new Chart(document.getElementById('whatIfChart'),{type:'line',data:{labels:data.points.map(p=>p.value),datasets:[{label:'Cost (BDT)',data:data.points.map(p=>p.total_cost_bdt),borderColor:'#60a5fa',backgroundColor:'rgba(96,165,250,0.1)',fill:true,tension:0.3,pointRadius:4}]},options:{responsive:true,maintainAspectRatio:false,scales:{x:{title:{display:true,text:paramNames[data.param]||data.param,color:textColor},ticks:{color:textColor}},y:{ticks:{color:textColor},grid:{color:gridColor},beginAtZero:true}}}});
    setTimeout(()=>sec.scrollIntoView({behavior:'smooth',block:'start'}),100);
}

/* ── Render Carbon ────────────────────────────────────── */
function renderCarbonResults(data) {
    const sec = document.getElementById('carbonResults'); sec.style.display='block';
    sec.innerHTML = `<div class="summary-grid">
        <div class="summary-card"><div class="summary-icon blue"><div class="summary-data"><span class="summary-value">${data.total_cost_bdt.toLocaleString('en-US',{minimumFractionDigits:2})}</span><span class="summary-label">Total Cost (BDT)</span></div></div></div>
        <div class="summary-card"><div class="summary-icon green"><div class="summary-data"><span class="summary-value">${data.total_carbon_kg}</span><span class="summary-label">Total Carbon (kg CO₂)</span></div></div></div>
        <div class="summary-card"><div class="summary-icon orange"><div class="summary-data"><span class="summary-value">${data.total_grid_kwh.toFixed(1)}</span><span class="summary-label">Grid Total (kWh)</span></div></div></div>
        <div class="summary-card"><div class="summary-icon purple"><div class="summary-data"><span class="summary-value">${data.weighted_objective}</span><span class="summary-label">Weighted Objective</span></div></div></div>
    </div>`;
    setTimeout(()=>sec.scrollIntoView({behavior:'smooth',block:'start'}),100);
}

/* ── Charts ───────────────────────────────────────────── */
function renderCharts(schedule, cap) {
    Object.values(charts).forEach(c=>{if(c&&c.destroy)c.destroy()}); charts={};
    const labels=schedule.map(h=>`${String(h.hour).padStart(2,'0')}:00`);
    const grid=schedule.map(h=>h.grid_kwh); const solarU=schedule.map(h=>h.solar_used_kwh);
    const soc=schedule.map(h=>(h.battery_energy_after_kwh/cap)*100);
    const actions=schedule.map(h=>h.battery_action==='charge'?1:h.battery_action==='discharge'?-1:0);
    const minResPct=(parseFloat(document.getElementById('batteryMin').value||40)/cap)*100;
    const isDark=document.documentElement.getAttribute('data-theme')!=='light';
    const textColor=isDark?'#94a3b8':'#475569'; const gridColor=isDark?'rgba(148,163,184,0.1)':'rgba(15,23,42,0.06)';
    const baseOpts=()=>({responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:textColor,font:{family:'Inter',size:11}},position:'top'}},scales:{x:{ticks:{color:textColor,font:{size:10},maxRotation:0,autoSkip:true,maxTicksLimit:12},grid:{color:gridColor}},y:{ticks:{color:textColor,font:{size:10}},grid:{color:gridColor},beginAtZero:true}}});
    charts.gridSolar=new Chart(document.getElementById('gridSolarChart'),{type:'bar',data:{labels,datasets:[{label:'Grid',data:grid,backgroundColor:'rgba(96,165,250,0.6)',borderRadius:3},{label:'Solar Used',data:solarU,backgroundColor:'rgba(251,191,36,0.6)',borderRadius:3},{label:'Demand',data:schedule.map(h=>h.grid_kwh+h.solar_used_kwh),type:'line',borderColor:'#f87171',backgroundColor:'transparent',borderWidth:2,pointRadius:0,tension:0.3}]},options:baseOpts()});
    charts.battery=new Chart(document.getElementById('batteryChart'),{type:'line',data:{labels,datasets:[{label:'SOC%',data:soc,borderColor:'#60a5fa',backgroundColor:'rgba(96,165,250,0.08)',fill:true,borderWidth:2,pointRadius:0,tension:0.3,yAxisID:'y'},{label:'Floor',data:Array(24).fill(minResPct),borderColor:'rgba(248,113,113,0.5)',borderDash:[6,4],borderWidth:1,pointRadius:0,fill:false,yAxisID:'y'}]},options:{...baseOpts(),scales:{...baseOpts().scales,y:{...baseOpts().scales.y,max:105,ticks:{...baseOpts().scales.y.ticks,callback:v=>v+'%'}}}}});
    charts.cost=new Chart(document.getElementById('costChart'),{type:'bar',data:{labels,datasets:[{label:'Cost (BDT)',data:grid.map((g,i)=>g*3.2),backgroundColor:grid.map((g,i)=>g*3.2>(grid.reduce((a,b)=>a+b,0)*3.2/24*1.2)?'rgba(248,113,113,0.6)':'rgba(52,211,153,0.6)'),borderRadius:3}]},options:baseOpts()});
    charts.tariff=new Chart(document.getElementById('tariffChart'),{type:'line',data:{labels,datasets:[{label:'SOC%',data:soc,borderColor:'#a78bfa',backgroundColor:'transparent',borderWidth:2,pointRadius:0,tension:0.3,yAxisID:'y'},{label:'Action',data:actions,type:'bar',backgroundColor:actions.map(a=>a>0?'rgba(52,211,153,0.5)':a<0?'rgba(251,146,60,0.5)':'rgba(148,163,184,0.15)'),borderRadius:3,yAxisID:'y1'}]},options:{...baseOpts(),scales:{...baseOpts().scales,y:{...baseOpts().scales.y,position:'left'},y1:{...baseOpts().scales.y,position:'right',grid:{drawOnChartArea:false},ticks:{color:textColor,font:{size:10},callback:v=>v>0?'CHG':v<0?'DCH':''}}}}});
}

/* ── Theme ────────────────────────────────────────────── */
function toggleTheme() {
    const html=document.documentElement; const current=html.getAttribute('data-theme');
    const next=current==='dark'?'light':'dark'; html.setAttribute('data-theme',next);
    localStorage.setItem('gridwise-theme',next); toast(`${next} mode`,'info');
    if(currentResponse)renderCharts(currentResponse.hourly_plan,parseFloat(document.getElementById('batteryCapacity').value||220));
}

/* ── Export ───────────────────────────────────────────── */
function exportJSON(){if(!currentResponse){toast('No results','error');return;}const b=new Blob([JSON.stringify(currentResponse,null,2)],{type:'application/json'});const u=URL.createObjectURL(b);const a=document.createElement('a');a.href=u;a.download=`gridwise-${currentResponse.scenario_id||'result'}.json`;document.body.appendChild(a);a.click();document.body.removeChild(a);URL.revokeObjectURL(u);toast('Exported JSON','success');}
function exportCSV(){if(!currentResponse){toast('No schedule','error');return;}const cap=parseFloat(document.getElementById('batteryCapacity').value)||220;const header='Hour,Grid_kWh,SolarUsed_kWh,Action,Batt_kWh,SOC%,Cost_BDT\n';const rows=currentResponse.hourly_plan.map(h=>{const soc=(h.battery_energy_after_kwh/cap)*100;return [h.hour,h.grid_kwh.toFixed(1),h.solar_used_kwh.toFixed(1),h.battery_action,h.battery_kwh.toFixed(1),soc.toFixed(0),(h.grid_kwh*3.2).toFixed(2)].join(',')}).join('\n');const b=new Blob([header+rows],{type:'text/csv'});const u=URL.createObjectURL(b);const a=document.createElement('a');a.href=u;a.download=`gridwise-schedule.csv`;document.body.appendChild(a);a.click();document.body.removeChild(a);URL.revokeObjectURL(u);toast('Exported CSV','success');}
function copyJSON(){if(!currentResponse)return;navigator.clipboard.writeText(JSON.stringify(currentResponse,null,2)).then(()=>toast('Copied','success'));}
function copyDirectives(){if(!currentResponse)return;const text=currentResponse.directive_interpretation.map(d=>`${d.directive_type}: ${d.explanation||''}`).join('\n');navigator.clipboard.writeText(text).then(()=>toast('Copied','success'));}
function toggleJSON(){const v=document.getElementById('jsonViewer');v.style.display=v.style.display==='none'?'block':'none';}

/* ── URL State ────────────────────────────────────────── */
function updateURLState() {
    const params = new URLSearchParams();
    params.set('tab', document.querySelector('.nav-tab.active')?.textContent?.toLowerCase().replace(' ','')||'optimise');
    params.set('id', document.getElementById('scenarioId')?.value||'');
    const notes = getNotes(); if(notes.length) params.set('notes', notes.join('|||'));
    history.replaceState(null,'',`?${params.toString()}`);
}
function restoreURLState() {
    const params = new URLSearchParams(window.location.search);
    const tab = params.get('tab'); if(tab) switchTab(tab);
    const id = params.get('id'); if(id) document.getElementById('scenarioId').value=id;
    const notes = params.get('notes'); if(notes) {
        const c=document.getElementById('notesContainer'); c.innerHTML='';
        notes.split('|||').forEach((n,i)=>{const row=document.createElement('div');row.className='note-row';row.innerHTML=`<span class="note-index">${i}</span><input type="text" class="input" value="${n}" data-note="${i}"><button class="btn btn-icon btn-danger" onclick="removeNote(this)"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>`;c.appendChild(row);});
    }
}

/* ── Keyboard Shortcuts ───────────────────────────────── */
function handleKeys(e){if(e.key==='Escape'){closeShortcuts();hideLoading();}if(e.key==='?'&&!e.target.closest('input,textarea,select')){e.preventDefault();showShortcuts();}if(e.key==='t'&&!e.target.closest('input,textarea,select')){e.preventDefault();toggleTheme();}if(e.key==='e'&&!e.target.closest('input,textarea,select')){e.preventDefault();exportJSON();}if(e.key==='r'&&!e.target.closest('input,textarea,select')){e.preventDefault();randomScenario();}if(e.ctrlKey&&e.key==='Enter'){e.preventDefault();runOptimization();}const tabs=['optimise','compare','whatif','carbon','history','demo'];if(['1','2','3','4','5','6'].includes(e.key)&&!e.target.closest('input,textarea,select')){switchTab(tabs[parseInt(e.key)-1]);}}
function showShortcuts(){document.getElementById('shortcutsModal').style.display='flex';}
function closeShortcuts(){document.getElementById('shortcutsModal').style.display='none';}

/* ── Loading ──────────────────────────────────────────── */
function showLoading(text){document.getElementById('loadingText').textContent=text||'Processing...';document.getElementById('loadingOverlay').style.display='flex';const msgs=['Interpreting operator notes with LLM...','Validating directive structures...','Running guardrails checks...','Solving MILP optimisation...','Building 24-hour schedule...'];let i=0;loadingAnim=setInterval(()=>{document.getElementById('loadingText').textContent=msgs[i%msgs.length];i++;},1200);}
function hideLoading(){document.getElementById('loadingOverlay').style.display='none';if(loadingAnim){clearInterval(loadingAnim);loadingAnim=null;}}

/* ── Toast ────────────────────────────────────────────── */
function toast(msg,type='info'){const c=document.getElementById('toastContainer');const el=document.createElement('div');el.className=`toast toast-${type}`;const icons={success:'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',error:'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',info:'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'};el.innerHTML=`${icons[type]||icons.info}<span>${msg}</span>`;c.appendChild(el);setTimeout(()=>{el.style.animation='toastOut 0.3s ease-in forwards';setTimeout(()=>el.remove(),300);},4000);}
