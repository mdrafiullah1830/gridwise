/* ── State ─────────────────────────────────────────────── */
let currentResponse = null;
let charts = {};
let loadingAnim = null;

/* ── Init ─────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', async () => {
    initHourlyTable();
    loadSamples();
    checkHealth();
    setInterval(checkHealth, 30000);
    document.addEventListener('keydown', handleKeys);
    document.addEventListener('keydown', handleNoteCount);
    document.getElementById('sampleSelect').addEventListener('change', loadSample);
    const saved = localStorage.getItem('gridwise-theme');
    if (saved) document.documentElement.setAttribute('data-theme', saved);
});

/* ── Health Check ─────────────────────────────────────── */
async function checkHealth() {
    const badge = document.getElementById('statusBadge');
    try {
        const r = await fetch('/health');
        const d = await r.json();
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
        [0.01, 0, 3.20], [0.01, 0, 3.20], [0.01, 0, 3.20], [0.01, 0, 3.20],
        [0.02, 0, 3.20], [0.02, 0, 3.20], [0.02, 2, 3.20], [0.03, 10, 3.20],
        [0.04, 30, 3.20], [0.04, 65, 3.20], [0.05, 130, 3.20], [0.05, 182, 3.20],
        [0.05, 210, 3.20], [0.05, 194, 3.20], [0.05, 130, 3.20], [0.04, 65, 3.20],
        [0.04, 30, 3.20], [0.03, 10, 3.20], [0.02, 2, 3.20], [0.02, 0, 3.20],
        [0.01, 0, 3.20], [0.01, 0, 3.20], [0.01, 0, 3.20], [0.01, 0, 3.20]
    ];
    let html = '';
    for (let h = 0; h < 24; h++) {
        const [d, s, t] = defaults[h];
        html += `<tr>
            <td>${String(h).padStart(2, '0')}:00</td>
            <td><input type="number" value="${d}" step="0.01" min="0" data-hr="${h}" data-field="demand"></td>
            <td><input type="number" value="${s}" step="0.1" min="0" data-hr="${h}" data-field="solar"></td>
            <td><input type="number" value="${t}" step="0.01" min="0" data-hr="${h}" data-field="tariff"></td>
        </tr>`;
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
        const dEl = document.querySelector(`[data-hr="${h}"][data-field="demand"]`);
        const sEl = document.querySelector(`[data-hr="${h}"][data-field="solar"]`);
        const tEl = document.querySelector(`[data-hr="${h}"][data-field="tariff"]`);
        if (dEl) dEl.value = demand[h] ?? 0;
        if (sEl) sEl.value = solar[h] ?? 0;
        if (tEl) tEl.value = tariff[h] ?? 0;
    }
}

function randomiseHourlyData() {
    const demand = Array.from({ length: 24 }, () => +(Math.random() * 50 + 200).toFixed(3));
    const solar = Array.from({ length: 24 }, (_, i) => i < 6 || i > 19 ? 0 : +((i - 5) * 35).toFixed(1));
    const tariff = Array.from({ length: 24 }, () => +(Math.random() * 3 + 2).toFixed(2));
    setHourlyData(demand, solar, tariff);
    toast('Randomised hourly data', 'info');
}

function clearHourlyData() { setHourlyData(Array(24).fill(0), Array(24).fill(0), Array(24).fill(0)); }

/* ── Notes ────────────────────────────────────────────── */
function getNotes() {
    const inputs = document.querySelectorAll('#notesContainer input[data-note]');
    return Array.from(inputs).map(i => i.value.trim()).filter(Boolean);
}

function addNote() {
    const inputs = document.querySelectorAll('#notesContainer input[data-note]');
    if (inputs.length >= 3) { toast('Maximum 3 notes allowed', 'error'); return; }
    const container = document.getElementById('notesContainer');
    const idx = inputs.length;
    const row = document.createElement('div');
    row.className = 'note-row';
    row.innerHTML = `
        <span class="note-index">${idx}</span>
        <input type="text" class="input" placeholder="e.g. Keep battery above 30% from midnight..." data-note="${idx}">
        <button class="btn btn-icon btn-danger" onclick="removeNote(this)" title="Remove">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>`;
    container.appendChild(row);
    row.querySelector('input').focus();
}

