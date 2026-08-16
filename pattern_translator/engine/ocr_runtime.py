from __future__ import annotations

import threading
from typing import Callable, TypeVar


_Result = TypeVar("_Result")
_PADDLE_INFERENCE_LOCK = threading.Lock()


def run_serialized(operation: Callable[..., _Result], *args, **kwargs) -> _Result:
    """Run one operation against Paddle's process-wide inference runtime."""
    with _PADDLE_INFERENCE_LOCK:
        return operation(*args, **kwargs)
