/**
 * Agentic Trading Lab - Frontend Application
 * Connects to backend API for real data
 */

const API_BASE = "http://localhost:8000";

let chartInstance = null;
let currentMode = "backtest";
let allRuns = [];
let comparisonData = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    console.log('Dashboard initializing...');
    
    // Setup mode toggle
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            switchMode(e.target.dataset.mode);
        });
    });

    // Setup slider value displays
    document.querySelectorAll('.slider').forEach(slider => {
        slider.addEventListener('input', (e) => {
            updateSliderValue(e.target);
        });
    });

    // Setup time period buttons
    document.querySelectorAll('.time-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            updateTimePeriod(e.target);
        });
    });

    // Setup quick scenario buttons
    document.querySelectorAll('.scenario-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            handleScenario(e.currentTarget);
        });
    });

    // Setup run backtest button
    const runBtn = document.querySelector('.run-backtest-btn');
    if (runBtn) {
        runBtn.addEventListener('click', () => {
            runBacktest();
        });
    }

    // Setup collapsible advanced settings
    const advancedToggle = document.getElementById('advancedToggle');
    const advancedContent = document.getElementById('advancedContent');
    if (advancedToggle && advancedContent) {
        advancedToggle.addEventListener('click', () => {
            advancedToggle.classList.toggle('active');
            advancedContent.style.display = advancedContent.style.display === 'none' ? 'block' : 'none';
        });
    }

    // Load initial data
    await loadData();
    
    // Load market ticker data
    await loadMarketTicker();
    
    // Load performance metrics
    await loadPerformanceMetrics();
    
    // Refresh ticker every 30 seconds
    setInterval(loadMarketTicker, 30000);
});

/**
 * Load performance metrics from latest backtest run
 */
