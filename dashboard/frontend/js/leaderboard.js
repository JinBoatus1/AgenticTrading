// ============================================================================
// LEADERBOARD (Competition tab — real baselines from API)
// ============================================================================

let leaderboardPayload = null;
let currentLeaderboardFilter = 'all';
let selectedLeaderboardEntry = null;
let equityCurvesData = null;
let equityCurvesChartInstance = null;
let currentChartView = 'cumulative';
let leaderboardListenersInitialized = false;

const LEADERBOARD_COLORS = {
  'S&P 500 (SPY)': { color: '#9AA4B2', bgColor: 'rgba(154, 164, 178, 0.15)', isBaseline: true },
  'Dow Jones Industrial Average (DJIA)': { color: '#F5C04A', bgColor: 'rgba(245, 192, 74, 0.15)', isBaseline: true },
  'Buy-and-hold (DJIA 30)': { color: '#5AC8FA', bgColor: 'rgba(90, 200, 250, 0.15)', isBaseline: true },
  'Mean-Variance (DJIA 30)': { color: '#C77DFF', bgColor: 'rgba(199, 125, 255, 0.15)', isBaseline: true },
  'Equal-weight (DJIA 30)': { color: '#7ED957', bgColor: 'rgba(126, 217, 87, 0.15)', isBaseline: true },
};

