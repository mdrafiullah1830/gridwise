/* ── GridWise Frontend ──────────────────────────────────── */

const API_BASE = '';
let charts = {};
let currentResult = null;

// ── Sample Data ──────────────────────────────────────────
const SAMPLE_CASES = [
    {
        id: "SAMPLE-01",
        label: "Solar cleaning + distractor",
        notes: [
            "Facilities will wash the rooftop solar panels from noon until 2 PM. During cleaning, usable solar should be treated as roughly 25% of the forecast.",
            "The sports office moved next month's registration deadline."
        ],
        demand: [90,85,80,80,85,95,110,130,150,165,175,180,185,180,170,165,170,185,205,215,205,175,135,105],
        solar: [0,0,0,0,0,0,5,20,50,90,130,160,180,170,140,90,45,10,0,0,0,0,0,0],
        tariff: [6,6,5,5,5,6,8,10,12,14,16,16,15,14,13,14,18,22,28,30,26,18,10,7],
        battery: { capacity: 220, initial: 110, min: 40, chargeRate: 50, dischargeRate: 50 }
    },
    {
        id: "SAMPLE-02",
        label: "Battery charging maintenance",
        notes: ["The battery charger will be isolated from 2 AM until 5 AM for electrical maintenance."],
        demand: [100,95,90,90,95,105,120,135,145,155,165,175,180,175,165,160,170,190,210,220,210,180,145,115],
        solar: [0,0,0,0,0,0,0,10,30,55,80,100,110,105,85,60,30,10,0,0,0,0,0,0],
        tariff: [6,5,4,4,4,5,7,9,11,13,15,16,16,15,14,15,19,24,31,33,29,20,11,7],
        battery: { capacity: 200, initial: 70, min: 30, chargeRate: 55, dischargeRate: 55 }
    },
    {
        id: "SAMPLE-03",
        label: "Emergency reserve as percentage",
        notes: ["Keep at least 50% of the battery capacity stored in the battery from 6 PM until 9 PM for emergency operations."],
        demand: [90,85,80,80,85,95,110,130,150,165,175,180,185,180,170,165,170,185,205,215,205,175,135,105],
        solar: [0,0,0,0,0,0,5,20,50,90,130,160,180,170,140,90,45,10,0,0,0,0,0,0],
        tariff: [6,6,5,5,5,6,8,10,12,14,16,16,15,14,13,14,18,22,28,30,26,18,10,7],
        battery: { capacity: 200, initial: 120, min: 40, chargeRate: 50, dischargeRate: 50 }
    },
    {
        id: "SAMPLE-04",
        label: "No-discharge protection test",
        notes: ["For protection testing, the battery must not discharge from 6 PM until 8 PM."],
        demand: [95,90,85,85,90,100,115,130,145,155,165,175,180,175,170,165,175,195,215,225,215,185,150,120],
        solar: [0,0,0,0,0,0,5,15,40,75,110,145,165,155,125,80,35,5,0,0,0,0,0,0],
        tariff: [7,6,6,5,5,6,8,10,12,14,16,16,15,14,13,14,17,21,29,32,30,20,11,8],
        battery: { capacity: 230, initial: 130, min: 40, chargeRate: 55, dischargeRate: 55 }
    },
    {
        id: "SAMPLE-05",
        label: "Temporary feeder grid cap",
        notes: ["From 6 PM until 9 PM, campus grid import must not exceed 155 kWh in any hour because the feeder is operating under a temporary limit."],
        demand: [90,85,80,80,85,95,110,130,150,165,175,180,185,180,170,165,170,185,205,215,205,175,135,105],
        solar: [0,0,0,0,0,0,5,20,50,90,130,160,180,170,140,90,45,10,0,0,0,0,0,0],
        tariff: [6,6,5,5,5,6,8,10,12,14,16,16,15,14,13,14,18,22,28,30,26,18,10,7],
        battery: { capacity: 240, initial: 120, min: 30, chargeRate: 60, dischargeRate: 60 }
    }
];

// ── Init ─────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initHourlyTable();
    populateSampleSelect();
    checkHealth();
});

async function checkHealth() {
    const badge = document.getElementById('statusBadge');
    try {
        const r = await fetch(`${API_BASE}/health`);
        const d = await r.json();
        if (d.status === 'ok') {
            badge.className = 'status-badge ok';
            badge.querySelector('span:last-child').textContent = 'Service Online';
        } else throw new Error();
    } catch {
        badge.className = 'status-badge err';
        badge.querySelector('span:last-child').textContent = 'Offline';
    }
}

