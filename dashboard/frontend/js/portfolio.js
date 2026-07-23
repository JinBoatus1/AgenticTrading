/*
 * portfolio.js — "My Portfolio" section for the My Agents page.
 *
 * Signed-in users load GET /api/v1/portfolio (account-bound $10k ledger).
 * Guests / demo keep the SAMPLE DATA mock below.
 */

// ---------------------------------------------------------------------------
// Mock data (guest / demo only)
// ---------------------------------------------------------------------------
const PORTFOLIO_MOCK = {
    summary: {
        totalValue: 10000,
        cashAvailable: 7000,
        allocated: 3000,
    },
};

/** @type {null | { equity: number, cash_available: number, allocated: number }} */
let livePortfolio = null;

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------
function pfMoney(value) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(Number(value) || 0);
}

function pfSignedMoney(value) {
    const sign = Number(value) >= 0 ? '+' : '-';
    return `${sign}${pfMoney(Math.abs(Number(value) || 0))}`;
}

function pfSignedPct(value) {
    const sign = Number(value) >= 0 ? '+' : '';
    return `${sign}${(Number(value) || 0).toFixed(2)}%`;
}

// ---------------------------------------------------------------------------
// PortfolioSummaryCard
// ---------------------------------------------------------------------------
function buildSummaryCards(summary) {
    const total = Number(summary.totalValue) || 0;
    const available = Number(summary.cashAvailable) || 0;
    const allocated = summary.allocated != null
        ? Number(summary.allocated)
        : Math.max(total - available, 0);
    return [
        {
            label: 'Total Portfolio',
            value: pfMoney(total),
            sub: 'Account equity',
            tone: 'muted',
            icon: 'wallet',
        },
        {
            label: 'Cash Available',
            value: pfMoney(available),
            sub: 'Still unallocated',
            tone: 'muted',
            icon: 'cash',
        },
        {
            label: 'Allocated',
            value: pfMoney(allocated),
            sub: 'Assigned to agents',
            tone: 'muted',
            icon: 'allocate',
        },
    ];
}

const PF_ICONS = {
    wallet: '<path d="M19 7V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-2"/><path d="M16 12h5v4h-5a2 2 0 0 1 0-4Z"/>',
    pulse: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    trend: '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
    cash: '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 12h.01M18 12h.01"/>',
    allocate: '<circle cx="12" cy="12" r="9"/><path d="M12 3v9l7 4"/>',
};

function renderPortfolioSummary(summary) {
    const grid = document.getElementById('portfolioSummaryGrid');
    if (!grid) return;
    const cards = buildSummaryCards(summary);
    grid.innerHTML = cards
        .map(
            (c) => `
        <div class="portfolio-summary-card">
            <div class="portfolio-summary-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${PF_ICONS[c.icon] || ''}</svg>
            </div>
            <div class="portfolio-summary-body">
                <span class="portfolio-summary-label">${c.label}</span>
                <span class="portfolio-summary-value ${c.valueTone ? 'is-' + c.valueTone : ''}">${c.value}</span>
                <span class="portfolio-summary-sub is-${c.tone}">${c.sub}</span>
            </div>
        </div>`,
        )
        .join('');
}

// ---------------------------------------------------------------------------
// AllocationChart
// ---------------------------------------------------------------------------
const pfChartInstances = {};

function renderAllocationChart(key, data) {
    const canvas = document.getElementById(`${key}AllocationChart`);
    const legendEl = document.getElementById(`${key}AllocationLegend`);
    const totalEl = document.getElementById(`${key}AllocationTotal`);
    if (!canvas || typeof Chart === 'undefined') return;

    const labels = data.slices.map((s) => s.label);
    const values = data.slices.map((s) => s.value);
    const colors = data.slices.map((s) => s.color);

    if (pfChartInstances[key]) {
        pfChartInstances[key].destroy();
    }

    pfChartInstances[key] = new Chart(canvas.getContext('2d'), {
        type: 'pie',
        data: {
            labels,
            datasets: [
                {
                    data: values,
                    backgroundColor: colors,
                    borderColor: 'rgba(10, 14, 39, 0.9)',
                    borderWidth: 2,
                    hoverOffset: 6,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => {
                            const slice = data.slices[ctx.dataIndex];
                            const amount = slice.assignedCapital != null
                                ? slice.assignedCapital
                                : slice.value;
                            return `${slice.label}: ${slice.pct}% · ${pfMoney(amount)}`;
                        },
                    },
                },
            },
        },
    });

    if (totalEl) {
        totalEl.innerHTML = `
            <span class="allocation-total-label">Total</span>
            <span class="allocation-total-value">${pfMoney(data.total)}</span>`;
    }

    if (legendEl) {
        const rows = data.slices
            .map(
                (s) => {
                    const displayValue = s.assignedCapital != null ? s.assignedCapital : s.value;
                    return `
            <li class="allocation-legend-row">
                <span class="allocation-legend-name">
                    <span class="allocation-legend-dot" style="background:${s.color}"></span>
                    ${s.label}
                </span>
                <span class="allocation-legend-pct">${s.pct}%</span>
                <span class="allocation-legend-value">${pfMoney(displayValue)}</span>
            </li>`;
                },
            )
            .join('');
        legendEl.innerHTML = rows;
    }
}

// ---------------------------------------------------------------------------
// Capital allocation by agent (portfolio-wide: assigned + unassigned)
// ---------------------------------------------------------------------------
const AGENT_SLICE_COLORS = ['#22d3ee', '#a855f7', '#34d399', '#fbbf24', '#f87171', '#c084fc', '#38bdf8', '#2dd4bf'];
const UNASSIGNED_SLICE_COLOR = '#64748b';