function removeNote(btn) {
    const rows = document.querySelectorAll('#notesContainer .note-row');
    if (rows.length <= 1) { toast('At least 1 note required', 'error'); return; }
    btn.closest('.note-row').remove();
    reindexNotes();
}

function reindexNotes() {
    document.querySelectorAll('#notesContainer .note-row').forEach((row, i) => {
        row.querySelector('.note-index').textContent = i;
        row.querySelector('input').dataset.note = i;
    });
}

function handleNoteCount(e) {
    if (e.key === 'Tab' && e.target.closest('#notesContainer')) {
        const inputs = document.querySelectorAll('#notesContainer input[data-note]');
        if (e.target === inputs[inputs.length - 1] && !e.shiftKey) {
            const count = document.querySelectorAll('#notesContainer .note-row').length;
            if (count < 3) { addNote(); }
        }
    }
}

/* ── Samples ──────────────────────────────────────────── */
async function loadSamples() {
    try {
        const r = await fetch('/scenarios');
        const data = await r.json();
        const sel = document.getElementById('sampleSelect');
        sel.innerHTML = '<option value="">Select a sample case...</option>';
        data.samples.forEach(s => {
            const opt = document.createElement('option');
            opt.value = JSON.stringify(s);
            opt.textContent = `${s.id} — ${s.notes[0]?.substring(0, 50)}...`;
            sel.appendChild(opt);
        });
    } catch {
        toast('Failed to load samples', 'error');
    }
}

function loadSample() {
    const sel = document.getElementById('sampleSelect');
    if (!sel.value) return;
    try {
        const s = JSON.parse(sel.value);
        document.getElementById('scenarioId').value = s.id;
        document.getElementById('batteryCapacity').value = s.battery.capacity_kwh;
        document.getElementById('batteryInitial').value = s.battery.initial_energy_kwh;
        document.getElementById('batteryMin').value = s.battery.minimum_energy_kwh;
        document.getElementById('batteryChargeRate').value = s.battery.max_charge_kwh_per_hour;
        document.getElementById('batteryDischargeRate').value = s.battery.max_discharge_kwh_per_hour;

        const demand = s.hours.map(h => h.demand_kwh);
        const solar = s.hours.map(h => h.solar_kwh);
        const tariff = s.hours.map(h => h.tariff_bdt_per_kwh);
        setHourlyData(demand, solar, tariff);

        const container = document.getElementById('notesContainer');
        container.innerHTML = '';
        s.notes.forEach((note, i) => {
            const row = document.createElement('div');
            row.className = 'note-row';
            row.innerHTML = `
                <span class="note-index">${i}</span>
                <input type="text" class="input" value="${note}" data-note="${i}">
                <button class="btn btn-icon btn-danger" onclick="removeNote(this)" title="Remove">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>`;
            container.appendChild(row);
        });
        toast(`Loaded ${s.id}`, 'success');
    } catch (e) { console.error(e); toast('Invalid sample data', 'error'); }
}

function randomScenario() {
    const notes = [
        "Solar panels will be washed from noon until 2 PM",
        "Battery should stay above 30% overnight for emergencies",
        "Please avoid charging during peak hours 17:00 to 21:00",
        "The battery must be fully charged before midnight",
        "Grid import should not exceed 60 kWh at any hour",
        "Keep battery reserve at least 40 kWh from 01:00 to 06:00",
        "Battery should be fully charged by 11:00",
        "Schedule battery to power the load from 21:00 to 05:00"
    ];
    const rand = [];
    const count = Math.floor(Math.random() * 3) + 1;
    const used = new Set();
    while (rand.length < count) {
        const idx = Math.floor(Math.random() * notes.length);
        if (!used.has(idx)) { used.add(idx); rand.push(notes[idx]); }
    }
    const container = document.getElementById('notesContainer');
    container.innerHTML = '';
    rand.forEach((note, i) => {
        const row = document.createElement('div');
        row.className = 'note-row';
        row.innerHTML = `
            <span class="note-index">${i}</span>
            <input type="text" class="input" value="${note}" data-note="${i}">
            <button class="btn btn-icon btn-danger" onclick="removeNote(this)" title="Remove">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>`;
        container.appendChild(row);
    });
    toast('Loaded random scenario', 'info');
}

