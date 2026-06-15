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
    console.log('New anonymous session:', sessionId);
  } else {
    console.log('Restored session:', sessionId);
  }
  window.SESSION_ID = sessionId;
}

// Load default configuration from backend
async function loadDefaults() {
  try {
    const defaultsUrl = API_BASE === 'http://localhost:8000' 
      ? 'http://localhost:8000/config/defaults' 
      : 'https://agentictrading.onrender.com/config/defaults';
    
    console.log('📥 Fetching defaults from:', defaultsUrl);
    
    const response = await fetch(defaultsUrl);
    console.log('🔍 Response status:', response.status, response.statusText);
    
    if (!response.ok) {
      console.warn('⚠️  Failed to fetch defaults:', response.status, response.statusText);
      return;
    }
    
    const defaults = await response.json();
    console.log('📋 Raw defaults response:', defaults);
    
    if (!defaults || defaults.error) {
      console.log('⚠️  Error in defaults:', defaults?.error || 'Unknown error');
      console.log('⚠️  No defaults configured, using URL params instead');
      return;
    }
    
    console.log('✅ Loaded defaults:', defaults);
    
    // Apply defaults to UI
    if (defaults.defaultSettings) {
      const settings = defaults.defaultSettings;
      
      // Set date inputs (using correct ID selectors)
      if (settings.startDate) {
        const startInput = document.getElementById('startDate');
        if (startInput) {
          startInput.value = settings.startDate;
          console.log('✅ Set startDate to:', settings.startDate);
        } else {
          console.warn('⚠️  Could not find #startDate input');
        }
      }
      
      if (settings.endDate) {
        const endInput = document.getElementById('endDate');
        if (endInput) {
          endInput.value = settings.endDate;
          console.log('✅ Set endDate to:', settings.endDate);
        } else {
          console.warn('⚠️  Could not find #endDate input');
        }
      }
      
      // Set asset universe
      if (settings.assetList && settings.assetList.length > 0) {
        if (settings.assetList.length === 7 && settings.assetList.includes('AAPL') && settings.assetList.includes('NVDA')) {
          selectPreset('mag7');
          console.log('✅ Selected Magnificent 7 preset');
        }
      }
      
      console.log('✅ Applied default settings to UI');
    }
    
    // Store defaults globally
    window.DEFAULT_RUNS = defaults.defaultRuns || {};
    console.log('📋 Default run IDs:', window.DEFAULT_RUNS);
    
  } catch (error) {
    console.warn('⚠️  Failed to load defaults:', error.message);
  }
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

const AUTH_TOKEN_KEY = 'auth-token';
const AUTH_USER_KEY = 'auth-user';

const AuthAPI = {
  async request(path, options = {}) {
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    });

    const contentType = response.headers.get('content-type');
    const data = contentType && contentType.includes('application/json')
      ? await response.json()
      : null;

    if (!response.ok) {
      const message = data?.detail || data?.error || `HTTP ${response.status}`;
      throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
    }

    return data;
  },

  signup(email, displayName, password) {
    return this.request('/api/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ email, display_name: displayName, password }),
    });
  },

  login(email, password) {
    return this.request('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  },

  me() {
    return this.request('/api/auth/me', { method: 'GET' });
  },

  logout() {
    return this.request('/api/auth/logout', { method: 'POST' });
  },
};

let authMode = 'login';

function getStoredAuthUser() {
  try {
    const raw = localStorage.getItem(AUTH_USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (error) {
    console.warn('Invalid stored auth user:', error);
    return null;
  }
}

function setAuthState(user, token) {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
  localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
  window.AUTH_USER = user;
  updateAuthUI();
}

function clearAuthState() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(AUTH_USER_KEY);
  window.AUTH_USER = null;
  updateAuthUI();
}

function updateAuthUI() {
  const user = getStoredAuthUser();
  const label = document.getElementById('authUserLabel');
  const openBtn = document.getElementById('authOpenBtn');
  const logoutBtn = document.getElementById('authLogoutBtn');
  if (!label || !openBtn || !logoutBtn) {
    return;
  }

  if (user) {
    label.textContent = user.display_name || user.email;
    label.hidden = false;
    openBtn.hidden = true;
    logoutBtn.hidden = false;
  } else {
    label.hidden = true;
    openBtn.hidden = false;
    logoutBtn.hidden = true;
  }

}

function setAuthMode(mode) {
  authMode = mode;
  const title = document.getElementById('authModalTitle');
  const subtitle = document.getElementById('authModalSubtitle');
  const submitBtn = document.getElementById('authSubmitBtn');
  const switchBtn = document.getElementById('authSwitchBtn');
  const passwordInput = document.getElementById('authPassword');
  const errorEl = document.getElementById('authError');
  const displayNameField = document.getElementById('authDisplayNameField');
  const displayNameInput = document.getElementById('authDisplayName');

  if (title) title.textContent = mode === 'signup' ? 'Sign up' : 'Log in';
  if (subtitle) {
    subtitle.textContent = 'Optional — backtest and paper trading work without an account.';
  }
  if (submitBtn) submitBtn.textContent = mode === 'signup' ? 'Create account' : 'Log in';
  if (switchBtn) {
    switchBtn.textContent = mode === 'signup'
      ? 'Already have an account? Log in'
      : 'Need an account? Sign up';
  }
  if (passwordInput) {
    passwordInput.autocomplete = mode === 'signup' ? 'new-password' : 'current-password';
  }
  if (displayNameField) {
    displayNameField.hidden = mode !== 'signup';
  }
  if (displayNameInput) {
    displayNameInput.required = mode === 'signup';
    if (mode !== 'signup') {
      displayNameInput.value = '';
    }
  }
  if (errorEl) errorEl.hidden = true;
  updateAuthUI();
}

function openAuthModal(mode = 'login') {
  const modal = document.getElementById('authModal');
  if (!modal) return;
  setAuthMode(mode);
  modal.hidden = false;
}

function closeAuthModal() {
  const modal = document.getElementById('authModal');
  const form = document.getElementById('authForm');
  const errorEl = document.getElementById('authError');
  if (modal) modal.hidden = true;
  if (form) form.reset();
  if (errorEl) errorEl.hidden = true;
  setAuthMode('login');
}

async function refreshAuthUser() {
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  if (!token) {
    clearAuthState();
    return;
  }

  try {
    const data = await AuthAPI.me();
    localStorage.setItem(AUTH_USER_KEY, JSON.stringify(data.user));
    window.AUTH_USER = data.user;
    updateAuthUI();
  } catch (error) {
    console.warn('Auth session expired:', error.message);
    clearAuthState();
  }
}

function initAuthUI() {
  const openBtn = document.getElementById('authOpenBtn');
  const logoutBtn = document.getElementById('authLogoutBtn');
  const closeBtn = document.getElementById('authModalClose');
  const backdrop = document.getElementById('authModalBackdrop');
  const switchBtn = document.getElementById('authSwitchBtn');
  const form = document.getElementById('authForm');

  openBtn?.addEventListener('click', () => openAuthModal('login'));
  logoutBtn?.addEventListener('click', async () => {
    try {
      await AuthAPI.logout();
    } catch (error) {
      console.warn('Logout request failed:', error.message);
    } finally {
      clearAuthState();
    }
  });
  closeBtn?.addEventListener('click', closeAuthModal);
  backdrop?.addEventListener('click', closeAuthModal);
  switchBtn?.addEventListener('click', () => {
    setAuthMode(authMode === 'signup' ? 'login' : 'signup');
  });

  form?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const email = document.getElementById('authEmail')?.value.trim();
    const displayName = document.getElementById('authDisplayName')?.value.trim();
    const password = document.getElementById('authPassword')?.value;
    const errorEl = document.getElementById('authError');
    const submitBtn = document.getElementById('authSubmitBtn');

    if (!email || !password) {
      return;
    }

    if (authMode === 'signup' && !displayName) {
      if (errorEl) {
        errorEl.textContent = 'Display name is required for sign up.';
        errorEl.hidden = false;
      }
      return;
    }

    submitBtn.disabled = true;
    if (errorEl) errorEl.hidden = true;

    try {
      const data = authMode === 'signup'
        ? await AuthAPI.signup(email, displayName, password)
        : await AuthAPI.login(email, password);
      setAuthState(data.user, data.token);
      closeAuthModal();
    } catch (error) {
      if (errorEl) {
        errorEl.textContent = error.message;
        errorEl.hidden = false;
      }
    } finally {
      submitBtn.disabled = false;
    }
  });

  window.AUTH_USER = getStoredAuthUser();
  updateAuthUI();
  refreshAuthUser();
}

