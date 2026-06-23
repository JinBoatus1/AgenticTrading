"""Unit tests for ``AgentRunner`` driving the full step loop over a fake backend."""

from __future__ import annotations

import json

import pytest

from agentictrading import (
    AgentRunner,
    ATLClient,
    ATLRunFailedError,
    ATLTimeoutError,
    RunResult,
)

API_KEY = "ag_secret_should_never_leak"


def _client() -> ATLClient:
    return ATLClient("http://test.local", API_KEY, timeout=5)


_AWAITING = {
    "status": "awaiting_decision",
    "run_id": "run_1",
    "step_id": "step_1",
    "sequence": 0,
    "observation": {"market": {"features": {}}, "portfolio": {"cash": 100, "equity": 100, "positions": []}},
    "constraints": {},
}
_LOADING = {"status": "loading", "run_id": "run_1", "message": "loading"}
_COMPLETED = {"status": "completed", "run_id": "run_1", "result_run_id": "ext_1"}


class RunnerBackend:
    """Routes the handful of endpoints AgentRunner touches."""

    def __init__(self, step_sequence, result=None):
        self.step_sequence = list(step_sequence)
        self.result = result or {"run_id": "run_1", "status": "completed",
                                 "metrics": {"total_return": 0.05}}
        self.submitted = []

    def __call__(self, req):
        url = req.full_url
        method = req.get_method()
        if method == "POST" and url.endswith("/api/v1/runs"):
            return (200, {"run_id": "run_1", "status": "created"})
        if url.endswith("/steps/next"):
            return (200, self.step_sequence.pop(0))
        if url.endswith("/decision"):
            self.submitted.append(json.loads(req.data.decode()))
            return (200, {"run_id": "run_1", "step_id": "step_1", "accepted": True,
                          "validation": {"passed": True, "rejections": []}, "fills": [],
                          "portfolio_after": {}, "run_status": "running"})
        if url.endswith("/result"):
            return (200, self.result)
        raise AssertionError(f"unexpected url {url}")


def _run(runner, **kw):
    return runner.run_backtest(
        "agv_1",
        environment_id="us-equity-hourly-v1",
        start_date="2026-04-15",
        end_date="2026-04-16",
        poll_interval=0,
        **kw,
    )


def test_runner_loading_then_decision_then_completed(fake_http):
    class HoldAgent:
        def __init__(self):
            self.decide_calls = 0
            self.exec_results = []

        def decide(self, observation):
            self.decide_calls += 1
            return {"orders": [], "rationale": "hold"}

        def on_execution_result(self, result):
            self.exec_results.append(result)

    backend = RunnerBackend([_LOADING, _AWAITING, _COMPLETED])
    fake_http(backend)
    agent = HoldAgent()
    result = _run(AgentRunner(_client(), agent))

    assert isinstance(result, RunResult)
    assert result.metrics["total_return"] == 0.05
    assert agent.decide_calls == 1
    assert len(agent.exec_results) == 1  # hook fired once
    assert len(backend.submitted) == 1


def test_runner_completed_immediately(fake_http):
    class Agent:
        def decide(self, observation):
            raise AssertionError("decide should not be called")

    backend = RunnerBackend([_COMPLETED])
    fake_http(backend)
    result = _run(AgentRunner(_client(), Agent()))
    assert result.metrics["total_return"] == 0.05
    assert backend.submitted == []


def test_runner_failed_state_raises(fake_http):
    class Agent:
        def decide(self, observation):
            return {"orders": []}

    backend = RunnerBackend([{"status": "failed", "run_id": "run_1", "message": "engine crashed"}])
    fake_http(backend)
    with pytest.raises(ATLRunFailedError) as ei:
        _run(AgentRunner(_client(), Agent()))
    assert "engine crashed" in str(ei.value)


def test_runner_hook_failure_surfaces_and_no_resubmit(fake_http):
    class BoomAgent:
        def __init__(self):
            self.decide_calls = 0

        def decide(self, observation):
            self.decide_calls += 1
            return {"orders": []}

        def on_execution_result(self, result):
            raise RuntimeError("hook fail")

    backend = RunnerBackend([_AWAITING, _COMPLETED])
    fake_http(backend)
    agent = BoomAgent()
    with pytest.raises(RuntimeError, match="hook fail"):
        _run(AgentRunner(_client(), agent))
    assert agent.decide_calls == 1
    assert len(backend.submitted) == 1  # accepted decision never resubmitted


def test_runner_optional_hook_absent_ok(fake_http):
    class MinimalAgent:
        def decide(self, observation):
            return {"orders": []}

    backend = RunnerBackend([_AWAITING, _COMPLETED])
    fake_http(backend)
    result = _run(AgentRunner(_client(), MinimalAgent()))
    assert result.metrics["total_return"] == 0.05


def test_runner_on_run_completed_hook(fake_http):
    class Agent:
        def __init__(self):
            self.completed = []

        def decide(self, observation):
            return {"orders": []}

        def on_run_completed(self, result):
            self.completed.append(result)

    backend = RunnerBackend([_AWAITING, _COMPLETED])
    fake_http(backend)
    agent = Agent()
    _run(AgentRunner(_client(), agent))
    assert len(agent.completed) == 1


def test_runner_max_wait_timeout(fake_http):
    class Agent:
        def decide(self, observation):
            return {"orders": []}

    backend = RunnerBackend([_LOADING, _LOADING, _LOADING])
    fake_http(backend)
    with pytest.raises(ATLTimeoutError):
        _run(AgentRunner(_client(), Agent()), max_wait_seconds=0)


def test_runner_unexpected_status_raises(fake_http):
    class Agent:
        def decide(self, observation):
            return {"orders": []}

    from agentictrading import ATLAPIError

    backend = RunnerBackend([{"status": "weird", "run_id": "run_1"}])
    fake_http(backend)
    with pytest.raises(ATLAPIError):
        _run(AgentRunner(_client(), Agent()))


def test_runner_requires_decide():
    class NotAnAgent:
        pass

    with pytest.raises(TypeError):
        AgentRunner(_client(), NotAnAgent())
