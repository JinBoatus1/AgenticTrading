// ============================================================================
// LEADERBOARD (Competition tab — real baselines from API)
// ============================================================================

let leaderboardPayload = null;
let currentLeaderboardFilter = 'all';
let currentLeaderboardSort = 'return'; // 'return' | 'sharpe'
let selectedLeaderboardEntry = null;
let equityCurvesData = null;
let equityCurvesChartInstance = null;
let currentChartView = 'absolute'; // default: money ($). 'cumulative' = % return
let leaderboardListenersInitialized = false;

// Chart visual-hierarchy state
let hiddenSeries = new Set();
let hiddenInitialized = false;
let hoveredDatasetIndex = null;
let canvasLeaveBound = false;
const selectedBenchmarkLabel = 'SPY';

// Stable per-series style presets. `kind` drives width/opacity hierarchy:
//   benchmark -> neutral gray, dotted / dash-dot, understated
//   strategy  -> colored, long-dashed, secondary
//   team      -> solid, prominent (colors assigned stably, never by rank)
const LEADERBOARD_STYLES = {
  SPY: { color: '#CBD5E1', kind: 'benchmark', dash: [2, 4] },
  DJIA: { color: '#94A3B8', kind: 'benchmark', dash: [8, 4, 2, 4] },
  'Buy & Hold': { color: '#38BDF8', kind: 'strategy', dash: [10, 6] },
  'Mean-Variance': { color: '#C084FC', kind: 'strategy', dash: [10, 6] },
  'Equal-Weight': { color: '#4ADE80', kind: 'strategy', dash: [10, 6] },
};

// Visual hierarchy: teams are boldest, strategy baselines secondary, market
// indices (benchmarks) the most understated — thin, neutral, low-opacity.
const KIND_WIDTH = { team: 2.25, strategy: 1.6, benchmark: 1.1 };
const KIND_ALPHA = { team: 1.0, strategy: 0.7, benchmark: 0.5 };
const EMPHASIS_WIDTH = 3;

// Stable bright palette for actual competition teams (assigned first-seen).
const TEAM_COLOR_PALETTE = [
  '#F97316', '#EAB308', '#EC4899', '#14B8A6', '#A855F7',
  '#EF4444', '#06B6D4', '#84CC16', '#F43F5E', '#8B5CF6',
];
const teamColorMap = {};

function shortName(label) {
  // Model names are already canonical/short; only guard against long team names.
  return label && label.length > 18 ? `${label.slice(0, 17)}…` : (label || '');
}

