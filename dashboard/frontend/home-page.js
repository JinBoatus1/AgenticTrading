/**
 * Home page mock live events (frontend only).
 * Replace useMockLiveEvents with a real event source when backend is ready.
 */
const ENABLE_MOCK_LIVE_EVENTS = true;

const INITIAL_EVENTS = [
    {
        id: 'initial-decision',
        type: 'decision_generated',
        agent: 'FinAgent Alpha',
        action: 'BUY',
        symbol: 'NVDA',
        price: 921.43,
        confidence: 0.74,
        rationale: 'Momentum strengthened with above-average volume.',
        createdAt: Date.now() - 2 * 60 * 1000,
    },
    {
        id: 'initial-trade-tsla',
        type: 'trade_executed',
        agent: 'QuantNova',
        action: 'SELL',
        symbol: 'TSLA',
        price: 410.22,
        rationale: 'Taking profits after resistance.',
        createdAt: Date.now() - 5 * 60 * 1000,
    },
    {
        id: 'initial-trade-aapl',
        type: 'trade_executed',
        agent: 'MacroMind',
        action: 'BUY',
        symbol: 'AAPL',
        price: 195.63,
        rationale: 'Positive earnings momentum.',
        createdAt: Date.now() - 8 * 60 * 1000,
    },
    {
        id: 'initial-backtest',
        type: 'backtest_completed',
        agent: 'SignalScout',
        strategy: 'Mean Reversion v2',
        returnValue: 4.2,
        sharpe: 1.42,
        createdAt: Date.now() - 12 * 60 * 1000,
    },
    {
        id: 'initial-risk',
        type: 'risk_check_passed',
        agent: 'RiskGuardian',
        message: 'Portfolio risk remains within configured limits.',
        createdAt: Date.now() - 15 * 60 * 1000,
    },
    {
        id: 'initial-rank',
        type: 'rank_changed',
        agent: 'FinAgent Alpha',
        previousRank: 7,
        newRank: 6,
        createdAt: Date.now() - 18 * 60 * 1000,
    },
];

const MOCK_EVENTS = [
    {
        id: 'mock-decision-1',
        type: 'decision_generated',
        agent: 'FinAgent Alpha',
        action: 'BUY',
        symbol: 'NVDA',
        price: 921.43,
        confidence: 0.74,
        rationale: 'Momentum strengthened with above-average volume.',
    },
    {
        id: 'mock-trade-1',
        type: 'trade_executed',
        agent: 'QuantNova',
        action: 'SELL',
        symbol: 'TSLA',
        price: 410.22,
        rationale: 'Taking profits after resistance.',
    },
    {
        id: 'mock-trade-2',
        type: 'trade_executed',
        agent: 'MacroMind',
        action: 'BUY',
        symbol: 'AAPL',
        price: 195.63,
        rationale: 'Positive earnings momentum.',
    },
    {
        id: 'mock-backtest-1',
        type: 'backtest_completed',
        agent: 'SignalScout',
        strategy: 'Mean Reversion v2',
        returnValue: 4.2,
        sharpe: 1.42,
    },
    {
        id: 'mock-risk-1',
        type: 'risk_check_passed',
        agent: 'RiskGuardian',
        message: 'Portfolio risk remains within configured limits.',
    },
    {
        id: 'mock-rank-1',
        type: 'rank_changed',
        agent: 'FinAgent Alpha',
        previousRank: 7,
        newRank: 6,
    },
];

const HOME_MARKET_PULSE_DATA = {
    traded: [
        { ticker: 'NVDA', count: 28, change: '+3.42%', up: true },
        { ticker: 'AAPL', count: 21, change: '+1.66%', up: true },
        { ticker: 'TSLA', count: 18, change: '+1.24%', up: true },
        { ticker: 'META', count: 16, change: '+4.25%', up: true },
        { ticker: 'AMZN', count: 15, change: '+3.69%', up: true },
    ],
    discussed: [
        { ticker: 'NVDA', count: 42, up: true },
        { ticker: 'TSLA', count: 35, up: false },
        { ticker: 'AAPL', count: 29, up: true },
        { ticker: 'MSFT', count: 24, up: true },
        { ticker: 'META', count: 19, up: true },
    ],
    trending: [
        { ticker: 'META', change: '+4.25%', up: true },
        { ticker: 'NVDA', change: '+3.42%', up: true },
        { ticker: 'AMZN', change: '+3.09%', up: true },
        { ticker: 'MSFT', change: '+2.32%', up: true },
        { ticker: 'AAPL', change: '+1.66%', up: true },
    ],
};