function portfolioPct(value, totalPortfolioValue) {
    const total = Number(totalPortfolioValue) || 0;
    if (total <= 0) return 0;
    return Math.round((Number(value) / total) * 1000) / 10;
}

function getTotalPortfolioValue() {
    if (livePortfolio) return Number(livePortfolio.equity) || 0;
    return Number(PORTFOLIO_MOCK.summary.totalValue) || 0;
}

function setPortfolioSampleBadgeVisible(visible) {
    const badge = document.getElementById('portfolioSampleBadge');
    if (!badge) return;
    // Inline style on the badge beats the UA [hidden] rule — toggle display.
    badge.style.display = visible ? 'inline-block' : 'none';
}

function isPortfolioSignedIn() {
    try {
        const tokenKey = typeof AUTH_TOKEN_KEY === 'string' ? AUTH_TOKEN_KEY : 'auth-token';
        const token = localStorage.getItem(tokenKey);
        if (!token) return false;
        if (typeof getStoredAuthUser === 'function') return !!getStoredAuthUser();
        return true;
    } catch (_) {
        return false;
    }
}

function summaryFromLivePortfolio(portfolio) {
    const equity = Number(portfolio.equity) || 0;
    const cash = Number(portfolio.cash_available) || 0;
    const allocated = portfolio.allocated != null
        ? Number(portfolio.allocated)
        : Math.max(equity - cash, 0);
    return {
        totalValue: equity,
        cashAvailable: cash,
        allocated,
    };
}

function buildAgentAllocationData(agents, totalPortfolioValue) {
    const total = Number(totalPortfolioValue) || 0;

    const assignedAgents = (agents || []).filter(
        (agent) => agent.cash_allocation != null && Number(agent.cash_allocation) > 0,
    );

    if (total <= 0) {
        return {
            total: 0,
            slices: [{ label: 'Unassigned', value: 0, pct: 0, color: UNASSIGNED_SLICE_COLOR }],
        };
    }

    if (!assignedAgents.length) {
        return {
            total,
            slices: [{
                label: 'Unassigned',
                value: total,
                pct: 100,
                color: UNASSIGNED_SLICE_COLOR,
            }],
        };
    }

    const assignedTotal = assignedAgents.reduce(
        (sum, agent) => sum + Number(agent.cash_allocation),
        0,
    );
    const unassigned = Math.max(total - assignedTotal, 0);
    const overAllocated = assignedTotal > total;
    const chartScale = overAllocated && assignedTotal > 0 ? total / assignedTotal : 1;

    const slices = [];

    // Agents first, Unassigned last (legend + pie order).
    assignedAgents.forEach((agent, index) => {
        const assignedCapital = Number(agent.cash_allocation);
        const chartValue = assignedCapital * chartScale;
        slices.push({
            label: agent.name || 'Agent',
            value: chartValue,
            assignedCapital,
            pct: portfolioPct(assignedCapital, total),
            color: AGENT_SLICE_COLORS[index % AGENT_SLICE_COLORS.length],
        });
    });

    if (unassigned > 0) {
        slices.push({
            label: 'Unassigned',
            value: unassigned,
            pct: portfolioPct(unassigned, total),
            color: UNASSIGNED_SLICE_COLOR,
        });
    }

    if (!slices.length) {
        slices.push({
            label: 'Unassigned',
            value: total,
            pct: 100,
            color: UNASSIGNED_SLICE_COLOR,
        });
    }

    return { total, slices, overAllocated };
}

function updateAgentAllocationFromAgents(agents) {
    renderAllocationChart('agent', buildAgentAllocationData(agents, getTotalPortfolioValue()));
}

function renderPortfolioFromMock(agents) {
    livePortfolio = null;
    setPortfolioSampleBadgeVisible(true);
    renderPortfolioSummary(PORTFOLIO_MOCK.summary);
    renderAllocationChart('agent', buildAgentAllocationData(agents, getTotalPortfolioValue()));
}

function renderPortfolioFromLive(portfolio, agents) {
    livePortfolio = {
        equity: Number(portfolio.equity) || 0,
        cash_available: Number(portfolio.cash_available) || 0,
        allocated: Number(portfolio.allocated) || 0,
    };
    setPortfolioSampleBadgeVisible(false);
    renderPortfolioSummary(summaryFromLivePortfolio(livePortfolio));
    updateAgentAllocationFromAgents(agents);
}

// ---------------------------------------------------------------------------
// Public entry point — called when the My Agents tab becomes visible.
// ---------------------------------------------------------------------------
async function renderPortfolio(agents) {
    const list = agents || [];
    if (!isPortfolioSignedIn() || typeof API === 'undefined' || typeof API_BASE === 'undefined') {
        renderPortfolioFromMock(list);
        return;
    }
    try {
        const data = await API.get(`${API_BASE}/api/v1/portfolio`);
        const portfolio = data && data.portfolio;
        if (!portfolio) {
            renderPortfolioFromMock(list);
            return;
        }
        renderPortfolioFromLive(portfolio, list);
    } catch (error) {
        console.warn('Portfolio API unavailable; showing sample data:', error?.message || error);
        renderPortfolioFromMock(list);
    }
}

window.renderPortfolio = renderPortfolio;
window.updateAgentAllocationFromAgents = updateAgentAllocationFromAgents;