function hexToRgba(hex, alpha) {
  const h = String(hex || '').replace('#', '');
  const r = parseInt(h.slice(0, 2), 16) || 0;
  const g = parseInt(h.slice(2, 4), 16) || 0;
  const b = parseInt(h.slice(4, 6), 16) || 0;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function getTeamColor(stableId) {
  const key = String(stableId);
  if (!teamColorMap[key]) {
    const idx = Object.keys(teamColorMap).length % TEAM_COLOR_PALETTE.length;
    teamColorMap[key] = TEAM_COLOR_PALETTE[idx];
  }
  return teamColorMap[key];
}

function getSeriesStyle(label, entry) {
  const preset = LEADERBOARD_STYLES[label];
  if (preset) return { ...preset };
  return { color: getTeamColor(entry?.entry_id || label), kind: 'team', dash: [] };
}

function getEntryKind(entry) {
  if (entry.entry_type && entry.entry_type !== 'baseline') return 'team';
  const label = entry.model || entry.team_name;
  const preset = LEADERBOARD_STYLES[label];
  return preset ? preset.kind : 'strategy';
}

function formatLeaderboardNumber(num) {
  return Number(num || 0).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function formatShortDate(isoDay) {
  if (!isoDay) return '';
  const d = new Date(`${isoDay}T00:00:00`);
  if (Number.isNaN(d.getTime())) return isoDay;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function buildEquityCurvesFromEntries(entries) {
  // Align every series on a shared, sorted date axis (by calendar day) rather
  // than by positional index, so curves with different lengths/end dates render
  // at their true x-positions instead of being shifted.
  const dateSet = new Set();
  const perEntry = [];

  entries.forEach((entry) => {
    const points = entry.equity_curve || [];
    if (!points.length) return;
    const byDay = {};
    points.forEach((pt) => {
      const ts = String(pt.timestamp || '');
      const day = ts.length >= 10 ? ts.slice(0, 10) : ts;
      if (!day) return;
      byDay[day] = Number(pt.equity) || 0;
      dateSet.add(day);
    });
    perEntry.push({ entry, seriesLabel: entry.model || entry.team_name, byDay });
  });

  const days = Array.from(dateSet).sort();
  const curves = {};
  const trajectories = {};
  const initials = {};

  perEntry.forEach(({ entry, seriesLabel, byDay }) => {
    const values = days.map((d) => (d in byDay ? byDay[d] : null));
    const firstReal = values.find((v) => v != null);
    curves[seriesLabel] = values;
    initials[seriesLabel] = Number(entry.initial_equity) || firstReal || 100000;
    trajectories[seriesLabel] = getSeriesStyle(seriesLabel, entry);
  });

  return { days, curves, trajectories, initials };
}

// Default chart visibility: top 5 teams + benchmarks. Strategy baselines are
// hidden by default (selectable via legend) — unless there are no teams yet,
// in which case we show them so the chart isn't just two gray lines.
function computeDefaultHidden(entries) {
  const hidden = new Set();
  const teams = entries.filter((e) => getEntryKind(e) === 'team');
  const hasTeams = teams.length > 0;
  const visibleTeamIds = new Set(teams.slice(0, 5).map((e) => e.entry_id));

  entries.forEach((entry) => {
    const label = entry.model || entry.team_name;
    const kind = getEntryKind(entry);
    if (kind === 'team' && !visibleTeamIds.has(entry.entry_id)) hidden.add(label);
    if (kind === 'strategy' && hasTeams) hidden.add(label);
  });
  return hidden;
}

function updateLeaderboardHeader(payload) {
  const entries = payload.entries || [];
  // Entries arrive pre-ranked; the first team entry is the leading participant.
  const teams = entries.filter((e) => getEntryKind(e) === 'team');

  const totalEl = document.getElementById('totalTeams');
  const windowEl = document.getElementById('tradingWindow');
  const updatedEl = document.getElementById('lastUpdate');
  const leaderEl = document.getElementById('leaderTeam');

  if (totalEl) totalEl.textContent = String(teams.length);
  if (windowEl) windowEl.textContent = payload.window?.label || '—';
  if (updatedEl) {
    updatedEl.textContent = payload.updated_at
      ? new Date(payload.updated_at).toLocaleString()
      : '—';
  }
  if (leaderEl) leaderEl.textContent = teams.length ? teams[0].team_name : 'No team results';
}

function initLeaderboardListeners() {
  document.querySelectorAll('.filter-tab').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.filter-tab').forEach((b) => b.classList.remove('active'));
      e.target.classList.add('active');
      currentLeaderboardFilter = e.target.dataset.filter;
      applyFilterVisibility();
      populateLeaderboardTable();
      renderEquityCurvesChart();
    });
  });

  document.querySelectorAll('.sort-btn').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.sort-btn').forEach((b) => b.classList.remove('active'));
      e.target.classList.add('active');
      currentLeaderboardSort = e.target.dataset.sort === 'sharpe' ? 'sharpe' : 'return';
      populateLeaderboardTable();
    });
  });

  document.querySelectorAll('.view-toggle-btn').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      document.querySelectorAll('.view-toggle-btn').forEach((b) => b.classList.remove('active'));
      e.target.classList.add('active');
      currentChartView = e.target.dataset.view === 'absolute' ? 'absolute' : 'cumulative';
      await renderEquityCurvesChart();
    });
  });

  document.querySelectorAll('.chart-view-btn').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      document.querySelectorAll('.chart-view-btn').forEach((b) => b.classList.remove('active'));
      e.target.classList.add('active');
      currentChartView = e.target.dataset.view;
      await renderEquityCurvesChart();
    });
  });
}