const EVENT_META = {
    decision_generated: { label: 'NEW DECISION', tone: 'cyan', icon: 'icon-brain' },
    trade_executed: { label: 'TRADE EXECUTED', tone: 'trade', icon: 'icon-chart' },
    backtest_completed: { label: 'BACKTEST COMPLETE', tone: 'cyan', icon: 'icon-flask' },
    risk_check_passed: { label: 'RISK CHECK PASSED', tone: 'green', icon: 'icon-shield-check' },
    rank_changed: { label: 'RANK UPDATE', tone: 'blue', icon: 'icon-trending-up' },
};

let homeMockTimer = null;
let homeMockIndex = 0;
let homeToastTimer = null;
let homeActivePulseTab = 'traded';
let homeFeedHovered = false;
let homeMetricValues = { agents: 28, decisions: 147, trades: 36, backtests: 12 };
let homeEvents = [];
let homeLatestEvent = null;

function homeIcon(name) {
    return `<svg class="ui-icon" aria-hidden="true"><use href="#${name}"/></svg>`;
}

function homeSparkline(up) {
    const points = up
        ? '0,14 8,10 16,12 24,6 32,8 40,2'
        : '0,4 8,8 16,6 24,12 32,10 40,14';
    const color = up ? '#22c55e' : '#ef4444';
    return `<svg class="home-sparkline" viewBox="0 0 40 16" aria-hidden="true"><polyline points="${points}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

function formatPrice(price) {
    return `$${Number(price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatRelativeTime(createdAt) {
    const diffMs = Math.max(0, Date.now() - createdAt);
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
}

function eventToActivity(event, timeLabel) {
    const meta = EVENT_META[event.type] || { tone: 'cyan', icon: 'icon-activity' };
    const time = timeLabel || formatRelativeTime(event.createdAt || Date.now());
    const base = { id: event.id, time };

    switch (event.type) {
        case 'decision_generated':
            return {
                ...base,
                agent: event.agent,
                headline: 'generated a decision',
                action: `${event.action} ${event.symbol}`,
                context: event.rationale,
                tone: event.action === 'BUY' ? 'green' : event.action === 'SELL' ? 'red' : 'cyan',
                icon: meta.icon,
            };
        case 'trade_executed':
            return {
                ...base,
                agent: event.agent,
                headline: 'executed a trade',
                action: `${event.action} ${event.symbol} at ${formatPrice(event.price)}`,
                context: event.rationale,
                tone: event.action === 'SELL' ? 'red' : 'green',
                icon: meta.icon,
            };
        case 'backtest_completed':
            return {
                ...base,
                agent: event.agent,
                headline: 'completed a backtest',
                action: event.strategy,
                context: `Return +${event.returnValue}% · Sharpe ${event.sharpe}`,
                tone: 'amber',
                icon: meta.icon,
            };
        case 'risk_check_passed':
            return {
                ...base,
                agent: event.agent,
                headline: 'passed a risk check',
                action: event.message,
                context: '',
                tone: 'green',
                icon: meta.icon,
            };
        case 'rank_changed':
            return {
                ...base,
                agent: event.agent,
                headline: 'changed rank',
                action: `Moved from #${event.previousRank} to #${event.newRank}.`,
                context: '',
                tone: 'blue',
                icon: meta.icon,
            };
        default:
            return null;
    }
}

function eventToToast(event) {
    const meta = EVENT_META[event.type] || { label: 'LIVE EVENT', tone: 'cyan' };
    let actionText = '';
    let tone = meta.tone;

    switch (event.type) {
        case 'decision_generated':
            actionText = `${event.action} ${event.symbol} at ${formatPrice(event.price)}`;
            tone = event.action === 'BUY' ? 'green' : event.action === 'SELL' ? 'red' : 'cyan';
            break;
        case 'trade_executed':
            actionText = `${event.action} ${event.symbol} at ${formatPrice(event.price)}`;
            tone = event.action === 'SELL' ? 'red' : 'green';
            break;
        case 'backtest_completed':
            actionText = `${event.strategy} · Return +${event.returnValue}%`;
            tone = 'cyan';
            break;
        case 'risk_check_passed':
            actionText = event.message;
            tone = 'green';
            break;
        case 'rank_changed':
            actionText = `Rank #${event.previousRank} → #${event.newRank}`;
            tone = 'blue';
            break;
        default:
            actionText = 'New activity';
    }

    return {
        label: meta.label,
        time: 'just now',
        agent: event.agent,
        action: actionText,
        rationale: event.rationale || event.message || '',
        tone,
        icon: meta.icon,
    };
}

function renderActivityItem(item, isNew) {
    const cls = isNew ? ' home-timeline-item--new' : '';
    const context = item.context
        ? `<p class="home-timeline-context">${item.context}</p>`
        : '';
    return `
        <article class="home-timeline-item home-timeline-item--${item.tone}${cls}" data-event-id="${item.id || ''}">
            <div class="home-timeline-rail" aria-hidden="true">
                <span class="home-timeline-dot"></span>
            </div>
            <div class="home-timeline-body">
                <div class="home-timeline-head">
                    <span class="home-timeline-time">${item.time}</span>
                    <span class="home-timeline-icon">${homeIcon(item.icon)}</span>
                </div>
                <p class="home-timeline-text"><strong>${item.agent}</strong> ${item.headline}</p>
                <p class="home-timeline-action">${item.action}</p>
                ${context}
            </div>
        </article>
    `;
}

function renderActivityFeed(items) {
    const feed = document.getElementById('homeActivityFeed');
    if (!feed) return;

    if (!items.length) {
        feed.innerHTML = '<p class="home-timeline-fallback">Waiting for the next agent event…</p>';
        return;
    }

    feed.innerHTML = items.map((item) => renderActivityItem(item, false)).join('');
}

function prependActivity(item) {
    const feed = document.getElementById('homeActivityFeed');
    if (!feed) return;

    const fallback = feed.querySelector('.home-timeline-fallback');
    if (fallback) fallback.remove();

    feed.insertAdjacentHTML('afterbegin', renderActivityItem(item, true));
    const first = feed.firstElementChild;
    if (first && !homeFeedHovered) {
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                first.classList.remove('home-timeline-item--new');
                first.classList.add('home-timeline-item--highlight');
                window.setTimeout(() => first.classList.remove('home-timeline-item--highlight'), 700);
            });
        });
    } else if (first) {
        first.classList.remove('home-timeline-item--new');
    }

    while (feed.children.length > 6) {
        feed.lastElementChild?.remove();
    }
}