/* ── Optimization ─────────────────────────────────────── */
async function runOptimization() {
    const btn = document.getElementById('optimizeBtn');
    const btnText = document.getElementById('optimizeBtnText');
    const notes = getNotes();
    if (!notes.length) { toast('Add at least 1 operator note', 'error'); return; }

    const hourly = getHourlyData();
    const cap = parseFloat(document.getElementById('batteryCapacity').value) || 220;
    const initE = parseFloat(document.getElementById('batteryInitial').value) || 110;
    const minE = parseFloat(document.getElementById('batteryMin').value) || 40;
    const chRate = parseFloat(document.getElementById('batteryChargeRate').value) || 50;
    const dchRate = parseFloat(document.getElementById('batteryDischargeRate').value) || 50;

    const hours = [];
    for (let h = 0; h < 24; h++) {
        hours.push({
            hour: h,
            demand_kwh: hourly.demand[h],
            solar_kwh: hourly.solar[h],
            tariff_bdt_per_kwh: hourly.tariff[h]
        });
    }

    const payload = {
        scenario_id: document.getElementById('scenarioId').value || `SCENARIO-${Date.now()}`,
        operator_notes: notes,
        hours: hours,
        battery: {
            capacity_kwh: cap,
            initial_energy_kwh: initE,
            minimum_energy_kwh: minE,
            max_charge_kwh_per_hour: chRate,
            max_discharge_kwh_per_hour: dchRate
        }
    };

    btn.disabled = true;
    btnText.textContent = 'Processing...';
    showLoading('Interpreting operator notes with LLM...');

    try {
        const res = await fetch('/optimize-energy', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        hideLoading();

        if (!res.ok) {
            toast(data.detail || data.error || 'Optimisation failed', 'error');
            return;
        }

        currentResponse = data;
        renderResults(data, cap, initE);
        toast(`Optimised — Total cost: BDT ${data.total_cost_bdt}`, 'success');
    } catch (err) {
        hideLoading();
        toast(`Request failed: ${err.message}`, 'error');
    } finally {
        btn.disabled = false;
        btnText.textContent = 'Optimise Schedule';
    }
}

/* ── Render Results ───────────────────────────────────── */
function renderResults(data, cap, initE) {
    document.getElementById('resultsSection').style.display = 'block';
    document.getElementById('totalCost').textContent = data.total_cost_bdt.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    document.getElementById('totalGrid').textContent = data.total_grid_kwh.toFixed(1);
    document.getElementById('peakGrid').textContent = data.peak_grid_kwh.toFixed(1);
    document.getElementById('elapsedTime').textContent = '—';
    document.getElementById('planSummary').textContent = data.plan_summary || '';

    renderDirectives(data.directive_interpretation);
    renderSchedule(data.hourly_plan, cap);
    renderJSON(data);
    renderCharts(data.hourly_plan, data.directive_interpretation, cap, initE);

    setTimeout(() => {
        document.getElementById('resultsSection').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
}

function renderDirectives(directives) {
    const container = document.getElementById('directiveList');
    const typeNames = {
        solar_reduction: 'Solar Reduction', minimum_battery_reserve: 'Min Battery Reserve',
        no_charge_window: 'No Charge Window', no_discharge_window: 'No Discharge Window',
        max_grid_window: 'Max Grid Window', no_op: 'No Operation'
    };
    const typeBadge = {
        solar_reduction: 'badge-solar', minimum_battery_reserve: 'badge-reserve',
        no_charge_window: 'badge-nocharge', no_discharge_window: 'badge-nodischarge',
        max_grid_window: 'badge-maxgrid', no_op: 'badge-noop'
    };

    container.innerHTML = directives.map(d => {
        const type = d.directive_type;
        const adj = d.structured_adjustment;
        let detail = '';
        if (type === 'solar_reduction' && adj) detail = `Factor: ${adj.factor ?? 'N/A'}`;
        else if (type === 'minimum_battery_reserve' && adj) detail = `Reserve: ${adj.minimum_energy_kwh ?? 'N/A'} kWh`;
        else if (type.includes('window') && adj) detail = `Hours: ${(adj.hours?.[0] ?? '?')}:00 → ${(adj.hours?.[adj.hours.length - 1] ?? '?')}:00`;
        else if (type === 'max_grid_window' && adj) detail = `Hours: ${adj.hours?.[0] ?? '?'}:00 → ${adj.hours?.[adj.hours.length - 1] ?? '?'}:00 · Max: ${adj.max_grid_kwh ?? 'N/A'} kWh`;
        else if (type === 'no_op') detail = 'All parameters at default — no optimisation needed';
        return `
            <div class="directive-item ${type === 'no_op' ? 'noop' : ''}">
                <span class="directive-badge ${typeBadge[type] || 'badge-solar'}">${typeNames[type] || type}</span>
                <div>
                    <div class="directive-text">${d.explanation || JSON.stringify(d)}</div>
                    <div class="directive-detail">${detail}</div>
                </div>
            </div>`;
    }).join('');
}

function renderSchedule(schedule, cap) {
    const tbody = document.getElementById('scheduleBody');
    tbody.innerHTML = schedule.map(h => {
        const socPct = (h.battery_energy_after_kwh / cap) * 100;
        const barW = Math.max(2, socPct * 0.6);
        const actionClass = h.battery_action === 'charge' ? 'action-charge' : h.battery_action === 'discharge' ? 'action-discharge' : 'action-idle';
        return `<tr>
            <td>${String(h.hour).padStart(2, '0')}:00</td>
            <td>${h.grid_kwh.toFixed(1)}</td>
            <td>${h.solar_used_kwh.toFixed(1)}</td>
            <td><span class="action-badge ${actionClass}">${h.battery_action.toUpperCase()}</span></td>
            <td>${h.battery_kwh.toFixed(1)}</td>
            <td><span class="soc-bar" style="width:${barW}px"></span>${socPct.toFixed(0)}%</td>
            <td>${h.grid_kwh.toFixed(1)}</td>
            <td>${'—'}</td>
            <td>${(h.grid_kwh * 3.2).toFixed(2)}</td>
        </tr>`;
    }).join('');
}

function renderJSON(data) {
    const viewer = document.getElementById('jsonViewer');
    viewer.textContent = JSON.stringify(data, null, 2);
}

/* ── Charts ───────────────────────────────────────────── */
function renderCharts(schedule, directives, cap, initE) {
    Object.values(charts).forEach(c => c.destroy());
    charts = {};
    const labels = schedule.map(h => `${String(h.hour).padStart(2, '0')}:00`);
    const grid = schedule.map(h => h.grid_kwh);
    const solarU = schedule.map(h => h.solar_used_kwh);
    const batt = schedule.map(h => h.battery_kwh);
    const soc = schedule.map(h => (h.battery_energy_after_kwh / cap) * 100);
    const actions = schedule.map(h => h.battery_action === 'charge' ? 1 : h.battery_action === 'discharge' ? -1 : 0);
    const costs = schedule.map((h, i) => {
        const tariff = currentResponse?.hourly_plan ? 3.2 : 3.2;
        return h.grid_kwh * tariff;
    });

    const minReservePct = (parseFloat(document.getElementById('batteryMin').value || 40) / cap) * 100;

    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    const gridColor = isDark ? 'rgba(148,163,184,0.1)' : 'rgba(15,23,42,0.06)';
    const textColor = isDark ? '#94a3b8' : '#475569';

    const baseOpts = () => ({
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: textColor, font: { family: 'Inter', size: 11 } }, position: 'top' } },
        scales: {
            x: { ticks: { color: textColor, font: { size: 10 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 12 }, grid: { color: gridColor } },
            y: { ticks: { color: textColor, font: { size: 10 } }, grid: { color: gridColor }, beginAtZero: true }
        }
    });

    charts.gridSolar = new Chart(document.getElementById('gridSolarChart'), {
        type: 'bar',
        data: {
            labels,
            datasets: [
                { label: 'Grid (kWh)', data: grid, backgroundColor: 'rgba(96,165,250,0.6)', borderRadius: 3 },
                { label: 'Solar Used (kWh)', data: solarU, backgroundColor: 'rgba(251,191,36,0.6)', borderRadius: 3 },
                { label: 'Demand (kWh)', data: schedule.map(h => h.grid_kwh + h.solar_used_kwh), type: 'line', borderColor: '#f87171', backgroundColor: 'transparent', borderWidth: 2, pointRadius: 0, tension: 0.3 }
            ]
        },
        options: baseOpts()
    });

    charts.battery = new Chart(document.getElementById('batteryChart'), {
        type: 'line',
        data: {
            labels,
            datasets: [
                { label: 'SOC (%)', data: soc, borderColor: '#60a5fa', backgroundColor: 'rgba(96,165,250,0.08)', fill: true, borderWidth: 2, pointRadius: 0, tension: 0.3, yAxisID: 'y' },
                { label: 'SOC Floor', data: Array(24).fill(minReservePct), borderColor: 'rgba(248,113,113,0.5)', borderDash: [6, 4], borderWidth: 1, pointRadius: 0, fill: false, yAxisID: 'y' },
                { label: 'Capacity', data: Array(24).fill(100), borderColor: 'rgba(148,163,184,0.25)', borderDash: [4, 4], borderWidth: 1, pointRadius: 0, fill: false, yAxisID: 'y' }
            ]
        },
        options: { ...baseOpts(), scales: { ...baseOpts().scales, y: { ...baseOpts().scales.y, max: 105, ticks: { ...baseOpts().scales.y.ticks, callback: v => v + '%' } } } }
    });

    charts.cost = new Chart(document.getElementById('costChart'), {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'Cost (BDT)', data: costs,
                backgroundColor: costs.map(c => c > (costs.reduce((a, b) => a + b, 0) / 24 * 1.2) ? 'rgba(248,113,113,0.6)' : 'rgba(52,211,153,0.6)'),
                borderRadius: 3
            }]
        },
        options: baseOpts()
    });

    charts.tariff = new Chart(document.getElementById('tariffChart'), {
        type: 'line',
        data: {
            labels,
            datasets: [
                { label: 'SOC (%)', data: soc, borderColor: '#a78bfa', backgroundColor: 'transparent', borderWidth: 2, pointRadius: 0, tension: 0.3, yAxisID: 'y' },
                { label: 'Battery Action', data: actions, type: 'bar', backgroundColor: actions.map(a => a > 0 ? 'rgba(52,211,153,0.5)' : a < 0 ? 'rgba(251,146,60,0.5)' : 'rgba(148,163,184,0.15)'), borderRadius: 3, yAxisID: 'y1' }
            ]
        },
        options: {
            ...baseOpts(),
            scales: {
                ...baseOpts().scales,
                y: { ...baseOpts().scales.y, position: 'left' },
                y1: { ...baseOpts().scales.y, position: 'right', grid: { drawOnChartArea: false }, ticks: { color: textColor, font: { size: 10 }, callback: v => v > 0 ? 'CHG' : v < 0 ? 'DCH' : '' } }
            }
        }
    });
}