// Store default run IDs
window.DEFAULT_RUNS = {};

let chartInstance = null;
let currentMode = "backtest";
let allRuns = [];
let comparisonData = null;
let defaultConfig = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    // Initialize session FIRST (before any API calls)
    initSession();
    initAuthUI();
    const config = loadConfigFromURL();
    window.CURRENT_CONFIG = config;
    console.log('⚙️ Experiment config:', config);
    console.log('Session ID:', window.SESSION_ID);
    
    console.log('Dashboard initializing...');

    initMarketEventFeed();
    
    // Setup mode toggle
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            switchMode(e.currentTarget.dataset.mode);
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

    // Setup universe tabs
    document.querySelectorAll('.universe-tab').forEach(tab => {
        tab.addEventListener('click', (e) => handleUniverseTabSwitch(e.target));
    });
    
    // Setup preset cards
    document.getElementById('djiaCard').addEventListener('click', () => selectPreset('djia'));
    document.getElementById('mag7Card').addEventListener('click', () => selectPreset('mag7'));
    
    // Setup custom universe builder
    setupAssetSearch();
    
    const addAssetBtn = document.querySelector('.add-asset-btn');
    if (addAssetBtn) {
        addAssetBtn.addEventListener('click', handleAddAsset);
    }
    
    const searchInput = document.getElementById('assetSearchInput');
    if (searchInput) {
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') handleAddAsset();
        });
    }
    
    // Setup chip removal
    document.querySelectorAll('.chip-remove').forEach(btn => {
        btn.addEventListener('click', (e) => removeChip(e.target.closest('.chip')));
    });

    // Load default configuration if available (after DOM is ready)
    try {
      await loadDefaults();
    } catch (error) {
      console.warn('Failed to load defaults:', error);
    }

    // Load initial data
    await loadData();
    
    // Load market ticker data
    await loadMarketTicker();
    
    // Load performance metrics
    await loadPerformanceMetrics();
    
    // Refresh ticker every 30 seconds
    setInterval(loadMarketTicker, 30000);
    
    console.log('🎯 Dashboard ready. Default runs:', window.DEFAULT_RUNS || 'None configured');
});

/**
 * Load performance metrics from latest backtest run
 */
async function loadPerformanceMetrics() {
    try {
        let metrics = null;

        try {
            const sessionRuns = await API.get(`${API_BASE}/api/backtest/runs?t=${Date.now()}`);
            const myAlgoRuns = sessionRuns.filter(r => r.run_id && r.run_id.startsWith('algo_'));
            if (myAlgoRuns.length) {
                metrics = myAlgoRuns.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))[0];
            }
        } catch (e) {
            console.warn('Could not load session runs for my algo metrics');
        }

        if (!metrics) {
            metrics = await API.get(`${API_BASE}/runs/latest/metrics?t=${Date.now()}`);
        }

        if (!metrics || !metrics.initial_equity) {
            console.warn('Invalid metrics data:', metrics);
            displayNoMetrics();
            return;
        }

        displayPerformanceMetrics(metrics);
        console.log('✅ Performance metrics loaded:', metrics);
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
    let totalReturnPercent = metrics.total_return || 0;
    if (Math.abs(totalReturnPercent) <= 1 && totalReturnPercent !== 0) {
        totalReturnPercent = totalReturnPercent * 100;
    }
    const finalValue = metrics.final_equity || (initialCapital * (1 + totalReturnPercent / 100));
    
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
        let maxDrawdown = metrics.max_drawdown || 0;
        if (Math.abs(maxDrawdown) <= 1 && maxDrawdown !== 0) {
            maxDrawdown = maxDrawdown * 100;
        }
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

const MAG7_TICKER_SYMBOLS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'TSLA', 'META'];

/**
 * Load live market data from Alpaca API (Magnificent 7)
 */
