/**
 * Agentic Trading Lab - Frontend Application
 * Connects to backend API for real data
 */

// ============================================================================
// Session Management (Anonymous Browser Isolation)
// ============================================================================

// Initialize anonymous session on first load
const ACTIVE_AGENT_KEY = 'active-agent-id';
const ACTIVE_AGENT_NAME_KEY = 'active-agent-name';
const BROWSER_OWNER_KEY = 'browser-owner-id';
const HIDDEN_DEMO_AGENTS_KEY = 'hidden-demo-agent-ids';
const SELECTED_BACKTEST_RUN_KEY = 'selected-backtest-run-id';
const NAV_STATE_KEY = 'nav-state';
const DISCORD_SERVER_URL = 'https://discord.gg/9HnQ6XDG98';
const BACKTEST_POLL_MAX_SECONDS = 600; // 10 minutes at 1-second polling intervals

function initSession() {
  // Stable browser identity — never changes when switching agents.
  // Bootstrap from trading-session-id so legacy agents whose
  // owner_browser_session equals their session id keep working.
  let browserOwnerId = localStorage.getItem(BROWSER_OWNER_KEY);
  if (!browserOwnerId) {
    browserOwnerId = localStorage.getItem('trading-session-id') || crypto.randomUUID();
    localStorage.setItem(BROWSER_OWNER_KEY, browserOwnerId);
  }
  window.BROWSER_OWNER_ID = browserOwnerId;

  // Trading session — switches per active agent (backtest data scope)
  let sessionId = localStorage.getItem('trading-session-id');
  if (!sessionId) {
    sessionId = browserOwnerId;
    localStorage.setItem('trading-session-id', sessionId);
    console.log('New trading session:', sessionId);
  } else {
    console.log('Restored trading session:', sessionId);
  }
  window.SESSION_ID = sessionId;
}

async function restoreActiveAgentSession() {
  const agentId = localStorage.getItem(ACTIVE_AGENT_KEY);
  if (!agentId) return;

  try {
    const data = await API.get(`${API_BASE}/api/v1/agents/${agentId}`);
    const agent = data.agent;
    if (!agent?.session_id) return;
    applyActiveAgent(agent, { persistActiveId: false });
    try {
      await API.post(`${API_BASE}/api/v1/agents/${agent.agent_id}/activate`, {});
    } catch (claimError) {
      console.warn('Agent claim on restore failed:', claimError.message);
    }
    console.log('Restored active agent:', agent.name, agent.session_id);
  } catch (error) {
    console.warn('Could not restore active agent:', error.message);
    // Only drop saved agent if it was deleted server-side
    if (String(error.message || '').includes('404') || String(error.message || '').includes('not found')) {
      localStorage.removeItem(ACTIVE_AGENT_KEY);
      localStorage.removeItem(ACTIVE_AGENT_NAME_KEY);
    }
  }
}

function applyActiveAgent(agent, options = {}) {
  if (!agent?.session_id) return;
  localStorage.setItem('trading-session-id', agent.session_id);
  if (options.persistActiveId !== false) {
    localStorage.setItem(ACTIVE_AGENT_KEY, agent.agent_id);
    localStorage.setItem(ACTIVE_AGENT_NAME_KEY, agent.name || '');
  }
  window.SESSION_ID = agent.session_id;
  window.ACTIVE_AGENT = agent;
  localStorage.removeItem(SELECTED_BACKTEST_RUN_KEY);

  const nameEl = document.getElementById('playgroundAgentName');
  if (nameEl) nameEl.textContent = agent.name || 'External Agent';

  const statusEl = document.getElementById('playgroundAgentStatus');
  if (statusEl) {
    statusEl.textContent = 'External';
    statusEl.className = 'status-badge baseline';
  }

  const discordEl = document.getElementById('playgroundAgentDiscord');
  if (discordEl) {
    discordEl.textContent = `Session ${agent.session_id.slice(0, 8)}…`;
    discordEl.className = 'agent-discord connected';
  }
}

async function activateAgent(agent) {
  applyActiveAgent(agent);
  try {
    await API.post(`${API_BASE}/api/v1/agents/${agent.agent_id}/activate`, {});
  } catch (error) {
    console.warn('Agent activate ping failed:', error.message);
  }
}

function formatAgentReturn(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const pct = Number(value) * 100;
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(1)}%`;
}

function formatUsd(value) {
  const num = Number(value);
  if (value == null || Number.isNaN(num)) return null;
  if (num === 0) return '$0';
  if (num < 0.01) return `$${num.toFixed(4)}`;
  return `$${num.toFixed(num < 1 ? 3 : 2)}`;
}

function formatTokenCount(value) {
  const num = Number(value);
  if (!num || Number.isNaN(num)) return '0';
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}k`;
  return String(num);
}

// ============================================================================
// Local mock agents — fallback used when the backend returns no agents (or is
// unavailable). Lets the redesigned My Agents page render without a backend.
// TODO: Replace mock agent data with backend API data later.
// ============================================================================
const MAX_AGENT_CASH_ALLOCATION = 3000;
const AGENT_CASH_OVERRIDE_PREFIX = 'agent-cash-allocation:';

function formatAgentCashAllocation(value) {
  if (value == null || value === '') return '—';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Number(value));
}

function parseAgentCashAllocationInput(raw) {
  const value = Number(raw);
  if (!Number.isFinite(value) || value < 0) {
    throw new Error(`Initial cash must be between $0 and $${MAX_AGENT_CASH_ALLOCATION.toLocaleString()}.`);
  }
  if (value > MAX_AGENT_CASH_ALLOCATION) {
    throw new Error(`Initial cash cannot exceed $${MAX_AGENT_CASH_ALLOCATION.toLocaleString()}.`);
  }
  return Math.round(value);
}

function applyAgentCashAllocationOverride(agent) {
  if (!agent?.agent_id) return agent;
  if (agent.cash_allocation != null) return agent;
  try {
    const raw = localStorage.getItem(`${AGENT_CASH_OVERRIDE_PREFIX}${agent.agent_id}`);
    if (raw == null) return agent;
    const value = Number(raw);
    if (!Number.isFinite(value)) return agent;
    return { ...agent, cash_allocation: value };
  } catch (e) {
    return agent;
  }
}

function decorateAgent(agent) {
  return applyAgentCashAllocationOverride(applyAgentNameOverride(agent));
}

const MOCK_AGENTS = [
  {
    agent_id: 'mock-test-agent-2', name: 'test agent 2', agent_type: 'builtin',
    model_name: 'anthropic/claude-haiku-4-5', run_count: 1,
    latest_run: { total_return: 0.065, sharpe_ratio: 2.67 },
    total_input_tokens: 41000, total_output_tokens: 21500, total_est_cost_usd: 0.085, runs: [],
  },
  {
    agent_id: 'mock-test-agent', name: 'test agent', agent_type: 'builtin', is_active: true,
    model_name: 'anthropic/claude-haiku-4-5', run_count: 1,
    latest_run: { total_return: -0.004, sharpe_ratio: -16.84 },
    total_input_tokens: 30000, total_output_tokens: 17500, total_est_cost_usd: 0.064, runs: [],
  },
  {
    agent_id: 'mock-test', name: 'test', agent_type: 'external',
    model_name: 'local-model', run_count: 0,
    latest_run: {}, total_input_tokens: 0, total_output_tokens: 0, runs: [],
  },
  {
    agent_id: 'mock-sdk-1', name: 'sdk-selftest-agent', agent_type: 'external',
    model_name: 'rule-based', run_count: 1,
    latest_run: { total_return: 0.02, sharpe_ratio: 4.25 },
    total_input_tokens: 44800, total_output_tokens: 20000, total_est_cost_usd: 0.0, runs: [],
  },
  {
    agent_id: 'mock-sdk-2', name: 'sdk-selftest-agent', agent_type: 'external',
    model_name: 'rule-based', run_count: 1,
    latest_run: { total_return: 0.022, sharpe_ratio: 8.89 },
    total_input_tokens: 28400, total_output_tokens: 0, total_est_cost_usd: 0.0, runs: [],
  },
  {
    agent_id: 'mock-sdk-3', name: 'sdk-selftest-agent', agent_type: 'external',
    model_name: 'rule-based', run_count: 1,
    latest_run: { total_return: 0.022, sharpe_ratio: 8.89 },
    total_input_tokens: 21000, total_output_tokens: 0, total_est_cost_usd: 0.0, runs: [],
  },
  {
    agent_id: 'mock-sdk-4', name: 'sdk-selftest-agent', agent_type: 'external',
    model_name: 'rule-based', run_count: 1,
    latest_run: { total_return: 0.012, sharpe_ratio: 8.89 },
    total_input_tokens: 28400, total_output_tokens: 0, total_est_cost_usd: 0.0, runs: [],
  },
  {
    agent_id: 'mock-protocol-demo', name: 'protocol-demo', agent_type: 'external',
    model_name: 'rule-based-demo', run_count: 2,
    latest_run: { total_return: 0.06, sharpe_ratio: 7.38 },
    total_input_tokens: 0, total_output_tokens: 0, total_est_cost_usd: 0.0, runs: [],
  },
  {
    agent_id: 'mock-test-2', name: 'test', agent_type: 'external',
    model_name: 'local-model', run_count: 1,
    latest_run: { total_return: 0.081, sharpe_ratio: 25.66 },
    total_input_tokens: 7400, total_output_tokens: 0, total_est_cost_usd: 0.0, runs: [],
  },
];

// Holds the most recently loaded agents so the toolbar can re-filter without refetching.
let allAgents = [];
let agentViewMode = 'grid';
function resolveAgentStatusBadge(agent) {
  if (agent.is_live === true || agent.deployment_status === 'live') {
    return { label: 'Live', className: 'live' };
  }
  const runCount = Number(agent.run_count) || (Array.isArray(agent.runs) ? agent.runs.length : 0);
  if (runCount > 0) {
    return { label: 'Backtested', className: 'backtested' };
  }
  return { label: 'Draft', className: 'draft' };
}

// Demo/mock agents (MOCK_AGENTS) have no database row, so renames made in the editor
// are stored locally under `agent-name-override:{id}`. Real agents use the same key
// only when a server PATCH fails, so the edited name still shows in the UI.
function applyAgentNameOverride(agent) {
  if (!agent || !agent.agent_id) return agent;
  try {
    const raw = localStorage.getItem(`agent-name-override:${agent.agent_id}`);
    if (!raw) return agent;
    const override = JSON.parse(raw);
    return {
      ...agent,
      name: override.name || agent.name,
      description: override.description ?? agent.description,
    };
  } catch (e) {
    return agent;
  }
}