function flashMetric(key, delta) {
    if (homeMetricValues[key] === undefined) return;
    homeMetricValues[key] = Math.max(0, homeMetricValues[key] + delta);
    const map = {
        agents: 'homeMetricAgents',
        decisions: 'homeMetricDecisions',
        trades: 'homeMetricTrades',
        backtests: 'homeMetricBacktests',
    };
    const el = document.getElementById(map[key]);
    if (!el) return;
    el.classList.add('home-metric-value--flash');
    el.textContent = String(homeMetricValues[key]);
    window.setTimeout(() => el.classList.remove('home-metric-value--flash'), 650);
}

function applyEventMetrics(event) {
    switch (event.type) {
        case 'decision_generated':
            flashMetric('decisions', 1);
            break;
        case 'trade_executed':
            flashMetric('trades', 1);
            break;
        case 'backtest_started':
            flashMetric('backtests', 1);
            break;
        case 'backtest_completed':
            flashMetric('backtests', -1);
            break;
        case 'agent_online':
            flashMetric('agents', 1);
            break;
        case 'agent_offline':
            flashMetric('agents', -1);
            break;
        default:
            break;
    }
}

function flashField(el) {
    if (!el) return;
    el.classList.add('home-field--flash');
    window.setTimeout(() => el.classList.remove('home-field--flash'), 650);
}

