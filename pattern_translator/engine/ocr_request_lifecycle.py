from __future__ import annotations

from typing import Dict, Optional, Tuple


PENDING = "pending"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"


def new_request(request_id: str) -> Dict[str, str]:
    return {"request_id": request_id, "state": PENDING}


def is_active(request: object) -> bool:
    return isinstance(request, dict) and request.get("state") in {PENDING, RUNNING}


def claim_request(
    request: object, request_id: str
) -> Tuple[Optional[Dict[str, str]], bool]:
    """Atomically consume one pending request for execution."""
    if not isinstance(request, dict):
        return None, False
    if request.get("request_id") != request_id or request.get("state") != PENDING:
        return request, False
    claimed = dict(request)
    claimed["state"] = RUNNING
    return claimed, True


def finish_request(
    request: object, request_id: str, *, succeeded: bool
) -> Optional[Dict[str, str]]:
    """Move the matching running request to a terminal state."""
    if not isinstance(request, dict):
        return None
    if request.get("request_id") != request_id or request.get("state") != RUNNING:
        return request
    finished = dict(request)
    finished["state"] = COMPLETED if succeeded else FAILED
    return finished