function applyAgentFilters() {
  const filter = document.getElementById('agentFilterSelect')?.value || 'all';
  const query = (document.getElementById('agentSearchInput')?.value || '').trim().toLowerCase();
  const activeId = localStorage.getItem(ACTIVE_AGENT_KEY);

  let list = allAgents.map(decorateAgent);
  if (filter === 'builtin') {
    list = list.filter((a) => a.agent_type === 'builtin');
  } else if (filter === 'external') {
    list = list.filter((a) => a.agent_type !== 'builtin');
  } else if (filter === 'active') {
    list = list.filter((a) => a.is_active || a.agent_id === activeId);
  } else if (filter === 'registered') {
    list = list.filter((a) => !(a.is_active || a.agent_id === activeId));
  }

  if (query) {
    list = list.filter(
      (a) =>
        String(a.name || '').toLowerCase().includes(query) ||
        String(a.model_name || '').toLowerCase().includes(query),
    );
  }

  renderAgentsGrid(list);
}

function setAgentViewMode(mode) {
  agentViewMode = mode === 'list' ? 'list' : 'grid';
  const grid = document.getElementById('agentsGrid');
  if (grid) grid.classList.toggle('agents-grid--list', agentViewMode === 'list');
  document.getElementById('agentViewGrid')?.classList.toggle('active', agentViewMode === 'grid');
  document.getElementById('agentViewList')?.classList.toggle('active', agentViewMode === 'list');
}

function isDemoAgent(agentId) {
  return typeof agentId === 'string' && agentId.startsWith('mock-');
}

function getHiddenDemoAgentIds() {
  try {
    const raw = localStorage.getItem(HIDDEN_DEMO_AGENTS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch (e) {
    return [];
  }
}

function hideDemoAgent(agentId) {
  const hidden = getHiddenDemoAgentIds();
  if (!hidden.includes(agentId)) {
    hidden.push(agentId);
    localStorage.setItem(HIDDEN_DEMO_AGENTS_KEY, JSON.stringify(hidden));
  }
}

function visibleMockAgents() {
  const hidden = new Set(getHiddenDemoAgentIds());
  return MOCK_AGENTS.filter((agent) => !hidden.has(agent.agent_id));
}

// Demo mode is opt-in via ?demo=1 so local development does not show fake agents
// that cannot be deleted from the database.
function isDemoMode() {
  try {
    const params = new URLSearchParams(window.location.search);
    return params.get('demo') === '1';
  } catch (e) {
    return false;
  }
}

// Distinct error-state shown when the agents API is unreachable — never mask a
// backend outage by rendering fake data.
function renderAgentsError() {
  const grid = document.getElementById('agentsGrid');
  const empty = document.getElementById('agentsEmptyState');
  const errorEl = document.getElementById('agentsErrorState');
  if (grid) grid.innerHTML = '';
  if (empty) empty.hidden = true;
  if (errorEl) errorEl.hidden = false;
}

function renderAgentsGrid(agents) {
  const grid = document.getElementById('agentsGrid');
  const empty = document.getElementById('agentsEmptyState');
  const errorEl = document.getElementById('agentsErrorState');
  if (!grid) return;

  if (errorEl) errorEl.hidden = true;  // a successful render clears any prior error
  grid.innerHTML = '';
  if (!agents.length) {
    if (empty) empty.hidden = false;
    return;
  }
  if (empty) empty.hidden = true;

  agents.forEach((agent) => {
    const isBuiltin = agent.agent_type === 'builtin';
    const statusBadge = resolveAgentStatusBadge(agent);
    const card = document.createElement('div');
    card.className = `section-card agent-card agent-card--compact${isBuiltin ? ' agent-card-builtin' : ''}`;

    const typeBadge = isBuiltin
      ? '<span class="status-badge builtin">Built-in</span>'
      : '<span class="agent-discord connected">External agent</span>';

    const apiKeyButton = isBuiltin
      ? ''
      : `<button class="agent-action-btn agent-action-secondary agent-rotate-key-btn" type="button" data-agent-id="${escapeHtml(agent.agent_id)}">New API key</button>`;

    const cashBadge = agent.cash_allocation != null
      ? `<span class="agent-cash-allocation" title="Starting capital budget for this agent">Initial cash: ${formatAgentCashAllocation(agent.cash_allocation)}</span>`
      : '';

    card.innerHTML = `
      <div class="agent-card-head">
        <h3 class="agent-name">${escapeHtml(agent.name)}</h3>
        <span class="status-badge ${statusBadge.className}">${statusBadge.label}</span>
      </div>
      <div class="agent-meta">
        <span>${escapeHtml(agent.model_name || 'local-model')}</span>
        ${typeBadge}
        ${cashBadge}
      </div>
      ${isBuiltin && agent.description ? `<p class="agent-description">${escapeHtml(agent.description)}</p>` : ''}
      <div class="agent-meta">
        <span>${agent.run_count || 0} backtest run(s)</span>
        ${renderAgentTokenCost(agent)}
      </div>
      ${renderAgentRunList(agent)}
      <div class="agent-card-actions">
        <button class="agent-action-btn agent-edit-btn" type="button" data-agent-id="${escapeHtml(agent.agent_id)}">Edit</button>
        <button class="agent-action-btn agent-select-btn" type="button" data-agent-id="${escapeHtml(agent.agent_id)}">View in Playground</button>
        ${apiKeyButton}
        <button class="agent-action-btn agent-delete-btn" type="button" data-agent-id="${escapeHtml(agent.agent_id)}">Delete</button>
      </div>
    `;
    grid.appendChild(card);
  });

  grid.querySelectorAll('.agent-edit-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const agent = agents.find((a) => a.agent_id === btn.dataset.agentId);
      if (!agent || !window.AgentEditor) return;
      navigateToPage('playground', { playgroundTab: 'agents' });
      showPlaygroundPanel('agents');
      window.AgentEditor.open(agent);
    });
  });

  grid.querySelectorAll('.agent-select-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const agent = agents.find((a) => a.agent_id === btn.dataset.agentId);
      if (!agent) return;
      await activateAgent(agent);
      navigateToPage('playground', { playgroundTab: 'backtest' });
      currentMode = 'backtest';
      await loadData();
    });
  });

  grid.querySelectorAll('.agent-run-link').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const agent = agents.find((a) => a.agent_id === btn.dataset.agentId);
      const runId = btn.dataset.runId;
      if (!agent || !runId) return;
      await activateAgent(agent);
      localStorage.setItem(SELECTED_BACKTEST_RUN_KEY, runId);
      navigateToPage('playground', { playgroundTab: 'backtest' });
      currentMode = 'backtest';
      await loadData();
    });
  });

  grid.querySelectorAll('.agent-rotate-key-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const agent = agents.find((a) => a.agent_id === btn.dataset.agentId);
      if (!agent) return;
      if (!confirm(`Create a new API key for "${agent.name}"? The current key will stop working immediately.`)) {
        return;
      }
      btn.disabled = true;
      try {
        await rotateAgentApiKey(agent);
      } catch (error) {
        alert(error.message || 'Failed to create new API key');
      } finally {
        btn.disabled = false;
      }
    });
  });

  grid.querySelectorAll('.agent-delete-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const agentId = btn.dataset.agentId;
      if (!agentId || !confirm('Delete this agent? Backtest history stays in the database.')) return;
      try {
        if (isDemoAgent(agentId)) {
          hideDemoAgent(agentId);
          if (localStorage.getItem(ACTIVE_AGENT_KEY) === agentId) {
            localStorage.removeItem(ACTIVE_AGENT_KEY);
            localStorage.removeItem(ACTIVE_AGENT_NAME_KEY);
          }
          await loadAgents();
          return;
        }
        await API.request(`${API_BASE}/api/v1/agents/${agentId}`, { method: 'DELETE' });
        if (localStorage.getItem(ACTIVE_AGENT_KEY) === agentId) {
          localStorage.removeItem(ACTIVE_AGENT_KEY);
          localStorage.removeItem(ACTIVE_AGENT_NAME_KEY);
        }
        await loadAgents();
      } catch (error) {
        alert(error.message || 'Failed to delete agent');
      }
    });
  });
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function renderAgentTokenCost(agent) {
  const totalTokens =
    Number(agent.total_input_tokens || 0) + Number(agent.total_output_tokens || 0);
  if (!totalTokens) return '';
  const cost = formatUsd(agent.total_est_cost_usd);
  const costLabel = cost ? `${cost} est. LLM cost` : '';
  return `<span title="Estimated from market context served and decisions returned">${formatTokenCount(totalTokens)} tokens${costLabel ? ` · ${costLabel}` : ''}</span>`;
}

function renderAgentRunList(agent) {
  const runs = (agent.runs || []).slice(0, 3);
  if (!runs.length) return '';
  const items = runs
    .map(
      (run) => `
        <button type="button" class="agent-run-link" data-agent-id="${escapeHtml(agent.agent_id)}" data-run-id="${escapeHtml(run.run_id)}">
          <span class="agent-run-primary">${escapeHtml(formatBacktestRunPrimary(run))}</span>
          <span class="agent-run-secondary">${escapeHtml(formatBacktestRunSecondary(run))}</span>
        </button>`,
    )
    .join('');
  return `<div class="agent-run-list">${items}</div>`;
}

function listBacktestableAgents() {
  return (allAgents || []).filter((agent) => agent?.agent_id && !isDemoAgent(agent.agent_id));
}

function populateBacktestAgentSelect() {
  const select = document.getElementById('backtestAgentSelect');
  if (!select) return;

  const agents = listBacktestableAgents();
  const activeId = localStorage.getItem(ACTIVE_AGENT_KEY);

  if (!agents.length) {
    select.innerHTML = '<option value="">No agents yet — create one in My Agents</option>';
    select.disabled = true;
    return;
  }

  select.disabled = false;
  select.innerHTML = agents
    .map((agent) => {
      const type = agent.agent_type === 'builtin' ? 'Built-in' : 'External';
      const model = agent.model_name || 'local-model';
      const label = `${agent.name} · ${model} · ${type}`;
      return `<option value="${escapeHtml(agent.agent_id)}">${escapeHtml(label)}</option>`;
    })
    .join('');

  const selectedId =
    activeId && agents.some((agent) => agent.agent_id === activeId)
      ? activeId
      : agents[0].agent_id;
  select.value = selectedId;
}

