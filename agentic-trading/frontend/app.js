/**
 * Agentic Trading Lab - Frontend Application
 * Connects to backend API for real data
 */

// ============================================================================
// Session Management (Anonymous Browser Isolation)
// ============================================================================

// Initialize anonymous session on first load
function initSession() {
  let sessionId = localStorage.getItem('trading-session-id');
  if (!sessionId) {
    sessionId = crypto.randomUUID();
    localStorage.setItem('trading-session-id', sessionId);
    console.log('🆕 New anonymous session:', sessionId);
  } else {
    console.log('📋 Restored session:', sessionId);
  }
  window.SESSION_ID = sessionId;
}

// Parse URL config for TensorFlow Playground-style sharing
function loadConfigFromURL() {
  const params = new URLSearchParams(window.location.search);
  return {
    assets: params.get('assets') || 'AAPL,MSFT',
    startDate: params.get('startDate') || '2024-01-01',
    endDate: params.get('endDate') || '2024-12-31',
    agent: params.get('agent') || 'claude',
    benchmark: params.get('benchmark') || 'djia',
    slippage: parseFloat(params.get('slippage') || '0.001'),
    txCost: parseFloat(params.get('txCost') || '10'),
  };
}

// Generate shareable URL with current config
function generateShareURL(config) {
  const params = new URLSearchParams(config);
  return `${window.location.origin}${window.location.pathname}?${params.toString()}`;
}

// ============================================================================
// Robust API Wrapper (auto-attaches X-Session-Id for backtest routes)
// ============================================================================