async function loadLeaderboardData() {
  console.log('Loading leaderboard from API...');

  try {
    const url = `${API_BASE}/api/v1/leaderboard?t=${Date.now()}`;
    leaderboardPayload = await API.get(url);
    const entries = leaderboardPayload.entries || [];
    equityCurvesData = buildEquityCurvesFromEntries(entries);

    if (!hiddenInitialized) {
      hiddenSeries = computeDefaultHidden(entries);
      hiddenInitialized = true;
    }

    updateLeaderboardHeader(leaderboardPayload);
    populateLeaderboardTable();

    if (!leaderboardListenersInitialized) {
      initLeaderboardListeners();
      leaderboardListenersInitialized = true;
    }

    await renderEquityCurvesChart();
  } catch (error) {
    console.error('Error loading leaderboard:', error);
    displayLeaderboardError(error.message);
  }
}

function getFilteredLeaderboardEntries() {
  let entries = (leaderboardPayload?.entries || []).slice();
  if (currentLeaderboardFilter === 'baselines') {
    entries = entries.filter((e) => e.entry_type === 'baseline');
  } else if (currentLeaderboardFilter === 'teams') {
    entries = entries.filter((e) => getEntryKind(e) === 'team');
  }

  const key = currentLeaderboardSort === 'sharpe' ? 'sharpe_ratio' : 'cumulative_return';
  entries.sort((a, b) => (Number(b[key]) || 0) - (Number(a[key]) || 0));
  return entries;
}

// The filter tabs also drive which curves are visible on the chart.
function applyFilterVisibility() {
  const entries = leaderboardPayload?.entries || [];
  if (currentLeaderboardFilter === 'teams') {
    hiddenSeries = new Set(
      entries.filter((e) => getEntryKind(e) !== 'team').map((e) => e.model || e.team_name)
    );
  } else if (currentLeaderboardFilter === 'baselines') {
    hiddenSeries = new Set(
      entries.filter((e) => e.entry_type !== 'baseline').map((e) => e.model || e.team_name)
    );
  } else {
    hiddenSeries = computeDefaultHidden(entries);
  }
}

function populateLeaderboardTable() {
  const tbody = document.getElementById('leaderboardTableBody');
  if (!tbody) return;

  const filtered = getFilteredLeaderboardEntries();
  if (!filtered.length) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;padding:24px;color:var(--text-secondary);">No leaderboard entries yet. Baselines compute on first load (requires market data).</td></tr>';
    return;
  }

  tbody.innerHTML = filtered.map((entry) => {
    const rankBadges = `<span class="rank-badge ${entry.rank_cr <= 3 ? 'top3' : ''}">${entry.rank_cr}</span>
         <span class="rank-badge ${entry.rank_sr <= 3 ? 'top3' : ''}">${entry.rank_sr}</span>`;

    const safeId = String(entry.entry_id || entry.team_name).replace(/'/g, "\\'");
    const ret = Number(entry.cumulative_return || 0);
    const retClass = ret >= 0 ? 'return-positive' : 'return-negative';
    const ddRaw = Number(entry.max_drawdown || 0);
    const dd = (Math.abs(ddRaw) * 100).toFixed(2);

    return `
      <tr onclick="selectLeaderboardTeam('${safeId}')">
        <td class="rank-cell">${entry.rank}</td>
        <td>
          <div class="team-name-badge">
            <span>${entry.team_name}</span>
            <span class="team-badge">${entry.team_badge || 'Baseline'}</span>
          </div>
        </td>
        <td>${entry.model || '—'}</td>
        <td style="text-align: right; font-family: var(--font-mono);">$${formatLeaderboardNumber(entry.portfolio_value)}</td>
        <td style="text-align: right;" class="${retClass}">
          <span class="metric-value-text">${(ret * 100).toFixed(2)}%</span>
        </td>
        <td style="text-align: right; font-family: var(--font-mono);">${Number(entry.sharpe_ratio || 0).toFixed(2)}</td>
        <td style="text-align: right; font-family: var(--font-mono);">${dd}%</td>
        <td style="text-align: center;">${rankBadges}</td>
        <td style="text-align: right; font-weight: 600;">${Number(entry.final_score || 0).toFixed(2)}</td>
      </tr>
    `;
  }).join('');
}

