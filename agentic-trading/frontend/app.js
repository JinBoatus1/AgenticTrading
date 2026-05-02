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
    
    // Refresh ticker every 30 seconds
    setInterval(loadMarketTicker, 30000);
});

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
        const changeClass = quote.changePercent >= 0 ? 'positive' : 'negative';
        const changeSign = quote.changePercent >= 0 ? '+' : '';
        
        tickerHTML += `
            <div class="ticker-item">
                <span class="symbol">${quote.symbol}</span>
                <span class="price">${quote.price.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
                <span class="change ${changeClass}">${changeSign}${quote.changePercent.toFixed(2)}%</span>
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
                        // Reload data to display new backtest results
                        await loadData();
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
    
    loadData();
}

/**
 * Load dashboard data from backend API
 */
async function loadData() {
    try {
        console.log('Loading data for mode:', currentMode);
        
        if (currentMode === 'backtest') {
            // Fetch all runs
            const runsResponse = await fetch(`${API_BASE}/runs`);
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
            
            // Fetch comparison data with run IDs
            const compareUrl = `${API_BASE}/compare?run_ids=${encodeURIComponent(runIds)}`;
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
                        position: 'top',
                        labels: {
                            color: '#e5e7eb',
                            font: { size: 12, weight: '500' },
                            padding: 16,
                            usePointStyle: true,
                            pointStyle: 'line',
                            boxWidth: 12,
                            boxHeight: 2,
                        }
                    },
                    tooltip: {
                        enabled: true,
                        backgroundColor: 'rgba(10, 14, 39, 0.95)',
                        titleColor: '#e5e7eb',
                        bodyColor: '#9ca3af',
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
                            color: '#9ca3af',
                            font: { size: 11, family: 'Monaco, Courier New' },
                            callback: function(value) {
                                return '$' + value.toLocaleString();
                            }
                        },
                        grid: {
                            color: '#111827',
                            drawBorder: false,
                        },
                    },
                    x: {
                        ticks: {
                            color: '#9ca3af',
                            font: { size: 11 }
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

console.log('Frontend loaded - connecting to API at ' + API_BASE);