async function loadPerformanceMetrics() {
    try {
        // Add cache-busting timestamp to ensure fresh data
        const cacheBustUrl = `${API_BASE}/runs/latest/metrics?t=${Date.now()}`;
        const response = await fetch(cacheBustUrl, {
            // Force fresh data, don't use browser cache
            headers: {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        });
        
        if (response.ok) {
            const metrics = await response.json();
            
            // Validate metrics data
            if (!metrics || !metrics.initial_equity) {
                console.warn('Invalid metrics data:', metrics);
                displayNoMetrics();
                return;
            }
            
            displayPerformanceMetrics(metrics);
            console.log('✅ Performance metrics loaded:', metrics);
            
            // Log summary for debugging
            const finalValue = metrics.initial_equity * (1 + (metrics.total_return || 0) / 100);
            console.log(`   Final Value: $${finalValue.toFixed(0)}`);
            console.log(`   Return: ${(metrics.total_return || 0).toFixed(2)}%`);
            console.log(`   Max Drawdown: ${(metrics.max_drawdown || 0).toFixed(2)}%`);
            console.log(`   Sharpe: ${(metrics.sharpe_ratio || 0).toFixed(2)}`);
        } else {
            const errorText = await response.text();
            console.warn(`Could not fetch metrics: ${response.status}`, errorText);
            // Show placeholder if no data available
            displayNoMetrics();
        }
    } catch (error) {
        console.warn('Error fetching performance metrics:', error.message);
        displayNoMetrics();
    }
}

/**
 * Display performance metrics in the summary panel
 */
/**
 * Display performance metrics from backtest results.
 * 
 * Metric Formulas:
 * 1. Final Portfolio Value: last portfolio value in equity curve
 * 2. Cumulative Return: (final_value - initial_capital) / initial_capital * 100
 * 3. Max Drawdown: minimum drawdown = (value - running_peak) / running_peak * 100
 * 4. Sharpe Ratio: (mean(returns) / std(returns)) * sqrt(252*6.5)
 *    - Hourly data with 252 trading days/year and 6.5 hours/day
 */
function displayPerformanceMetrics(metrics) {
    console.log('displayPerformanceMetrics() called with:', metrics);
    
    // Calculate final value from initial equity and total return
    const initialCapital = metrics.initial_equity || 100000;
    const totalReturnPercent = metrics.total_return || 0;
    const finalValue = initialCapital * (1 + totalReturnPercent / 100);
    
    // Update Final Value
    const finalValueEl = document.querySelector('[data-metric="final-value"]');
    if (finalValueEl) {
        finalValueEl.textContent = '$' + finalValue.toLocaleString('en-US', {
            minimumFractionDigits: 0,
            maximumFractionDigits: 0
        });
        finalValueEl.className = 'metric-value ' + (totalReturnPercent >= 0 ? 'positive' : 'negative');
        console.log(`  → Updated Final Value: $${finalValue.toFixed(0)}`);
    }
    
    // Update Cumulative Return (renamed from Total Return)
    const returnEl = document.querySelector('[data-metric="total-return"]');
    if (returnEl) {
        const returnSign = totalReturnPercent >= 0 ? '+' : '';
        const returnText = returnSign + totalReturnPercent.toFixed(2) + '%';
        returnEl.textContent = returnText;
        returnEl.className = 'metric-value ' + (totalReturnPercent >= 0 ? 'positive' : 'negative');
        console.log(`  → Updated Cumulative Return: ${returnText}`);
    }
    
    // Update Max Drawdown
    const drawdownEl = document.querySelector('[data-metric="max-drawdown"]');
    if (drawdownEl) {
        const maxDrawdown = metrics.max_drawdown || 0;
        const drawdownText = maxDrawdown.toFixed(2) + '%';
        drawdownEl.textContent = drawdownText;
        drawdownEl.className = 'metric-value ' + (maxDrawdown >= 0 ? 'positive' : 'negative');
        console.log(`  → Updated Max Drawdown: ${drawdownText}`);
    }
    
    // Update Sharpe Ratio
    // Note: Calculated using hourly data with annualization factor sqrt(252*6.5)
    const sharpeEl = document.querySelector('[data-metric="sharpe"]');
    if (sharpeEl) {
        const sharpe = metrics.sharpe_ratio || 0;
        const sharpeText = sharpe.toFixed(2);
        sharpeEl.textContent = sharpeText;
        sharpeEl.className = 'metric-value';
        console.log(`  → Updated Sharpe Ratio: ${sharpeText}`);
        // Tooltip already set in HTML with title attribute
    }
}

/**
 * Display placeholder when no metrics available
 */
function displayNoMetrics() {
    const elements = [
        '[data-metric="final-value"]',
        '[data-metric="total-return"]',
        '[data-metric="max-drawdown"]',
        '[data-metric="sharpe"]'
    ];
    
    elements.forEach(selector => {
        const el = document.querySelector(selector);
        if (el) {
            el.textContent = '--';
            el.className = 'metric-value';
        }
    });
}

/**
 * Load live market data from Alpaca API
 */
async function loadMarketTicker() {
    try {
        // Default symbols: SPY, QQQ, AAPL, MSFT, NVDA, BTC
        const response = await fetch(`${API_BASE}/ticker?symbols=SPY,QQQ,AAPL,MSFT,NVDA,BTC`);
        const data = await response.json();
        
        if (data.quotes && data.quotes.length > 0) {
            updateTickerDisplay(data.quotes);
            console.log('✅ Market ticker updated:', data.quotes.length, 'symbols');
        }
    } catch (error) {
        console.warn('Could not fetch market ticker:', error.message);
        // Silently fail - ticker is non-critical
    }
}

/**
 * Update ticker bar with real market data
 */
function updateTickerDisplay(quotes) {
    const tickerBar = document.getElementById('tickerBar');
    if (!tickerBar) return;
    
    // Build ticker items from quotes
    let tickerHTML = '';
    
    quotes.forEach(quote => {
        // Handle missing changePercent
        let changeDisplay = '--';
        let changeClass = '';
        let tooltip = '';
        
        if (quote.changePercent !== null && quote.changePercent !== undefined) {
            const changeSign = quote.changePercent >= 0 ? '+' : '';
            changeDisplay = `${changeSign}${quote.changePercent.toFixed(2)}%`;
            changeClass = quote.changePercent >= 0 ? 'positive' : 'negative';
            
            // Add tooltip
            const isCrypto = quote.symbol === 'BTC' || quote.symbol === 'ETH';
            tooltip = isCrypto ? 'title="24h change"' : 'title="Change vs previous close"';
        } else {
            tooltip = 'title="Data unavailable"';
        }
        
        tickerHTML += `
            <div class="ticker-item">
                <span class="symbol">${quote.symbol}</span>
                <span class="price">${quote.price.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                <span class="change ${changeClass}" ${tooltip}>${changeDisplay}</span>
                <svg class="ticker-chart" viewBox="0 0 30 12"><path d="M0,8 L5,6 L10,7 L15,4 L20,5 L25,3 L30,5" stroke="currentColor" fill="none" stroke-width="1"/></svg>
            </div>
        `;
    });
    
    // Add spacer at end
    tickerHTML += `
        <div class="ticker-spacer">
            <span class="ticker-dropdown">Market ▼</span>
            <span class="ticker-filter">US Equities</span>
        </div>
    `;
    
    tickerBar.innerHTML = tickerHTML;
}

/**
 * Update slider value display
 */
function updateSliderValue(slider) {
    const container = slider.closest('.slider-container');
    const valueSpan = container.querySelector('.slider-value');
    if (valueSpan) {
        const value = slider.value;
        const max = slider.max;
        
        if (max === '100') {
            valueSpan.textContent = (value / 100).toFixed(2);
        } else {
            valueSpan.textContent = parseFloat(value).toFixed(2);
        }
    }
}

/**
 * Update time period selection
 */
function updateTimePeriod(btn) {
    document.querySelectorAll('.time-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    console.log('Time period changed:', btn.textContent);
}

/**
 * Handle quick scenario buttons
 */
function handleScenario(btn) {
    const scenario = btn.querySelector('span:last-child').textContent;
    console.log('Scenario selected:', scenario);
    
    const sliders = document.querySelectorAll('.slider');
    
    switch(scenario) {
        case 'Low Cost':
            sliders[3].value = 0.01;
            sliders[4].value = 0.01;
            break;
        case 'High Momentum':
            sliders[1].value = 80;
            sliders[2].value = 6;
            break;
        case 'Conservative':
            sliders[1].value = 20;
            sliders[2].value = 1.5;
            break;
    }
    
    sliders.forEach(updateSliderValue);
}

/**
 * Run backtest
 */
async function runBacktest() {
    // Get dates from form
    const startDateInput = document.getElementById('startDate');
    const endDateInput = document.getElementById('endDate');
    
    if (!startDateInput || !endDateInput) {
        console.error('Date inputs not found');
        alert('Error: Date inputs not found');
        return;
    }
    
    const startDate = startDateInput.value;
    const endDate = endDateInput.value;
    
    if (!startDate || !endDate) {
        alert('Please select both start and end dates');
        return;
    }
    
    console.log(`Running backtest: ${startDate} to ${endDate}`);
    
    const btn = document.querySelector('.run-backtest-btn');
    btn.textContent = '⏳ Running...';
    btn.disabled = true;
    
    try {
        // Call API to start backtest
        const response = await fetch(`${API_BASE}/backtest/run?start_date=${startDate}&end_date=${endDate}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        const data = await response.json();
        
        if (!data.success) {
            alert(`Error: ${data.error || 'Backtest failed'}`);
            btn.textContent = '▶ Run Backtest';
            btn.disabled = false;
            return;
        }
        
        console.log('✅ Backtest started:', data.message);
        
        // Poll for status
        await pollBacktestStatus(btn);
        
    } catch (error) {
        console.error('Error starting backtest:', error);
        alert(`Error: ${error.message}`);
        btn.textContent = '▶ Run Backtest';
        btn.disabled = false;
    }
}

/**
 * Poll backtest status until complete
 */
async function pollBacktestStatus(btn) {
    const maxAttempts = 120; // 2 minutes with 1-second intervals
    let attempts = 0;
    
    return new Promise((resolve) => {
        const interval = setInterval(async () => {
            attempts++;
            
            try {
                const response = await fetch(`${API_BASE}/backtest/status`);
                const status = await response.json();
                
                if (!status.running) {
                    clearInterval(interval);
                    
                    if (status.error) {
                        console.error('Backtest error:', status.error);
                        alert(`Backtest failed: ${status.error}`);
                    } else if (status.success) {
                        console.log('✅ Backtest completed:', status.message);
                        alert(`Backtest completed! Found ${status.runs_count} runs.`);
                        
                        // CRITICAL: Reload data in correct order:
                        // 1. Load all runs from /runs endpoint (populates allRuns)
                        // 2. Load comparison data for chart display (uses allRuns run_ids)
                        // 3. Load latest metrics for summary panel (from /runs/latest/metrics)
                        console.log('→ Reloading backtest data...');
                        await loadData();
                        
                        console.log('→ Refreshing performance metrics...');
                        await loadPerformanceMetrics();
                        
                        console.log('✅ Dashboard updated with latest backtest results');
                    }
                    
                    btn.textContent = '▶ Run Backtest';
                    btn.disabled = false;
                    resolve();
                } else if (attempts % 10 === 0) {
                    console.log(`⏳ Backtest running... (${attempts}s elapsed)`);
                }
                
                if (attempts >= maxAttempts) {
                    clearInterval(interval);
                    console.warn('Backtest timeout - still running after 2 minutes');
                    btn.textContent = '▶ Run Backtest';
                    btn.disabled = false;
                    resolve();
                }
            } catch (error) {
                console.error('Error polling backtest status:', error);
            }
        }, 1000);
    });
}

/**
 * Get selected symbols from checkboxes
 */
function getSelectedSymbols() {
    const symbols = [];
    document.querySelectorAll('.checkbox-item input:checked').forEach(cb => {
        const symbol = cb.nextElementSibling.textContent.trim();
        symbols.push(symbol);
    });
    return symbols;
}

/**
 * Switch between modes
 */
function switchMode(mode) {
    console.log('Switching to mode:', mode);
    currentMode = mode;
    
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`[data-mode="${mode}"]`).classList.add('active');
    
    // Show/hide appropriate views
    const backtestView = document.querySelector('.main-container');
    const paperView = document.getElementById('paperTradingView');
    
    if (mode === 'paper') {
        if (backtestView) backtestView.style.display = 'none';
        if (paperView) paperView.style.display = 'block';
        loadPaperTradingData();
    } else {
        if (backtestView) backtestView.style.display = 'grid';
        if (paperView) paperView.style.display = 'none';
        loadData();
    }
}

/**
 * Load dashboard data from backend API
 */
async function loadData() {
    try {
        console.log('Loading data for mode:', currentMode);
        
        if (currentMode === 'backtest') {
            // Fetch all runs (with cache-busting)
            const runsResponse = await fetch(`${API_BASE}/runs?t=${Date.now()}`);
            if (!runsResponse.ok) {
                console.error('Failed to fetch runs:', runsResponse.status);
                return;
            }
            
            allRuns = await runsResponse.json();
            console.log('Loaded runs:', allRuns.length, allRuns);
            
            if (allRuns.length === 0) {
                console.warn('No runs available');
                return;
            }
            
            // Build run_ids parameter
            const runIds = allRuns.map(r => r.run_id).join(',');
            console.log('Comparing run IDs:', runIds);
            
            // Fetch comparison data with run IDs (with cache-busting)
            const compareUrl = `${API_BASE}/compare?run_ids=${encodeURIComponent(runIds)}&t=${Date.now()}`;
            const compareResponse = await fetch(compareUrl);
            if (!compareResponse.ok) {
                console.error('Failed to fetch comparison:', compareResponse.status);
                const errorText = await compareResponse.text();
                console.error('Error details:', errorText);
                return;
            }
            
            comparisonData = await compareResponse.json();
            console.log('Loaded comparison data:', comparisonData);
            
            // Display charts with real data
            initializeCharts();
        }
        
    } catch (error) {
        console.error('Error loading data:', error);
    }
}

/**
 * Initialize charts with real data from backend
 * Shows exactly 3 lines: Agent (green), buy-and-hold (blue), DJIA (orange)
 */
function initializeCharts() {
    if (!comparisonData || !comparisonData.runs) {
        console.warn('No comparison data available');
        return;
    }
    
    const perfCtx = document.getElementById('performanceChart');
    if (perfCtx && perfCtx.getContext) {
        if (chartInstance) {
            chartInstance.destroy();
        }

        const ctx = perfCtx.getContext('2d');
        
        // Extract runs from comparison data
        const runs = comparisonData.runs;
        if (runs.length === 0) {
            console.warn('No runs to display');
            return;
        }
        
        // Group by agent type and take the first (most recent) of each
        const agentMap = {};
        const timeseriesMap = {};
        
        runs.forEach(run => {
            const agentType = run.agent_name.toLowerCase();
            
            // Store first occurrence of each agent type
            if (!agentMap[agentType]) {
                agentMap[agentType] = run;
                timeseriesMap[agentType] = run.data.map(point => point.equity);
            }
        });
        
        // Build datasets in specific order: Agent, DJIA, buy-and-hold
        const datasets = [];
        const colorMap = {
            'agent': '#4FC3F7',      // Light Blue (Primary focus)
            'djia': '#F5C04A',       // Gold/Yellow (Market reference)
            'buy-and-hold': '#9AA4B2'   // Gray/Silver (Secondary baseline)
        };
        
        const order = ['agent', 'djia', 'buy-and-hold'];
        const timestamps = runs[0].data.map(point => point.timestamp);
        
        order.forEach(agentType => {
            if (agentMap[agentType]) {
                const run = agentMap[agentType];
                const equityPoints = timeseriesMap[agentType];
                const color = colorMap[agentType] || '#4dabf7';
                
                datasets.push({
                    label: run.agent_name,
                    data: equityPoints,
                    borderColor: color,
                    backgroundColor: 'transparent',
                    borderWidth: 2.5,
                    tension: 0.3,
                    fill: false,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                });
                
                console.log(`Added: ${run.agent_name} (${agentType}) - ${equityPoints.length} points`);
            }
        });

        chartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: formatTimestamps(timestamps),
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                plugins: {
                    legend: {
                        display: true,
                        labels: {
                            color: '#e5e7eb',
                            font: { size: 12, weight: '600' },
                            padding: 15,
                            usePointStyle: true,
                            pointStyle: 'line',
                            boxWidth: 12,
                            boxHeight: 2,
                        }
                    },
                    tooltip: {
                        enabled: true,
                        backgroundColor: 'rgba(0, 0, 0, 0.9)',
                        titleColor: '#e5e7eb',
                        bodyColor: '#e5e7eb',
                        borderColor: '#1f2937',
                        borderWidth: 1,
                        padding: 12,
                        displayColors: true,
                        callbacks: {
                            label: function(context) {
                                const value = context.parsed.y;
                                return context.dataset.label + ': $' + value.toFixed(0);
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: false,
                        ticks: {
                            color: '#e5e7eb',
                            font: { size: 11, weight: '500' },
                            callback: function(value) {
                                return '$' + value.toLocaleString();
                            }
                        },
                        grid: {
                            color: '#1f2937',
                            drawBorder: false,
                        },
                    },
                    x: {
                        ticks: {
                            color: '#e5e7eb',
                            font: { size: 11, weight: '500' }
                        },
                        grid: {
                            display: false,
                            drawBorder: false,
                        }
                    }
                }
            }
        });
        
        console.log('✅ Chart initialized - showing 3 lines (Agent, buy-and-hold, DJIA)');
    }
}

/**
 * Format agent label for display
 */
function formatAgentLabel(agentName) {
    const labels = {
        'Agent': 'Selected Agent (Claude)',
        'buy-and-hold': 'Market Baseline (SPY)',
        'equal-weight': 'Equal-Weight Baseline',
        'deepseek': 'DeepSeek Agent'
    };
    return labels[agentName] || agentName;
}

/**
 * Format timestamps for chart labels
 */
function formatTimestamps(timestamps) {
    if (!timestamps || timestamps.length === 0) {
        return generateDateLabels(8);
    }
    
    return timestamps.map(ts => {
        try {
            const date = new Date(ts);
            const month = date.toLocaleString('en-US', { month: 'short' });
            const day = date.getDate();
            return `${month} ${day}`;
        } catch (e) {
            return ts;
        }
    });
}

/**
 * Generate date labels (fallback)
 */
function generateDateLabels(days) {
    const labels = [];
    const startDate = new Date(2026, 3, 15);
    
    for (let i = 0; i < days; i++) {
        const date = new Date(startDate);
        date.setDate(date.getDate() + i);
        const month = date.toLocaleString('en-US', { month: 'short' });
        const day = date.getDate();
        labels.push(`${month} ${day}`);
    }
    
    return labels;
}

/**
 * Format currency
 */
function formatCurrency(value) {
    return '$' + value.toLocaleString('en-US', { 
        minimumFractionDigits: 2,
        maximumFractionDigits: 2 
    });
}

/**
 * Format percentage
 */
function formatPercent(value) {
    return (value * 100).toFixed(2) + '%';
}

/**
 * ============================================================================
 * PAPER TRADING MODE
 * ============================================================================
 */

/**
 * Load all paper trading data in parallel
 */
async function loadPaperTradingData() {
    console.log('📈 Loading paper trading data...');
    
    try {
        // Fetch all data in parallel
        const [accountRes, positionsRes, historyRes, tradesRes] = await Promise.all([
            fetch(`${API_BASE}/paper/account?t=${Date.now()}`),
            fetch(`${API_BASE}/paper/positions?t=${Date.now()}`),
            fetch(`${API_BASE}/paper/portfolio-history?t=${Date.now()}`),
            fetch(`${API_BASE}/paper/trades?t=${Date.now()}`)
        ]);
        
        // Parse responses
        const accountData = accountRes.ok ? await accountRes.json() : null;
        const positionsData = positionsRes.ok ? await positionsRes.json() : null;
        const historyData = historyRes.ok ? await historyRes.json() : null;
        const tradesData = tradesRes.ok ? await tradesRes.json() : null;
        
        console.log('✅ All paper trading data loaded');
        console.log('  Account:', accountData?.account);
        console.log('  Positions:', positionsData?.positions?.length || 0);
        console.log('  Equity curve points:', historyData?.equity_curve?.length || 0);
        console.log('  Recent trades:', tradesData?.trades?.length || 0);
        
        // Display account metrics
        if (accountData?.success && accountData?.account) {
            displayAccountMetrics(accountData.account);
        }
        
        // Display positions
        if (positionsData?.success && positionsData?.positions) {
            displayPositions(positionsData.positions);
        }
        
        // Display equity curve
        if (historyData?.success && historyData?.equity_curve) {
            displayEquityCurve(historyData.equity_curve);
        }
        
        // Display trades
        if (tradesData?.success && tradesData?.trades) {
            displayTrades(tradesData.trades);
        }
        
    } catch (error) {
        console.error('Error loading paper trading data:', error);
        displayPaperError('Failed to load paper trading data: ' + error.message);
    }
}

/**
 * Display account metrics
 */
function displayAccountMetrics(account) {
    console.log('Displaying account metrics:', account);
    
    // Portfolio Value (use equity)
    const portfolioEl = document.getElementById('portfolioValue');
    if (portfolioEl) {
        const equity = parseFloat(account.equity) || parseFloat(account.portfolio_value) || 0;
        portfolioEl.textContent = formatCurrency(equity);
        portfolioEl.className = 'paper-value';
    }
    
    // Cash
    const cashEl = document.getElementById('cashValue');
    if (cashEl) {
        const cash = parseFloat(account.cash) || 0;
        cashEl.textContent = formatCurrency(cash);
        cashEl.className = 'paper-value';
    }
    
    // Buying Power
    const buyingPowerEl = document.getElementById('buyingPowerValue');
    if (buyingPowerEl) {
        const buyingPower = parseFloat(account.buying_power) || 0;
        buyingPowerEl.textContent = formatCurrency(buyingPower);
        buyingPowerEl.className = 'paper-value';
    }
    
    // Day P&L (try to get from account, fallback to 0)
    const dayPnLEl = document.getElementById('dayPnL');
    if (dayPnLEl) {
        const dayPnL = parseFloat(account.day_pnl) || 0;
        const dayPnLPercent = parseFloat(account.equity) ? (dayPnL / parseFloat(account.equity)) * 100 : 0;
        dayPnLEl.textContent = (dayPnL >= 0 ? '+' : '') + formatCurrency(dayPnL);
        dayPnLEl.className = 'paper-value ' + (dayPnL >= 0 ? 'positive' : 'negative');
    }
}

/**
 * Display positions list
 */
function displayPositions(positions) {
    console.log('Displaying positions:', positions.length);
    
    const positionsList = document.getElementById('positionsList');
    if (!positionsList) return;
    
    if (!positions || positions.length === 0) {
        positionsList.innerHTML = '<div class="loading">No open positions</div>';
        return;
    }
    
    positionsList.innerHTML = positions.map(pos => {
        const qty = parseFloat(pos.qty) || 0;
        const currentPrice = parseFloat(pos.current_price) || 0;
        const unrealizedPnL = parseFloat(pos.unrealized_pl) || 0;
        const unrealizedPnLPercent = parseFloat(pos.unrealized_plpc) || 0;
        const isPositive = unrealizedPnL >= 0;
        
        return `
            <div class="position-item">
                <div style="flex: 1;">
                    <div class="position-symbol">${pos.symbol}</div>
                    <div class="position-qty">${Math.abs(qty)} @ $${currentPrice.toFixed(2)}</div>
                </div>
                <div style="text-align: right;">
                    <div class="position-pnl ${isPositive ? 'positive' : 'negative'}">
                        ${isPositive ? '+' : ''}$${unrealizedPnL.toFixed(2)}
                    </div>
                    <div style="font-size: 11px; color: var(--text-muted);">
                        ${isPositive ? '+' : ''}${(unrealizedPnLPercent * 100).toFixed(2)}%
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

/**
 * Display equity curve chart
 */
function displayEquityCurve(equityCurve) {
    console.log('Displaying equity curve with', equityCurve.length, 'points');
    
    const canvas = document.getElementById('paperEquityChart');
    if (!canvas) return;
    
    // Destroy existing chart if any
    if (window.paperChartInstance) {
        window.paperChartInstance.destroy();
    }
    
    const ctx = canvas.getContext('2d');
    
    // Extract timestamps and equity values
    const timestamps = equityCurve.map(point => {
        const date = new Date(point.timestamp);
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    });
    
    const equityValues = equityCurve.map(point => parseFloat(point.equity) || 0);
    
    // Create chart
    window.paperChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: timestamps,
            datasets: [{
                label: 'Portfolio Equity',
                data: equityValues,
                borderColor: '#4FC3F7',
                backgroundColor: 'transparent',
                borderWidth: 2.5,
                fill: false,
                tension: 0.3,
                pointRadius: 0,
                pointHoverRadius: 5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: '#e5e7eb',
                        font: { size: 12, weight: '600' },
                        padding: 15,
                        usePointStyle: true,
                        pointStyle: 'line',
                        boxWidth: 12,
                        boxHeight: 2,
                    }
                },
                tooltip: {
                    enabled: true,
                    backgroundColor: 'rgba(0, 0, 0, 0.9)',
                    titleColor: '#e5e7eb',
                    bodyColor: '#e5e7eb',
                    borderColor: '#1f2937',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: true,
                    callbacks: {
                        label: function(context) {
                            const value = context.parsed.y;
                            return context.dataset.label + ': $' + value.toFixed(0);
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    ticks: {
                        color: '#e5e7eb',
                        font: { size: 11, weight: '500' },
                        callback: (value) => formatCurrency(value)
                    },
                    grid: {
                        color: '#1f2937',
                        drawBorder: false
                    }
                },
                x: {
                    ticks: {
                        color: '#e5e7eb',
                        font: { size: 11, weight: '500' },
                        maxRotation: 45,
                        minRotation: 0
                    },
                    grid: {
                        display: false,
                        drawBorder: false
                    }
                }
            }
        }
    });
}

/**
 * Display recent trades
 */
function displayTrades(trades) {
    console.log('Displaying trades:', trades.length);
    
    const tradesList = document.getElementById('tradesList');
    if (!tradesList) return;
    
    if (!trades || trades.length === 0) {
        tradesList.innerHTML = '<div class="loading">No recent trades</div>';
        return;
    }
    
    // Show latest 20 trades
    const recentTrades = trades.slice(0, 20);
    
    tradesList.innerHTML = recentTrades.map(trade => {
        // Parse timestamp from trade ID or use current time as fallback
        let timeStr = '--:--';
        if (trade.timestamp) {
            const date = new Date(trade.timestamp);
            timeStr = date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
        } else if (trade.id) {
            // Extract timestamp from ID format like "20260430093148799"
            const idParts = trade.id.split('::');
            if (idParts[0].length >= 14) {
                const ts = idParts[0];
                const year = parseInt(ts.substring(0, 4));
                const month = parseInt(ts.substring(4, 6));
                const day = parseInt(ts.substring(6, 8));
                const hour = parseInt(ts.substring(8, 10));
                const minute = parseInt(ts.substring(10, 12));
                timeStr = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
            }
        }
        
        const side = (trade.side || 'hold').toLowerCase();
        const qty = Math.abs(parseFloat(trade.qty) || 0);
        const price = parseFloat(trade.price) || 0;
        
        return `
            <div class="trade-item">
                <div style="flex: 1;">
                    <div class="trade-symbol">${trade.symbol}</div>
                    <div class="trade-qty">${qty} @ $${price.toFixed(2)}</div>
                </div>
                <div style="text-align: right;">
                    <div class="trade-side ${side}">${side.toUpperCase()}</div>
                    <div class="trade-time">${timeStr}</div>
                </div>
            </div>
        `;
    }).join('');
}

/**
 * Refresh paper trading data
 */
async function refreshPaperData() {
    const btn = document.querySelector('.paper-refresh-btn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = '⏳ Refreshing...';
    }
    
    await loadPaperTradingData();
    
    if (btn) {
        btn.disabled = false;
        btn.textContent = '🔄 Refresh';
    }
}

/**
 * Display error message in paper trading view
 */
function displayPaperError(message) {
    console.error('Paper trading error:', message);
    
    const positionsList = document.getElementById('positionsList');
    if (positionsList) {
        positionsList.innerHTML = `<div class="loading" style="color: var(--danger-color);">Error: ${message}</div>`;
    }
}

console.log('Frontend loaded - connecting to API at ' + API_BASE);