function selectLeaderboardTeam(entryId) {
  const entries = leaderboardPayload?.entries || [];
  selectedLeaderboardEntry =
    entries.find((e) => String(e.entry_id) === String(entryId)) ||
    entries.find((e) => e.team_name === entryId);
  if (!selectedLeaderboardEntry) return;

  const entry = selectedLeaderboardEntry;
  const detailPanel = document.getElementById('selectedTeamDetail');
  if (detailPanel) {
    const ret = Number(entry.cumulative_return || 0);
    const retColor = ret >= 0 ? 'var(--success-color)' : 'var(--danger-color)';
    detailPanel.innerHTML = `
      <div class="team-detail-row">
        <span class="team-detail-label">Name</span>
        <span class="team-detail-value">${entry.team_name}</span>
      </div>
      <div class="team-detail-row">
        <span class="team-detail-label">Model</span>
        <span class="team-detail-value">${entry.model || '—'}</span>
      </div>
      <div class="team-detail-row">
        <span class="team-detail-label">Return</span>
        <span class="team-detail-value" style="color: ${retColor};">${(ret * 100).toFixed(2)}%</span>
      </div>
      <div class="team-detail-row">
        <span class="team-detail-label">Sharpe</span>
        <span class="team-detail-value">${Number(entry.sharpe_ratio || 0).toFixed(2)}</span>
      </div>
      <div class="team-detail-row">
        <span class="team-detail-label">Max Drawdown</span>
        <span class="team-detail-value">${(Math.abs(Number(entry.max_drawdown || 0)) * 100).toFixed(2)}%</span>
      </div>
      <div class="team-detail-row">
        <span class="team-detail-label">Rank</span>
        <span class="team-detail-value">${entry.rank} / ${leaderboardPayload?.total_entries || '—'}</span>
      </div>
      <div class="team-detail-row">
        <span class="team-detail-label">Type</span>
        <span class="team-detail-value">${entry.entry_type === 'baseline' ? 'Baseline' : 'Agent'}</span>
      </div>
    `;
  }

  // Selecting an entry also forces it visible and re-emphasizes it on the chart.
  const label = entry.model || entry.team_name;
  hiddenSeries.delete(label);
  renderEquityCurvesChart();
}

function getEmphasisLabel(orderedEntries) {
  if (selectedLeaderboardEntry) {
    return selectedLeaderboardEntry.model || selectedLeaderboardEntry.team_name;
  }
  const leadTeam = orderedEntries.find((e) => getEntryKind(e) === 'team');
  return leadTeam ? (leadTeam.model || leadTeam.team_name) : null;
}

function styleDatasets(chart) {
  const emphasisLabel = chart.$emphasisLabel;
  chart.data.datasets.forEach((ds, i) => {
    const st = ds._style || { kind: 'team' };
    const baseW = KIND_WIDTH[st.kind] || 2;
    let alpha;
    let width;
    if (hoveredDatasetIndex != null) {
      if (i === hoveredDatasetIndex) {
        alpha = 1.0;
        width = Math.max(baseW + 0.75, 2.5);
      } else {
        alpha = 0.25;
        width = baseW;
      }
    } else {
      const emph = ds.label === emphasisLabel;
      alpha = emph ? 1.0 : (KIND_ALPHA[st.kind] ?? 1.0);
      width = emph ? EMPHASIS_WIDTH : baseW;
    }
    ds.borderColor = hexToRgba(st.color, alpha);
    ds.borderWidth = width;
  });
}