function formatLeaderboardNumber(num) {
  return Number(num || 0).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function getLeaderboardColorConfig(name, entryType) {
  if (LEADERBOARD_COLORS[name]) {
    return LEADERBOARD_COLORS[name];
  }
  return {
    color: entryType === 'baseline' ? '#9ca3af' : '#60a5fa',
    bgColor: 'rgba(156, 163, 175, 0.15)',
    isBaseline: entryType === 'baseline',
  };
}

function buildEquityCurvesFromEntries(entries) {
  const days = [];
  const curves = {};
  const trajectories = {};

  entries.forEach((entry) => {
    const points = entry.equity_curve || [];
    if (!points.length) return;

    const labels = [];
    const values = [];
    points.forEach((pt) => {
      const ts = String(pt.timestamp || '');
      const day = ts.length >= 10 ? ts.slice(0, 10) : ts;
      labels.push(day);
      values.push(Number(pt.equity) || 0);
    });

    if (!days.length) {
      days.push(...labels);
    }

    const seriesLabel = entry.model || entry.team_name;
    curves[seriesLabel] = values;
    trajectories[seriesLabel] = getLeaderboardColorConfig(seriesLabel, entry.entry_type);
  });

  return { days, curves, trajectories };
}

function updateLeaderboardHeader(payload) {
  const totalEl = document.getElementById('totalTeams');
  const windowEl = document.getElementById('tradingWindow');
  const updatedEl = document.getElementById('lastUpdate');
  const leaderEl = document.getElementById('leaderTeam');

  if (totalEl) totalEl.textContent = String(payload.total_entries || 0);
  if (windowEl) windowEl.textContent = payload.window?.label || '—';
  if (updatedEl) {
    updatedEl.textContent = payload.updated_at
      ? new Date(payload.updated_at).toLocaleString()
      : '—';
  }
  if (leaderEl) leaderEl.textContent = payload.leader || '—';
}

function initLeaderboardListeners() {
  document.querySelectorAll('.filter-tab').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.filter-tab').forEach((b) => b.classList.remove('active'));
      e.target.classList.add('active');
      currentLeaderboardFilter = e.target.dataset.filter;
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
    equityCurvesData = buildEquityCurvesFromEntries(leaderboardPayload.entries || []);

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
  const entries = leaderboardPayload?.entries || [];
  if (currentLeaderboardFilter === 'top10') {
    return entries.slice(0, 10);
  }
  if (currentLeaderboardFilter === 'baselines') {
    return entries.filter((e) => e.entry_type === 'baseline');
  }
  return entries;
}

function populateLeaderboardTable() {
  const tbody = document.getElementById('leaderboardTableBody');
  if (!tbody) return;

  const filtered = getFilteredLeaderboardEntries();
  if (!filtered.length) {
    tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:24px;color:var(--text-secondary);">No leaderboard entries yet. Baselines compute on first load (requires Alpaca data).</td></tr>';
    return;
  }

  tbody.innerHTML = filtered.map((entry) => {
    const isBaseline = entry.entry_type === 'baseline';
    const wlCell = isBaseline
      ? '<span style="color:var(--text-muted);">—</span>'
      : `<span class="metric-value-text">${Number(entry.win_loss_ratio || 0).toFixed(2)}</span>`;
    const rankBadges = isBaseline
      ? `<span class="rank-badge ${entry.rank_cr <= 3 ? 'top3' : ''}">${entry.rank_cr}</span>
         <span class="rank-badge ${entry.rank_sr <= 3 ? 'top3' : ''}">${entry.rank_sr}</span>`
      : `<span class="rank-badge ${entry.rank_cr <= 3 ? 'top3' : ''}">${entry.rank_cr}</span>
         <span class="rank-badge ${entry.rank_sr <= 3 ? 'top3' : ''}">${entry.rank_sr}</span>
         <span class="rank-badge">${entry.rank_wl || '—'}</span>`;

    const safeId = String(entry.entry_id || entry.team_name).replace(/'/g, "\\'");
    const ret = Number(entry.cumulative_return || 0);
    const retClass = ret >= 0 ? 'return-positive' : 'return-negative';

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
        <td style="text-align: right; font-family: var(--font-mono);">${wlCell}</td>
        <td style="text-align: center;">${rankBadges}</td>
        <td style="text-align: right; font-weight: 600;">${Number(entry.final_score || 0).toFixed(2)}</td>
        <td style="text-align: center;">
          <span class="status-badge baseline">${entry.status || 'Baseline'}</span>
        </td>
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
  if (!detailPanel) return;

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
      <span class="team-detail-value">${(Number(entry.max_drawdown || 0) * 100).toFixed(2)}%</span>
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

async function renderEquityCurvesChart() {
  if (!equityCurvesData) return;

  const canvas = document.getElementById('equityCurvesChart');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  const { days, curves, trajectories } = equityCurvesData;

  const datasets = Object.entries(curves).map(([teamName, curveValues]) => {
    const config = getLeaderboardColorConfig(teamName, trajectories[teamName]?.isBaseline ? 'baseline' : 'agent');
    const initial = curveValues[0] || 100000;
    const data = transformLeaderboardChartData(curveValues, currentChartView, initial);
    const isBaseline = trajectories[teamName]?.isBaseline;

    return {
      label: teamName,
      data,
      borderColor: config.color,
      backgroundColor: config.bgColor,
      borderWidth: 2.5,
      borderDash: isBaseline ? [6, 4] : [],
      pointRadius: 0,
      pointHoverRadius: 5,
      tension: 0.3,
      fill: false,
    };
  });

  if (equityCurvesChartInstance) {
    equityCurvesChartInstance.destroy();
  }

  equityCurvesChartInstance = new Chart(ctx, {
    type: 'line',
    data: { labels: days, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: true,
          position: 'bottom',
          labels: {
            color: '#e5e7eb',
            font: { size: 12, weight: '600' },
            padding: 15,
            usePointStyle: true,
          },
        },
        tooltip: {
          callbacks: {
            label(context) {
              const value = context.parsed.y;
              if (currentChartView === 'absolute') {
                return `${context.dataset.label}: $${formatLeaderboardNumber(value)}`;
              }
              return `${context.dataset.label}: ${(value * 100).toFixed(2)}%`;
            },
          },
        },
      },
      scales: {
        x: {
          ticks: { color: '#9ca3af', maxRotation: 45 },
          grid: { color: '#1f2937' },
        },
        y: {
          ticks: {
            color: '#9ca3af',
            callback(value) {
              if (currentChartView === 'absolute') {
                return '$' + formatLeaderboardNumber(value);
              }
              return (value * 100).toFixed(1) + '%';
            },
          },
          grid: { color: '#1f2937' },
        },
      },
    },
  });
}

function transformLeaderboardChartData(curveValues, viewType, initialValue) {
  const base = initialValue || curveValues[0] || 100000;
  if (viewType === 'absolute') {
    return curveValues;
  }
  return curveValues.map((v) => (v - base) / base);
}

function displayLeaderboardError(message) {
  const tbody = document.getElementById('leaderboardTableBody');
  if (tbody) {
    tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; padding: 30px; color: var(--danger-color);">Error: ${message}</td></tr>`;
  }
}

window.loadLeaderboardData = loadLeaderboardData;
window.selectLeaderboardTeam = selectLeaderboardTeam;