const API = {
  async request(endpoint, options = {}) {
    const headers = {
      'Content-Type': 'application/json',
      'x-session-id': window.SESSION_ID,  // Lowercase to match CORS allow_headers
      ...options.headers,
    };
    
    try {
      const response = await fetch(endpoint, { 
        ...options, 
        headers,
      });
      
      const contentType = response.headers.get('content-type');
      let data;
      
      if (contentType && contentType.includes('application/json')) {
        data = await response.json();
      } else {
        const text = await response.text();
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${text.substring(0, 200)}`);
        }
        return text;
      }
      
      if (!response.ok) {
        const errorMsg = data.error || data.message || `HTTP ${response.status}`;
        throw new Error(errorMsg);
      }
      
      return data;
    } catch (error) {
      console.error(`❌ API Error [${endpoint}]:`, error.message);
      throw error;
    }
  },
  
  get(endpoint) {
    return this.request(endpoint, { method: 'GET' });
  },
  
  post(endpoint, data) {
    return this.request(endpoint, { method: 'POST', body: JSON.stringify(data) });
  },
};

// ============================================================================
// Use production URL on Vercel, localhost for local development
// ============================================================================

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? 'http://localhost:8000'
    : 'https://agentictrading.onrender.com';

let chartInstance = null;
let currentMode = "backtest";
let allRuns = [];
let comparisonData = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    // Initialize session FIRST (before any API calls)
    initSession();
    const config = loadConfigFromURL();
    window.CURRENT_CONFIG = config;
    console.log('⚙️ Experiment config:', config);
    console.log('📋 Session ID:', window.SESSION_ID);
    
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

    // Setup task type and asset selection logic
    // For Algorithmic Trading: only one asset can be selected
    // For Portfolio Management: multiple assets can be selected
    const assetCheckboxes = document.querySelectorAll('.checkbox-list input[type="checkbox"]');
    assetCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', handleAlgorithmicAssetSelection);
    });

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
        const metrics = await API.get(cacheBustUrl);
        
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
 * Handle asset selection for Algorithmic Trading mode
 * Only allows one asset to be selected at a time
 */
function handleAlgorithmicAssetSelection(e) {
    const isAlgorithmicSelected = document.querySelector('input[name="taskType"][value="algorithmic"]').checked;
    
    if (!isAlgorithmicSelected) return;
    
    if (e.target.checked) {
        // Uncheck all other checkboxes
        document.querySelectorAll('.checkbox-list input[type="checkbox"]').forEach(checkbox => {
            if (checkbox !== e.target) {
                checkbox.checked = false;
            }
        });
    }
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
        return;
    }
    
    const startDate = startDateInput.value;
    const endDate = endDateInput.value;
    
    if (!startDate || !endDate) {
        console.warn('⚠️ Please select both start and end dates');
        return;
    }
    
    console.log(`Running backtest: ${startDate} to ${endDate}`);
    
    const btn = document.querySelector('.run-backtest-btn');
    btn.textContent = '⏳ Running...';
    btn.disabled = true;
    
    try {
        // Call API with session ID
        const data = await API.post(`${API_BASE}/backtest/run?start_date=${startDate}&end_date=${endDate}`, {});
        
        if (!data.success) {
            console.error('❌ Backtest failed:', data.error || 'Unknown error');
            btn.textContent = '❌ Error - Try Again';
            btn.disabled = false;
            setTimeout(() => {
                btn.textContent = '▶ Run Backtest';
            }, 3000);
            return;
        }
        
        console.log('✅ Backtest started:', data.message);
        
        // Poll for status (now session-aware)
        await pollBacktestStatus(btn);
        
    } catch (error) {
        console.error('❌ Error starting backtest:', error.message);
        btn.textContent = '❌ Error - Try Again';
        btn.disabled = false;
        setTimeout(() => {
            btn.textContent = '▶ Run Backtest';
        }, 3000);
    }
}

/**
 * Poll backtest status until complete
 */
async function pollBacktestStatus(btn) {
    const maxAttempts = 120; // 2 minutes with 1-second intervals
    let attempts = 0;
    let isComplete = false;
    
    return new Promise((resolve) => {
        const interval = setInterval(async () => {
            if (isComplete) return; // Prevent re-entry
            
            attempts++;
            
            try {
                // Status endpoint now session-specific
                const status = await API.get(`${API_BASE}/backtest/status`);
                
                if (!status.running) {
                    isComplete = true;
                    clearInterval(interval);
                    
                    if (status.error) {
                        console.error('❌ Backtest error:', status.error);
                    } else if (status.success) {
                        console.log('✅ Backtest completed:', status.message);
                        console.log(`   Found ${status.runs_count} runs`);
                        
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
                    isComplete = true;
                    clearInterval(interval);
                    console.warn('⚠️ Backtest timeout - still running after 2 minutes');
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
    const leaderboardView = document.getElementById('leaderboardView');
    
    if (mode === 'paper') {
        if (backtestView) backtestView.style.display = 'none';
        if (paperView) paperView.style.display = 'block';
        if (leaderboardView) leaderboardView.style.display = 'none';
        loadPaperTradingData();
    } else if (mode === 'contest') {
        if (backtestView) backtestView.style.display = 'none';
        if (paperView) paperView.style.display = 'none';
        if (leaderboardView) leaderboardView.style.display = 'flex';
        loadLeaderboardData();
    } else {
        if (backtestView) backtestView.style.display = 'grid';
        if (paperView) paperView.style.display = 'none';
        if (leaderboardView) leaderboardView.style.display = 'none';
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
            const runsData = await API.get(`${API_BASE}/runs?t=${Date.now()}`);
            
            allRuns = runsData;
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
            const compareData = await API.get(compareUrl);
            
            comparisonData = compareData;
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
                            title: function(context) {
                                if (context.length > 0) {
                                    const dataIndex = context[0].dataIndex;
                                    const timestamp = timestamps[dataIndex];
                                    try {
                                        const date = new Date(timestamp);
                                        const month = date.toLocaleString('en-US', { month: 'short' });
                                        const day = date.getDate();
                                        const hour = String(date.getHours()).padStart(2, '0');
                                        return `${month} ${day} ${hour}:00`;
                                    } catch (e) {
                                        return timestamp;
                                    }
                                }
                                return '';
                            },
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
            await displayEquityCurve(historyData.equity_curve);
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
async function displayEquityCurve(equityCurve) {
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
    
    // Fetch DJIA baseline
    let djiaValues = [];
    try {
        const response = await fetch(`${API_BASE}/paper/baselines?t=${Date.now()}`);
        if (response.ok) {
            const data = await response.json();
            if (data.baselines && data.baselines.djia) {
                djiaValues = data.baselines.djia.map(point => parseFloat(point.equity) || 0);
                console.log('✅ DJIA baseline loaded:', djiaValues.length, 'points');
            }
        }
    } catch (error) {
        console.warn('Could not fetch DJIA baseline:', error.message);
    }
    
    // Build datasets
    const datasets = [{
        label: 'Your Portfolio',
        data: equityValues,
        borderColor: '#4FC3F7',
        backgroundColor: 'transparent',
        borderWidth: 2.5,
        fill: false,
        tension: 0.3,
        pointRadius: 0,
        pointHoverRadius: 5
    }];
    
    // Add DJIA if available
    if (djiaValues.length === equityValues.length) {
        datasets.push({
            label: 'DJIA Index',
            data: djiaValues,
            borderColor: '#F5C04A',
            backgroundColor: 'transparent',
            borderWidth: 2.5,
            fill: false,
            tension: 0.3,
            pointRadius: 0,
            pointHoverRadius: 5
        });
    }
    
    // Create chart
    window.paperChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: timestamps,
            datasets: datasets
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

// ============================================================================
// LEADERBOARD MODE
// ============================================================================

/**
 * Mock leaderboard data for MVP
 */
const MOCK_LEADERBOARD_DATA = [
    {
        rank: 1,
        team_name: 'AlphaForge',
        team_badge: 'LIVE',
        model: 'Claude 3.7 Sonnet + RAG',
        portfolio_value: 112472.93,
        cumulative_return: 0.1247,
        sharpe_ratio: 1.86,
        win_loss_ratio: 1.72,
        rank_cr: 2,
        rank_sr: 1,
        rank_wl: 1,
        final_score: 1.33,
        status: 'Live'
    },
    {
        rank: 2,
        team_name: 'SignalWeaver',
        team_badge: 'LIVE',
        model: 'GPT-4o + Workflow',
        portfolio_value: 109210.58,
        cumulative_return: 0.0921,
        sharpe_ratio: 1.32,
        win_loss_ratio: 1.58,
        rank_cr: 3,
        rank_sr: 2,
        rank_wl: 2,
        final_score: 2.33,
        status: 'Live'
    },
    {
        rank: 3,
        team_name: 'RiskPilot',
        team_badge: 'LIVE',
        model: 'Gemini 2.5 Pro + RL',
        portfolio_value: 106345.11,
        cumulative_return: 0.0634,
        sharpe_ratio: 1.21,
        win_loss_ratio: 1.41,
        rank_cr: 4,
        rank_sr: 3,
        rank_wl: 3,
        final_score: 3.33,
        status: 'Live'
    },
    {
        rank: 4,
        team_name: 'MarketMinds',
        team_badge: 'LIVE',
        model: 'Claude 3.7 Sonnet',
        portfolio_value: 103724.61,
        cumulative_return: 0.0372,
        sharpe_ratio: 0.98,
        win_loss_ratio: 1.36,
        rank_cr: 6,
        rank_sr: 4,
        rank_wl: 4,
        final_score: 4.67,
        status: 'Live'
    },
    {
        rank: 5,
        team_name: 'QuantNebula',
        team_badge: 'LIVE',
        model: 'Llama 4 + FinBERT',
        portfolio_value: 101183.76,
        cumulative_return: 0.0118,
        sharpe_ratio: 0.65,
        win_loss_ratio: 1.29,
        rank_cr: 7,
        rank_sr: 6,
        rank_wl: 5,
        final_score: 6.00,
        status: 'Live'
    },
    {
        rank: 6,
        team_name: 'CashGuard',
        team_badge: 'LIVE',
        model: 'Rule-Based + Sentiment',
        portfolio_value: 99545.23,
        cumulative_return: -0.0045,
        sharpe_ratio: 0.31,
        win_loss_ratio: 1.18,
        rank_cr: 8,
        rank_sr: 7,
        rank_wl: 6,
        final_score: 7.00,
        status: 'Live'
    },
    {
        rank: 7,
        team_name: 'DeltaVector',
        team_badge: 'LIVE',
        model: 'XGBoost + Technicals',
        portfolio_value: 97699.32,
        cumulative_return: -0.0231,
        sharpe_ratio: 0.12,
        win_loss_ratio: 0.93,
        rank_cr: 9,
        rank_sr: 8,
        rank_wl: 7,
        final_score: 8.00,
        status: 'Live'
    },
    {
        rank: 8,
        team_name: 'OpenClaw Baseline',
        team_badge: 'BASELINE',
        model: 'OpenAI Baseline Agent',
        portfolio_value: 96875.12,
        cumulative_return: -0.0312,
        sharpe_ratio: -0.05,
        win_loss_ratio: 0.78,
        rank_cr: 10,
        rank_sr: 9,
        rank_wl: 8,
        final_score: 9.00,
        status: 'Baseline'
    },
    {
        rank: 9,
        team_name: 'DJIA Buy-and-Hold',
        team_badge: 'BASELINE',
        model: 'SPY Buy-and-Hold',
        portfolio_value: 101860.50,
        cumulative_return: 0.0186,
        sharpe_ratio: 0.92,
        win_loss_ratio: 1.15,
        rank_cr: 5,
        rank_sr: 5,
        rank_wl: 10,
        final_score: 6.67,
        status: 'Baseline'
    },
    {
        rank: 10,
        team_name: 'SPY Buy-and-Hold',
        team_badge: 'BASELINE',
        model: 'SPY Buy-and-Hold',
        portfolio_value: 102650.00,
        cumulative_return: 0.0265,
        sharpe_ratio: 1.15,
        win_loss_ratio: 1.25,
        rank_cr: 1,
        rank_sr: 10,
        rank_wl: 9,
        final_score: 6.67,
        status: 'Baseline'
    }
];

let currentLeaderboardFilter = 'all';
let currentLeaderboardMetric = 'final_rank';
let selectedTeam = null;

/**
 * Initialize leaderboard event listeners
 */
function initLeaderboardListeners() {
    // Filter tabs
    document.querySelectorAll('.filter-tab').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.filter-tab').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            currentLeaderboardFilter = e.target.dataset.filter;
            populateLeaderboardTable();
        });
    });

    // Metric tabs
    document.querySelectorAll('.metric-tab').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.metric-tab').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            currentLeaderboardMetric = e.target.dataset.metric;
            // Note: In full implementation, would resort table by this metric
        });
    });
}

/**
 * Load leaderboard data and display
 */
async function loadLeaderboardData() {
    console.log('Loading leaderboard data...');
    
    try {
        // TODO: Replace with actual API call when backend is ready
        // const data = await API.get(`${API_BASE}/api/leaderboard`);
        
        // For now, use mock data
        populateLeaderboardTable();
        initLeaderboardListeners();
        
    } catch (error) {
        console.error('Error loading leaderboard:', error);
        displayLeaderboardError(error.message);
    }
}

/**
 * Populate leaderboard table with data
 */
function populateLeaderboardTable() {
    const tbody = document.getElementById('leaderboardTableBody');
    if (!tbody) return;

    let filtered = MOCK_LEADERBOARD_DATA;

    // Apply filter
    if (currentLeaderboardFilter === 'top10') {
        filtered = filtered.slice(0, 10);
    } else if (currentLeaderboardFilter === 'top20') {
        filtered = filtered.slice(0, 20);
    } else if (currentLeaderboardFilter === 'my-team') {
        // In real app, would filter for user's team
        filtered = filtered.filter(t => t.team_name === 'AlphaForge');
    } else if (currentLeaderboardFilter === 'baselines') {
        filtered = filtered.filter(t => t.status === 'Baseline');
    }

    tbody.innerHTML = filtered.map(team => `
        <tr onclick="selectLeaderboardTeam('${team.team_name}')">
            <td class="rank-cell">${team.rank}</td>
            <td>
                <div class="team-name-badge">
                    ${team.rank <= 3 ? '🏆' : ''}
                    <span>${team.team_name}</span>
                    <span class="team-badge">${team.team_badge}</span>
                </div>
            </td>
            <td>${team.model}</td>
            <td style="text-align: right; font-family: var(--font-mono);">$${formatNumber(team.portfolio_value)}</td>
            <td style="text-align: right;" class="${team.cumulative_return >= 0 ? 'return-positive' : 'return-negative'}">
                <span class="metric-value-text">${(team.cumulative_return * 100).toFixed(2)}%</span>
            </td>
            <td style="text-align: right; font-family: var(--font-mono);">${team.sharpe_ratio.toFixed(2)}</td>
            <td style="text-align: right; font-family: var(--font-mono);">${team.win_loss_ratio.toFixed(2)}</td>
            <td style="text-align: center;">
                <span class="rank-badge ${team.rank_cr <= 3 ? 'top3' : ''}">${team.rank_cr}</span>
                <span class="rank-badge ${team.rank_sr <= 3 ? 'top3' : ''}">${team.rank_sr}</span>
                <span class="rank-badge ${team.rank_wl <= 3 ? 'top3' : ''}">${team.rank_wl}</span>
            </td>
            <td style="text-align: right; font-weight: 600;">${team.final_score.toFixed(2)}</td>
            <td style="text-align: center;">
                <span class="status-badge ${team.status.toLowerCase()}">${team.status}</span>
            </td>
        </tr>
    `).join('');
}

/**
 * Select a team and show details in sidebar
 */
function selectLeaderboardTeam(teamName) {
    selectedTeam = MOCK_LEADERBOARD_DATA.find(t => t.team_name === teamName);
    if (!selectedTeam) return;

    const detailPanel = document.getElementById('selectedTeamDetail');
    if (!detailPanel) return;

    detailPanel.innerHTML = `
        <div class="team-detail-row">
            <span class="team-detail-label">Team Name</span>
            <span class="team-detail-value">${selectedTeam.team_name}</span>
        </div>
        <div class="team-detail-row">
            <span class="team-detail-label">Live Return</span>
            <span class="team-detail-value" style="color: ${selectedTeam.cumulative_return >= 0 ? 'var(--success-color)' : 'var(--danger-color)'};">
                ${(selectedTeam.cumulative_return * 100).toFixed(2)}%
            </span>
        </div>
        <div class="team-detail-row">
            <span class="team-detail-label">Backtest Return</span>
            <span class="team-detail-value">+15.62%</span>
        </div>
        <div class="team-detail-row">
            <span class="team-detail-label">Live/Backtest Gap</span>
            <span class="team-detail-value" style="color: var(--danger-color);">-3.15%</span>
        </div>
        <div class="team-detail-row">
            <span class="team-detail-label">Current Rank</span>
            <span class="team-detail-value">${selectedTeam.rank} / 128</span>
        </div>
        <div class="team-detail-row">
            <span class="team-detail-label">Status</span>
            <span class="team-detail-value">${selectedTeam.status}</span>
        </div>
        <button class="view-details-btn" style="margin-top: 8px; width: 100%;">View Team Analytics →</button>
    `;
}

/**
 * Display error in leaderboard view
 */
function displayLeaderboardError(message) {
    const tbody = document.getElementById('leaderboardTableBody');
    if (tbody) {
        tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; padding: 30px; color: var(--danger-color);">Error: ${message}</td></tr>`;
    }
}

/**
 * Helper: Format large numbers
 */
function formatNumber(num) {
    return num.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

console.log('Frontend loaded - connecting to API at ' + API_BASE);