async function loadMarketTicker() {
    try {
        const symbols = MAG7_TICKER_SYMBOLS.join(',');
        const response = await fetch(`${API_BASE}/ticker?symbols=${symbols}`);
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

function buildTickerItemHtml(quote) {
    let changeDisplay = '--';
    let changeClass = '';
    let tooltip = 'title="Data unavailable"';
    let sparkPath = 'M0,8 L5,6 L10,7 L15,4 L20,5 L25,3 L30,5';

    if (quote.changePercent !== null && quote.changePercent !== undefined) {
        const changeSign = quote.changePercent >= 0 ? '+' : '';
        changeDisplay = `${changeSign}${quote.changePercent.toFixed(2)}%`;
        changeClass = quote.changePercent >= 0 ? 'positive' : 'negative';
        tooltip = 'title="Change vs previous close"';
        sparkPath = quote.changePercent >= 0
            ? 'M0,10 L5,8 L10,9 L15,6 L20,7 L25,4 L30,3'
            : 'M0,3 L5,5 L10,4 L15,7 L20,6 L25,9 L30,10';
    }

    const price = quote.price != null
        ? quote.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
        : '--';

    return `
        <div class="ticker-item">
            <span class="symbol">${quote.symbol}</span>
            <span class="price">${price}</span>
            <span class="change ${changeClass}" ${tooltip}>${changeDisplay}</span>
            <svg class="ticker-chart ${changeClass}" viewBox="0 0 30 12" aria-hidden="true">
                <path d="${sparkPath}" stroke="currentColor" fill="none" stroke-width="1"/>
            </svg>
        </div>
    `;
}

/**
 * Update ticker bar with real market data (duplicated for seamless scroll)
 */
function updateTickerDisplay(quotes) {
    const tickerTrack = document.getElementById('tickerTrack');
    if (!tickerTrack) return;

    const order = new Map(MAG7_TICKER_SYMBOLS.map((symbol, index) => [symbol, index]));
    const sortedQuotes = [...quotes].sort(
        (a, b) => (order.get(a.symbol) ?? 99) - (order.get(b.symbol) ?? 99)
    );

    const rowHtml = sortedQuotes.map(buildTickerItemHtml).join('');
    tickerTrack.innerHTML = `<div class="ticker-set">${rowHtml}</div><div class="ticker-set" aria-hidden="true">${rowHtml}</div>`;
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
 * Asset Universe Builder - Preset & Custom
 */

// Asset universe definitions
const ASSET_UNIVERSES = {
    djia: {
        name: 'DJIA',
        assets: ['AAPL', 'MSFT', 'JPM', 'JNJ', 'V', 'PG', 'MRK', 'DIS', 'BA', 'HD', 'KO', 'AXP', 'GE', 'IBM', 'INTC']
    },
    mag7: {
        name: 'Magnificent 7',
        assets: ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'TSLA', 'META']
    }
};

// Popular stocks for autocomplete
// S&P 100 stocks
const POPULAR_STOCKS = {
    'AAPL': 'Apple Inc.',
    'MSFT': 'Microsoft Corp.',
    'GOOGL': 'Alphabet Inc.',
    'AMZN': 'Amazon Inc.',
    'NVDA': 'NVIDIA Corp.',
    'TSLA': 'Tesla Inc.',
    'META': 'Meta Platforms',
    'BRK.B': 'Berkshire Hathaway',
    'JPM': 'JPMorgan Chase',
    'JNJ': 'Johnson & Johnson',
    'V': 'Visa Inc.',
    'WMT': 'Walmart Inc.',
    'PG': 'Procter & Gamble',
    'UNH': 'UnitedHealth Group',
    'HD': 'Home Depot',
    'MA': 'Mastercard',
    'DIS': 'Walt Disney',
    'PYPL': 'PayPal Inc.',
    'ADBE': 'Adobe Inc.',
    'CRM': 'Salesforce Inc.',
    'NFLX': 'Netflix Inc.',
    'BA': 'Boeing Co.',
    'KO': 'Coca-Cola Co.',
    'IBM': 'IBM Corp.',
    'INTC': 'Intel Corp.',
    'AMD': 'Advanced Micro Devices',
    'CSCO': 'Cisco Systems',
    'QCOM': 'Qualcomm',
    'VZ': 'Verizon Communications',
    'T': 'AT&T Inc.',
    'CAT': 'Caterpillar Inc.',
    'HON': 'Honeywell International',
    'MMM': '3M Company',
    'GE': 'General Electric',
    'AXP': 'American Express',
    'MCD': 'McDonalds Corp.',
    'PEP': 'PepsiCo Inc.',
    'KMB': 'Kimberly-Clark',
    'CL': 'Colgate-Palmolive',
    'SYK': 'Stryker Corporation',
    'LMT': 'Lockheed Martin',
    'PLD': 'Prologis Inc.',
    'AMT': 'American Tower',
    'PSA': 'Public Storage',
    'O': 'Realty Income',
    'DUK': 'Duke Energy',
    'SO': 'Southern Company',
    'NEE': 'NextEra Energy',
    'SCHW': 'Charles Schwab',
    'SPGI': 'S&P Global',
    'MCK': 'McKesson Corp.',
    'BX': 'Blackstone Inc.',
    'AIG': 'American International Group',
    'GD': 'General Dynamics',
    'LUV': 'Southwest Airlines',
    'UAL': 'United Airlines',
    'DAL': 'Delta Air Lines',
    'AAL': 'American Airlines',
    'COST': 'Costco Wholesale',
    'ABBV': 'AbbVie Inc.',
    'GILD': 'Gilead Sciences',
    'ISRG': 'Intuitive Surgical',
    'VEEV': 'Veeva Systems',
    'CRWD': 'CrowdStrike',
    'MU': 'Micron Technology',
    'AVGO': 'Broadcom Inc.',
    'INTU': 'Intuit Inc.',
    'AMAT': 'Applied Materials',
    'LRCX': 'Lam Research',
    'SNPS': 'Synopsys',
    'CDNS': 'Cadence Design',
    'NOW': 'ServiceNow',
    'SPLK': 'Splunk',
    'OKTA': 'Okta Inc.',
    'ZM': 'Zoom Video',
    'DOCU': 'DocuSign',
    'TWLO': 'Twilio',
    'DDOG': 'Datadog',
    'SNOW': 'Snowflake Inc.',
};

let selectedUniverse = 'djia'; // Default

function handleUniverseTabSwitch(tab) {
    const tabName = tab.dataset.tab;
    
    // Update tab buttons
    document.querySelectorAll('.universe-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    
    // Update content visibility explicitly
    const builtinTab = document.getElementById('builtinTab');
    const customTab = document.getElementById('customTab');
    
    if (tabName === 'builtin') {
        builtinTab.classList.add('active');
        builtinTab.style.display = 'block';
        customTab.classList.remove('active');
        customTab.style.display = 'none';
    } else {
        builtinTab.classList.remove('active');
        builtinTab.style.display = 'none';
        customTab.classList.add('active');
        customTab.style.display = 'block';
    }
    
    console.log(`Switched to ${tabName} universe tab`);
    notifyAssetUniverseChanged();
}

function selectPreset(preset) {
    if (!ASSET_UNIVERSES[preset]) {
        preset = 'djia';
    }

    selectedUniverse = preset;

    document.getElementById('djiaCard').classList.remove('selected');
    document.getElementById('mag7Card').classList.remove('selected');

    if (preset === 'djia') {
        document.getElementById('djiaCard').classList.add('selected');
        document.getElementById('djiaCard').querySelector('.preset-btn').textContent = 'Selected';
        document.getElementById('mag7Card').querySelector('.preset-btn').textContent = 'Select';
    } else if (preset === 'mag7') {
        document.getElementById('mag7Card').classList.add('selected');
        document.getElementById('mag7Card').querySelector('.preset-btn').textContent = 'Selected';
        document.getElementById('djiaCard').querySelector('.preset-btn').textContent = 'Select';
    }

    const universeData = ASSET_UNIVERSES[preset];
    console.log(`✅ Selected preset: ${universeData.name}`);
    notifyAssetUniverseChanged();
}

function handleAddAsset() {
    const input = document.getElementById('assetSearchInput');
    const ticker = input.value.trim().toUpperCase();
    
    if (!ticker) return;
    
    // Validate ticker (only alphanumeric, 1-5 chars)
    if (!/^[A-Z0-9]{1,5}$/.test(ticker)) {
        console.warn(`⚠️ Invalid ticker: ${ticker}`);
        return;
    }
    
    // Check if already added
    if (document.querySelector(`[data-ticker="${ticker}"]`)) {
        console.warn(`⚠️ ${ticker} already in custom universe`);
        input.value = '';
        return;
    }
    
    // Create chip
    const chip = document.createElement('div');
    chip.className = 'chip';
    chip.dataset.ticker = ticker;
    const companyName = POPULAR_STOCKS[ticker] || ticker;
    chip.innerHTML = `<span class="chip-ticker">${ticker}</span> <span class="chip-remove">×</span>`;
    chip.title = companyName;
    
    // Add remove listener
    chip.querySelector('.chip-remove').addEventListener('click', () => removeChip(chip));
    
    // Add to container
    document.getElementById('selectedChips').appendChild(chip);
    input.value = '';
    
    console.log(`✅ Added ${ticker} to custom universe`);
    notifyAssetUniverseChanged();
}

function removeChip(chipEl) {
    const ticker = chipEl.dataset.ticker;
    chipEl.remove();
    console.log(`❌ Removed ${ticker} from custom universe`);
    notifyAssetUniverseChanged();
}

function notifyAssetUniverseChanged() {
    document.dispatchEvent(new CustomEvent('asset-universe-changed'));
}

function initMarketEventFeed() {
    const container = document.getElementById('marketEventsFeed');
    if (!container) {
        console.warn('Market events container not found');
        return null;
    }
    if (!window.MarketEventFeed) {
        console.warn('MarketEventFeed module not loaded — check market-events/*.js script paths');
        return null;
    }

    window.marketEventFeed = new window.MarketEventFeed({
        container,
        getSelectedAssets
    });
    return window.marketEventFeed;
}

/**
 * Show autocomplete suggestions as user types
 */
function setupAssetSearch() {
    const searchInput = document.getElementById('assetSearchInput');
    let autocompleteDiv = null;
    
    if (!searchInput) return;
    
    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.trim().toUpperCase();
        
        // Remove existing autocomplete
        if (autocompleteDiv) autocompleteDiv.remove();
        
        if (query.length === 0) return;
        
        // Filter matching stocks
        const matches = Object.entries(POPULAR_STOCKS)
            .filter(([ticker, name]) => 
                ticker.includes(query) || name.toUpperCase().includes(query)
            )
            .slice(0, 5); // Limit to 5 suggestions
        
        if (matches.length === 0) return;
        
        // Create autocomplete dropdown
        autocompleteDiv = document.createElement('div');
        autocompleteDiv.className = 'asset-autocomplete';
        
        matches.forEach(([ticker, name]) => {
            const option = document.createElement('div');
            option.className = 'autocomplete-option';
            option.innerHTML = `<strong>${ticker}</strong> - ${name}`;
            option.addEventListener('click', () => {
                searchInput.value = ticker;
                handleAddAsset();
                if (autocompleteDiv) autocompleteDiv.remove();
            });
            autocompleteDiv.appendChild(option);
        });
        
        const inputGroup = searchInput.closest('.search-input-group');
        inputGroup.appendChild(autocompleteDiv);
    });
    
    // Hide autocomplete when clicking elsewhere
    document.addEventListener('click', (e) => {
        if (e.target !== searchInput && autocompleteDiv) {
            autocompleteDiv.remove();
            autocompleteDiv = null;
        }
    });
}

/**
 * Run backtest
 */
/**
 * Get selected assets based on Preset or Custom tab
 */
function getSelectedAssets() {
    const builtinTab = document.getElementById('builtinTab');
    const isBuiltin = builtinTab.classList.contains('active');
    
    if (!isBuiltin) {
        // Get chips from custom universe
        const chips = document.querySelectorAll('#selectedChips .chip');
        const assets = Array.from(chips).map(chip => chip.dataset.ticker);
        return assets.length > 0 ? assets : ['AAPL']; // Default fallback
    } else {
        // Get assets from selected built-in universe
        return ASSET_UNIVERSES[selectedUniverse].assets;
    }
}

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
    
    // Get selected assets and model
    const assets = getSelectedAssets();
    const modelSelect = document.getElementById('modelSelect');
    const model = modelSelect ? modelSelect.value : 'claude-haiku-4.5';
    
    console.log(`Running backtest: ${startDate} to ${endDate}`);
    console.log(`Assets: ${assets.join(', ')}`);
    console.log(`Model: ${model}`);
    
    const btn = document.querySelector('.run-backtest-btn');
    btn.textContent = '⏳ Running...';
    btn.disabled = true;
    
    try {
        // Call API with session ID, assets, and model
        const params = new URLSearchParams({
            start_date: startDate,
            end_date: endDate,
            assets: assets.join(','),
            model: model
        });
        const data = await API.post(`${API_BASE}/backtest/run?${params.toString()}`, {});
        
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
    const activeBtn = document.querySelector(`[data-mode="${mode}"]`);
    if (activeBtn) activeBtn.classList.add('active');
    
    const backtestView = document.querySelector('.main-container');
    const paperView = document.getElementById('paperTradingView');
    const myAlgoView = document.getElementById('myTradingAlgoView');
    const leaderboardView = document.getElementById('leaderboardView');
    
    const hideAll = () => {
        if (backtestView) backtestView.style.display = 'none';
        if (paperView) paperView.style.display = 'none';
        if (myAlgoView) myAlgoView.style.display = 'none';
        if (leaderboardView) leaderboardView.style.display = 'none';
    };
    
    if (mode === 'paper') {
        hideAll();
        if (paperView) paperView.style.display = 'block';
        loadPaperTradingData();
    } else if (mode === 'my-algo') {
        hideAll();
        if (myAlgoView) myAlgoView.style.display = 'block';
        loadMyTradingAlgoPage();
    } else if (mode === 'contest') {
        hideAll();
        if (leaderboardView) leaderboardView.style.display = 'flex';
        loadLeaderboardData();
    } else {
        hideAll();
        if (backtestView) backtestView.style.display = 'grid';
        loadData();
    }
}

function isMyAlgoRun(run) {
    return run && run.run_id && String(run.run_id).startsWith('algo_');
}

function findLatestRunByAgent(runs, agentName) {
    const matched = runs.filter(r => r.agent_name === agentName);
    if (!matched.length) return null;
    return matched.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))[0];
}