function updateSpotlightFromEvent(event) {
    if (event.agent !== 'FinAgent Alpha') return;

    const actionMain = document.getElementById('homeSpotlightActionMain');
    const priceEl = document.getElementById('homeSpotlightPrice');
    const timeEl = document.getElementById('homeSpotlightActionTime');
    const rationaleEl = document.getElementById('homeSpotlightRationale');
    const activeEl = document.getElementById('homeSpotlightLastActive');
    const sparkline = document.getElementById('homeSpotlightSparkline');
    const actionBlock = actionMain?.closest('.home-spotlight-action-block');

    if (event.type === 'decision_generated' || event.type === 'trade_executed') {
        const verbEl = actionMain?.querySelector('.home-spotlight-action-verb');
        if (verbEl) {
            verbEl.textContent = event.action;
            verbEl.className = `home-spotlight-action-verb ${event.action === 'SELL' ? 'home-highlight-negative' : 'home-highlight-positive'}`;
            flashField(verbEl);
        }
        if (priceEl) {
            priceEl.textContent = formatPrice(event.price);
            flashField(priceEl);
        }
        if (actionMain) flashField(actionMain);
        if (timeEl) {
            timeEl.textContent = 'just now';
            flashField(timeEl);
        }
        if (rationaleEl && event.rationale) {
            rationaleEl.textContent = event.rationale;
            flashField(rationaleEl);
        }
        if (activeEl) {
            activeEl.textContent = 'just now';
            flashField(activeEl);
        }
        if (sparkline) {
            const line = sparkline.querySelector('polyline');
            if (line) line.setAttribute('points', '0,16 6,12 12,14 18,8 24,10 30,4 36,6 40,2');
            flashField(sparkline.closest('.home-spotlight-stat'));
        }
        if (actionBlock) {
            actionBlock.classList.add('home-spotlight-action-block--flash');
            window.setTimeout(() => actionBlock.classList.remove('home-spotlight-action-block--flash'), 700);
        }
    } else if (event.type === 'rank_changed') {
        if (activeEl) {
            activeEl.textContent = 'just now';
            flashField(activeEl);
        }
    }
}

function highlightPulseSymbol(symbol) {
    if (!symbol) return;
    document.querySelectorAll('.home-pulse-row').forEach((row) => {
        if (row.dataset.ticker === symbol) {
            row.classList.add('home-pulse-row--flash');
            window.setTimeout(() => row.classList.remove('home-pulse-row--flash'), 900);
        }
    });
}

function renderMarketPulseTab(tab) {
    homeActivePulseTab = tab;
    const list = document.getElementById('homeMarketPulseList');
    if (!list) return;

    let rowsHtml = '';

    if (tab === 'traded') {
        rowsHtml = HOME_MARKET_PULSE_DATA.traded.map((row) => `
            <div class="home-pulse-row" data-ticker="${row.ticker}">
                <div class="home-pulse-ticker">${row.ticker}</div>
                <div class="home-pulse-agents tabular-nums">${row.count} agents</div>
                <div class="home-pulse-change tabular-nums positive">${row.change}</div>
                ${homeSparkline(row.up)}
            </div>
        `).join('');
    } else if (tab === 'discussed') {
        rowsHtml = HOME_MARKET_PULSE_DATA.discussed.map((row) => `
            <div class="home-pulse-row" data-ticker="${row.ticker}">
                <div class="home-pulse-ticker">${row.ticker}</div>
                <div class="home-pulse-agents tabular-nums">${row.count} mentions</div>
                <div class="home-pulse-change tabular-nums home-pulse-muted">—</div>
                ${homeSparkline(row.up !== false)}
            </div>
        `).join('');
    } else {
        rowsHtml = HOME_MARKET_PULSE_DATA.trending.map((row) => `
            <div class="home-pulse-row" data-ticker="${row.ticker}">
                <div class="home-pulse-ticker">${row.ticker}</div>
                <div class="home-pulse-agents tabular-nums home-pulse-muted">trending</div>
                <div class="home-pulse-change tabular-nums positive">${row.change}</div>
                ${homeSparkline(row.up)}
            </div>
        `).join('');
    }

    list.innerHTML = rowsHtml || '<p class="home-pulse-fallback">No agent market activity available.</p>';
}

function hideLiveToast() {
    const toast = document.getElementById('homeLiveToast');
    if (!toast) return;
    toast.classList.remove('home-live-toast--visible');
    window.clearTimeout(homeToastTimer);
    homeToastTimer = window.setTimeout(() => {
        toast.hidden = true;
    }, 280);
}

function showLiveToast(toastData) {
    const toast = document.getElementById('homeLiveToast');
    if (!toast) return;

    toast.className = `home-live-toast home-live-toast--${toastData.tone || 'cyan'}`;

    const label = toast.querySelector('.home-live-toast-label');
    const agent = toast.querySelector('.home-live-toast-agent');
    const action = toast.querySelector('.home-live-toast-action');
    const rationale = toast.querySelector('.home-live-toast-rationale');
    const iconUse = toast.querySelector('.home-live-toast-icon use');

    if (label) label.textContent = `${toastData.label} · ${toastData.time}`;
    if (agent) agent.textContent = toastData.agent;
    if (action) action.textContent = toastData.action;
    if (rationale) {
        rationale.textContent = toastData.rationale ? `"${toastData.rationale}"` : '';
        rationale.hidden = !toastData.rationale;
    }
    if (iconUse && toastData.icon) iconUse.setAttribute('href', `#${toastData.icon}`);

    toast.hidden = false;
    requestAnimationFrame(() => toast.classList.add('home-live-toast--visible'));
    window.clearTimeout(homeToastTimer);
    homeToastTimer = window.setTimeout(hideLiveToast, 6000);
}