// Subtle glow only on the emphasized (selected/leading) curve.
const selectedGlowPlugin = {
  id: 'selectedGlow',
  beforeDatasetDraw(chart, args) {
    const ds = chart.data.datasets[args.index];
    if (ds && ds.label === chart.$emphasisLabel && hoveredDatasetIndex == null) {
      const { ctx } = chart;
      ctx.save();
      ctx.shadowColor = hexToRgba((ds._style && ds._style.color) || '#ffffff', 0.45);
      ctx.shadowBlur = 6;
    }
  },
  afterDatasetDraw(chart, args) {
    const ds = chart.data.datasets[args.index];
    if (ds && ds.label === chart.$emphasisLabel && hoveredDatasetIndex == null) {
      chart.ctx.restore();
    }
  },
};

// Right-endpoint labels: name + latest return for each visible curve, with
// vertical collision avoidance and subtle leader lines to displaced labels.
const endpointLabelPlugin = {
  id: 'endpointLabels',
  afterDatasetsDraw(chart) {
    const { ctx, chartArea } = chart;
    const labels = [];

    chart.data.datasets.forEach((ds, i) => {
      const meta = chart.getDatasetMeta(i);
      if (meta.hidden || ds.hidden || !ds._raw || !meta.data || !meta.data.length) return;
      let lastIdx = -1;
      for (let k = ds._raw.length - 1; k >= 0; k -= 1) {
        if (ds._raw[k] != null) { lastIdx = k; break; }
      }
      if (lastIdx < 0 || !meta.data[lastIdx]) return;

      const ret = (ds._entry && ds._entry.cumulative_return != null)
        ? Number(ds._entry.cumulative_return)
        : (ds._raw[lastIdx] - ds._initial) / (ds._initial || 1);

      labels.push({
        i,
        anchorX: meta.data[lastIdx].x,
        anchorY: meta.data[lastIdx].y,
        y: meta.data[lastIdx].y,
        color: (ds._style && ds._style.color) || '#e5e7eb',
        text: `${shortName(ds.label)}  ${(ret * 100).toFixed(1)}%`,
      });
    });
    if (!labels.length) return;

    // Stagger overlapping labels downward, keeping >= GAP px spacing. Each
    // label keeps its original endpoint y (anchorY) so we can tell later
    // whether collision-avoidance actually moved it.
    const GAP = 20;
    // Only draw a leader line once a label has been displaced enough that the
    // connection is genuinely ambiguous; otherwise it just leaves a tiny stub.
    const LEADER_MIN_DISPLACEMENT = 7;
    labels.sort((a, b) => a.y - b.y);
    for (let k = 1; k < labels.length; k += 1) {
      if (labels[k].y - labels[k - 1].y < GAP) labels[k].y = labels[k - 1].y + GAP;
    }
    // If the stack overflows the plot bottom, shift the whole stack up.
    const overflow = labels[labels.length - 1].y - chartArea.bottom;
    if (overflow > 0) labels.forEach((lab) => { lab.y -= overflow; });

    // Labels live entirely inside the reserved right gutter so the plotted
    // line paths (which end at chartArea.right) never leave stubs under them.
    const gutterStart = chartArea.right + 6;
    const labelX = chartArea.right + 12;
    ctx.save();
    ctx.font = '600 11px Inter, system-ui, sans-serif';
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'left';
    labels.forEach((lab) => {
      const faded = hoveredDatasetIndex != null && lab.i !== hoveredDatasetIndex;
      const displaced = Math.abs(lab.y - lab.anchorY) > LEADER_MIN_DISPLACEMENT;
      if (displaced) {
        // Subtle dotted leader, drawn only within the gutter (never over the
        // data line endpoint), connecting the displaced label to its curve.
        ctx.setLineDash([1, 3]);
        ctx.strokeStyle = hexToRgba(lab.color, faded ? 0.12 : 0.35);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(gutterStart, lab.anchorY);
        ctx.lineTo(labelX - 3, lab.y);
        ctx.stroke();
        ctx.setLineDash([]);
      }
      ctx.fillStyle = hexToRgba(lab.color, faded ? 0.3 : 1);
      ctx.fillText(lab.text, labelX, lab.y);
    });
    ctx.restore();
  },
};