/**
 * Load dashboard data from backend API
 */
async function loadData() {
    try {
        console.log('Loading data for mode:', currentMode);
        
        if (currentMode === 'backtest') {
            let sessionRuns = [];
            try {
                sessionRuns = await API.get(`${API_BASE}/api/backtest/runs?t=${Date.now()}`);
            } catch (e) {
                console.warn('Session runs unavailable:', e.message);
            }

            const myAlgoRuns = sessionRuns.filter(isMyAlgoRun);
            const latestMyAlgo = myAlgoRuns.length
                ? myAlgoRuns.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))[0]
                : null;

            if (latestMyAlgo) {
                window.MY_ALGO_RUN_ID = latestMyAlgo.run_id;
            } else {
                window.MY_ALGO_RUN_ID = null;
            }

            allRuns = await API.get(`${API_BASE}/runs?t=${Date.now()}`);
            console.log('Loaded runs:', allRuns.length);

            if (allRuns.length === 0 && !latestMyAlgo) {
                console.warn('No runs available');
                return;
            }

            let runIds;
            if (latestMyAlgo) {
                const buyhold = findLatestRunByAgent(allRuns, 'buy-and-hold');
                const djia = findLatestRunByAgent(allRuns, 'DJIA');
                runIds = [latestMyAlgo.run_id, djia?.run_id, buyhold?.run_id].filter(Boolean).join(',');
                console.log('My Algo compare IDs:', runIds);
            } else {
                runIds = allRuns.map(r => r.run_id).join(',');
            }

            if (!runIds) {
                console.warn('No run IDs to compare');
                return;
            }

            const compareUrl = `${API_BASE}/compare?run_ids=${encodeURIComponent(runIds)}&t=${Date.now()}`;
            comparisonData = await API.get(compareUrl);
            console.log('Loaded comparison data:', comparisonData);

            initializeCharts();
            await loadPerformanceMetrics();
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
            let agentType;
            if (isMyAlgoRun(run)) {
                agentType = 'my-algo';
            } else {
                agentType = run.agent_name.toLowerCase();
            }
            
            if (!agentMap[agentType]) {
                agentMap[agentType] = run;
                timeseriesMap[agentType] = run.data.map(point => point.equity);
            }
        });
        
        const datasets = [];
        const colorMap = {
            'my-algo': '#fbbf24',
            'agent': '#4FC3F7',
            'djia': '#F5C04A',
            'buy-and-hold': '#9AA4B2'
        };
        
        const order = agentMap['my-algo']
            ? ['my-algo', 'djia', 'buy-and-hold']
            : ['agent', 'djia', 'buy-and-hold'];
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
        
        console.log('✅ Chart initialized -', order.filter(t => agentMap[t]).join(', '));
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
    console.log('Loading paper trading data...');
    
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
        btn.textContent = 'Refresh';
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
 * Generate mock equity curve data for teams
 * Each team has daily portfolio value data from Sept 1 - Oct 31, 2026
 */