function pushMockEvent(event) {
    const stamped = { ...event, createdAt: Date.now() };
    homeEvents = [stamped, ...homeEvents].slice(0, 6);
    homeLatestEvent = stamped;

    const activity = eventToActivity(stamped);
    if (activity) prependActivity(activity);

    applyEventMetrics(stamped);
    updateSpotlightFromEvent(stamped);

    if (stamped.symbol) highlightPulseSymbol(stamped.symbol);

    showLiveToast(eventToToast(stamped));
}

function emitMockLiveEvent() {
    const event = MOCK_EVENTS[homeMockIndex % MOCK_EVENTS.length];
    homeMockIndex += 1;
    pushMockEvent({ ...event, id: `${event.id}-${homeMockIndex}` });
}

function scheduleNextMockEvent() {
    if (!ENABLE_MOCK_LIVE_EVENTS) return;
    const delay = 6000 + Math.floor(Math.random() * 4000);
    homeMockTimer = window.setTimeout(() => {
        if (document.getElementById('homeView')?.style.display !== 'none') {
            emitMockLiveEvent();
        }
        scheduleNextMockEvent();
    }, delay);
}

function stopHomeMockEvents() {
    window.clearTimeout(homeMockTimer);
    homeMockTimer = null;
}

function dismissLatestEvent() {
    hideLiveToast();
}

function useMockLiveEvents() {
    return {
        events: homeEvents,
        latestEvent: homeLatestEvent,
        metrics: { ...homeMetricValues },
        spotlight: null,
        pulseData: HOME_MARKET_PULSE_DATA,
        dismissLatestEvent,
        start() {
            stopHomeMockEvents();
            if (!ENABLE_MOCK_LIVE_EVENTS) return;
            homeMockTimer = window.setTimeout(() => {
                if (document.getElementById('homeView')?.style.display !== 'none') {
                    emitMockLiveEvent();
                }
                scheduleNextMockEvent();
            }, 3000);
        },
        stop: stopHomeMockEvents,
    };
}

let homeMockLive = null;

function initMarketPulseTabs() {
    document.querySelectorAll('[data-pulse-tab]').forEach((btn) => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.pulseTab;
            document.querySelectorAll('[data-pulse-tab]').forEach((b) => {
                b.classList.toggle('active', b.dataset.pulseTab === tab);
            });
            renderMarketPulseTab(tab);
        });
    });
    renderMarketPulseTab('traded');
}

function initActivityFeedHover() {
    const feed = document.getElementById('homeActivityFeed');
    if (!feed) return;
    feed.addEventListener('mouseenter', () => { homeFeedHovered = true; });
    feed.addEventListener('mouseleave', () => { homeFeedHovered = false; });
}

function navigateToLeaderboard() {
    if (typeof navigateToPage === 'function') {
        navigateToPage('competition', { competitionTab: 'leaderboard' });
    }
}

function initHomePage() {
    homeEvents = INITIAL_EVENTS.map((event) => ({ ...event }));
    renderActivityFeed(homeEvents.map((event) => eventToActivity(event)));
    initMarketPulseTabs();
    initActivityFeedHover();

    document.getElementById('homeLiveToastClose')?.addEventListener('click', dismissLatestEvent);

    document.getElementById('homeViewLeaderboardBtn')?.addEventListener('click', navigateToLeaderboard);
    document.getElementById('homeResourceLeaderboardBtn')?.addEventListener('click', navigateToLeaderboard);

    document.getElementById('homeActivityViewAll')?.addEventListener('click', (e) => {
        e.preventDefault();
        if (typeof navigateToPage === 'function') {
            navigateToPage('playground', { playgroundTab: 'overview' });
        }
    });

    homeMockLive = useMockLiveEvents();
    if (document.getElementById('homeView')?.style.display !== 'none') {
        homeMockLive.start();
    }
}

function onHomePageShow() {
    if (!homeMockLive) homeMockLive = useMockLiveEvents();
    homeMockLive.start();
}

function onHomePageHide() {
    homeMockLive?.stop();
    hideLiveToast();
}

window.initHomePage = initHomePage;
window.onHomePageShow = onHomePageShow;
window.onHomePageHide = onHomePageHide;
window.useMockLiveEvents = useMockLiveEvents;
