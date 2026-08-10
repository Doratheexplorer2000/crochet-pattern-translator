"""Browser-side Plausible transport for Streamlit applications."""

from __future__ import annotations

import os
import uuid
from typing import MutableMapping, Optional

import streamlit as st


_BRIDGE_JS = r"""
export default function(component) {
const { data, parentElement } = component;
const scriptUrl = String(data?.script_url || "").trim();
const event = data?.event || null;
const link = data?.link || null;
const debug = Boolean(data?.debug);

const debugLog = (...args) => {
  if (debug) console.debug("[Plausible]", ...args);
};
const debugWarn = (...args) => {
  if (debug) console.warn("[Plausible]", ...args);
};

function ensureTracker() {
  if (!scriptUrl) {
    debugWarn("PUBLIC_PLAUSIBLE_SCRIPT_URL is not configured");
    return Promise.reject(new Error("Plausible script URL is not configured"));
  }

  window.plausible = window.plausible || function (...args) {
    (window.plausible.q = window.plausible.q || []).push(args);
  };
  window.plausible.init = window.plausible.init || function (options) {
    window.plausible.o = options || {};
  };

  if (!window.__ciPlausibleInitialized) {
    window.plausible.init();
    window.__ciPlausibleInitialized = true;
  }

  if (window.__ciPlausibleLoadPromise) {
    return window.__ciPlausibleLoadPromise;
  }

  window.__ciPlausibleLoadPromise = new Promise((resolve, reject) => {
    let script = document.getElementById("ci-plausible-script");
    if (script?.dataset.loaded === "true") {
      resolve();
      return;
    }

    if (!script) {
      script = document.createElement("script");
      script.id = "ci-plausible-script";
      script.async = true;
      script.src = scriptUrl;
      document.head.appendChild(script);
      debugLog("tracker requested", scriptUrl);
    }

    script.addEventListener("load", () => {
      script.dataset.loaded = "true";
      debugLog("tracker loaded", scriptUrl);
      resolve();
    }, { once: true });
    script.addEventListener("error", () => {
      debugWarn("tracker failed to load", scriptUrl);
      window.__ciPlausibleLoadPromise = null;
      script.remove();
      reject(new Error("Plausible tracker failed to load"));
    }, { once: true });
  });

  return window.__ciPlausibleLoadPromise;
}

function eventStorageKey(eventName, eventId) {
  return `ci:plausible:v2:${eventName}:${eventId}`;
}

function hasSent(key) {
  try {
    return window.sessionStorage.getItem(key) === "sent";
  } catch {
    return false;
  }
}

function markSent(key) {
  try {
    window.sessionStorage.setItem(key, "sent");
  } catch {
    // The in-memory guard below still prevents duplicates in this page.
  }
  window.__ciPlausibleSentEvents = window.__ciPlausibleSentEvents || new Set();
  window.__ciPlausibleSentEvents.add(key);
}

function wasSent(key) {
  return hasSent(key) || Boolean(window.__ciPlausibleSentEvents?.has(key));
}

async function sendEvent() {
  await dispatchEvent(event);
}

async function dispatchEvent(eventData) {
  const eventName = String(eventData?.name || "").trim();
  const eventId = String(eventData?.id || "").trim();
  if (!eventName || !eventId) return;

  const key = eventStorageKey(eventName, eventId);
  if (wasSent(key)) {
    debugLog("duplicate suppressed", eventName, eventId);
    return;
  }

  try {
    await ensureTracker();
    markSent(key);
    window.plausible(eventName, {
      url: window.location.href,
      callback: (result) => {
        if (result?.status) {
          debugLog("event delivered", eventName, result.status);
        } else if (result?.error) {
          debugWarn("event delivery failed", eventName, result.error);
        } else {
          debugWarn("event ignored", eventName);
        }
      },
    });
    debugLog("event dispatched", eventName, eventId);
  } catch (error) {
    debugWarn("event not dispatched", eventName, error);
  }
}

function newLinkEventId(eventName) {
  try {
    return `${eventName}:${crypto.randomUUID()}`;
  } catch {
    return `${eventName}:${Date.now()}:${Math.random().toString(16).slice(2)}`;
  }
}

function renderTrackedLink() {
  const label = String(link?.label || "").trim();
  const href = String(link?.href || "").trim();
  const eventName = String(link?.event_name || "").trim();
  if (!label || !href || !eventName || !parentElement) return;

  let root = parentElement.querySelector("[data-ci-plausible-link-root]");
  if (!root) {
    root = document.createElement("div");
    root.dataset.ciPlausibleLinkRoot = "true";
    parentElement.appendChild(root);
  }

  const anchor = document.createElement("a");
  anchor.className = "ci-plausible-link-button";
  anchor.href = href;
  anchor.target = "_blank";
  anchor.rel = "noopener noreferrer";
  anchor.textContent = label;
  anchor.addEventListener("click", () => {
    void dispatchEvent({
      name: eventName,
      id: newLinkEventId(eventName),
    });
  });
  root.replaceChildren(anchor);
}

void ensureTracker().catch(() => {});
void sendEvent();
renderTrackedLink();
}
"""