function generateMockEquityCurveData() {
    // Competition window: Sep 1 - Oct 30, 2026 (62 trading days)
    // Starting with $100k on Sep 1
    // Trading days: Mon-Fri, Sep 1, 2026 (Monday) through Oct 30, 2026 (Friday)
    const days = [];
    const dates = [];
    
    // Trading days in the Sep 1 - Oct 30, 2026 window (all weekdays)
    const tradingDays = [
        '2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04',
        '2026-09-07', '2026-09-08', '2026-09-09', '2026-09-10', '2026-09-11',
        '2026-09-14', '2026-09-15', '2026-09-16', '2026-09-17', '2026-09-18',
        '2026-09-21', '2026-09-22', '2026-09-23', '2026-09-24', '2026-09-25',
        '2026-09-28', '2026-09-29', '2026-09-30',
        '2026-10-01', '2026-10-02', '2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09',
        '2026-10-12', '2026-10-13', '2026-10-14', '2026-10-15', '2026-10-16',
        '2026-10-19', '2026-10-20', '2026-10-21', '2026-10-22', '2026-10-23',
        '2026-10-26', '2026-10-27', '2026-10-28', '2026-10-29', '2026-10-30'
    ];
    
    for (const day of tradingDays) {
        days.push(day);
        dates.push(new Date(day + 'T00:00:00Z'));
    }
    
    // Define each team's growth trajectory
    const teamTrajectories = {
        'AlphaForge': {
            initialValue: 100000,
            volatility: 0.008,
            trend: 0.0002,
            peakDay: 32,
            drawdownDays: [[35, 40]],
            color: '#3b82f6'
        },
        'SignalWeaver': {
            initialValue: 100000,
            volatility: 0.010,
            trend: 0.00015,
            peakDay: 28,
            drawdownDays: [[33, 40]],
            color: '#f97316'
        },
        'RiskPilot': {
            initialValue: 100000,
            volatility: 0.009,
            trend: 0.0001,
            peakDay: 25,
            drawdownDays: [[31, 37]],
            color: '#06b6d4'
        },
        'MarketMinds': {
            initialValue: 100000,
            volatility: 0.011,
            trend: 0.00005,
            peakDay: 27,
            drawdownDays: [[29, 42]],
            color: '#8b5cf6'
        },
        'QuantNebula': {
            initialValue: 100000,
            volatility: 0.012,
            trend: 0.000020,
            peakDay: 23,
            drawdownDays: [[24, 45]],
            color: '#ec4899'
        },
        'CashGuard': {
            initialValue: 100000,
            volatility: 0.006,
            trend: -0.000008,
            peakDay: 14,
            drawdownDays: [[17, 45]],
            color: '#84cc16'
        },
        'DeltaVector': {
            initialValue: 100000,
            volatility: 0.013,
            trend: -0.00005,
            peakDay: 18,
            drawdownDays: [[21, 45]],
            color: '#f43f5e'
        },
        'OpenClaw Baseline': {
            initialValue: 100000,
            volatility: 0.009,
            trend: -0.00008,
            peakDay: 14,
            drawdownDays: [[17, 45]],
            color: '#a1a1a1',
            isBaseline: true
        },
        'DJIA Buy-and-Hold': {
            initialValue: 100000,
            volatility: 0.007,
            trend: 0.000035,
            peakDay: 38,
            drawdownDays: [[14, 17]],
            color: '#9ca3af',
            isBaseline: true
        },
        'SPY Buy-and-Hold': {
            initialValue: 100000,
            volatility: 0.0065,
            trend: 0.00005,
            peakDay: 40,
            drawdownDays: [[12, 15]],
            color: '#d1d5db',
            isBaseline: true
        }
    };
    
    // Generate curves using seeded random walk (stable across page loads)
    const curves = {};
    for (const [teamName, config] of Object.entries(teamTrajectories)) {
        const curve = [];
        let value = config.initialValue;
        let seed = teamName.split('').reduce((s, c) => s + c.charCodeAt(0), 0);
        const rng = () => {
            seed = (seed * 9301 + 49297) % 233280;
            return seed / 233280;
        };

        for (let i = 0; i < days.length; i++) {
            if (i === 0) {
                curve.push(config.initialValue);
                continue;
            }

            const random = (rng() - 0.5) * 2;
            const drift = config.trend * config.initialValue;
            const volatilityComponent = random * config.volatility * value;

            let drawdownFactor = 1.0;
            for (const [start, end] of config.drawdownDays) {
                if (i >= start && i <= end) {
                    drawdownFactor *= (1 - (i - start) / (end - start) * 0.008);
                }
            }

            value *= (1 + drift / value + volatilityComponent / value) * drawdownFactor;
            curve.push(Math.max(value, config.initialValue * 0.9));
        }

        curves[teamName] = curve;
    }
    
    return { dates, days, curves, trajectories: teamTrajectories };
}

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
        rank_cr: 1,
        rank_sr: 1,
        rank_wl: 1,
        final_score: 1.00,
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
        rank_cr: 2,
        rank_sr: 2,
        rank_wl: 2,
        final_score: 2.00,
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
        rank_cr: 3,
        rank_sr: 3,
        rank_wl: 3,
        final_score: 3.00,
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
        rank_cr: 4,
        rank_sr: 4,
        rank_wl: 4,
        final_score: 4.00,
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
        rank_cr: 5,
        rank_sr: 5,
        rank_wl: 5,
        final_score: 5.00,
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
        rank_cr: 6,
        rank_sr: 6,
        rank_wl: 6,
        final_score: 6.00,
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
        rank_cr: 7,
        rank_sr: 7,
        rank_wl: 7,
        final_score: 7.00,
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
        rank_cr: 8,
        rank_sr: 8,
        rank_wl: 8,
        final_score: 8.00,
        status: 'Baseline'
    },
    {
        rank: 9,
        team_name: 'DJIA Buy-and-Hold',
        team_badge: 'BASELINE',
        model: 'Buy-and-Hold Baseline',
        portfolio_value: 101860.50,
        cumulative_return: 0.0186,
        sharpe_ratio: 0.92,
        win_loss_ratio: 1.15,
        rank_cr: 9,
        rank_sr: 9,
        rank_wl: 9,
        final_score: 9.00,
        status: 'Baseline'
    },
    {
        rank: 10,
        team_name: 'SPY Buy-and-Hold',
        team_badge: 'BASELINE',
        model: 'Buy-and-Hold Baseline',
        portfolio_value: 102650.00,
        cumulative_return: 0.0265,
        sharpe_ratio: 1.15,
        win_loss_ratio: 1.25,
        rank_cr: 10,
        rank_sr: 10,
        rank_wl: 10,
        final_score: 10.00,
        status: 'Baseline'
    }
];