function syncModelSelectFromAgent(agent) {
  const modelSelect = document.getElementById('modelSelect');
  if (!modelSelect || !agent?.model_name) return;
  const hasOption = Array.from(modelSelect.options).some(
    (option) => option.value === agent.model_name,
  );
  if (hasOption) {
    modelSelect.value = agent.model_name;
  }
}

function getSelectedBacktestAgent() {
  const select = document.getElementById('backtestAgentSelect');
  if (select?.value) {
    const agent = allAgents.find((item) => item.agent_id === select.value);
    if (agent) return agent;
  }
  return resolveActiveAgentForBacktest();
}

async function onBacktestAgentSelectChange() {
  const select = document.getElementById('backtestAgentSelect');
  if (!select?.value) return;
  const agent = allAgents.find((item) => item.agent_id === select.value);
  if (!agent) return;

  await activateAgent(agent);
  syncModelSelectFromAgent(agent);
  localStorage.removeItem(SELECTED_BACKTEST_RUN_KEY);
  if (currentMode === 'backtest') {
    await loadData();
    loadPerformanceMetrics();
  }
}

async function loadAgents() {
  try {
    let data = await API.get(`${API_BASE}/api/v1/agents`);
    let agents = data.agents || [];

    // Fallback: fetch saved active agent directly (survives owner/session mismatch)
    const activeId = localStorage.getItem(ACTIVE_AGENT_KEY);
    if (activeId && !agents.some((a) => a.agent_id === activeId)) {
      try {
        const one = await API.get(`${API_BASE}/api/v1/agents/${activeId}`);
        if (one?.agent) {
          agents = [one.agent, ...agents];
        }
      } catch (fallbackError) {
        console.warn('Active agent fallback failed:', fallbackError.message);
      }
    }

    if (!agents.length) {
      try {
        const runs = await API.get(`${API_BASE}/api/backtest/runs?t=${Date.now()}`);
        const hasExt = (runs || []).some((r) => r.run_id && String(r.run_id).startsWith('ext_'));
        if (hasExt) {
          const imported = await API.post(`${API_BASE}/api/v1/agents/import-session`, {});
          if (imported?.agent) {
            agents = [imported.agent];
            applyActiveAgent(imported.agent);
          }
        }
      } catch (importError) {
        console.warn('Session import skipped:', importError.message);
      }
    }

    // Demo only: seed illustrative agents so the page has content without a
    // backend. Real users get the genuine empty-state (rendered by
    // renderAgentsGrid) instead of fabricated agents.
    if (!agents.length && isDemoMode()) {
      agents = visibleMockAgents();
    }

    allAgents = agents;
    applyAgentFilters();
    populateBacktestAgentSelect();
    if (typeof window.updateAgentAllocationFromAgents === 'function') {
      window.updateAgentAllocationFromAgents(allAgents.map(decorateAgent));
    }
  } catch (error) {
    console.warn('Failed to load agents:', error.message);
    if (isDemoMode()) {
      allAgents = visibleMockAgents();
      applyAgentFilters();
      populateBacktestAgentSelect();
    } else {
      // Real backend outage: show a distinct error-state, never fake data.
      allAgents = [];
      renderAgentsError();
      populateBacktestAgentSelect();
    }
  }
}

function openCreateExternalAgentModal() {
  closeAddAgentModal();
  const modal = document.getElementById('createExternalAgentModal');
  const errorEl = document.getElementById('createExternalAgentError');
  const form = document.getElementById('createExternalAgentForm');
  if (errorEl) errorEl.hidden = true;
  if (form) form.reset();
  if (modal) modal.hidden = false;
}

function closeCreateExternalAgentModal() {
  const modal = document.getElementById('createExternalAgentModal');
  if (modal) modal.hidden = true;
}

function openCreateBuiltinAgentModal() {
  closeAddAgentModal();
  const modal = document.getElementById('createBuiltinAgentModal');
  const errorEl = document.getElementById('createBuiltinAgentError');
  const form = document.getElementById('createBuiltinAgentForm');
  if (errorEl) errorEl.hidden = true;
  if (form) form.reset();
  if (modal) modal.hidden = false;
}

function closeCreateBuiltinAgentModal() {
  const modal = document.getElementById('createBuiltinAgentModal');
  if (modal) modal.hidden = true;
}

