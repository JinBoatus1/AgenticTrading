/*
 * portfolio.js — "My Portfolio" section for the My Agents page.
 *
 * Renders four summary cards and three allocation donut charts using the
 * existing Chart.js library (loaded in index.html). Everything here is a
 * static, frontend-only mockup — no API, database, broker, or auth calls.
 *
 * TODO: Replace mock portfolio data with backend API data later.
 */

// ---------------------------------------------------------------------------
// Mock data
// TODO: Replace mock portfolio data with backend API data later.
// ---------------------------------------------------------------------------
const PORTFOLIO_MOCK = {
    summary: {
        totalValue: 128742.34,
        dayPnl: 2847.21,
        dayPnlPct: 2.26,
        totalReturn: 18742.34,
        totalReturnPct: 17.02,
        cashAvailable: 12340.56,
    },
    allocations: {
        asset: {
            total: 128742.34,
            slices: [
                { label: 'Stocks', pct: 63.1, value: 81169.32, color: '#22d3ee' },
                { label: 'Crypto', pct: 26.4, value: 34000.21, color: '#a855f7' },
                { label: 'Cash',   pct: 10.5, value: 13572.81, color: '#64748b' },
            ],
        },
        stock: {
            total: 81169.33,
            slices: [
                { label: 'AAPL',  pct: 18.2, value: 14778.35, color: '#22d3ee' },
                { label: 'MSFT',  pct: 16.7, value: 13555.12, color: '#38bdf8' },
                { label: 'NVDA',  pct: 14.9, value: 12077.88, color: '#34d399' },
                { label: 'AMZN',  pct: 8.8,  value: 7126.44,  color: '#fbbf24' },
                { label: 'TSLA',  pct: 3.1,  value: 2522.09,  color: '#f87171' },
                { label: 'META',  pct: 1.4,  value: 1119.44,  color: '#c084fc' },
                { label: 'Other', pct: 36.9, value: 29999.99, color: '#475569' },
            ],
        },
        crypto: {
            total: 34000.21,
            slices: [
                { label: 'BTC',   pct: 44.5, value: 15122.09, color: '#f59e0b' },
                { label: 'ETH',   pct: 30.2, value: 10264.07, color: '#818cf8' },
                { label: 'SOL',   pct: 11.3, value: 3841.12,  color: '#2dd4bf' },
                { label: 'ADA',   pct: 6.1,  value: 2078.43,  color: '#3b82f6' },
                { label: 'DOT',   pct: 4.2,  value: 1424.50,  color: '#ec4899' },
                { label: 'Other', pct: 3.7,  value: 1269.99,  color: '#475569' },
            ],
        },
    },
};

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

function pfMoneyCompact(value) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        maximumFractionDigits: 0,
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
    return [
        {
            label: 'Total Portfolio Value',
            value: pfMoney(summary.totalValue),
            sub: `vs last close ${pfSignedMoney(summary.dayPnl)} (${pfSignedPct(summary.dayPnlPct)})`,
            tone: summary.dayPnl >= 0 ? 'positive' : 'negative',
            icon: 'wallet',
        },
        {
            label: 'Day P/L',
            value: pfSignedMoney(summary.dayPnl),
            sub: `${pfSignedPct(summary.dayPnlPct)} vs last close`,
            tone: summary.dayPnl >= 0 ? 'positive' : 'negative',
            valueTone: summary.dayPnl >= 0 ? 'positive' : 'negative',
            icon: 'pulse',
        },
        {
            label: 'Total Return',
            value: pfSignedMoney(summary.totalReturn),
            sub: `${pfSignedPct(summary.totalReturnPct)} all time`,
            tone: summary.totalReturn >= 0 ? 'positive' : 'negative',
            valueTone: summary.totalReturn >= 0 ? 'positive' : 'negative',
            icon: 'trend',
        },
        {
            label: 'Cash Available',
            value: pfMoney(summary.cashAvailable),
            sub: 'Available to trade',
            tone: 'muted',
            icon: 'cash',
        },
    ];
}

const PF_ICONS = {
    wallet: '<path d="M19 7V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-2"/><path d="M16 12h5v4h-5a2 2 0 0 1 0-4Z"/>',
    pulse: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    trend: '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
    cash: '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 12h.01M18 12h.01"/>',
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
    const centerEl = document.getElementById(`${key}AllocationCenter`);
    if (!canvas || typeof Chart === 'undefined') return;

    const labels = data.slices.map((s) => s.label);
    const values = data.slices.map((s) => s.value);
    const colors = data.slices.map((s) => s.color);

    if (pfChartInstances[key]) {
        pfChartInstances[key].destroy();
    }

    pfChartInstances[key] = new Chart(canvas.getContext('2d'), {
        type: 'doughnut',
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
            cutout: '68%',
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => {
                            const slice = data.slices[ctx.dataIndex];
                            return `${slice.label}: ${slice.pct}% · ${pfMoney(slice.value)}`;
                        },
                    },
                },
            },
        },
    });

    if (centerEl) {
        centerEl.innerHTML = `
            <span class="allocation-center-value">${pfMoneyCompact(data.total)}</span>
            <span class="allocation-center-label">Total</span>`;
    }

    if (legendEl) {
        const rows = data.slices
            .map(
                (s) => `
            <li class="allocation-legend-row">
                <span class="allocation-legend-name">
                    <span class="allocation-legend-dot" style="background:${s.color}"></span>
                    ${s.label}
                </span>
                <span class="allocation-legend-pct">${s.pct}%</span>
                <span class="allocation-legend-value">${pfMoney(s.value)}</span>
            </li>`,
            )
            .join('');
        legendEl.innerHTML = `${rows}
            <li class="allocation-legend-row allocation-legend-total">
                <span class="allocation-legend-name">Total</span>
                <span class="allocation-legend-pct">100%</span>
                <span class="allocation-legend-value">${pfMoney(data.total)}</span>
            </li>`;
    }
}

// ---------------------------------------------------------------------------
// Public entry point — called when the My Agents tab becomes visible.
// ---------------------------------------------------------------------------
function renderPortfolio() {
    // TODO: Replace mock portfolio data with backend API data later.
    const data = PORTFOLIO_MOCK;
    renderPortfolioSummary(data.summary);
    renderAllocationChart('asset', data.allocations.asset);
    renderAllocationChart('stock', data.allocations.stock);
    renderAllocationChart('crypto', data.allocations.crypto);
}

window.renderPortfolio = renderPortfolio;