let currentLeaderboardFilter = 'all';
let currentLeaderboardMetric = 'final_rank';
let selectedTeam = null;
let equityCurvesData = null;
let equityCurvesChartInstance = null;
let currentChartView = 'cumulative';
let myAlgoInitialized = false;
let leaderboardListenersInitialized = false;

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
    
    // Chart view controls
    initChartControls();
}

/**
 * Load leaderboard data and display
 */
async function loadLeaderboardData() {
    console.log('Loading leaderboard data (mock only)...');
    
    try {
        equityCurvesData = generateMockEquityCurveData();
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

/**
 * Render equity curves chart with Chart.js
 */
async function renderEquityCurvesChart() {
    if (!equityCurvesData) return;
    
    const canvas = document.getElementById('equityCurvesChart');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const { days, curves } = equityCurvesData;
    
    const datasets = Object.entries(curves).map(([teamName, curveValues]) => {
        const config = getTeamColorConfig(teamName);
        const data = transformChartData(curveValues, currentChartView);
        const trajectoryConfig = equityCurvesData.trajectories[teamName];
        const isBaseline = trajectoryConfig && trajectoryConfig.isBaseline;
        
        return {
            label: teamName,
            data: data,
            borderColor: config.color,
            backgroundColor: config.bgColor,
            borderWidth: 2.5,
            borderDash: isBaseline ? [5, 5] : [],
            pointRadius: 0,
            pointHoverRadius: 5,
            tension: 0.3,
            fill: false,
            spanGaps: false,
            hoverBorderWidth: 4,
            hoverBorderColor: config.color,
        };
    });
    
    if (equityCurvesChartInstance) {
        equityCurvesChartInstance.destroy();
    }
    
    equityCurvesChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: days,
            datasets: datasets,
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
                    position: 'bottom',
                    labels: {
                        color: '#e5e7eb',  // Brighter text for better contrast
                        font: {
                            size: 12,
                            weight: '600',
                        },
                        padding: 15,
                        usePointStyle: true,
                        pointStyle: 'circle',
                        boxWidth: 8,
                    },
                    onClick: (e, legendItem, legend) => {
                        // Allow toggling dataset visibility
                        const index = legendItem.datasetIndex;
                        const chart = legend.chart;
                        const meta = chart.getDatasetMeta(index);
                        meta.hidden = !meta.hidden;
                        chart.update();
                    },
                },
                tooltip: {
                    enabled: true,
                    mode: 'index',
                    intersect: false,
                    backgroundColor: 'rgba(5, 7, 20, 0.95)',
                    borderColor: '#404854',
                    borderWidth: 2,
                    titleColor: '#e5e7eb',
                    bodyColor: '#d1d5db',
                    padding: 12,
                    cornerRadius: 6,
                    titleFont: {
                        size: 13,
                        weight: 'bold',
                    },
                    bodyFont: {
                        size: 12,
                    },
                    callbacks: {
                        title: function(context) {
                            return 'Date: ' + context[0].label;
                        },
                        label: function(context) {
                            const value = context.parsed.y;
                            if (currentChartView === 'cumulative') {
                                return context.dataset.label + ': ' + (value * 100).toFixed(2) + '%';
                            } else if (currentChartView === 'absolute') {
                                return context.dataset.label + ': $' + formatNumber(value);
                            } else {
                                return context.dataset.label + ': ' + (value * 100).toFixed(2) + '%';
                            }
                        },
                    },
                },
            },
            scales: {
                x: {
                    display: true,
                    grid: {
                        color: 'rgba(31, 41, 55, 0.8)',
                        drawBorder: false,
                    },
                    ticks: {
                        color: '#9ca3af',
                        font: { size: 11, weight: '500' },
                        maxRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 10,
                    },
                },
                y: {
                    display: true,
                    grid: {
                        color: 'rgba(31, 41, 55, 0.8)',  // Brighter grid lines
                        drawBorder: false,
                    },
                    ticks: {
                        color: '#9ca3af',  // Brighter axis labels
                        font: {
                            size: 11,
                            weight: '500',
                        },
                        callback: function(value) {
                            if (currentChartView === 'cumulative' || currentChartView === 'drawdown') {
                                return (value * 100).toFixed(1) + '%';
                            } else {
                                return '$' + (value / 1000).toFixed(0) + 'k';
                            }
                        },
                    },
                    beginAtZero: currentChartView === 'drawdown',
                },
            },
        },
    });
    
    console.log('✅ Equity curves chart rendered');
}

/**
 * Get team color configuration - Bright colors for dark background (10jqka inspired)
 */
