"""Browser-side Plausible transport for Streamlit applications."""

from __future__ import annotations

import os
import uuid
from typing import MutableMapping, Optional

import streamlit as st


_BRIDGE_JS = r"""
export default function(component) {
const { data } = component;
const scriptUrl = String(data?.script_url || "").trim();
const event = data?.event || null;
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
  const eventName = String(event?.name || "").trim();
  const eventId = String(event?.id || "").trim();
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

void ensureTracker().catch(() => {});
void sendEvent();
}
"""

_plausible_bridge = st.components.v2.component(
    "crochet_intelligence_plausible_bridge",
    js=_BRIDGE_JS,
)


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
    script_url = os.getenv("PUBLIC_PLAUSIBLE_SCRIPT_URL", "").strip()
    debug = os.getenv("PLAUSIBLE_DEBUG", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    try:
        _plausible_bridge(
            key="crochet_intelligence_plausible_bridge",
            data={
                "script_url": script_url,
                "event": pending_event,
                "debug": debug,
            },
            height="content",
        )
    except Exception as exc:
        if debug:
            print(f"[Plausible] bridge mount failed: {exc}")
