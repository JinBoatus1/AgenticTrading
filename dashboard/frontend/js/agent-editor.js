/**
 * agent-editor.js — Fullscreen agent pipeline editor (sub-agent chain).
 * Pipeline config: localStorage. Agent name/description: PATCH /api/v1/agents/{id}.
 */
(function () {
  'use strict';

  const STORAGE_PREFIX = 'agent-pipeline-config:';
  const NAME_OVERRIDE_PREFIX = 'agent-name-override:';
  const API_BASE = window.location.origin;

  // Demo/mock agents (see MOCK_AGENTS in app.js) only exist in the frontend —
  // they have no database row, so PATCH would 404. We persist their edits
  // locally instead so the rename is still reflected in the UI.
  function isDemoAgent(agentId) {
    return typeof agentId === 'string' && agentId.startsWith('mock-');
  }

  const SUB_AGENT_PRESETS = [
    {
      presetKey: 'info_gather',
      label: 'Information Gathering',
      defaultPrompt:
        'You are the information-gathering sub-agent. Collect key facts relevant to trading decisions from market data, news, and macro events. Filter noise and keep high-confidence facts and indicator changes.',
      defaultOutputFormat:
        'JSON: { "timestamp": "ISO8601", "symbols": ["..."], "facts": [{ "source": "...", "summary": "...", "impact": "bullish|bearish|neutral" }], "confidence": 0.0-1.0 }',
    },
    {
      presetKey: 'info_to_signal',
      label: 'Information to Signal',
      defaultPrompt:
        'You are the signal-generation sub-agent. Based on upstream information-gathering output, convert facts and indicators into executable trading signals (direction, strength, time horizon).',
      defaultOutputFormat:
        'JSON: { "signals": [{ "symbol": "...", "direction": "long|short|flat", "strength": 0.0-1.0, "horizon": "1h|4h|1d", "rationale": "..." }] }',
    },
    {
      presetKey: 'signal_to_execution',
      label: 'Signal to Execution',
      defaultPrompt:
        'You are the trade-execution sub-agent. Turn signals into concrete order instructions, respecting position limits, liquidity, and slippage. Output a submit-ready buy/sell plan.',
      defaultOutputFormat:
        'JSON: { "orders": [{ "symbol": "...", "side": "buy|sell|hold", "qty": number, "order_type": "market|limit", "limit_price": number|null, "reason": "..." }] }',
    },
    {
      presetKey: 'global_strategy',
      label: 'Global Trading Strategy',
      defaultPrompt:
        'You are the global strategy sub-agent. Coordinate asset allocation, risk budget, and conflicting signals so the overall portfolio stays within strategy constraints and target return/risk profile.',
      defaultOutputFormat:
        'JSON: { "portfolio_targets": [{ "symbol": "...", "target_weight": 0.0-1.0 }], "risk_budget": { "max_drawdown": number, "max_single_position": number }, "strategy_notes": "..." }',
    },
    {
      presetKey: 'stop_loss_take_profit',
      label: 'Stop Loss / Take Profit',
      defaultPrompt:
        'You are the risk-management sub-agent. Set stop-loss and take-profit rules for open positions, monitor unrealized P/L, and output close or reduce instructions when triggers fire.',
      defaultOutputFormat:
        'JSON: { "risk_actions": [{ "symbol": "...", "action": "stop_loss|take_profit|trail|hold", "trigger_price": number, "size_pct": 0.0-1.0, "reason": "..." }] }',
    },
    {
      presetKey: 'custom',
      label: 'Custom Sub-agent',
      defaultPrompt: 'Describe this sub-agent\'s responsibilities and decision boundaries.',
      defaultOutputFormat: 'JSON: { "output": "..." }',
    },
  ];

  const presetByKey = Object.fromEntries(SUB_AGENT_PRESETS.map((p) => [p.presetKey, p]));

  let currentAgent = null;
  let subAgents = [];
  let saveStatusTimer = null;
  let isDirty = false;
  let savedSnapshot = '';

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function storageKey(agentId) {
    return `${STORAGE_PREFIX}${agentId}`;
  }

  function newSubAgentId() {
    return `sub_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  }

  function createSubAgentFromPreset(presetKey, customLabel) {
    const preset = presetByKey[presetKey] || presetByKey.custom;
    const label =
      presetKey === 'custom' && customLabel
        ? customLabel.trim()
        : preset.label;
    return {
      id: newSubAgentId(),
      presetKey,
      label,
      prompt: preset.defaultPrompt,
      outputFormat: preset.defaultOutputFormat,
    };
  }

  function defaultPipeline() {
    return SUB_AGENT_PRESETS.filter((p) => p.presetKey !== 'custom').map((preset) => ({
      id: newSubAgentId(),
      presetKey: preset.presetKey,
      label: preset.label,
      prompt: preset.defaultPrompt,
      outputFormat: preset.defaultOutputFormat,
    }));
  }

  function normalizeLoadedSubAgent(item) {
    const presetKey = item.presetKey || 'custom';
    const preset = presetByKey[presetKey];
    const isCustom = presetKey === 'custom' || !preset;
    return {
      id: item.id || newSubAgentId(),
      presetKey,
      label: isCustom ? (item.label || 'Sub-agent') : preset.label,
      prompt: item.prompt || (preset ? preset.defaultPrompt : ''),
      outputFormat: item.outputFormat || (preset ? preset.defaultOutputFormat : ''),
    };
  }

  // For real agents the backend-stored pipeline is the source of truth; fall
  // back to any locally cached / default pipeline when the agent has none yet.
  // Demo (mock) agents have no backend row, so they always use localStorage.
  function resolvePipeline(agent) {
    if (!isDemoAgent(agent.agent_id) && Array.isArray(agent.pipeline) && agent.pipeline.length) {
      return agent.pipeline.map(normalizeLoadedSubAgent);
    }
    return loadPipeline(agent.agent_id);
  }

  function loadPipeline(agentId) {
    try {
      const raw = localStorage.getItem(storageKey(agentId));
      if (!raw) return defaultPipeline();
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed.subAgents) || !parsed.subAgents.length) {
        return defaultPipeline();
      }
      return parsed.subAgents.map(normalizeLoadedSubAgent);
    } catch {
      return defaultPipeline();
    }
  }

  function savePipelineLocal(agentId, agents) {
    localStorage.setItem(
      storageKey(agentId),
      JSON.stringify({ subAgents: agents, updatedAt: new Date().toISOString() })
    );
  }

  function getEditorState() {
    const nameInput = document.getElementById('agentEditorNameInput');
    const descInput = document.getElementById('agentEditorDescription');
    return {
      name: nameInput ? nameInput.value.trim() : '',
      description: descInput ? descInput.value.trim() : '',
      subAgents: collectPipelineFromDom(),
    };
  }

  function snapshotState() {
    return JSON.stringify(getEditorState());
  }

  function setDirty(dirty) {
    isDirty = dirty;
    const badge = document.getElementById('agentEditorDirtyBadge');
    if (badge) badge.hidden = !dirty;
  }

  function markDirtyFromInput() {
    setDirty(snapshotState() !== savedSnapshot);
  }

  function captureSavedSnapshot() {
    savedSnapshot = snapshotState();
    setDirty(false);
  }

  function collectPipelineFromDom() {
    const pipeline = document.getElementById('agentEditorPipeline');
    if (!pipeline) return subAgents;

    return subAgents.map((sub) => {
      const card = pipeline.querySelector(`[data-sub-id="${sub.id}"]`);
      if (!card) return sub;
      const labelInput = card.querySelector('[data-field="label"]');
      const promptInput = card.querySelector('[data-field="prompt"]');
      const outputInput = card.querySelector('[data-field="outputFormat"]');
      return {
        ...sub,
        label: labelInput ? labelInput.value.trim() || sub.label : sub.label,
        prompt: promptInput ? promptInput.value : sub.prompt,
        outputFormat: outputInput ? outputInput.value : sub.outputFormat,
      };
    });
  }

  function showSaveStatus(message, isError) {
    const el = document.getElementById('agentEditorSaveStatus');
    if (!el) return;
    el.hidden = false;
    el.textContent = message;
    el.classList.toggle('agent-editor-save-status--error', !!isError);
    clearTimeout(saveStatusTimer);
    saveStatusTimer = setTimeout(() => {
      el.hidden = true;
    }, 3000);
  }

  function updateStepCount() {
    const el = document.getElementById('agentEditorStepCount');
    if (!el) return;
    const n = subAgents.length;
    el.textContent = `${n} step${n === 1 ? '' : 's'}`;
  }

  function refreshAddSelect() {
    const select = document.getElementById('agentEditorAddSelect');
    const customName = document.getElementById('agentEditorCustomName');
    if (!select) return;

    const usedPresetKeys = new Set(
      subAgents.filter((s) => s.presetKey !== 'custom').map((s) => s.presetKey)
    );

    select.innerHTML = '<option value="">— Select type —</option>';
    SUB_AGENT_PRESETS.forEach((preset) => {
      if (preset.presetKey !== 'custom' && usedPresetKeys.has(preset.presetKey)) return;
      const opt = document.createElement('option');
      opt.value = preset.presetKey;
      opt.textContent = preset.label;
      select.appendChild(opt);
    });

    const customOpt = document.createElement('option');
    customOpt.value = 'custom';
    customOpt.textContent = 'Custom Sub-agent';
    select.appendChild(customOpt);

    if (customName) {
      customName.hidden = select.value !== 'custom';
    }
  }

  function moveSubAgent(index, delta) {
    const next = index + delta;
    if (next < 0 || next >= subAgents.length) return;
    subAgents = collectPipelineFromDom();
    const tmp = subAgents[index];
    subAgents[index] = subAgents[next];
    subAgents[next] = tmp;
    renderPipeline();
    markDirtyFromInput();
  }

  function duplicateSubAgent(subId) {
    subAgents = collectPipelineFromDom();
    const idx = subAgents.findIndex((s) => s.id === subId);
    if (idx < 0) return;
    const src = subAgents[idx];
    const copy = {
      ...src,
      id: newSubAgentId(),
      presetKey: 'custom',
      label: `${src.label} (copy)`,
    };
    subAgents.splice(idx + 1, 0, copy);
    renderPipeline();
    markDirtyFromInput();
    showSaveStatus('Sub-agent duplicated');
  }

  function restoreSubAgentDefaults(subId) {
    subAgents = collectPipelineFromDom();
    const sub = subAgents.find((s) => s.id === subId);
    if (!sub) return;
    const preset = presetByKey[sub.presetKey];
    if (!preset || sub.presetKey === 'custom') return;
    sub.prompt = preset.defaultPrompt;
    sub.outputFormat = preset.defaultOutputFormat;
    renderPipeline();
    markDirtyFromInput();
    showSaveStatus('Restored default prompt for this step');
  }

  function renderPipeline() {
    const pipeline = document.getElementById('agentEditorPipeline');
    if (!pipeline) return;

    pipeline.innerHTML = '';
    updateStepCount();

    subAgents.forEach((sub, index) => {
      const card = document.createElement('article');
      card.className = 'section-card agent-sub-card';
      card.setAttribute('role', 'listitem');
      card.dataset.subId = sub.id;

      const isCustom = sub.presetKey === 'custom';
      const isFirst = index === 0;
      const isLast = index === subAgents.length - 1;
      const canRestore = !isCustom && presetByKey[sub.presetKey];

      const labelField = isCustom
        ? `<input class="agent-sub-label-input" type="text" data-field="label" value="${escapeHtml(sub.label)}" placeholder="Sub-agent name" aria-label="Sub-agent name">`
        : `<span class="agent-sub-preset-label">${escapeHtml(sub.label)}</span>`;

      card.innerHTML = `
        <div class="agent-sub-head">
          <div class="agent-sub-head-left">
            <span class="agent-sub-index" aria-hidden="true">${index + 1}</span>
            ${labelField}
          </div>
          <div class="agent-sub-actions">
            <div class="agent-sub-reorder" role="group" aria-label="Reorder sub-agent">
              <button class="agent-sub-move-btn" type="button" data-action="up" data-sub-id="${escapeHtml(sub.id)}" aria-label="Move up" ${isFirst ? 'disabled' : ''}>↑</button>
              <button class="agent-sub-move-btn" type="button" data-action="down" data-sub-id="${escapeHtml(sub.id)}" aria-label="Move down" ${isLast ? 'disabled' : ''}>↓</button>
            </div>
            <button class="agent-sub-icon-btn" type="button" data-action="duplicate" data-sub-id="${escapeHtml(sub.id)}" title="Duplicate">⧉</button>
            ${canRestore ? `<button class="agent-sub-icon-btn" type="button" data-action="restore" data-sub-id="${escapeHtml(sub.id)}" title="Restore defaults">↺</button>` : ''}
            <button class="agent-sub-remove-btn" type="button" data-action="remove" data-sub-id="${escapeHtml(sub.id)}" aria-label="Remove sub-agent">Remove</button>
          </div>
        </div>
        <div class="agent-sub-fields">
          <label class="agent-sub-field">
            <span class="agent-sub-field-label">Task prompt</span>
            <span class="agent-sub-field-hint">What this sub-agent should do</span>
            <textarea data-field="prompt" rows="5" placeholder="Describe this sub-agent's role…">${escapeHtml(sub.prompt)}</textarea>
          </label>
          <label class="agent-sub-field">
            <span class="agent-sub-field-label">Output format</span>
            <span class="agent-sub-field-hint">Structure passed to the next model</span>
            <textarea data-field="outputFormat" rows="4" placeholder="JSON or structured text…">${escapeHtml(sub.outputFormat)}</textarea>
          </label>
        </div>
        ${!isLast ? '<div class="agent-sub-connector" aria-hidden="true"><span>↓ Output to next sub-agent</span></div>' : ''}
      `;

      pipeline.appendChild(card);
    });

    pipeline.querySelectorAll('[data-action]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const action = btn.dataset.action;
        const subId = btn.dataset.subId;
        const idx = subAgents.findIndex((s) => s.id === subId);
        if (action === 'up') moveSubAgent(idx, -1);
        else if (action === 'down') moveSubAgent(idx, 1);
        else if (action === 'duplicate') duplicateSubAgent(subId);
        else if (action === 'restore') restoreSubAgentDefaults(subId);
        else if (action === 'remove') {
          if (subAgents.length <= 1) {
            showSaveStatus('Keep at least one sub-agent', true);
            return;
          }
          subAgents = collectPipelineFromDom().filter((s) => s.id !== subId);
          renderPipeline();
          refreshAddSelect();
          markDirtyFromInput();
        }
      });
    });

    refreshAddSelect();
  }

  function fillHeader(agent) {
    const nameInput = document.getElementById('agentEditorNameInput');
    const descInput = document.getElementById('agentEditorDescription');
    const meta = document.getElementById('agentEditorMeta');

    if (nameInput) nameInput.value = agent.name || '';
    if (descInput) descInput.value = agent.description || '';
    if (meta) {
      const type = agent.agent_type === 'builtin' ? 'Built-in' : 'External';
      meta.textContent = `${agent.model_name || 'local-model'} · ${type}`;
    }
  }

  function serializePipeline(steps) {
    return steps.map((sub) => ({
      id: sub.id,
      presetKey: sub.presetKey,
      label: sub.label,
      prompt: sub.prompt,
      outputFormat: sub.outputFormat,
    }));
  }

  async function patchAgent(agent, name, description, pipeline) {
    const payload = {
      name,
      description: description || null,
      pipeline: serializePipeline(pipeline),
    };
    const endpoint = `${API_BASE}/api/v1/agents/${encodeURIComponent(agent.agent_id)}`;

    async function requestWithHeaders(extraHeaders) {
      if (window.API?.patch) {
        return window.API.patch(endpoint, payload, extraHeaders);
      }
      const headers = {
        'Content-Type': 'application/json',
        'x-session-id': window.SESSION_ID,
        ...extraHeaders,
      };
      const token = localStorage.getItem('auth-token');
      if (token) headers.Authorization = `Bearer ${token}`;

      const response = await fetch(endpoint, {
        method: 'PATCH',
        headers,
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = data.detail || data.message || `HTTP ${response.status}`;
        const error = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
        error.status = response.status;
        throw error;
      }
      return data;
    }

    try {
      const data = await requestWithHeaders({
        'x-browser-id': window.BROWSER_OWNER_ID,
        'x-session-id': agent.session_id || window.SESSION_ID,
      });
      return data.agent;
    } catch (error) {
      // Legacy/imported agents may store owner_browser_session = session_id.
      // Retry with session-only ownership (omit X-Browser-Id) when denied.
      if (error.status !== 403 || !agent?.session_id) throw error;
      const data = await requestWithHeaders({
        'x-session-id': agent.session_id,
        'x-browser-id': '',
      });
      return data.agent;
    }
  }

  function open(agent) {
    if (!agent || !agent.agent_id) return;

    currentAgent = { ...agent };
    subAgents = resolvePipeline(agent);
    fillHeader(agent);
    renderPipeline();

    const view = document.getElementById('agentEditorView');
    if (view) {
      view.hidden = false;
      document.body.classList.add('agent-editor-open');
    }

    const playgroundView = document.getElementById('playgroundView');
    if (playgroundView) playgroundView.setAttribute('aria-hidden', 'true');

    captureSavedSnapshot();
    document.getElementById('agentEditorNameInput')?.focus();
  }

  function close(force) {
    if (!force && isDirty) {
      if (!window.confirm('Discard unsaved changes?')) return;
    }

    subAgents = collectPipelineFromDom();

    const view = document.getElementById('agentEditorView');
    if (view) view.hidden = true;
    document.body.classList.remove('agent-editor-open');

    const playgroundView = document.getElementById('playgroundView');
    if (playgroundView) playgroundView.removeAttribute('aria-hidden');

    currentAgent = null;
    setDirty(false);
  }

  async function save() {
    if (!currentAgent) return;

    const state = getEditorState();
    if (!state.name) {
      showSaveStatus('Agent name is required', true);
      document.getElementById('agentEditorNameInput')?.focus();
      return;
    }

    subAgents = state.subAgents;
    const saveBtn = document.getElementById('agentEditorSaveBtn');
    if (saveBtn) {
      saveBtn.disabled = true;
      saveBtn.textContent = 'Saving…';
    }

    // Demo agents have no backend row: persist name/description locally and skip
    // the PATCH (which would 404) so the rename still sticks in the UI.
    if (isDemoAgent(currentAgent.agent_id)) {
      try {
        localStorage.setItem(
          `${NAME_OVERRIDE_PREFIX}${currentAgent.agent_id}`,
          JSON.stringify({ name: state.name, description: state.description })
        );
        currentAgent = { ...currentAgent, name: state.name, description: state.description };
        savePipelineLocal(currentAgent.agent_id, subAgents);
        if (localStorage.getItem('active-agent-id') === currentAgent.agent_id) {
          localStorage.setItem('active-agent-name', state.name);
        }
        captureSavedSnapshot();
        showSaveStatus('Saved (demo agent — stored locally)');
        window.dispatchEvent(
          new CustomEvent('agent-editor-saved', { detail: { agent: currentAgent } })
        );
      } finally {
        if (saveBtn) {
          saveBtn.disabled = false;
          saveBtn.textContent = 'Save';
        }
      }
      return;
    }

    try {
      const updated = await patchAgent(
        currentAgent,
        state.name,
        state.description,
        subAgents
      );
      currentAgent = { ...currentAgent, ...updated, pipeline: subAgents };
      savePipelineLocal(currentAgent.agent_id, subAgents);
      localStorage.removeItem(`${NAME_OVERRIDE_PREFIX}${currentAgent.agent_id}`);

      if (localStorage.getItem('active-agent-id') === currentAgent.agent_id) {
        localStorage.setItem('active-agent-name', state.name);
      }

      fillHeader(currentAgent);
      captureSavedSnapshot();
      showSaveStatus('Saved successfully');
      window.dispatchEvent(
        new CustomEvent('agent-editor-saved', { detail: { agent: currentAgent } })
      );
    } catch (error) {
      savePipelineLocal(currentAgent.agent_id, subAgents);
      localStorage.setItem(
        `${NAME_OVERRIDE_PREFIX}${currentAgent.agent_id}`,
        JSON.stringify({ name: state.name, description: state.description })
      );
      currentAgent = { ...currentAgent, name: state.name, description: state.description };
      fillHeader(currentAgent);
      captureSavedSnapshot();
      showSaveStatus(
        `Saved locally; server update failed: ${error.message}`,
        true
      );
      window.dispatchEvent(
        new CustomEvent('agent-editor-saved', { detail: { agent: currentAgent } })
      );
    } finally {
      if (saveBtn) {
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save';
      }
    }
  }

  function resetPipeline() {
    if (!window.confirm('Reset the pipeline to the default 5 sub-agents? Unsaved prompt edits will be lost.')) {
      return;
    }
    subAgents = defaultPipeline();
    renderPipeline();
    markDirtyFromInput();
    showSaveStatus('Pipeline reset to defaults');
  }

  function addSubAgent() {
    const select = document.getElementById('agentEditorAddSelect');
    const customNameEl = document.getElementById('agentEditorCustomName');
    const presetKey = select ? select.value : '';
    if (!presetKey) {
      showSaveStatus('Select a sub-agent type to add', true);
      return;
    }

    subAgents = collectPipelineFromDom();

    let customLabel = null;
    if (presetKey === 'custom' && customNameEl) {
      customLabel = customNameEl.value.trim() || 'Custom Sub-agent';
    }

    subAgents.push(createSubAgentFromPreset(presetKey, customLabel));
    renderPipeline();
    markDirtyFromInput();
    showSaveStatus('Sub-agent added');

    if (select) select.value = '';
    if (customNameEl) {
      customNameEl.value = '';
      customNameEl.hidden = true;
    }

    const pipeline = document.getElementById('agentEditorPipeline');
    if (pipeline && pipeline.lastElementChild) {
      pipeline.lastElementChild.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  function bindEvents() {
    document.getElementById('agentEditorBackBtn')?.addEventListener('click', () => close(false));
    document.getElementById('agentEditorSaveBtn')?.addEventListener('click', () => save());
    document.getElementById('agentEditorAddBtn')?.addEventListener('click', addSubAgent);
    document.getElementById('agentEditorResetBtn')?.addEventListener('click', resetPipeline);

    document.getElementById('agentEditorAddSelect')?.addEventListener('change', (e) => {
      const customName = document.getElementById('agentEditorCustomName');
      if (customName) customName.hidden = e.target.value !== 'custom';
    });

    const body = document.getElementById('agentEditorView');
    body?.addEventListener('input', markDirtyFromInput);
    body?.addEventListener('change', markDirtyFromInput);

    document.addEventListener('keydown', (event) => {
      const view = document.getElementById('agentEditorView');
      if (view?.hidden) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        close(false);
      }
      if ((event.ctrlKey || event.metaKey) && event.key === 's') {
        event.preventDefault();
        save();
      }
    });

    window.addEventListener('beforeunload', (event) => {
      if (isDirty && !document.getElementById('agentEditorView')?.hidden) {
        event.preventDefault();
        event.returnValue = '';
      }
    });
  }

  bindEvents();

  window.AgentEditor = { open, close, save, loadPipeline };
})();