function buildCustomLegend(chart) {
  const container = document.getElementById('equityCurvesLegend');
  if (!container) return;

  const order = { team: 0, strategy: 1, benchmark: 2 };
  const items = chart.data.datasets
    .map((ds, i) => ({ ds, i }))
    .sort((a, b) => (order[a.ds._style.kind] ?? 9) - (order[b.ds._style.kind] ?? 9));

  container.innerHTML = items.map(({ ds }) => {
    const st = ds._style;
    const hidden = hiddenSeries.has(ds.label);
    const w = Math.min(KIND_WIDTH[st.kind] || 2, 2.4);
    const dash = (st.dash && st.dash.length) ? st.dash.join(',') : '';
    const stroke = hidden ? 'rgba(148,163,184,0.4)' : st.color;
    return `
      <button class="legend-item${hidden ? ' legend-hidden' : ''}" data-label="${ds.label.replace(/"/g, '&quot;')}">
        <svg class="legend-sample" width="26" height="10" viewBox="0 0 26 10">
          <line x1="1" y1="5" x2="25" y2="5" stroke="${stroke}" stroke-width="${w}"
            ${dash ? `stroke-dasharray="${dash}"` : ''} stroke-linecap="round" />
        </svg>
        <span class="legend-label">${shortName(ds.label)}</span>
      </button>`;
  }).join('');

  container.querySelectorAll('.legend-item').forEach((el) => {
    el.addEventListener('click', () => {
      const label = el.dataset.label;
      if (hiddenSeries.has(label)) hiddenSeries.delete(label);
      else hiddenSeries.add(label);
      renderEquityCurvesChart();
    });
  });
}

