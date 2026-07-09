/**
 * agent-editor.js — Fullscreen agent pipeline editor (sub-agent chain).
 * Persists config to localStorage until backend API is wired.
 */
(function () {
  'use strict';

  const STORAGE_PREFIX = 'agent-pipeline-config:';

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

  function savePipeline(agentId, agents) {
    localStorage.setItem(
      storageKey(agentId),
      JSON.stringify({ subAgents: agents, updatedAt: new Date().toISOString() })
    );
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
    }, 2500);
  }

  function refreshAddSelect() {
    const select = document.getElementById('agentEditorAddSelect');
    if (!select) return;

    const usedPresetKeys = new Set(
      subAgents.filter((s) => s.presetKey !== 'custom').map((s) => s.presetKey)
    );

    select.innerHTML = '<option value="">— Select sub-agent type —</option>';
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
  }

  function renderPipeline() {
    const pipeline = document.getElementById('agentEditorPipeline');
    if (!pipeline) return;

    pipeline.innerHTML = '';

    subAgents.forEach((sub, index) => {
      const card = document.createElement('article');
      card.className = 'section-card agent-sub-card';
      card.setAttribute('role', 'listitem');
      card.dataset.subId = sub.id;

      const isCustom = sub.presetKey === 'custom';
      const labelField = isCustom
        ? `<input class="agent-sub-label-input" type="text" data-field="label" value="${escapeHtml(sub.label)}" placeholder="Sub-agent name" aria-label="Sub-agent name">`
        : `<span class="agent-sub-preset-label">${escapeHtml(sub.label)}</span>`;

      card.innerHTML = `
        <div class="agent-sub-head">
          <div class="agent-sub-head-left">
            <span class="agent-sub-index">${index + 1}</span>
            ${labelField}
          </div>
          <button class="agent-sub-remove-btn" type="button" data-sub-id="${escapeHtml(sub.id)}" aria-label="Remove sub-agent">Remove</button>
        </div>
        <div class="agent-sub-fields">
          <label class="agent-sub-field">
            <span class="agent-sub-field-label">Task prompt</span>
            <span class="agent-sub-field-hint">What this sub-agent should do</span>
            <textarea data-field="prompt" rows="4" placeholder="Describe this sub-agent's role…">${escapeHtml(sub.prompt)}</textarea>
          </label>
          <label class="agent-sub-field">
            <span class="agent-sub-field-label">Output format</span>
            <span class="agent-sub-field-hint">Structure passed to the next model</span>
            <textarea data-field="outputFormat" rows="3" placeholder="JSON or structured text…">${escapeHtml(sub.outputFormat)}</textarea>
          </label>
        </div>
        ${index < subAgents.length - 1 ? '<div class="agent-sub-connector" aria-hidden="true"><span>↓ Output to next sub-agent</span></div>' : ''}
      `;

      pipeline.appendChild(card);
    });

    pipeline.querySelectorAll('.agent-sub-remove-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        if (subAgents.length <= 1) {
          showSaveStatus('Keep at least one sub-agent', true);
          return;
        }
        subAgents = collectPipelineFromDom().filter((s) => s.id !== btn.dataset.subId);
        renderPipeline();
        refreshAddSelect();
      });
    });

    refreshAddSelect();
  }

  function open(agent) {
    if (!agent || !agent.agent_id) return;

    currentAgent = agent;
    subAgents = loadPipeline(agent.agent_id);

    const view = document.getElementById('agentEditorView');
    const title = document.getElementById('agentEditorTitle');
    const meta = document.getElementById('agentEditorMeta');

    if (title) title.textContent = agent.name || 'Agent';
    if (meta) {
      const parts = [
        agent.model_name || 'local-model',
        agent.agent_type === 'builtin' ? 'Built-in' : 'External',
      ];
      meta.textContent = parts.join(' · ');
    }

    renderPipeline();

    if (view) {
      view.hidden = false;
      document.body.classList.add('agent-editor-open');
    }

    const playgroundView = document.getElementById('playgroundView');
    if (playgroundView) playgroundView.setAttribute('aria-hidden', 'true');
  }

  function close() {
    subAgents = collectPipelineFromDom();

    const view = document.getElementById('agentEditorView');
    if (view) view.hidden = true;
    document.body.classList.remove('agent-editor-open');

    const playgroundView = document.getElementById('playgroundView');
    if (playgroundView) playgroundView.removeAttribute('aria-hidden');

    currentAgent = null;
  }

  function save() {
    if (!currentAgent) return;
    subAgents = collectPipelineFromDom();
    savePipeline(currentAgent.agent_id, subAgents);
    showSaveStatus('Configuration saved');
  }

  function addSubAgent() {
    const select = document.getElementById('agentEditorAddSelect');
    const presetKey = select ? select.value : '';
    if (!presetKey) {
      showSaveStatus('Select a sub-agent type to add', true);
      return;
    }

    subAgents = collectPipelineFromDom();

    let customLabel = null;
    if (presetKey === 'custom') {
      customLabel = window.prompt('Custom sub-agent name', 'Custom Sub-agent');
      if (customLabel === null) return;
    }

    subAgents.push(createSubAgentFromPreset(presetKey, customLabel));
    renderPipeline();
    showSaveStatus('Sub-agent added');

    const pipeline = document.getElementById('agentEditorPipeline');
    if (pipeline && pipeline.lastElementChild) {
      pipeline.lastElementChild.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  function bindEvents() {
    document.getElementById('agentEditorBackBtn')?.addEventListener('click', close);
    document.getElementById('agentEditorSaveBtn')?.addEventListener('click', save);
    document.getElementById('agentEditorAddBtn')?.addEventListener('click', addSubAgent);

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !document.getElementById('agentEditorView')?.hidden) {
        close();
      }
    });
  }

  bindEvents();

  window.AgentEditor = { open, close, save, loadPipeline };
})();