async function submitCreateBuiltinAgent(event) {
  event.preventDefault();
  const nameInput = document.getElementById('builtinAgentName');
  const modelInput = document.getElementById('builtinAgentModel');
  const descInput = document.getElementById('builtinAgentDescription');
  const errorEl = document.getElementById('createBuiltinAgentError');
  const submitBtn = document.getElementById('createBuiltinAgentSubmit');

  const name = nameInput?.value?.trim();
  const model_name = modelInput?.value?.trim() || 'anthropic/claude-haiku-4-5';
  const description = descInput?.value?.trim() || null;
  const cashInput = document.getElementById('builtinAgentCashAllocation');
  if (!name) return;

  let cash_allocation;
  try {
    cash_allocation = parseAgentCashAllocationInput(cashInput?.value);
  } catch (error) {
    if (errorEl) {
      errorEl.textContent = error.message;
      errorEl.hidden = false;
    }
    return;
  }

  if (errorEl) errorEl.hidden = true;
  if (submitBtn) submitBtn.disabled = true;

  try {
    const data = await API.post(`${API_BASE}/api/v1/agents`, {
      name,
      model_name,
      agent_type: 'builtin',
      description,
      cash_allocation,
    });
    closeCreateBuiltinAgentModal();
    if (data.agent) applyActiveAgent(data.agent);
    await loadAgents();
  } catch (error) {
    if (errorEl) {
      errorEl.textContent = error.message;
      errorEl.hidden = false;
    }
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

function showAgentCredentials(apiKey, options = {}) {
  const modal = document.getElementById('agentCredentialsModal');
  const titleEl = document.getElementById('agentCredentialsModalTitle');
  const subtitleEl = document.getElementById('agentCredentialsModalSubtitle');
  const apiInput = document.getElementById('agentCredentialApiKey');
  const copyBtn = document.getElementById('agentCredentialCopyBtn');
  const doneBtn = document.getElementById('agentCredentialDoneBtn');

  if (titleEl) {
    titleEl.textContent = options.title || 'Agent created';
  }
  if (subtitleEl) {
    subtitleEl.textContent =
      options.subtitle ||
      'Your agent is ready. Use the API key below to connect your trading client to Agentic Trading Lab.';
  }
  if (apiInput) apiInput.value = apiKey;
  if (copyBtn) {
    copyBtn.onclick = async () => {
      try {
        await navigator.clipboard.writeText(apiKey);
        const prev = copyBtn.textContent;
        copyBtn.textContent = 'Copied';
        setTimeout(() => {
          copyBtn.textContent = prev;
        }, 1500);
      } catch (error) {
        apiInput?.select();
        document.execCommand?.('copy');
        copyBtn.textContent = 'Copied';
      }
    };
  }
  if (doneBtn) {
    doneBtn.onclick = () => closeAgentCredentialsModal();
  }
  if (modal) modal.hidden = false;
}

async function rotateAgentApiKey(agent) {
  const data = await API.post(
    `${API_BASE}/api/v1/agents/${agent.agent_id}/rotate-api-key`,
    {},
  );
  await loadAgents();
  showAgentCredentials(data.api_key, {
    title: 'New API key created',
    subtitle: `A new key was issued for "${agent.name}". Update your client — the old key no longer works.`,
  });
  return data;
}

function closeAgentCredentialsModal() {
  const modal = document.getElementById('agentCredentialsModal');
  if (modal) modal.hidden = true;
}

async function submitCreateExternalAgent(event) {
  event.preventDefault();
  const nameInput = document.getElementById('externalAgentName');
  const modelInput = document.getElementById('externalAgentModel');
  const errorEl = document.getElementById('createExternalAgentError');
  const submitBtn = document.getElementById('createExternalAgentSubmit');

  const name = nameInput?.value?.trim();
  const model_name = modelInput?.value?.trim() || 'local-model';
  const cashInput = document.getElementById('externalAgentCashAllocation');
  if (!name) return;

  let cash_allocation;
  try {
    cash_allocation = parseAgentCashAllocationInput(cashInput?.value);
  } catch (error) {
    if (errorEl) {
      errorEl.textContent = error.message;
      errorEl.hidden = false;
    }
    return;
  }

  if (errorEl) errorEl.hidden = true;
  if (submitBtn) submitBtn.disabled = true;

  try {
    const data = await API.post(`${API_BASE}/api/v1/agents`, { name, model_name, cash_allocation });
    closeCreateExternalAgentModal();
    applyActiveAgent(data.agent);
    await loadAgents();
    showAgentCredentials(data.api_key);
  } catch (error) {
    if (errorEl) {
      errorEl.textContent = error.message;
      errorEl.hidden = false;
    }
  } finally {
    if (submitBtn) submitBtn.disabled = false;
  }
}

// Load default configuration from backend
async function loadDefaults() {
  try {
    const defaultsUrl = `${API_BASE}/config/defaults`;
    
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
      'x-session-id': window.SESSION_ID,
      'x-browser-id': window.BROWSER_OWNER_ID,
      ...options.headers,
    };
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    
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
        const errorMsg = data.detail || data.error || data.message || `HTTP ${response.status}`;
        const error = new Error(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg));
        error.status = response.status;
        throw error;
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

  patch(endpoint, data, extraHeaders = {}) {
    return this.request(endpoint, {
      method: 'PATCH',
      body: JSON.stringify(data),
      headers: extraHeaders,
    });
  },
};

// ============================================================================
// Use production URL on Vercel, localhost for local development
// ============================================================================

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? window.location.origin
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

async function claimAgentsForUser() {
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  if (!token) return;
  try {
    await API.post(`${API_BASE}/api/v1/agents/claim-account`, {});
  } catch (error) {
    console.warn('Agent account claim skipped:', error.message);
  }
  await loadAgents();
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
  const signInBtn = document.getElementById('authSignInBtn');
  const signUpBtn = document.getElementById('authSignUpBtn');
  const logoutBtn = document.getElementById('authLogoutBtn');
  if (!label || !signInBtn || !signUpBtn || !logoutBtn) {
    return;
  }

  if (user) {
    label.textContent = user.display_name || user.email;
    label.hidden = false;
    signInBtn.hidden = true;
    signUpBtn.hidden = true;
    logoutBtn.hidden = false;
  } else {
    label.hidden = true;
    signInBtn.hidden = false;
    signUpBtn.hidden = false;
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

  if (title) title.textContent = mode === 'signup' ? 'Sign up' : 'Sign in';
  if (subtitle) {
    subtitle.textContent = 'Optional — backtest and paper trading work without an account.';
  }
  if (submitBtn) submitBtn.textContent = mode === 'signup' ? 'Create account' : 'Sign in';
  if (switchBtn) {
    switchBtn.textContent = mode === 'signup'
      ? 'Already have an account? Sign in'
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

/** Open auth modal from landing-page links (?auth=login|signup). */
function openAuthFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const auth = (params.get('auth') || '').toLowerCase();
  if (auth !== 'login' && auth !== 'signup') return;

  // Already signed in — stay on the dashboard, no modal.
  if (localStorage.getItem(AUTH_TOKEN_KEY) && getStoredAuthUser()) {
    params.delete('auth');
    const clean = params.toString();
    const next = `${window.location.pathname}${clean ? `?${clean}` : ''}${window.location.hash}`;
    window.history.replaceState({}, '', next);
    return;
  }

  openAuthModal(auth === 'signup' ? 'signup' : 'login');
  params.delete('auth');
  const clean = params.toString();
  const next = `${window.location.pathname}${clean ? `?${clean}` : ''}${window.location.hash}`;
  window.history.replaceState({}, '', next);
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
    await claimAgentsForUser();
  } catch (error) {
    console.warn('Auth session expired:', error.message);
    clearAuthState();
  }
}

function initAuthUI() {
  const signInBtn = document.getElementById('authSignInBtn');
  const signUpBtn = document.getElementById('authSignUpBtn');
  const logoutBtn = document.getElementById('authLogoutBtn');
  const closeBtn = document.getElementById('authModalClose');
  const backdrop = document.getElementById('authModalBackdrop');
  const switchBtn = document.getElementById('authSwitchBtn');
  const form = document.getElementById('authForm');

  signInBtn?.addEventListener('click', () => openAuthModal('login'));
  signUpBtn?.addEventListener('click', () => openAuthModal('signup'));
  logoutBtn?.addEventListener('click', async () => {
    try {
      await AuthAPI.logout();
    } catch (error) {
      console.warn('Logout request failed:', error.message);
    } finally {
      clearAuthState();
      await loadAgents();
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
      await claimAgentsForUser();
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
  openAuthFromUrl();
  refreshAuthUser();
}

// Store default run IDs
window.DEFAULT_RUNS = {};

let chartInstance = null;
let liveBacktestChartActive = false;
let liveBacktestChartMeta = { timestamps: [] };
let tradingLogCache = [];
let tradingLogFilter = 'all';
let currentMode = "home";
let currentPage = "home";
let playgroundTab = "agents";
let competitionTab = "leaderboard";
let allRuns = [];
let comparisonData = null;
let backtestChartData = null;
let defaultConfig = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    // Initialize session FIRST (before any API calls)
    initSession();
    initAuthUI();
    applyInitialNavigation();
    window.addEventListener('agent-editor-saved', async (event) => {
        const agent = event.detail?.agent;
        if (agent?.agent_id) {
            const idx = allAgents.findIndex((a) => a.agent_id === agent.agent_id);
            if (idx >= 0) {
                allAgents[idx] = { ...allAgents[idx], ...agent };
            }
            applyAgentFilters();
        }
        if (agent?.agent_id === localStorage.getItem(ACTIVE_AGENT_KEY)) {
            localStorage.setItem(ACTIVE_AGENT_NAME_KEY, agent.name || '');
            const nameEl = document.getElementById('playgroundAgentName');
            if (nameEl) nameEl.textContent = agent.name || 'Agent';
        }
        await loadAgents();
    });
    window.addEventListener('agent-editor-open-run', async (event) => {
        const { agent, runId } = event.detail || {};
        if (!agent || !runId) return;
        if (window.AgentEditor) window.AgentEditor.close(true);
        await activateAgent(agent);
        localStorage.setItem(SELECTED_BACKTEST_RUN_KEY, runId);
        navigateToPage('playground', { playgroundTab: 'backtest' });
        currentMode = 'backtest';
        await loadData();
    });
    await restoreActiveAgentSession();
    const config = loadConfigFromURL();
    window.CURRENT_CONFIG = config;
    console.log('⚙️ Experiment config:', config);
    console.log('Session ID:', window.SESSION_ID);
    
    console.log('Dashboard initializing...');

    setupTickerResizeHandler();
    setupTickerScrollControls();

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

    const backtestRunSelect = document.getElementById('backtestRunSelect');
    if (backtestRunSelect) {
        backtestRunSelect.addEventListener('change', async () => {
            const runId = backtestRunSelect.value;
            if (runId) {
                localStorage.setItem(SELECTED_BACKTEST_RUN_KEY, runId);
            } else {
                localStorage.removeItem(SELECTED_BACKTEST_RUN_KEY);
            }
            await loadData();
        });
    }

    const tradingLogFilterSelect = document.getElementById('tradingLogFilter');
    if (tradingLogFilterSelect) {
        tradingLogFilterSelect.addEventListener('change', () => {
            tradingLogFilter = tradingLogFilterSelect.value || 'all';
            renderTradingLog(tradingLogCache, {
                emptyMessage: tradingLogCache.length
                    ? 'No trades match this filter.'
                    : 'Run a backtest to see trades here.',
            });
        });
    }

    const backtestAgentSelect = document.getElementById('backtestAgentSelect');
    if (backtestAgentSelect) {
        backtestAgentSelect.addEventListener('change', () => {
            onBacktestAgentSelectChange();
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

    initNavigation();

    // Load ticker without blocking the rest of the page
    loadMarketTicker();
    setInterval(loadMarketTicker, 30000);
    
    console.log('🎯 Dashboard ready. Default runs:', window.DEFAULT_RUNS || 'None configured');
});

/**
 * Load performance metrics from latest backtest run
 */
async function loadPerformanceMetrics() {
    try {
        // Mirror the chart: show metrics for the selected run. window.SELECTED_RUN
        // is set by loadData; resolve from session runs when called standalone.
        let metrics = window.SELECTED_RUN || null;

        if (!metrics) {
            try {
                const sessionRuns = await API.get(`${API_BASE}/api/backtest/runs?t=${Date.now()}`);
                metrics = resolveSelectedRun(sessionRuns);
            } catch (e) {
                console.warn('Could not load session runs for metrics');
            }
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
const TICKER_SCROLL_PX_PER_SEC = 55;
const TICKER_ESTIMATED_ITEM_WIDTH = 140;
let tickerResizeTimer = null;
let latestTickerQuotes = [];
let tickerScrollRaf = null;
let tickerScrollOffset = 0;
let tickerScrollSetWidth = 0;
let tickerScrollLastTime = 0;
let tickerScrollPaused = false;
let tickerScrollControlsBound = false;

function sortTickerQuotes(quotes) {
    const order = new Map(MAG7_TICKER_SYMBOLS.map((symbol, index) => [symbol, index]));
    return [...quotes].sort(
        (a, b) => (order.get(a.symbol) ?? 99) - (order.get(b.symbol) ?? 99)
    );
}

function getTickerMarqueeWidth() {
    const marquee = document.getElementById('tickerMarquee');
    return marquee?.clientWidth || window.innerWidth;
}

function getTickerQuoteFields(quote) {
    let changeDisplay = '--';
    let changeClass = '';
    let tooltip = 'Data unavailable';
    let sparkPath = 'M0,8 L5,6 L10,7 L15,4 L20,5 L25,3 L30,5';

    if (quote.changePercent !== null && quote.changePercent !== undefined) {
        const changeSign = quote.changePercent >= 0 ? '+' : '';
        changeDisplay = `${changeSign}${quote.changePercent.toFixed(2)}%`;
        changeClass = quote.changePercent >= 0 ? 'positive' : 'negative';
        tooltip = 'Change vs previous close';
        sparkPath = quote.changePercent >= 0
            ? 'M0,10 L5,8 L10,9 L15,6 L20,7 L25,4 L30,3'
            : 'M0,3 L5,5 L10,4 L15,7 L20,6 L25,9 L30,10';
    }

    const price = quote.price != null
        ? quote.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
        : '--';

    return { price, changeDisplay, changeClass, tooltip, sparkPath };
}

function buildTickerItemHtml(quote) {
    const fields = getTickerQuoteFields(quote);

    return `
        <div class="ticker-item" data-symbol="${quote.symbol}">
            <span class="symbol">${quote.symbol}</span>
            <span class="price">${fields.price}</span>
            <span class="change ${fields.changeClass}" title="${fields.tooltip}">${fields.changeDisplay}</span>
            <svg class="ticker-chart ${fields.changeClass}" viewBox="0 0 30 12" aria-hidden="true">
                <path d="${fields.sparkPath}" stroke="currentColor" fill="none" stroke-width="1"/>
            </svg>
        </div>
    `;
}

function buildTickerSetHtml(quotes, repeats) {
    const sortedQuotes = sortTickerQuotes(quotes);
    const itemHtml = sortedQuotes.map(buildTickerItemHtml).join('');
    return Array(Math.max(1, repeats)).fill(itemHtml).join('');
}

function stopTickerScroll() {
    if (tickerScrollRaf !== null) {
        cancelAnimationFrame(tickerScrollRaf);
        tickerScrollRaf = null;
    }
}

function getTickerSetWidth(tickerTrack) {
    return tickerTrack.querySelector('.ticker-set')?.offsetWidth || 0;
}

function tickerScrollFrame(now) {
    const tickerTrack = document.getElementById('tickerTrack');
    if (!tickerTrack || tickerTrack.dataset.tickerReady !== '1') {
        stopTickerScroll();
        return;
    }

    if (!tickerScrollSetWidth) {
        tickerScrollSetWidth = getTickerSetWidth(tickerTrack);
        if (!tickerScrollSetWidth) {
            tickerScrollRaf = requestAnimationFrame(tickerScrollFrame);
            return;
        }
    }

    if (!tickerScrollLastTime) {
        tickerScrollLastTime = now;
    }

    if (!tickerScrollPaused) {
        const dt = Math.min(0.05, (now - tickerScrollLastTime) / 1000);
        tickerScrollOffset -= TICKER_SCROLL_PX_PER_SEC * dt;
        if (tickerScrollOffset <= -tickerScrollSetWidth) {
            tickerScrollOffset += tickerScrollSetWidth;
        }
        tickerTrack.style.transform = `translate3d(${tickerScrollOffset}px, 0, 0)`;
    }

    tickerScrollLastTime = now;
    tickerScrollRaf = requestAnimationFrame(tickerScrollFrame);
}

function startTickerScroll() {
    stopTickerScroll();

    const tickerTrack = document.getElementById('tickerTrack');
    if (!tickerTrack || tickerTrack.dataset.tickerReady !== '1') {
        return;
    }

    tickerScrollOffset = 0;
    tickerScrollSetWidth = 0;
    tickerScrollLastTime = 0;
    tickerTrack.style.transform = 'translate3d(0, 0, 0)';
    tickerScrollRaf = requestAnimationFrame(tickerScrollFrame);
}

function scheduleTickerScrollStart() {
    stopTickerScroll();
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            startTickerScroll();
        });
    });
}

function setupTickerScrollControls() {
    if (tickerScrollControlsBound) {
        return;
    }
    tickerScrollControlsBound = true;

    const marquee = document.getElementById('tickerMarquee');
    marquee?.addEventListener('mouseenter', () => {
        tickerScrollPaused = true;
    });
    marquee?.addEventListener('mouseleave', () => {
        tickerScrollPaused = false;
        tickerScrollLastTime = 0;
    });

    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            stopTickerScroll();
            return;
        }
        if (document.getElementById('tickerTrack')?.dataset.tickerReady === '1') {
            scheduleTickerScrollStart();
        }
    });
}

function patchTickerItemElement(item, quote) {
    const fields = getTickerQuoteFields(quote);
    const priceEl = item.querySelector('.price');
    const changeEl = item.querySelector('.change');
    const chartEl = item.querySelector('.ticker-chart');
    const pathEl = item.querySelector('.ticker-chart path');

    if (priceEl) {
        priceEl.textContent = fields.price;
    }
    if (changeEl) {
        changeEl.textContent = fields.changeDisplay;
        changeEl.className = `change ${fields.changeClass}`.trim();
        changeEl.title = fields.tooltip;
    }
    if (chartEl) {
        chartEl.className = `ticker-chart ${fields.changeClass}`.trim();
    }
    if (pathEl) {
        pathEl.setAttribute('d', fields.sparkPath);
    }
}

function patchTickerQuotes(quotes) {
    const tickerTrack = document.getElementById('tickerTrack');
    if (!tickerTrack || tickerTrack.dataset.tickerReady !== '1') {
        return false;
    }

    const quoteBySymbol = new Map(quotes.map((quote) => [quote.symbol, quote]));
    tickerTrack.querySelectorAll('.ticker-item[data-symbol]').forEach((item) => {
        const quote = quoteBySymbol.get(item.dataset.symbol);
        if (quote) {
            patchTickerItemElement(item, quote);
        }
    });
    return true;
}

function estimateTickerRepeats(quotes, marqueeWidth) {
    const minSetWidth = marqueeWidth + 80;
    const singlePassWidth = Math.max(quotes.length, 1) * TICKER_ESTIMATED_ITEM_WIDTH;
    return Math.max(3, Math.ceil(minSetWidth / singlePassWidth));
}

function renderTickerTrack(quotes) {
    const tickerTrack = document.getElementById('tickerTrack');
    const marqueeWidth = getTickerMarqueeWidth();
    if (!tickerTrack) {
        return;
    }

    stopTickerScroll();
    let repeats = estimateTickerRepeats(quotes, marqueeWidth);
    let setHtml = buildTickerSetHtml(quotes, repeats);

    tickerTrack.innerHTML =
        `<div class="ticker-set">${setHtml}</div>` +
        `<div class="ticker-set" aria-hidden="true">${setHtml}</div>`;

    const firstSet = tickerTrack.querySelector('.ticker-set');
    while (firstSet && firstSet.offsetWidth < marqueeWidth + 40 && repeats < 24) {
        repeats += 1;
        setHtml = buildTickerSetHtml(quotes, repeats);
        tickerTrack.innerHTML =
            `<div class="ticker-set">${setHtml}</div>` +
            `<div class="ticker-set" aria-hidden="true">${setHtml}</div>`;
    }

    tickerTrack.dataset.tickerReady = '1';
    scheduleTickerScrollStart();
}

/**
 * Update ticker bar with real market data (tiled for seamless scroll)
 */
function updateTickerDisplay(quotes) {
    latestTickerQuotes = quotes;
    if (patchTickerQuotes(quotes)) {
        return;
    }
    renderTickerTrack(quotes);
}

function setupTickerResizeHandler() {
    window.addEventListener('resize', () => {
        if (tickerResizeTimer) {
            clearTimeout(tickerResizeTimer);
        }

        tickerResizeTimer = setTimeout(() => {
            const tickerTrack = document.getElementById('tickerTrack');
            if (!tickerTrack || tickerTrack.dataset.tickerReady !== '1') {
                return;
            }

            const firstSet = tickerTrack.querySelector('.ticker-set');
            const marqueeWidth = getTickerMarqueeWidth();
            if (!firstSet || firstSet.offsetWidth < marqueeWidth + 40) {
                const sourceQuotes = latestTickerQuotes.length
                    ? latestTickerQuotes
                    : MAG7_TICKER_SYMBOLS.map((symbol) => ({ symbol, price: null, changePercent: null }));
                tickerTrack.dataset.tickerReady = '0';
                stopTickerScroll();
                renderTickerTrack(sourceQuotes);
            } else {
                tickerScrollSetWidth = getTickerSetWidth(tickerTrack);
            }
        }, 200);
    });
}

/**
 * Load live market data from Alpaca API (Magnificent 7)
 */
async function loadMarketTicker() {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 45000);

    try {
        const symbols = MAG7_TICKER_SYMBOLS.join(',');
        const response = await fetch(`${API_BASE}/ticker?symbols=${symbols}`, {
            signal: controller.signal,
        });
        const data = await response.json().catch(() => ({}));

        if (data.quotes && data.quotes.length > 0) {
            updateTickerDisplay(data.quotes);
            console.log('✅ Market ticker updated:', data.quotes.length, 'symbols');
            return;
        }

        const message = data.error
            || (response.ok ? 'Market data temporarily unavailable' : `Market data unavailable (HTTP ${response.status})`);
        showTickerStatus(message);
        console.warn('Market ticker returned no quotes:', message);
    } catch (error) {
        const message = error.name === 'AbortError'
            ? 'Market data is taking longer than expected — retrying…'
            : 'Could not load market data';
        showTickerStatus(message);
        console.warn('Could not fetch market ticker:', error.message);
    } finally {
        clearTimeout(timeoutId);
    }
}

function showTickerStatus(message) {
    const tickerTrack = document.getElementById('tickerTrack');
    if (!tickerTrack || tickerTrack.dataset.tickerReady === '1') {
        return;
    }
    stopTickerScroll();
    tickerTrack.dataset.tickerReady = '0';
    tickerTrack.style.transform = 'none';
    tickerTrack.innerHTML = `<div class="ticker-placeholder">${message}</div>`;
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
        // Canonical Dow-30 — must mirror backend validator.DJIA_30
        // (pinned by dashboard/backend/tests/test_djia30_universe.py).
        assets: ['AAPL', 'AMGN', 'AMZN', 'AXP', 'BA', 'CAT', 'CRM', 'CSCO', 'CVX', 'DIS',
                 'GOOGL', 'GS', 'HD', 'HON', 'IBM', 'JNJ', 'JPM', 'KO', 'MCD', 'MMM',
                 'MRK', 'MSFT', 'NKE', 'NVDA', 'PG', 'SHW', 'TRV', 'UNH', 'V', 'WMT']
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

/**
 * Load the saved sub-agent pipeline for an agent (backend or localStorage).
 */
function loadAgentPipelineForBacktest(agent) {
    if (!agent) return null;
    if (Array.isArray(agent.pipeline) && agent.pipeline.length) {
        return agent.pipeline;
    }
    if (!agent.agent_id || typeof agent.agent_id !== 'string') return null;
    try {
        const raw = localStorage.getItem(`agent-pipeline-config:${agent.agent_id}`);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed.subAgents) && parsed.subAgents.length) {
            return parsed.subAgents.map((sub) => ({
                id: sub.id,
                presetKey: sub.presetKey,
                label: sub.label,
                prompt: sub.prompt,
                outputFormat: sub.outputFormat,
            }));
        }
    } catch (error) {
        console.warn('Could not load local pipeline config:', error);
    }
    return null;
}