async function renderEquityCurvesChart() {
  if (!equityCurvesData) return;

  const canvas = document.getElementById('equityCurvesChart');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  const { days, curves, initials } = equityCurvesData;
  const orderedEntries = (leaderboardPayload?.entries || []);
  const emphasisLabel = getEmphasisLabel(orderedEntries);

  const datasets = [];
  orderedEntries.forEach((entry) => {
    const label = entry.model || entry.team_name;
    const raw = curves[label];
    if (!raw || !raw.length) return;
    const initial = initials[label] || raw[0] || 100000;
    const style = getSeriesStyle(label, entry);

    datasets.push({
      label,
      data: transformLeaderboardChartData(raw, currentChartView, initial),
      _raw: raw,
      _initial: initial,
      _entry: entry,
      _style: style,
      borderColor: style.color,
      backgroundColor: 'transparent',
      borderDash: style.dash || [],
      borderCapStyle: 'round',
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0.1,
      fill: false,
      spanGaps: false,
      hidden: hiddenSeries.has(label),
    });
  });

  const baseInitial = (datasets[0] && datasets[0]._initial) || 100000;
  const isMoney = currentChartView === 'absolute';

  if (equityCurvesChartInstance) {
    equityCurvesChartInstance.destroy();
  }

  equityCurvesChartInstance = new Chart(ctx, {
    type: 'line',
    data: { labels: days, datasets },
    plugins: [selectedGlowPlugin, endpointLabelPlugin],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { right: 120, top: 8 } },
      // 'nearest' across BOTH axes (no axis:'x') so hover targets the single
      // line under the cursor instead of every series sharing that x-position.
      interaction: { mode: 'nearest', intersect: false },
      onHover(event, _els, chart) {
        let idx = null;
        const hits = chart.getElementsAtEventForMode(event, 'nearest', { intersect: false }, true);
        if (hits.length) idx = hits[0].datasetIndex;
        if (idx !== hoveredDatasetIndex) {
          hoveredDatasetIndex = idx;
          styleDatasets(chart);
          chart.update('none');
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          mode: 'nearest',
          intersect: false,
          position: 'nearest',
          backgroundColor: 'rgba(15, 23, 42, 0.96)',
          borderColor: 'rgba(148, 163, 184, 0.25)',
          borderWidth: 1,
          titleColor: '#e5e7eb',
          bodyColor: '#cbd5e1',
          padding: 10,
          displayColors: false,
          callbacks: {
            title(items) {
              if (!items.length) return '';
              return formatShortDate(items[0].label);
            },
            label(context) {
              const ds = context.dataset;
              const idx = context.dataIndex;
              const equity = (ds._raw && ds._raw[idx]) || 0;
              const ret = (equity - ds._initial) / (ds._initial || 1);
              const entry = ds._entry || {};
              const lines = [
                ds.label,
                `Return: ${(ret * 100).toFixed(2)}%`,
                `Value: $${formatLeaderboardNumber(equity)}`,
                `Rank: ${entry.rank ?? '—'} / ${leaderboardPayload?.total_entries || '—'}`,
              ];

              const benchDs = context.chart.data.datasets.find((d) => d.label === selectedBenchmarkLabel);
              if (benchDs && benchDs.label !== ds.label && benchDs._raw && benchDs._raw[idx] != null) {
                const benchRet = (benchDs._raw[idx] - benchDs._initial) / (benchDs._initial || 1);
                const diff = (ret - benchRet) * 100;
                const sign = diff >= 0 ? '+' : '';
                lines.push(`vs ${shortName(selectedBenchmarkLabel)}: ${sign}${diff.toFixed(2)}%`);
              }
              return lines;
            },
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: '#6b7280',
            maxRotation: 0,
            minRotation: 0,
            autoSkip: true,
            maxTicksLimit: 7,
            callback(value) {
              return formatShortDate(this.getLabelForValue(value));
            },
          },
          grid: { color: 'rgba(148, 163, 184, 0.05)', drawTicks: false },
        },
        y: {
          ticks: {
            color: '#9ca3af',
            callback(value) {
              if (isMoney) return `$${formatLeaderboardNumber(value)}`;
              return `${(value * 100).toFixed(1)}%`;
            },
          },
          grid: {
            color(c) {
              const v = c.tick.value;
              const isRef = isMoney ? Math.abs(v - baseInitial) < 1 : Math.abs(v) < 1e-9;
              return isRef ? 'rgba(148, 163, 184, 0.45)' : 'rgba(148, 163, 184, 0.08)';
            },
            lineWidth(c) {
              const v = c.tick.value;
              const isRef = isMoney ? Math.abs(v - baseInitial) < 1 : Math.abs(v) < 1e-9;
              return isRef ? 1.4 : 1;
            },
          },
        },
      },
    },
  });

  equityCurvesChartInstance.$emphasisLabel = emphasisLabel;
  styleDatasets(equityCurvesChartInstance);
  equityCurvesChartInstance.update('none');

  if (!canvasLeaveBound) {
    canvas.addEventListener('mouseleave', () => {
      if (hoveredDatasetIndex != null && equityCurvesChartInstance) {
        hoveredDatasetIndex = null;
        styleDatasets(equityCurvesChartInstance);
        equityCurvesChartInstance.update('none');
      }
    });
    canvasLeaveBound = true;
  }

  buildCustomLegend(equityCurvesChartInstance);
}

function transformLeaderboardChartData(curveValues, viewType, initialValue) {
  const base = initialValue || 100000;
  if (viewType === 'absolute') {
    return curveValues.slice();
  }
  return curveValues.map((v) => (v == null ? null : (v - base) / base));
}

function displayLeaderboardError(message) {
  const tbody = document.getElementById('leaderboardTableBody');
  if (tbody) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; padding: 30px; color: var(--danger-color);">Error: ${message}</td></tr>`;
  }
}

window.loadLeaderboardData = loadLeaderboardData;
window.selectLeaderboardTeam = selectLeaderboardTeam;