// ── Hourly Table ─────────────────────────────────────────
function initHourlyTable() {
    const body = document.getElementById('hourlyBody');
    body.innerHTML = '';
    for (let h = 0; h < 24; h++) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td style="font-weight:600;color:var(--text-secondary)">${String(h).padStart(2, '0')}</td>
            <td><input type="number" id="demand-${h}" value="0" min="0" step="1"></td>
            <td><input type="number" id="solar-${h}" value="0" min="0" step="1"></td>
            <td><input type="number" id="tariff-${h}" value="0" min="0" step="0.1"></td>
        `;
        body.appendChild(tr);
    }
}

function fillHourlyData(demand, solar, tariff) {
    for (let h = 0; h < 24; h++) {
        document.getElementById(`demand-${h}`).value = demand[h];
        document.getElementById(`solar-${h}`).value = solar[h];
        document.getElementById(`tariff-${h}`).value = tariff[h];
    }
}

// ── Notes ────────────────────────────────────────────────
let noteCount = 1;
function addNote() {
    if (noteCount >= 3) return;
    const container = document.getElementById('notesContainer');
    const row = document.createElement('div');
    row.className = 'note-row';
    row.innerHTML = `
        <input type="text" class="input" placeholder="Another operator note..." data-note="${noteCount}">
        <button class="btn btn-icon btn-danger" onclick="removeNote(this)" title="Remove">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
    `;
    container.appendChild(row);
    noteCount++;
}

function removeNote(btn) {
    if (noteCount <= 1) return;
    btn.closest('.note-row').remove();
    noteCount--;
}

function getNotes() {
    return Array.from(document.querySelectorAll('#notesContainer .note-row input'))
        .map(i => i.value.trim())
        .filter(v => v.length > 0);
}

function setNotes(notes) {
    const container = document.getElementById('notesContainer');
    container.innerHTML = '';
    noteCount = 0;
    notes.forEach((note, i) => {
        noteCount++;
        const row = document.createElement('div');
        row.className = 'note-row';
        row.innerHTML = `
            <input type="text" class="input" value="${note}" data-note="${i}">
            <button class="btn btn-icon btn-danger" onclick="removeNote(this)" title="Remove">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
        `;
        container.appendChild(row);
    });
}

// ── Sample Cases ─────────────────────────────────────────
function populateSampleSelect() {
    const sel = document.getElementById('sampleSelect');
    SAMPLE_CASES.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = `${c.id} — ${c.label}`;
        sel.appendChild(opt);
    });
    sel.addEventListener('change', () => {
        const c = SAMPLE_CASES.find(s => s.id === sel.value);
        if (!c) return;
        setNotes(c.notes);
        fillHourlyData(c.demand, c.solar, c.tariff);
        document.getElementById('scenarioId').value = c.id;
        document.getElementById('batteryCapacity').value = c.battery.capacity;
        document.getElementById('batteryInitial').value = c.battery.initial;
        document.getElementById('batteryMin').value = c.battery.min;
        document.getElementById('batteryChargeRate').value = c.battery.chargeRate;
        document.getElementById('batteryDischargeRate').value = c.battery.dischargeRate;
    });
}

function loadSampleCases() {
    document.getElementById('sampleSelect').value = 'SAMPLE-01';
    document.getElementById('sampleSelect').dispatchEvent(new Event('change'));
}

// ── Build Request ────────────────────────────────────────
function buildRequest() {
    const notes = getNotes();
    if (notes.length === 0) { alert('Add at least one operator note.'); return null; }

    const hours = [];
    for (let h = 0; h < 24; h++) {
        hours.push({
            hour: h,
            demand_kwh: parseFloat(document.getElementById(`demand-${h}`).value) || 0,
            solar_kwh: parseFloat(document.getElementById(`solar-${h}`).value) || 0,
            tariff_bdt_per_kwh: parseFloat(document.getElementById(`tariff-${h}`).value) || 0
        });
    }

    return {
        scenario_id: document.getElementById('scenarioId').value || 'SCENARIO-001',
        operator_notes: notes,
        hours,
        battery: {
            capacity_kwh: parseFloat(document.getElementById('batteryCapacity').value) || 220,
            initial_energy_kwh: parseFloat(document.getElementById('batteryInitial').value) || 110,
            minimum_energy_kwh: parseFloat(document.getElementById('batteryMin').value) || 40,
            max_charge_kwh_per_hour: parseFloat(document.getElementById('batteryChargeRate').value) || 50,
            max_discharge_kwh_per_hour: parseFloat(document.getElementById('batteryDischargeRate').value) || 50
        }
    };
}

// ── Optimise ─────────────────────────────────────────────
async function runOptimization() {
    const req = buildRequest();
    if (!req) return;

    const btn = document.getElementById('optimizeBtn');
    const overlay = document.getElementById('loadingOverlay');
    btn.disabled = true;
    overlay.style.display = 'flex';

    try {
        const t0 = performance.now();
        const resp = await fetch(`${API_BASE}/optimize-energy`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(req)
        });
        const elapsed = Math.round(performance.now() - t0);

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }

        const data = await resp.json();
        data._elapsed = elapsed;
        currentResult = data;
        renderResults(data, req);
    } catch (err) {
        alert(`Optimisation failed: ${err.message}`);
    } finally {
        btn.disabled = false;
        overlay.style.display = 'none';
    }
}

// ── Render Results ───────────────────────────────────────
function renderResults(data, req) {
    const section = document.getElementById('resultsSection');
    section.style.display = 'block';
    setTimeout(() => section.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);

    // Summary
    document.getElementById('totalCost').textContent = data.total_cost_bdt.toLocaleString();
    document.getElementById('totalGrid').textContent = data.total_grid_kwh.toLocaleString();
    document.getElementById('peakGrid').textContent = data.peak_grid_kwh.toLocaleString();
    document.getElementById('elapsedTime').textContent = data._elapsed;

    // Directives
    renderDirectives(data.directive_interpretation, req.operator_notes);

    // Charts
    renderCharts(data, req);

    // Schedule table
    renderSchedule(data, req);

    // Plan summary
    document.getElementById('planSummary').textContent = data.plan_summary;
}

function renderDirectives(directives, notes) {
    const list = document.getElementById('directiveList');
    list.innerHTML = '';
    directives.forEach((d, i) => {
        const isNoop = d.directive_type === 'no_op';
        const badgeClass = {
            solar_reduction: 'badge-solar',
            minimum_battery_reserve: 'badge-reserve',
            no_charge_window: 'badge-nocharge',
            no_discharge_window: 'badge-nodischarge',
            max_grid_window: 'badge-maxgrid',
            no_op: 'badge-noop'
        }[d.directive_type] || 'badge-noop';

        let detail = '';
        if (d.structured_adjustment) {
            const adj = d.structured_adjustment;
            if (adj.hours) detail += `Hours: [${adj.hours.join(', ')}]`;
            if (adj.factor != null) detail += ` · Factor: ${adj.factor}`;
            if (adj.minimum_energy_kwh != null) detail += ` · Min: ${adj.minimum_energy_kwh} kWh`;
            if (adj.max_grid_kwh != null) detail += ` · Max: ${adj.max_grid_kwh} kWh`;
        }

        const item = document.createElement('div');
        item.className = `directive-item ${isNoop ? 'noop' : ''}`;
        item.innerHTML = `
            <span class="directive-badge ${badgeClass}">${d.directive_type.replace('_', ' ')}</span>
            <div>
                <div class="directive-text">
                    <strong>Note ${i}:</strong> ${notes[i] || '(unknown)'}
                </div>
                ${detail ? `<div class="directive-text" style="margin-top:4px;font-family:var(--mono);font-size:0.8rem;color:var(--accent-cyan)">${detail}</div>` : ''}
                <div class="directive-text" style="margin-top:4px;font-style:italic;font-size:0.8rem">${d.explanation}</div>
            </div>
        `;
        list.appendChild(item);
    });
}

function renderCharts(data, req) {
    Object.values(charts).forEach(c => c.destroy());
    charts = {};

    const labels = Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, '0')}:00`);
    const plan = data.hourly_plan;
    const tariff = req.hours.map(h => h.tariff_bdt_per_kwh);
    const demand = req.hours.map(h => h.demand_kwh);

    const commonOpts = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 } } },
            tooltip: { backgroundColor: '#1e293b', titleColor: '#f1f5f9', bodyColor: '#94a3b8', borderColor: '#334155', borderWidth: 1, cornerRadius: 8, padding: 10 }
        },
        scales: {
            x: { ticks: { color: '#64748b', font: { size: 10 } }, grid: { color: 'rgba(148,163,184,0.06)' } },
            y: { ticks: { color: '#64748b', font: { size: 10 } }, grid: { color: 'rgba(148,163,184,0.06)' } }
        }
    };

    // Grid vs Solar
    charts.gridSolar = new Chart(document.getElementById('gridSolarChart'), {
        type: 'bar',
        data: {
            labels,
            datasets: [
                { label: 'Grid (kWh)', data: plan.map(p => p.grid_kwh), backgroundColor: 'rgba(96,165,250,0.7)', borderRadius: 3 },
                { label: 'Solar Used (kWh)', data: plan.map(p => p.solar_used_kwh), backgroundColor: 'rgba(251,146,60,0.7)', borderRadius: 3 },
                { label: 'Demand (kWh)', data: demand, type: 'line', borderColor: '#f87171', borderWidth: 2, pointRadius: 0, fill: false, tension: 0.3 }
            ]
        },
        options: { ...commonOpts, plugins: { ...commonOpts.plugins, tooltip: { ...commonOpts.plugins.tooltip, mode: 'index', intersect: false } } }
    });

    // Battery SOC
    const socColors = plan.map(p => {
        if (p.battery_action === 'charge') return 'rgba(52,211,153,0.8)';
        if (p.battery_action === 'discharge') return 'rgba(251,146,60,0.8)';
        return 'rgba(148,163,184,0.4)';
    });
    charts.battery = new Chart(document.getElementById('batteryChart'), {
        type: 'bar',
        data: {
            labels,
            datasets: [
                { label: 'SOC (kWh)', data: plan.map(p => p.battery_energy_after_kwh), backgroundColor: socColors, borderRadius: 3 },
                { label: 'Capacity', data: Array(24).fill(req.battery.capacity_kwh), type: 'line', borderColor: 'rgba(148,163,184,0.3)', borderWidth: 1, borderDash: [5, 5], pointRadius: 0, fill: false },
                { label: 'Min Reserve', data: Array(24).fill(req.battery.minimum_energy_kwh), type: 'line', borderColor: 'rgba(248,113,113,0.3)', borderWidth: 1, borderDash: [5, 5], pointRadius: 0, fill: false }
            ]
        },
        options: commonOpts
    });

    // Cost per hour
    charts.cost = new Chart(document.getElementById('costChart'), {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'Cost (BDT)',
                data: plan.map((p, i) => p.grid_kwh * tariff[i]),
                backgroundColor: plan.map((p, i) => {
                    const cost = p.grid_kwh * tariff[i];
                    const maxCost = Math.max(...plan.map((q, j) => q.grid_kwh * tariff[j]));
                    const ratio = maxCost > 0 ? cost / maxCost : 0;
                    return `rgba(167,139,250,${0.3 + ratio * 0.7})`;
                }),
                borderRadius: 3
            }]
        },
        options: commonOpts
    });

    // Tariff vs Battery Action
    const actionColors = plan.map(p => {
        if (p.battery_action === 'charge') return 'rgba(52,211,153,0.8)';
        if (p.battery_action === 'discharge') return 'rgba(251,146,60,0.8)';
        return 'rgba(148,163,184,0.3)';
    });
    charts.tariff = new Chart(document.getElementById('tariffChart'), {
        type: 'bar',
        data: {
            labels,
            datasets: [
                { label: 'Tariff (BDT/kWh)', data: tariff, type: 'line', borderColor: '#60a5fa', borderWidth: 2, pointRadius: 2, pointBackgroundColor: '#60a5fa', fill: { target: 'origin', above: 'rgba(96,165,250,0.05)' }, tension: 0.3, yAxisID: 'y' },
                { label: 'Battery Action', data: plan.map(p => p.battery_kwh), backgroundColor: actionColors, borderRadius: 3, yAxisID: 'y1' }
            ]
        },
        options: {
            ...commonOpts,
            scales: {
                ...commonOpts.scales,
                y: { ...commonOpts.scales.y, position: 'left', title: { display: true, text: 'Tariff', color: '#64748b' } },
                y1: { ...commonOpts.scales.y, position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: 'Battery kWh', color: '#64748b' } }
            }
        }
    });
}

