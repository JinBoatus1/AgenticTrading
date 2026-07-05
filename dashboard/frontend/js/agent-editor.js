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
      label: '信息收取',
      defaultPrompt:
        '你是信息收取子 Agent。从市场数据、新闻与宏观事件中收集与交易决策相关的关键信息，过滤噪声，保留高置信度事实与指标变化。',
      defaultOutputFormat:
        'JSON: { "timestamp": "ISO8601", "symbols": ["..."], "facts": [{ "source": "...", "summary": "...", "impact": "bullish|bearish|neutral" }], "confidence": 0.0-1.0 }',
    },
    {
      presetKey: 'info_to_signal',
      label: '信息转信号',
      defaultPrompt:
        '你是信号生成子 Agent。基于上游信息收取结果，将事实与指标转化为可执行的交易信号（方向、强度、时间窗口）。',
      defaultOutputFormat:
        'JSON: { "signals": [{ "symbol": "...", "direction": "long|short|flat", "strength": 0.0-1.0, "horizon": "1h|4h|1d", "rationale": "..." }] }',
    },
    {
      presetKey: 'signal_to_execution',
      label: '信号转交易执行',
      defaultPrompt:
        '你是交易执行子 Agent。将信号转化为具体订单指令，考虑仓位限制、流动性与滑点，输出可提交的买卖计划。',
      defaultOutputFormat:
        'JSON: { "orders": [{ "symbol": "...", "side": "buy|sell|hold", "qty": number, "order_type": "market|limit", "limit_price": number|null, "reason": "..." }] }',
    },
    {
      presetKey: 'global_strategy',
      label: '全局交易策略',
      defaultPrompt:
        '你是全局策略子 Agent。统筹资产分配、风险预算与多信号冲突仲裁，确保整体组合符合策略约束与目标收益/风险 profile。',
      defaultOutputFormat:
        'JSON: { "portfolio_targets": [{ "symbol": "...", "target_weight": 0.0-1.0 }], "risk_budget": { "max_drawdown": number, "max_single_position": number }, "strategy_notes": "..." }',
    },
    {
      presetKey: 'stop_loss_take_profit',
      label: '止损止盈',
      defaultPrompt:
        '你是风控子 Agent。为持仓设定止损与止盈规则，监控 unrealized P/L，在触发条件时输出平仓或减仓指令。',
      defaultOutputFormat:
        'JSON: { "risk_actions": [{ "symbol": "...", "action": "stop_loss|take_profit|trail|hold", "trigger_price": number, "size_pct": 0.0-1.0, "reason": "..." }] }',
    },
    {
      presetKey: 'custom',
      label: '自定义子 Agent',
      defaultPrompt: '描述该子 Agent 的职责与决策边界。',
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

  function loadPipeline(agentId) {
    try {
      const raw = localStorage.getItem(storageKey(agentId));
      if (!raw) return defaultPipeline();
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed.subAgents) || !parsed.subAgents.length) {
        return defaultPipeline();
      }
      return parsed.subAgents.map((item) => ({
        id: item.id || newSubAgentId(),
        presetKey: item.presetKey || 'custom',
        label: item.label || '子 Agent',
        prompt: item.prompt || '',
        outputFormat: item.outputFormat || '',
      }));
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

    select.innerHTML = '<option value="">— 选择子 Agent 类型 —</option>';
    SUB_AGENT_PRESETS.forEach((preset) => {
      if (preset.presetKey !== 'custom' && usedPresetKeys.has(preset.presetKey)) return;
      const opt = document.createElement('option');
      opt.value = preset.presetKey;
      opt.textContent = preset.label;
      select.appendChild(opt);
    });

    const customOpt = document.createElement('option');
    customOpt.value = 'custom';
    customOpt.textContent = '自定义子 Agent';
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
        ? `<input class="agent-sub-label-input" type="text" data-field="label" value="${escapeHtml(sub.label)}" placeholder="子 Agent 名称" aria-label="子 Agent 名称">`
        : `<span class="agent-sub-preset-label">${escapeHtml(sub.label)}</span>`;

      card.innerHTML = `
        <div class="agent-sub-head">
          <div class="agent-sub-head-left">
            <span class="agent-sub-index">${index + 1}</span>
            ${labelField}
          </div>
          <button class="agent-sub-remove-btn" type="button" data-sub-id="${escapeHtml(sub.id)}" aria-label="移除子 Agent">移除</button>
        </div>
        <div class="agent-sub-fields">
          <label class="agent-sub-field">
            <span class="agent-sub-field-label">任务 Prompt</span>
            <span class="agent-sub-field-hint">告诉该子 Agent 要做什么</span>
            <textarea data-field="prompt" rows="4" placeholder="描述该子 Agent 的职责…">${escapeHtml(sub.prompt)}</textarea>
          </label>
          <label class="agent-sub-field">
            <span class="agent-sub-field-label">输出格式</span>
            <span class="agent-sub-field-hint">传递给下一模型的信息结构</span>
            <textarea data-field="outputFormat" rows="3" placeholder="JSON 或结构化文本格式…">${escapeHtml(sub.outputFormat)}</textarea>
          </label>
        </div>
        ${index < subAgents.length - 1 ? '<div class="agent-sub-connector" aria-hidden="true"><span>↓ 输出至下一子 Agent</span></div>' : ''}
      `;

      pipeline.appendChild(card);
    });

    pipeline.querySelectorAll('.agent-sub-remove-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        if (subAgents.length <= 1) {
          showSaveStatus('至少保留一个子 Agent', true);
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
    showSaveStatus('配置已保存');
  }

  function addSubAgent() {
    const select = document.getElementById('agentEditorAddSelect');
    const presetKey = select ? select.value : '';
    if (!presetKey) {
      showSaveStatus('请先选择要添加的子 Agent 类型', true);
      return;
    }

    subAgents = collectPipelineFromDom();

    let customLabel = null;
    if (presetKey === 'custom') {
      customLabel = window.prompt('自定义子 Agent 名称', '自定义子 Agent');
      if (customLabel === null) return;
    }

    subAgents.push(createSubAgentFromPreset(presetKey, customLabel));
    renderPipeline();
    showSaveStatus('已添加子 Agent');

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