/**
 * Resolve the active agent object for backtest (API-backed or mock list).
 */
function resolveActiveAgentForBacktest() {
    if (window.ACTIVE_AGENT?.agent_id) {
        return window.ACTIVE_AGENT;
    }
    const activeId = localStorage.getItem(ACTIVE_AGENT_KEY);
    if (!activeId) return null;
    if (typeof allAgents !== 'undefined' && Array.isArray(allAgents)) {
        const found = allAgents.find((a) => a.agent_id === activeId);
        if (found) return found;
    }
    return null;
}

function formatBacktestElapsed(seconds) {
    const total = Math.max(0, Number(seconds) || 0);
    const minutes = Math.floor(total / 60);
    const secs = total % 60;
    return `${minutes}:${String(secs).padStart(2, '0')}`;
}

function showBacktestRunProgress(show, { isError = false } = {}) {
    const panel = document.getElementById('backtestRunProgress');
    if (!panel) return;
    panel.hidden = !show;
    panel.classList.toggle('is-error', !!isError);
}

function updateBacktestRunProgress({ elapsedSeconds = 0, message = '', maxSeconds = BACKTEST_POLL_MAX_SECONDS, stepPct = null }) {
    const elapsedEl = document.getElementById('backtestRunElapsed');
    const messageEl = document.getElementById('backtestRunProgressMessage');
    const barEl = document.getElementById('backtestRunProgressBar');
    const elapsed = Math.max(0, Number(elapsedSeconds) || 0);

    if (elapsedEl) elapsedEl.textContent = formatBacktestElapsed(elapsed);
    if (messageEl && message) messageEl.textContent = message;
    if (barEl) {
        const pct = Number.isFinite(stepPct)
            ? Math.min(99, Math.round(stepPct))
            : Math.min(95, Math.round((elapsed / maxSeconds) * 100));
        barEl.style.width = `${pct}%`;
    }
}

function getPerformanceChartOptions(timestampMeta) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
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
                    title(context) {
                        if (context.length > 0) {
                            const dataIndex = context[0].dataIndex;
                            const timestamp = timestampMeta.timestamps[dataIndex];
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
                    label(context) {
                        const value = context.parsed.y;
                        return `${context.dataset.label}: $${value.toFixed(0)}`;
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
                    callback(value) {
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
    };
}

function initLiveBacktestChart() {
    const perfCtx = document.getElementById('performanceChart');
    if (!perfCtx || !perfCtx.getContext) return;

    if (chartInstance) {
        chartInstance.destroy();
    }

    liveBacktestChartMeta = { timestamps: [] };
    liveBacktestChartActive = true;
    const ctx = perfCtx.getContext('2d');
    chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Agent (live)',
                data: [],
                borderColor: '#4FC3F7',
                backgroundColor: 'transparent',
                borderWidth: 2.5,
                tension: 0,
                fill: false,
                pointRadius: 0,
                pointHoverRadius: 5,
            }],
        },
        options: getPerformanceChartOptions(liveBacktestChartMeta),
    });
}