function renderSchedule(data, req) {
    const body = document.getElementById('scheduleBody');
    body.innerHTML = '';
    const tariff = req.hours.map(h => h.tariff_bdt_per_kwh);
    const maxSOC = req.battery.capacity_kwh;

    data.hourly_plan.forEach((p, i) => {
        const cost = (p.grid_kwh * tariff[i]).toFixed(1);
        const socPct = maxSOC > 0 ? (p.battery_energy_after_kwh / maxSOC * 100) : 0;
        const actionClass = p.battery_action === 'charge' ? 'action-charge' :
                           p.battery_action === 'discharge' ? 'action-discharge' : 'action-idle';

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${String(p.hour).padStart(2, '0')}</td>
            <td>${p.grid_kwh.toFixed(1)}</td>
            <td>${p.solar_used_kwh.toFixed(1)}</td>
            <td><span class="action-badge ${actionClass}">${p.battery_action}</span></td>
            <td>${p.battery_kwh.toFixed(1)}</td>
            <td><span class="soc-bar" style="width:${socPct * 0.8}px"></span>${p.battery_energy_after_kwh.toFixed(0)}</td>
            <td>${req.hours[i].demand_kwh}</td>
            <td>${tariff[i]}</td>
            <td style="font-weight:600">${cost}</td>
        `;
        body.appendChild(tr);
    });
}
