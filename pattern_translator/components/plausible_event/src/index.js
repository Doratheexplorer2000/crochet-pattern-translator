import { Streamlit } from "streamlit-component-lib";

const loadedScripts = new Map();

function loadTracker(scriptUrl) {
  if (loadedScripts.has(scriptUrl)) {
    return loadedScripts.get(scriptUrl);
  }

  const promise = new Promise((resolve, reject) => {
    window.plausible = window.plausible || function () {
      (window.plausible.q = window.plausible.q || []).push(arguments);
    };
    window.plausible.init = window.plausible.init || function (options) {
      window.plausible.o = options || {};
    };
    window.plausible.init({ autoCapturePageviews: false });

    const script = document.createElement("script");
    script.async = true;
    script.src = scriptUrl;
    script.addEventListener("load", resolve, { once: true });
    script.addEventListener("error", reject, { once: true });
    document.head.appendChild(script);
  });
  loadedScripts.set(scriptUrl, promise);
  return promise;
}

function parentUrl() {
  try {
    return window.parent.location.href;
  } catch {
    return document.referrer || window.location.href;
  }
}

function storageKey(eventName, eventId) {
  return `ci:plausible:${eventName}:${eventId}`;
}

function wasSent(key) {
  try {
    return window.sessionStorage.getItem(key) !== null;
  } catch {
    return false;
  }
}

function markSent(key) {
  try {
    window.sessionStorage.setItem(key, "sent");
  } catch {
    // Tracking still remains best-effort when browser storage is unavailable.
  }
}

async function emitEvent(args) {
  const eventName = String(args.event_name || "");
  const eventId = String(args.event_id || "");
  const scriptUrl = String(args.script_url || "");
  if (!eventName || !eventId || !scriptUrl) {
    return;
  }

  const key = storageKey(eventName, eventId);
  if (wasSent(key)) {
    return;
  }

  markSent(key);

  try {
    await loadTracker(scriptUrl);
    window.plausible(eventName, {
      url: parentUrl(),
    });
  } catch {
    // Browser analytics failures are intentionally silent.
  }
}

function linkEventId(baseEventId) {
  return `${baseEventId}:${Date.now()}:${Math.random().toString(16).slice(2)}`;
}

function renderLink(args) {
  const href = String(args.link_href || "");
  const label = String(args.link_label || "");
  if (!href || !label) {
    document.body.innerHTML = "";
    Streamlit.setFrameHeight(0);
    return false;
  }

  document.body.innerHTML = "";
  const link = document.createElement("a");
  link.className = "ci-plausible-link-button";
  link.href = href;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = label;
  link.addEventListener("click", () => {
    void emitEvent({
      ...args,
      event_id: linkEventId(String(args.event_id || "link")),
    });
  });
  document.body.appendChild(link);
  Streamlit.setFrameHeight(48);
  void loadTracker(String(args.script_url || ""));
  return true;
}

function onRender(event) {
  const args = event.detail.args || {};
  if (renderLink(args)) {
    return;
  }
  Streamlit.setFrameHeight(0);
  void emitEvent(args);
}

Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, onRender);
Streamlit.setComponentReady();
Streamlit.setFrameHeight(0);