_BRIDGE_CSS = r"""
.ci-plausible-link-button {
  align-items: center;
  border: 1px solid rgba(49, 51, 63, 0.2);
  border-radius: 0.5rem;
  box-sizing: border-box;
  color: rgb(49, 51, 63);
  display: inline-flex;
  font-size: 1rem;
  font-weight: 400;
  justify-content: center;
  line-height: 1.6;
  min-height: 2.5rem;
  padding: 0.375rem 0.75rem;
  text-decoration: none;
  user-select: none;
}

.ci-plausible-link-button:hover {
  border-color: #0f766e;
  color: #0f766e;
}

.ci-plausible-link-button:focus-visible {
  outline: 3px solid rgba(15, 118, 110, 0.28);
  outline-offset: 2px;
}

@media (prefers-color-scheme: dark) {
  .ci-plausible-link-button {
    border-color: rgba(250, 250, 250, 0.2);
    color: rgb(250, 250, 250);
  }

  .ci-plausible-link-button:hover {
    border-color: #2f928a;
    color: #2f928a;
  }
}
"""

_plausible_bridge = st.components.v2.component(
    "crochet_intelligence_plausible_bridge",
    css=_BRIDGE_CSS,
    js=_BRIDGE_JS,
)


def _tracking_config() -> tuple[str, bool]:
    return (
        os.getenv("PUBLIC_PLAUSIBLE_SCRIPT_URL", "").strip(),
        os.getenv("PLAUSIBLE_DEBUG", "").strip().lower()
        in {"1", "true", "yes", "on"},
    )


def _mount_bridge(*, key: str, event: object = None, link: object = None) -> bool:
    script_url, debug = _tracking_config()
    try:
        _plausible_bridge(
            key=key,
            data={
                "script_url": script_url,
                "event": event,
                "link": link,
                "debug": debug,
            },
            height="content",
        )
        return True
    except Exception as exc:
        if debug:
            print(f"[Plausible] bridge mount failed: {exc}")
        return False


def stage_plausible_event(
    session_state: MutableMapping[str, object],
    event_name: str,
) -> None:
    """Stage one event for the bridge mounted at the start of the next rerun."""
    if not event_name:
        return
    session_state["pending_plausible_v2_event"] = {
        "name": event_name,
        "id": uuid.uuid4().hex,
    }


def mount_plausible_bridge(
    pending_event: Optional[dict[str, object]],
) -> None:
    """Mount the main-page tracker once and optionally dispatch one event."""
    _mount_bridge(
        key="crochet_intelligence_plausible_bridge",
        event=pending_event,
    )


def emit_plausible_event(event_name: str, event_id: str, *, key: str) -> None:
    """Dispatch one browser event through the main-page V2 bridge."""
    if not event_name:
        return
    _mount_bridge(
        key=key,
        event={
            "name": event_name,
            "id": event_id or uuid.uuid4().hex,
        },
    )


def plausible_link_button(label: str, url: str, event_name: str, *, key: str) -> bool:
    """Render a tracked main-page link through the V2 bridge."""
    script_url, _debug = _tracking_config()
    if not script_url or not label or not url or not event_name:
        return False
    return _mount_bridge(
        key=key,
        link={
            "label": label,
            "href": url,
            "event_name": event_name,
        },
    )
