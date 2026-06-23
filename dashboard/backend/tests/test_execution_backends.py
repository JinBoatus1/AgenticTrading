import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest  # noqa: E402

from execution.base import ExecutionBackend  # noqa: E402
from execution.paper_backend import PaperBackend  # noqa: E402


def test_execution_backend_is_abstract():
    with pytest.raises(TypeError):
        ExecutionBackend()  # abstract — cannot instantiate


def test_paper_backend_is_designed_for_stub():
    backend = PaperBackend()
    assert backend.loop == "realtime"
    with pytest.raises(NotImplementedError):
        backend.build_context()