function updateLiveBacktestChart(progress) {
    if (!liveBacktestChartActive || !chartInstance || !progress) return;

    const curve = progress.equity_curve;
    if (!Array.isArray(curve) || curve.length === 0) return;

    liveBacktestChartMeta.timestamps = curve.map((point) => point.timestamp);
    chartInstance.data.labels = formatTimestamps(liveBacktestChartMeta.timestamps);
    chartInstance.data.datasets[0].data = curve.map((point) => point.equity);
    chartInstance.update('none');
}

function normalizeTradeRecord(trade) {
    const side = String(trade?.side || trade?.action || '').toUpperCase();
    const quantity = Number(trade?.quantity ?? trade?.shares ?? 0);
    const price = Number(trade?.price || 0);
    const value = Number(
        trade?.value ?? trade?.total_value ?? trade?.cost ?? trade?.proceeds ?? quantity * price
    );
    return {
        timestamp: trade?.timestamp,
        side,
        symbol: trade?.symbol || '--',
        quantity,
        price,
        value,
    };
}

function formatTradeTimestamp(ts) {
    if (!ts) return '--';
    try {
        const date = new Date(ts);
        return date.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false,
        });
    } catch (e) {
        return String(ts);
    }
}

function renderTradingLog(trades, { emptyMessage = 'No trades yet.' } = {}) {
    const tbody = document.getElementById('tradingLogBody');
    if (!tbody) return;

    tradingLogCache = Array.isArray(trades) ? trades.map(normalizeTradeRecord) : [];
    let filtered = tradingLogCache;
    if (tradingLogFilter === 'buy') {
        filtered = tradingLogCache.filter((trade) => trade.side === 'BUY');
    } else if (tradingLogFilter === 'sell') {
        filtered = tradingLogCache.filter((trade) => trade.side === 'SELL');
    }

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="trading-log-empty">${emptyMessage}</td></tr>`;
        return;
    }

    tbody.innerHTML = filtered.map((trade) => {
        const actionClass = trade.side === 'SELL' ? 'action-sell' : 'action-buy';
        const actionLabel = trade.side === 'SELL' ? 'SELL' : 'BUY';
        const totalValue = trade.value.toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
        return `<tr>
            <td>${formatTradeTimestamp(trade.timestamp)}</td>
            <td><span class="${actionClass}">${actionLabel}</span></td>
            <td>${trade.symbol}</td>
            <td>${trade.quantity} shares</td>
            <td>$${trade.price.toFixed(2)}</td>
            <td>$${totalValue}</td>
        </tr>`;
    }).join('');
}

function clearTradingLog(message = 'Waiting for trades…') {
    tradingLogCache = [];
    renderTradingLog([], { emptyMessage: message });
}

function updateLiveTradingLog(progress) {
    if (!progress?.trades) return;
    renderTradingLog(progress.trades);
}

async function loadTradingLogForRun(runId) {
    if (!runId) {
        clearTradingLog('Run a backtest to see trades here.');
        return;
    }
    try {
        const data = await API.get(`${API_BASE}/runs/${encodeURIComponent(runId)}/trades?t=${Date.now()}`);
        renderTradingLog(data.trades || [], { emptyMessage: 'No trades recorded for this run.' });
    } catch (error) {
        console.warn('Could not load trades:', error.message);
        clearTradingLog('No trades recorded for this run.');
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

    const assets = getSelectedAssets();
    const modelSelect = document.getElementById('modelSelect');
    const activeAgent = getSelectedBacktestAgent();
    if (!activeAgent) {
        alert('Please create or select an agent first.');
        return;
    }

    await activateAgent(activeAgent);
    syncModelSelectFromAgent(activeAgent);
    const pipeline = loadAgentPipelineForBacktest(activeAgent);
    const model = activeAgent?.model_name
        || (modelSelect ? modelSelect.value : 'claude-haiku-4.5');
    
    console.log(`Running backtest: ${startDate} to ${endDate}`);
    console.log(`Assets: ${assets.join(', ')}`);
    console.log(`Model: ${model}`);
    if (activeAgent?.agent_id) {
        console.log(`Agent: ${activeAgent.name} (${activeAgent.agent_id})`);
    }
    if (pipeline?.length) {
        console.log(`Sub-agent pipeline: ${pipeline.length} step(s)`);
    }
    
    const btn = document.querySelector('.run-backtest-btn');
    btn.textContent = '⏳ Running...';
    btn.disabled = true;
    showBacktestRunProgress(true);
    initLiveBacktestChart();
    clearTradingLog('Backtest running… trades will appear here.');
    updateBacktestRunProgress({
        elapsedSeconds: 0,
        message: pipeline?.length
            ? `Running ${pipeline.length}-step agent pipeline…`
            : 'Starting backtest…',
    });
    
    try {
        // Call API with session ID, assets, and model
        const params = new URLSearchParams({
            start_date: startDate,
            end_date: endDate,
            assets: assets.join(','),
            model: model
        });
        const payload = {
            start_date: startDate,
            end_date: endDate,
            model,
        };
        if (activeAgent?.agent_id && !String(activeAgent.agent_id).startsWith('mock-')) {
            payload.agent_id = activeAgent.agent_id;
        }
        if (pipeline?.length) {
            payload.pipeline = pipeline;
        }
        const data = await API.post(`${API_BASE}/backtest/run?${params.toString()}`, payload);
        
        if (!data.success) {
            console.error('❌ Backtest failed:', data.error || 'Unknown error');
            showBacktestRunProgress(true, { isError: true });
            updateBacktestRunProgress({
                elapsedSeconds: 0,
                message: data.error || 'Failed to start backtest.',
            });
            btn.textContent = '❌ Error - Try Again';
            btn.disabled = false;
            setTimeout(() => {
                btn.textContent = '▶ Run Backtest';
                showBacktestRunProgress(false);
            }, 5000);
            return;
        }
        
        console.log('✅ Backtest started:', data.message);
        
        // Poll for status (now session-aware)
        await pollBacktestStatus(btn);
        
    } catch (error) {
        console.error('❌ Error starting backtest:', error.message);
        showBacktestRunProgress(true, { isError: true });
        updateBacktestRunProgress({
            elapsedSeconds: 0,
            message: error.message || 'Failed to start backtest.',
        });
        btn.textContent = '❌ Error - Try Again';
        btn.disabled = false;
        setTimeout(() => {
            btn.textContent = '▶ Run Backtest';
            showBacktestRunProgress(false);
        }, 5000);
    }
}

/**
 * Poll backtest status until complete
 */
async function pollBacktestStatus(btn) {
    const maxAttempts = BACKTEST_POLL_MAX_SECONDS;
    let attempts = 0;
    let isComplete = false;
    
    return new Promise((resolve) => {
        const interval = setInterval(async () => {
            if (isComplete) return; // Prevent re-entry
            
            attempts++;
            const elapsedSeconds = attempts;
            
            try {
                const status = await API.get(`${API_BASE}/backtest/status`);
                const serverElapsed = Number(status.elapsed_seconds);
                const displayElapsed = Number.isFinite(serverElapsed) && serverElapsed > 0
                    ? serverElapsed
                    : elapsedSeconds;

                if (status.running) {
                    if (status.progress) {
                        updateLiveBacktestChart(status.progress);
                        updateLiveTradingLog(status.progress);
                    }
                    const step = Number(status.progress?.step);
                    const total = Number(status.progress?.total_steps);
                    const stepPct = Number.isFinite(step) && Number.isFinite(total) && total > 0
                        ? (100 * step / total)
                        : null;
                    updateBacktestRunProgress({
                        elapsedSeconds: displayElapsed,
                        message: status.message || 'Backtest is running…',
                        stepPct,
                    });
                    if (btn) {
                        btn.textContent = `⏳ Running… ${formatBacktestElapsed(displayElapsed)}`;
                    }
                }
                
                if (!status.running) {
                    isComplete = true;
                    clearInterval(interval);
                    liveBacktestChartActive = false;
                    
                    if (status.error) {
                        console.error('❌ Backtest error:', status.error);
                        showBacktestRunProgress(true, { isError: true });
                        updateBacktestRunProgress({
                            elapsedSeconds: displayElapsed,
                            message: status.error,
                        });
                    } else if (status.success) {
                        console.log('✅ Backtest completed:', status.message);
                        console.log(`   Found ${status.runs_count} runs`);
                        updateBacktestRunProgress({
                            elapsedSeconds: displayElapsed,
                            message: `Completed in ${formatBacktestElapsed(displayElapsed)}.`,
                        });
                        
                        console.log('→ Reloading backtest data...');
                        localStorage.removeItem(SELECTED_BACKTEST_RUN_KEY);
                        const runSelect = document.getElementById('backtestRunSelect');
                        if (runSelect) runSelect.value = '';
                        window.SELECTED_RUN = null;
                        await loadData();
                        
                        console.log('→ Refreshing performance metrics...');
                        await loadPerformanceMetrics();
                        
                        console.log('✅ Dashboard updated with latest backtest results');
                        setTimeout(() => showBacktestRunProgress(false), 2500);
                    } else {
                        showBacktestRunProgress(false);
                    }
                    
                    if (btn) {
                        btn.textContent = '▶ Run Backtest';
                        btn.disabled = false;
                    }
                    resolve();
                    return;
                }
                
                if (attempts >= maxAttempts) {
                    isComplete = true;
                    clearInterval(interval);
                    console.warn('⚠️ Backtest timeout - still running after 10 minutes');
                    showBacktestRunProgress(true, { isError: true });
                    updateBacktestRunProgress({
                        elapsedSeconds: maxAttempts,
                        message: 'Timed out after 10 minutes. The backtest may still be running in the background.',
                    });
                    if (btn) {
                        btn.textContent = '▶ Run Backtest';
                        btn.disabled = false;
                    }
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
 * Resolve page from URL for legacy deep links.
 */
// Persist the current tab so a page refresh restores it instead of going home.
function persistNavigation() {
    try {
        localStorage.setItem(
            NAV_STATE_KEY,
            JSON.stringify({
                page: currentPage,
                playgroundTab,
                competitionTab,
            }),
        );
    } catch (error) {
        /* localStorage unavailable — ignore */
    }
}

function clearNavBootState() {
    const html = document.documentElement;
    html.removeAttribute('data-nav-boot');
    html.removeAttribute('data-nav-page');
    html.removeAttribute('data-nav-playground-tab');
    html.removeAttribute('data-nav-competition-tab');
}

function applyInitialNavigation() {
    const initial = resolveInitialNavigation();
    navigateToPage(initial.page, {
        playgroundTab: initial.playgroundTab || 'agents',
        competitionTab: initial.competitionTab || 'leaderboard',
    });
    if (typeof initHomePage === 'function') {
        initHomePage();
    }
}

function resolveInitialNavigation() {
    const params = new URLSearchParams(window.location.search);
    const view = params.get('view') || params.get('mode');
    const hash = window.location.hash.replace('#', '');
    const legacy = view || hash;

    const legacyMap = {
        home: { page: 'home' },
        community: { page: 'community' },
        backtest: { page: 'playground', playgroundTab: 'backtest' },
        paper: { page: 'playground', playgroundTab: 'paper' },
        contest: { page: 'competition', competitionTab: 'leaderboard' },
        'my-algo': { page: 'playground', playgroundTab: 'agents' },
    };

    // An explicit URL view/hash always wins.
    if (legacy && legacyMap[legacy]) {
        return legacyMap[legacy];
    }

    // Otherwise restore the last visited tab across refreshes.
    try {
        const saved = JSON.parse(localStorage.getItem(NAV_STATE_KEY) || 'null');
        const validPages = ['home', 'playground', 'competition', 'community'];
        if (saved && validPages.includes(saved.page)) {
            return saved;
        }
    } catch (error) {
        /* corrupt/unavailable state — fall through to home */
    }

    return { page: 'home' };
}

function updatePlaygroundSubtabs() {
    document.querySelectorAll('[data-playground-tab]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.playgroundTab === playgroundTab);
    });
}

function updateCompetitionSubtabs() {
    document.querySelectorAll('[data-competition-tab]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.competitionTab === competitionTab);
    });
}

function showPlaygroundPanel(tab) {
    playgroundTab = tab;
    updatePlaygroundSubtabs();

    const agents = document.getElementById('playgroundAgentsPanel');
    const backtest = document.querySelector('.main-container');
    const paper = document.getElementById('paperTradingView');

    if (agents) agents.style.display = tab === 'agents' ? 'block' : 'none';
    if (backtest) backtest.style.display = tab === 'backtest' ? 'grid' : 'none';
    if (paper) paper.style.display = tab === 'paper' ? 'block' : 'none';

    if (tab === 'backtest') {
        currentMode = 'backtest';
        populateBacktestAgentSelect();
        loadData();
        loadPerformanceMetrics();
    } else if (tab === 'paper') {
        currentMode = 'paper';
        loadPaperTradingData();
    } else {
        currentMode = 'agents';
        if (typeof renderPortfolio === 'function') renderPortfolio(allAgents.map(decorateAgent));
        loadAgents();
    }

    persistNavigation();
}

function showCompetitionPanel(tab) {
    competitionTab = tab;
    updateCompetitionSubtabs();

    const leaderboard = document.getElementById('leaderboardView');
    const participants = document.getElementById('competitionParticipantsPanel');
    const about = document.getElementById('competitionAboutPanel');

    if (leaderboard) leaderboard.style.display = tab === 'leaderboard' ? 'flex' : 'none';
    if (participants) participants.style.display = tab === 'participants' ? 'block' : 'none';
    if (about) about.style.display = tab === 'about' ? 'block' : 'none';

    if (tab === 'leaderboard') {
        currentMode = 'contest';
        loadLeaderboardData();
    } else {
        currentMode = tab;
    }

    persistNavigation();
}

function navigateToPage(page, options = {}) {
    console.log('Navigating to page:', page, options);

    // "My Agents" now lives as a Playground subtab; redirect legacy links.
    if (page === 'agents') {
        page = 'playground';
        options = { ...options, playgroundTab: options.playgroundTab || 'agents' };
    }

    currentPage = page;

    if (options.playgroundTab) playgroundTab = options.playgroundTab;
    if (options.competitionTab) competitionTab = options.competitionTab;

    document.querySelectorAll('.primary-nav .mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === page);
    });

    const homeView = document.getElementById('homeView');
    const playgroundView = document.getElementById('playgroundView');
    const competitionView = document.getElementById('competitionView');
    const communityView = document.getElementById('communityView');
    const backtestPanel = document.querySelector('.main-container');
    const paperView = document.getElementById('paperTradingView');
    const myAlgoView = document.getElementById('myTradingAlgoView');
    const leaderboardView = document.getElementById('leaderboardView');

    const hide = (el) => {
        if (el) el.style.display = 'none';
    };

    hide(homeView);
    hide(playgroundView);
    hide(competitionView);
    hide(communityView);
    hide(backtestPanel);
    hide(paperView);
    hide(myAlgoView);
    hide(leaderboardView);
    hide(document.getElementById('playgroundAgentsPanel'));
    hide(document.getElementById('competitionParticipantsPanel'));
    hide(document.getElementById('competitionAboutPanel'));

    if (page === 'home') {
        currentMode = 'home';
        if (homeView) homeView.style.display = 'block';
        if (typeof onHomePageShow === 'function') onHomePageShow();
    } else {
        if (typeof onHomePageHide === 'function') onHomePageHide();
        if (page === 'playground') {
            if (playgroundView) playgroundView.style.display = 'block';
            showPlaygroundPanel(playgroundTab);
        } else if (page === 'competition') {
            if (competitionView) competitionView.style.display = 'block';
            showCompetitionPanel(competitionTab);
        } else if (page === 'community') {
            if (communityView) communityView.style.display = 'block';
        }
    }

    const nav = document.getElementById('primaryNav');
    const menuToggle = document.getElementById('navMenuToggle');
    if (nav) nav.classList.remove('open');
    if (menuToggle) menuToggle.setAttribute('aria-expanded', 'false');

    clearNavBootState();
    persistNavigation();
}

function switchPlaygroundTab(tab) {
    if (currentPage !== 'playground') {
        navigateToPage('playground', { playgroundTab: tab });
        return;
    }
    showPlaygroundPanel(tab);
}

function switchCompetitionTab(tab) {
    if (currentPage !== 'competition') {
        navigateToPage('competition', { competitionTab: tab });
        return;
    }
    showCompetitionPanel(tab);
}

function openAddAgentModal() {
    const modal = document.getElementById('addAgentModal');
    if (modal) modal.hidden = false;
}

function closeAddAgentModal() {
    const modal = document.getElementById('addAgentModal');
    if (modal) modal.hidden = true;
}

function initNavigation() {
    document.querySelectorAll('.primary-nav .mode-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            navigateToPage(e.currentTarget.dataset.mode);
        });
    });

    document.querySelectorAll('[data-playground-tab]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            switchPlaygroundTab(e.currentTarget.dataset.playgroundTab);
        });
    });

    document.querySelectorAll('[data-competition-tab]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            switchCompetitionTab(e.currentTarget.dataset.competitionTab);
        });
    });

    document.getElementById('homeOpenPlaygroundBtn')?.addEventListener('click', () => {
        navigateToPage('playground', { playgroundTab: 'agents' });
    });

    document.getElementById('homeViewCompetitionBtn')?.addEventListener('click', () => {
        navigateToPage('competition', { competitionTab: 'leaderboard' });
    });

    document.getElementById('homeViewMarketPulseBtn')?.addEventListener('click', () => {
        navigateToPage('playground', { playgroundTab: 'agents' });
    });

    document.querySelectorAll('[data-home-nav]').forEach(btn => {
        btn.addEventListener('click', () => {
            const target = btn.dataset.homeNav;
            if (target === 'agents') {
                navigateToPage('playground', { playgroundTab: 'agents' });
            } else if (target === 'playground') {
                navigateToPage('playground', { playgroundTab: 'agents' });
            } else if (target === 'discord') {
                const discordUrl = document.getElementById('homeConnectDiscordBtn')?.href
                    || document.getElementById('openDiscordBtn')?.href
                    || 'https://discord.gg/9HnQ6XDG98';
                window.open(discordUrl, '_blank', 'noopener,noreferrer');
            }
        });
    });

    document.querySelectorAll('.agent-view-playground').forEach(btn => {
        btn.addEventListener('click', () => {
            navigateToPage('playground', { playgroundTab: 'agents' });
        });
    });

    document.getElementById('agentFilterSelect')?.addEventListener('change', applyAgentFilters);
    document.getElementById('agentSearchInput')?.addEventListener('input', applyAgentFilters);
    document.getElementById('agentViewGrid')?.addEventListener('click', () => setAgentViewMode('grid'));
    document.getElementById('agentViewList')?.addEventListener('click', () => setAgentViewMode('list'));

    document.getElementById('addAgentBtn')?.addEventListener('click', openAddAgentModal);
    document.getElementById('addAgentModalClose')?.addEventListener('click', closeAddAgentModal);
    document.getElementById('addAgentModalBackdrop')?.addEventListener('click', closeAddAgentModal);
    document.getElementById('connectExternalAgentBtn')?.addEventListener('click', openCreateExternalAgentModal);
    document.getElementById('createExternalAgentModalClose')?.addEventListener('click', closeCreateExternalAgentModal);
    document.getElementById('createExternalAgentModalBackdrop')?.addEventListener('click', closeCreateExternalAgentModal);
    document.getElementById('createExternalAgentForm')?.addEventListener('submit', submitCreateExternalAgent);
    document.getElementById('createBuiltinAgentBtn')?.addEventListener('click', openCreateBuiltinAgentModal);
    document.getElementById('createBuiltinAgentModalClose')?.addEventListener('click', closeCreateBuiltinAgentModal);
    document.getElementById('createBuiltinAgentModalBackdrop')?.addEventListener('click', closeCreateBuiltinAgentModal);
    document.getElementById('createBuiltinAgentForm')?.addEventListener('submit', submitCreateBuiltinAgent);
    document.getElementById('agentCredentialsModalClose')?.addEventListener('click', closeAgentCredentialsModal);
    document.getElementById('agentCredentialsModalBackdrop')?.addEventListener('click', closeAgentCredentialsModal);

    document.getElementById('competitionRulesBtn')?.addEventListener('click', () => {
        if (currentPage !== 'competition') {
            navigateToPage('competition', { competitionTab: 'about' });
        } else {
            switchCompetitionTab('about');
        }
    });

    document.getElementById('navMenuToggle')?.addEventListener('click', () => {
        const nav = document.getElementById('primaryNav');
        const toggle = document.getElementById('navMenuToggle');
        if (!nav || !toggle) return;
        const isOpen = nav.classList.toggle('open');
        toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    });

}

/**
 * Switch between modes (legacy compatibility)
 */
function switchMode(mode) {
    console.log('Switching to mode:', mode);

    const legacyMap = {
        backtest: { page: 'playground', playgroundTab: 'backtest' },
        paper: { page: 'playground', playgroundTab: 'paper' },
        contest: { page: 'competition', competitionTab: 'leaderboard' },
        'my-algo': { page: 'playground', playgroundTab: 'agents' },
        home: { page: 'home' },
        agents: { page: 'playground', playgroundTab: 'agents' },
        playground: { page: 'playground', playgroundTab: 'agents' },
        competition: { page: 'competition', competitionTab: 'leaderboard' },
    };

    const target = legacyMap[mode] || { page: mode };
    navigateToPage(target.page, {
        playgroundTab: target.playgroundTab,
        competitionTab: target.competitionTab,
    });
}

function isMyAlgoRun(run) {
    return run && run.run_id && String(run.run_id).startsWith('algo_');
}

function isExternalAgentRun(run) {
    return run && run.run_id && String(run.run_id).startsWith('ext_');
}

function latestRun(runs) {
    if (!runs || !runs.length) return null;
    return runs.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))[0];
}

function scopedExternalRuns(sessionRuns, activeName) {
    const externalRuns = sessionRuns.filter(isExternalAgentRun);
    if (!activeName) return externalRuns;
    const scoped = externalRuns.filter((r) => r.agent_name === activeName);
    return scoped.length ? scoped : externalRuns;
}

function formatBacktestRunReturn(run) {
    if (run.total_return == null) return '—';
    const pct = Math.abs(run.total_return) <= 1 ? run.total_return * 100 : run.total_return;
    const sign = pct >= 0 ? '+' : '';
    return `${sign}${pct.toFixed(2)}%`;
}

function formatBacktestRunPrimary(run) {
    const dates = [run.start_date, run.end_date].filter(Boolean).join(' → ');
    return `${dates || run.run_id} · ${formatBacktestRunReturn(run)}`;
}

function formatBacktestRunSecondary(run) {
    const when = run.created_at ? new Date(run.created_at).toLocaleString() : '';
    const cost = formatUsd(run.est_cost_usd);
    const costLabel = cost && Number(run.est_cost_usd) > 0 ? cost : '';
    return [costLabel, when].filter(Boolean).join(' · ');
}

function formatBacktestRunLabel(run) {
    return [formatBacktestRunPrimary(run), formatBacktestRunSecondary(run)].filter(Boolean).join(' · ');
}

window.formatBacktestRunPrimary = formatBacktestRunPrimary;
window.formatBacktestRunSecondary = formatBacktestRunSecondary;
window.formatBacktestRunLabel = formatBacktestRunLabel;

function resolveSelectedExternalRun(externalRuns) {
    const selectedId = localStorage.getItem(SELECTED_BACKTEST_RUN_KEY);
    if (selectedId) {
        const match = externalRuns.find((r) => r.run_id === selectedId);
        if (match) return match;
    }
    return latestRun([...externalRuns]);
}

function populateBacktestRunSelector(externalRuns) {
    const select = document.getElementById('backtestRunSelect');
    if (!select) return;

    const sorted = [...externalRuns].sort(
        (a, b) => (b.created_at || '').localeCompare(a.created_at || ''),
    );

    if (!sorted.length) {
        select.innerHTML = '';
        select.hidden = true;
        return;
    }

    select.hidden = false;
    const previous = select.value || localStorage.getItem(SELECTED_BACKTEST_RUN_KEY);
    select.innerHTML = sorted
        .map(
            (run) =>
                `<option value="${escapeHtml(run.run_id)}">${escapeHtml(formatBacktestRunLabel(run))}</option>`,
        )
        .join('');

    const selectedId =
        previous && sorted.some((r) => r.run_id === previous)
            ? previous
            : sorted[0].run_id;
    select.value = selectedId;
    localStorage.setItem(SELECTED_BACKTEST_RUN_KEY, selectedId);
}

function resolveBaselineRunIds(extRun, sessionRuns) {
    if (!extRun) return { djia: null, buyhold: null };

    let djia = extRun.baseline_djia_run_id || null;
    let buyhold = extRun.baseline_buyhold_run_id || null;
    if (djia && buyhold) {
        return { djia, buyhold };
    }

    const extCreated = extRun.created_at || '';
    const { start_date: startDate, end_date: endDate } = extRun;
    const extRuns = sessionRuns
        .filter(isExternalAgentRun)
        .sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''));
    const extIdx = extRuns.findIndex((r) => r.run_id === extRun.run_id);
    const nextExtCreated =
        extIdx >= 0 && extIdx < extRuns.length - 1
            ? extRuns[extIdx + 1].created_at
            : null;

    function pick(agentName) {
        const candidates = sessionRuns
            .filter(
                (r) =>
                    r.agent_name === agentName &&
                    r.start_date === startDate &&
                    r.end_date === endDate &&
                    (r.created_at || '') >= extCreated &&
                    (!nextExtCreated || (r.created_at || '') < nextExtCreated),
            )
            .sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''));
        return candidates[0]?.run_id || null;
    }

    return {
        djia: djia || pick('DJIA'),
        buyhold: buyhold || pick('buy-and-hold'),
    };
}

function findLatestRunByAgent(runs, agentName) {
    const matched = runs.filter(r => r.agent_name === agentName);
    if (!matched.length) return null;
    return matched.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))[0];
}

// Baseline comparison series. They appear on the plot but are never listed or
// selectable as standalone runs.
const BASELINE_AGENT_NAMES = ['DJIA', 'buy-and-hold'];

function isBaselineRun(run) {
    return !!run && BASELINE_AGENT_NAMES.includes(run.agent_name);
}

function _runTime(value) {
    return new Date(String(value || '').replace(' ', 'T')).getTime() || 0;
}

// The selected run drives the whole backtest view. Built-in and external agents
// take the same path: prefer the explicitly clicked/selected run_id, else the
// agent's most recent (non-baseline) run.
function resolveSelectedRun(sessionRuns) {
    const realRuns = (sessionRuns || []).filter(r => !isBaselineRun(r));
    if (!realRuns.length) return null;
    const selectedId = localStorage.getItem(SELECTED_BACKTEST_RUN_KEY);
    if (selectedId) {
        const match = realRuns.find(r => r.run_id === selectedId);
        if (match) return match;
    }
    return latestRun(realRuns);
}

// Find the DJIA / buy-and-hold runs that belong to a given run: same session,
// same date window, created closest in time to the run (baselines are written
// seconds apart from the agent run).
function resolveBaselinesForRun(run, sessionRuns) {
    if (!run) return { djia: null, buyhold: null };
    const anchor = _runTime(run.created_at);
    function pick(agentName, explicitId) {
        if (explicitId) return explicitId;
        const candidates = (sessionRuns || []).filter(r =>
            r.agent_name === agentName &&
            r.start_date === run.start_date &&
            r.end_date === run.end_date);
        if (!candidates.length) return null;
        candidates.sort((a, b) =>
            Math.abs(_runTime(a.created_at) - anchor) - Math.abs(_runTime(b.created_at) - anchor));
        return candidates[0].run_id;
    }
    return {
        djia: pick('DJIA', run.baseline_djia_run_id),
        buyhold: pick('buy-and-hold', run.baseline_buyhold_run_id),
    };
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

            // Selectable runs are the agent's own runs; baselines are plotted
            // for comparison but never listed/selected. Built-in and external
            // agents share this path: the selected run_id drives everything.
            const selectableRuns = sessionRuns.filter(r => !isBaselineRun(r));
            populateBacktestRunSelector(selectableRuns);
            const selectedRun = resolveSelectedRun(sessionRuns);

            window.SELECTED_RUN = selectedRun;
            window.MY_ALGO_RUN_ID = isMyAlgoRun(selectedRun) ? selectedRun.run_id : null;
            window.EXTERNAL_AGENT_RUN_ID = isExternalAgentRun(selectedRun) ? selectedRun.run_id : null;

            if (!selectedRun) {
                console.warn('No backtest runs for this session');
                comparisonData = null;
                backtestChartData = null;
                displayNoMetrics();
                clearTradingLog('Run a backtest to see trades here.');
                return;
            }

            localStorage.setItem(SELECTED_BACKTEST_RUN_KEY, selectedRun.run_id);

            const chartUrl = `${API_BASE}/api/backtest/${encodeURIComponent(selectedRun.run_id)}/chart-data?t=${Date.now()}`;
            backtestChartData = await API.get(chartUrl);
            console.log('Loaded backtest chart data:', backtestChartData);

            initializeCharts();
            displayPerformanceMetrics(selectedRun);
            await loadTradingLogForRun(selectedRun.run_id);
        }
        
    } catch (error) {
        console.error('Error loading data:', error);
    }
}

/**
 * Initialize charts with real data from backend.
 * Agent vs DJIA index + Nasdaq-100 (same baselines as Discord plot.png).
 */
function initializeCharts() {
    if (!backtestChartData || !backtestChartData.series || !backtestChartData.series.length) {
        console.warn('No backtest chart data available');
        return;
    }

    const perfCtx = document.getElementById('performanceChart');
    if (perfCtx && perfCtx.getContext) {
        if (chartInstance) {
            chartInstance.destroy();
        }

        const ctx = perfCtx.getContext('2d');
        const { timestamps, x_labels: xLabels, series } = backtestChartData;

        const datasets = series.map((entry) => ({
            label: entry.label,
            data: entry.values,
            borderColor: entry.color,
            backgroundColor: 'transparent',
            borderWidth: 2.5,
            borderDash: entry.dashed ? [6, 4] : [],
            tension: 0,
            fill: false,
            pointRadius: 0,
            pointHoverRadius: 5,
        }));

        chartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: xLabels,
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
                            font: { size: 11, weight: '500' },
                            maxRotation: 0,
                            autoSkip: false,
                            callback: function(_value, index) {
                                const label = xLabels[index];
                                return label || undefined;
                            },
                        },
                        grid: {
                            display: false,
                            drawBorder: false,
                        }
                    }
                }
            }
        });

        liveBacktestChartActive = false;
        console.log('✅ Chart initialized -', series.map((s) => s.label).join(', '));
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
        tension: 0,
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
            tension: 0,
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