/* ── Theme ────────────────────────────────────────────── */
function toggleTheme() {
    const html = document.documentElement;
    const current = html.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('gridwise-theme', next);
    toast(`${next === 'dark' ? 'Dark' : 'Light'} mode`, 'info');
    if (currentResponse) renderCharts(currentResponse.hourly_plan, currentResponse.directive_interpretation, parseFloat(document.getElementById('batteryCapacity').value || 220), parseFloat(document.getElementById('batteryInitial').value || 110));
}

/* ── Export ───────────────────────────────────────────── */
function exportJSON() {
    if (!currentResponse) { toast('No results to export', 'error'); return; }
    const blob = new Blob([JSON.stringify(currentResponse, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = `gridwise-${currentResponse.scenario_id || 'result'}.json`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
    toast('Exported JSON', 'success');
}

function exportCSV() {
    if (!currentResponse) { toast('No schedule to export', 'error'); return; }
    const header = 'Hour,Grid_kWh,SolarUsed_kWh,Action,Batt_kWh,SOC%,Cost_BDT\n';
    const cap = parseFloat(document.getElementById('batteryCapacity').value) || 220;
    const rows = currentResponse.hourly_plan.map(h => {
        const socPct = (h.battery_energy_after_kwh / cap) * 100;
        const tariff = 3.2;
        return [h.hour, h.grid_kwh.toFixed(1), h.solar_used_kwh.toFixed(1), h.battery_action, h.battery_kwh.toFixed(1), socPct.toFixed(0), (h.grid_kwh * tariff).toFixed(2)].join(',');
    }).join('\n');
    const blob = new Blob([header + rows], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = `gridwise-schedule-${currentResponse.scenario_id || 'result'}.csv`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
    toast('Exported CSV', 'success');
}

function copyJSON() {
    if (!currentResponse) return;
    navigator.clipboard.writeText(JSON.stringify(currentResponse, null, 2))
        .then(() => toast('Copied to clipboard', 'success'))
        .catch(() => toast('Copy failed', 'error'));
}

function copyDirectives() {
    if (!currentResponse) return;
    const text = currentResponse.directive_interpretation.map(d => `${d.directive_type}: ${d.explanation || ''}`).join('\n');
    navigator.clipboard.writeText(text)
        .then(() => toast('Directives copied', 'success'))
        .catch(() => toast('Copy failed', 'error'));
}

function toggleJSON() {
    const viewer = document.getElementById('jsonViewer');
    const btn = document.getElementById('jsonToggle');
    if (viewer.style.display === 'none') {
        viewer.style.display = 'block';
        btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg> Hide';
    } else {
        viewer.style.display = 'none';
        btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg> Show';
    }
}

/* ── Keyboard Shortcuts ───────────────────────────────── */
function handleKeys(e) {
    if (e.key === 'Escape') { closeShortcuts(); hideLoading(); }
    if (e.key === '?' && !e.target.closest('input, textarea, select')) { e.preventDefault(); showShortcuts(); }
    if (e.key === 't' && !e.target.closest('input, textarea, select')) { e.preventDefault(); toggleTheme(); }
    if (e.key === 'e' && !e.target.closest('input, textarea, select')) { e.preventDefault(); exportJSON(); }
    if (e.key === 'r' && !e.target.closest('input, textarea, select')) { e.preventDefault(); randomScenario(); }
    if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); runOptimization(); }
    if (['1','2','3','4','5'].includes(e.key) && !e.target.closest('input, textarea, select')) {
        const sel = document.getElementById('sampleSelect');
        const opts = sel.options;
        const idx = parseInt(e.key);
        if (idx < opts.length) { sel.selectedIndex = idx; loadSample(); }
    }
}

function showShortcuts() { document.getElementById('shortcutsModal').style.display = 'flex'; }
function closeShortcuts() { document.getElementById('shortcutsModal').style.display = 'none'; }

/* ── Loading ──────────────────────────────────────────── */
function showLoading(text) {
    document.getElementById('loadingText').textContent = text || 'Processing...';
    document.getElementById('loadingOverlay').style.display = 'flex';
    const messages = [
        'Interpreting operator notes with LLM...',
        'Validating directive structures...',
        'Running guardrails checks...',
        'Solving MILP optimisation...',
        'Building 24-hour schedule...'
    ];
    let i = 0;
    loadingAnim = setInterval(() => {
        document.getElementById('loadingText').textContent = messages[i % messages.length];
        i++;
    }, 1200);
}

function hideLoading() {
    document.getElementById('loadingOverlay').style.display = 'none';
    if (loadingAnim) { clearInterval(loadingAnim); loadingAnim = null; }
}

/* ── Toast ────────────────────────────────────────────── */
function toast(msg, type = 'info') {
    const container = document.getElementById('toastContainer');
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    const icons = {
        success: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
        error: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
        info: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
    };
    el.innerHTML = `${icons[type] || icons.info}<span>${msg}</span>`;
    container.appendChild(el);
    setTimeout(() => { el.style.animation = 'toastOut 0.3s ease-in forwards'; setTimeout(() => el.remove(), 300); }, 4000);
}