function getTeamColorConfig(teamName) {
    const colors = {
        'AlphaForge': { color: '#60a5fa', bgColor: 'rgba(96, 165, 250, 0.15)' },
        'SignalWeaver': { color: '#fb923c', bgColor: 'rgba(251, 147, 60, 0.15)' },
        'RiskPilot': { color: '#22d3ee', bgColor: 'rgba(34, 211, 238, 0.15)' },
        'MarketMinds': { color: '#a78bfa', bgColor: 'rgba(167, 139, 250, 0.15)' },
        'QuantNebula': { color: '#f472b6', bgColor: 'rgba(244, 114, 182, 0.15)' },
        'CashGuard': { color: '#bef264', bgColor: 'rgba(190, 242, 100, 0.15)' },
        'DeltaVector': { color: '#ff6b7a', bgColor: 'rgba(255, 107, 122, 0.15)' },
        'OpenClaw Baseline': { color: '#a1a1a1', bgColor: 'rgba(161, 161, 161, 0.15)' },
        'DJIA Buy-and-Hold': { color: '#9ca3af', bgColor: 'rgba(156, 163, 175, 0.15)' },
        'SPY Buy-and-Hold': { color: '#d1d5db', bgColor: 'rgba(209, 213, 219, 0.15)' },
    };
    return colors[teamName] || { color: '#818cf8', bgColor: 'rgba(129, 140, 248, 0.15)' };
}

/**
 * Transform chart data based on view type
 */
function transformChartData(curveValues, viewType) {
    const initialValue = 100000;
    
    if (viewType === 'cumulative') {
        // Return percentage change from start
        return curveValues.map(v => (v - initialValue) / initialValue);
    } else if (viewType === 'absolute') {
        // Return absolute portfolio value
        return curveValues;
    } else if (viewType === 'drawdown') {
        // Return max drawdown from peak
        let maxValue = initialValue;
        return curveValues.map(v => {
            if (v > maxValue) maxValue = v;
            return (v - maxValue) / maxValue; // Negative for drawdowns
        });
    }
    return curveValues;
}

/**
 * Initialize chart view controls
 */
function initChartControls() {
    // View toggle (% or $)
    document.querySelectorAll('.view-toggle-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            document.querySelectorAll('.view-toggle-btn').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            currentChartView = e.target.dataset.view;
            await renderEquityCurvesChart();
        });
    });
    
    // Legacy support for old buttons (if they exist)
    document.querySelectorAll('.chart-view-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            document.querySelectorAll('.chart-view-btn').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            currentChartView = e.target.dataset.view;
            await renderEquityCurvesChart();
        });
    });
}

/**
 * Populate leaderboard table with data
 */
