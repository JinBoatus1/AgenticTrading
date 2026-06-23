"""``AgentRunner`` - a high-level loop so contributors only write decision logic.

A user implements an object with a ``decide(observation)`` method (and,
optionally, ``on_execution_result`` / ``on_run_completed`` hooks). The runner
handles the full lifecycle::

    create run
      -> poll next step
      -> wait while loading (bounded by max_wait_seconds)
      -> call agent.decide(observation)
      -> submit decision
      -> receive execution result
      -> repeat until completed
      -> retrieve final result

Lifecycle handling
------------------
``get_next_step`` returns one of ``loading`` / ``awaiting_decision`` /
``completed``; the backend raises for ``failed`` (``ATLRunFailedError``) and
``run_not_active`` (``ATLConflictError``). The runner handles each explicitly and
raises ``ATLAPIError`` on any unexpected status rather than spinning forever.

Hook failures
-------------
A decision is submitted to the backend *before* its hooks run. If
``on_execution_result`` or ``on_run_completed`` raises, that exception is
surfaced to the caller; the runner never resubmits an already-accepted decision
because a local hook failed.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Union

try:  # Protocol is available on 3.8+; guard for older typing backends.
    from typing import Protocol, runtime_checkable
except ImportError:  # pragma: no cover
    Protocol = object  # type: ignore

    def runtime_checkable(cls):  # type: ignore
        return cls

from .atl_client import ATLClient
from .exceptions import ATLAPIError, ATLRunFailedError, ATLTimeoutError
from .models import Decision, Observation, RunResult


@runtime_checkable
class TradingAgentProtocol(Protocol):
    """Minimal contract an agent must satisfy to be run by ``AgentRunner``."""

    def decide(self, observation: Observation) -> Union[Decision, Dict[str, Any]]:
        ...


# Run states the backend may surface that mean "stop, this run will not proceed".
_FAILED_STATES = {"failed", "cancelled", "canceled"}


class AgentRunner:
    """Drive an agent through a full run via an :class:`ATLClient`."""

    def __init__(self, client: ATLClient, agent: Any) -> None:
        if not callable(getattr(agent, "decide", None)):
            raise TypeError("agent must implement a callable decide(observation) method")
        self.client = client
        self.agent = agent

    def run_backtest(
        self,
        agent_version_id: str,
        *,
        environment_id: str,
        start_date: str,
        end_date: str,
        symbols: Optional[List[str]] = None,
        initial_cash: float = 100_000,
        config: Optional[Dict[str, Any]] = None,
        poll_interval: float = 2.0,
        max_wait_seconds: Optional[float] = 300.0,
        max_steps: Optional[int] = None,
    ) -> RunResult:
        """Create a backtest run and drive it to completion, returning the result.

        Parameters
        ----------
        poll_interval:
            Seconds to sleep between polls while the run is ``loading`` or in a
            transient state.
        max_wait_seconds:
            Maximum *cumulative* time to spend waiting on non-actionable states
            before raising :class:`ATLTimeoutError`. Pass ``None`` to wait
            indefinitely (must be explicitly chosen).
        max_steps:
            Optional cap on the number of decisions submitted (mostly for tests).
        """
        run = self.client.create_run(
            agent_version_id,
            environment_id=environment_id,
            start_date=start_date,
            end_date=end_date,
            symbols=symbols,
            initial_cash=initial_cash,
            config=config,
        )

        steps_done = 0
        waited = 0.0
        while True:
            step = self.client.get_next_step(run.id)
            status = step.status

            if status == "completed":
                break

            if status in _FAILED_STATES:
                raise ATLRunFailedError(
                    step.message or f"run entered state '{status}'",
                    code=status,
                    response=step.raw,
                )

            if status == "awaiting_decision":
                waited = 0.0  # progress made; reset the idle timer
                decision = self.agent.decide(step.observation)
                result = self.client.submit_decision(run.id, step.id, decision)
                # Decision is already accepted server-side; a hook raising here
                # surfaces to the caller and never triggers a resubmission.
                self._fire("on_execution_result", result)

                steps_done += 1
                if max_steps is not None and steps_done >= max_steps:
                    break
                continue

            if status in ("loading", "pending", "executing"):
                waited = self._wait(poll_interval, waited, max_wait_seconds, status)
                continue

            # Any other status is unexpected; fail loudly instead of spinning.
            raise ATLAPIError(
                f"unexpected step status '{status}' from get_next_step",
                code="unexpected_step_status",
                response=step.raw,
            )

        final = self.client.get_run_result(run.id)
        self._fire("on_run_completed", final)
        return final

    def _wait(
        self,
        poll_interval: float,
        waited: float,
        max_wait_seconds: Optional[float],
        status: str,
    ) -> float:
        if max_wait_seconds is not None and waited >= max_wait_seconds:
            raise ATLTimeoutError(
                f"exceeded max_wait_seconds={max_wait_seconds} while run was '{status}'",
                code="runner_wait_timeout",
            )
        sleep_for = poll_interval
        if max_wait_seconds is not None:
            sleep_for = min(poll_interval, max(0.0, max_wait_seconds - waited))
        self.client.wait(sleep_for)
        return waited + (sleep_for or poll_interval)

    def _fire(self, hook: str, payload: Any) -> None:
        fn = getattr(self.agent, hook, None)
        if callable(fn):
            fn(payload)  # exceptions propagate intentionally


__all__ = ["AgentRunner", "TradingAgentProtocol"]