function populateLeaderboardTable() {
    const tbody = document.getElementById('leaderboardTableBody');
    if (!tbody) return;

    let filtered = MOCK_LEADERBOARD_DATA;

    if (currentLeaderboardFilter === 'top10') {
        filtered = filtered.slice(0, 10);
    } else if (currentLeaderboardFilter === 'top20') {
        filtered = filtered.slice(0, 20);
    } else if (currentLeaderboardFilter === 'my-team') {
        filtered = filtered.filter(t => t.team_name === 'AlphaForge');
    } else if (currentLeaderboardFilter === 'baselines') {
        filtered = filtered.filter(t => t.status === 'Baseline');
    }

    tbody.innerHTML = filtered.map(team => `
        <tr onclick="selectLeaderboardTeam('${team.team_name}')">
            <td class="rank-cell">${team.rank}</td>
            <td>
                <div class="team-name-badge">
                    ${team.rank <= 3 ? '[CHAMPION]' : ''}
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

// ============================================================================
// My Trading Algo
// ============================================================================

const ALGO_BLOCK_FIELDS = {
    info_retrieval: 'blockInfoRetrieval',
    signal_transfer: 'blockSignalTransfer',
    trading_algorithm: 'blockTradingAlgorithm',
    stop_loss_take_profit: 'blockStopLoss',
};

const DEFAULT_ALGO_BLOCKS = {
    info_retrieval: "Monitor Trump's Twitter / X feed; capture tweets and sentiment signals",
    signal_transfer: 'AI auto-selects target stocks (single name or basket); map tickers from tweet semantics',
    trading_algorithm: 'No execution algo: buy whatever Trump mentions (immediate market follow)',
    stop_loss_take_profit: 'Stop loss: exit if position down 5%; take profit: hold after +20%; daily stop: exit if down 5% intraday',
};

function getAlgoBlocksFromUI() {
    return {
        info_retrieval: document.getElementById('blockInfoRetrieval')?.value?.trim() || '',
        signal_transfer: document.getElementById('blockSignalTransfer')?.value?.trim() || '',
        trading_algorithm: document.getElementById('blockTradingAlgorithm')?.value?.trim() || '',
        stop_loss_take_profit: document.getElementById('blockStopLoss')?.value?.trim() || '',
    };
}

function setAlgoBlocksToUI(blocks) {
    for (const [key, fieldId] of Object.entries(ALGO_BLOCK_FIELDS)) {
        const el = document.getElementById(fieldId);
        if (el && blocks[key] !== undefined) {
            el.value = blocks[key];
        }
    }
}

function highlightAlgoBlocks(updatedKeys) {
    document.querySelectorAll('.algo-block-card').forEach(card => card.classList.remove('highlight'));
    if (!updatedKeys?.length) return;
    for (const key of updatedKeys) {
        const card = document.querySelector(`.algo-block-card[data-block="${key}"]`);
        if (card) card.classList.add('highlight');
    }
    setTimeout(() => {
        document.querySelectorAll('.algo-block-card').forEach(card => card.classList.remove('highlight'));
    }, 2500);
}

function appendAlgoChatMessage(text, role = 'bot') {
    const container = document.getElementById('algoChatMessages');
    if (!container) return;
    const row = document.createElement('div');
    row.className = `algo-chat-msg ${role}`;
    const bubble = document.createElement('div');
    bubble.className = 'algo-chat-bubble';
    bubble.innerHTML = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    row.appendChild(bubble);
    container.appendChild(row);
    container.scrollTop = container.scrollHeight;
}

async function loadMyTradingAlgoPage() {
    if (!myAlgoInitialized) {
        initMyTradingAlgoUI();
        myAlgoInitialized = true;
    }
    try {
        const res = await API.get(`${API_BASE}/api/algo/defaults`);
        if (res.blocks) {
            setAlgoBlocksToUI(res.blocks);
        }
        if (res.backtest_window) {
            window.ALGO_BACKTEST_WINDOW = res.backtest_window;
            const statusEl = document.getElementById('algoExecuteStatus');
        if (statusEl) {
            statusEl.hidden = false;
            statusEl.className = 'algo-execute-status';
                statusEl.textContent =
                `Example strategy (edit before Execute). Backtest window: ${res.backtest_window.start_date} → ${res.backtest_window.end_date}`;
        }

        try {
            const setup = await API.get(`${API_BASE}/api/algo/setup`);
            renderAlgoSetupStatus(setup);
        } catch (setupErr) {
            renderAlgoSetupStatus(null, setupErr.message);
        }
        }
    } catch {
        setAlgoBlocksToUI(DEFAULT_ALGO_BLOCKS);
    }
}

function initMyTradingAlgoUI() {
    setAlgoBlocksToUI(DEFAULT_ALGO_BLOCKS);

    const sendBtn = document.getElementById('algoChatSendBtn');
    const input = document.getElementById('algoChatInput');
    const executeBtn = document.getElementById('executeAlgoBtn');

    const sendChat = async () => {
        const message = input?.value?.trim();
        if (!message) return;
        appendAlgoChatMessage(message, 'user');
        input.value = '';
        sendBtn.disabled = true;
        appendAlgoChatMessage('Thinking…', 'bot');

        try {
            const data = await API.post(`${API_BASE}/api/algo/chat`, {
                message,
                blocks: getAlgoBlocksFromUI(),
            });
            const msgs = document.getElementById('algoChatMessages');
            if (msgs && msgs.lastElementChild?.textContent === 'Thinking…') {
                msgs.removeChild(msgs.lastElementChild);
            }
            setAlgoBlocksToUI(data.blocks);
            syncAlgoTeamNameFromBlocks(data.blocks);
            highlightAlgoBlocks(data.updated_blocks);
            appendAlgoChatMessage(data.reply, 'bot');
        } catch (err) {
            appendAlgoChatMessage(`Error: ${err.message}`, 'bot');
        } finally {
            sendBtn.disabled = false;
            input.focus();
        }
    };

    sendBtn?.addEventListener('click', sendChat);
    input?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            sendChat();
        }
    });

    executeBtn?.addEventListener('click', executeMyTradingAlgo);
}

function syncAlgoTeamNameFromBlocks(blocks) {
    const nameInput = document.getElementById('algoTeamName');
    if (!nameInput) return;
    const info = (blocks.info_retrieval || '').toLowerCase();
    if (info.includes('musk') || (blocks.info_retrieval || '').toLowerCase().includes('musk')) {
        nameInput.value = 'Elon Musk Twitter Algo';
    } else if (info.includes('trump')) {
        nameInput.value = 'Trump Twitter Algo';
    }
}

function renderAlgoSetupStatus(setup, errorMsg) {
    let el = document.getElementById('algoSetupStatus');
    if (!el) {
        el = document.createElement('div');
        el.id = 'algoSetupStatus';
        el.className = 'algo-setup-status';
        const panel = document.querySelector('.algo-blocks-panel');
        if (panel) panel.appendChild(el);
    }
    el.hidden = false;

    if (errorMsg || !setup) {
        el.className = 'algo-setup-status error';
        el.innerHTML =
            '⚠️ Cannot reach My Trading Algo API (HTTP 404). <strong>Restart the backend</strong>: ' +
            '<code>python backend/app.py</code>, then open <code>http://localhost:8000</code>';
        return;
    }

    if (setup.ready) {
        el.className = 'algo-setup-status success';
        el.textContent = '✅ API keys configured. Edit your strategy, then Execute for a real backtest.';
        return;
    }

    const missing = [];
    if (!setup.anthropic_configured) missing.push('ANTHROPIC_API_KEY');
    if (!setup.alpaca_configured) missing.push('Alpaca (credentials/alpaca.json or env vars)');
    el.className = 'algo-setup-status error';
    el.textContent = `⚠️ Missing: ${missing.join(', ')}. Configure .env and restart the backend.`;
}

async function pollAlgoBacktestStatus() {
    const maxAttempts = 360;
    for (let i = 0; i < maxAttempts; i++) {
        let status;
        try {
            status = await API.get(`${API_BASE}/api/algo/status`);
        } catch (err) {
            if (String(err.message).includes('404')) {
                throw new Error(
                    'Backend missing /api/algo/status (old version). Stop with Ctrl+C and run: python backend/app.py'
                );
            }
            throw err;
        }
        const statusEl = document.getElementById('algoExecuteStatus');
        const btn = document.getElementById('executeAlgoBtn');

        if (status.running) {
            if (statusEl) {
                statusEl.textContent = status.progress || `Backtest running… (${i + 1}/${maxAttempts})`;
            }
            if (btn) btn.textContent = `⏳ Running… ${Math.floor(i * 5 / 60)}m`;
            await new Promise(r => setTimeout(r, 5000));
            continue;
        }

        if (status.error) {
            throw new Error(status.error);
        }

        if (status.result) {
            return status.result;
        }

        await new Promise(r => setTimeout(r, 3000));
    }
    throw new Error('Backtest timed out. Check the Backtest tab later.');
}

async function executeMyTradingAlgo() {
    const btn = document.getElementById('executeAlgoBtn');
    const statusEl = document.getElementById('algoExecuteStatus');
    const teamName = document.getElementById('algoTeamName')?.value?.trim();
    const blocks = getAlgoBlocksFromUI();

    const isDefault = Object.keys(DEFAULT_ALGO_BLOCKS).every(
        k => (blocks[k] || '').trim() === (DEFAULT_ALGO_BLOCKS[k] || '').trim()
    );
    if (isDefault) {
        if (statusEl) {
            statusEl.hidden = false;
            statusEl.className = 'algo-execute-status error';
            statusEl.textContent = 'Edit the strategy (chat or blocks) before Execute. The example config does not run a real backtest.';
        }
        appendAlgoChatMessage(
            'Edit all four modules before Execute. Leaderboard teams are mock; only your customized strategy uses real data on Backtest.',
            'bot'
        );
        return;
    }

    btn.disabled = true;
    btn.textContent = '⏳ Starting…';
    if (statusEl) {
        statusEl.hidden = false;
        statusEl.className = 'algo-execute-status';
        statusEl.textContent = 'Submitting real backtest (Alpaca + LLM)…';
    }

    try {
        const job = await API.post(`${API_BASE}/api/algo/execute`, {
            blocks,
            team_name: teamName || undefined,
        });

        if (statusEl) {
            statusEl.textContent = job.message || 'Backtest started. Please wait…';
        }

        const result = await pollAlgoBacktestStatus();
        const m = result.metrics;

        if (statusEl) {
            statusEl.className = 'algo-execute-status success';
            statusEl.textContent = `✅ ${result.message} Opening Backtest…`;
        }

        const retPct = (m.cumulative_return * 100).toFixed(2);
        appendAlgoChatMessage(
            `Backtest complete: "${result.team_name}" (${result.start_date} → ${result.end_date}).\n` +
            `Return ${retPct}%, Sharpe ${m.sharpe_ratio}, ${result.num_trades} trades.\n` +
            `Switched to Backtest to view your MY ALGO curve (vs DJIA / Buy-and-Hold).`,
            'bot'
        );

        if (result.run_id) {
            window.MY_ALGO_RUN_ID = result.run_id;
        }
        switchMode('backtest');
    } catch (err) {
        if (statusEl) {
            statusEl.className = 'algo-execute-status error';
            statusEl.textContent = `Execution failed: ${err.message}`;
        }
        appendAlgoChatMessage(`Backtest failed: ${err.message}`, 'bot');
    } finally {
        btn.disabled = false;
        btn.textContent = '▶ Execute Algo';
    }
}

console.log('Frontend loaded - connecting to API at ' + API_BASE);
