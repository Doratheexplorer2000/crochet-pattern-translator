import { Streamlit } from "streamlit-component-lib";

const workspace = document.getElementById("workspace");
const sourceImage = document.getElementById("source-image");
const selectionElement = document.getElementById("selection");
const precisionPad = document.getElementById("precision-pad");
const padCentre = document.getElementById("move-pad");
const confirmButton = document.getElementById("confirm-button");
const resetButton = document.getElementById("reset-button");
const cancelButton = document.getElementById("cancel-button");
const edgeHandles = Array.from(document.querySelectorAll(".edge-handle"));
const arrowButtons = Array.from(document.querySelectorAll(".arrow"));

let strings = {};
let imageSignature = "";
let imageWidth = 1;
let imageHeight = 1;
let minCropSize = 50;
let initialBox = { left: 0, top: 0, width: 1, height: 1 };
let selection = { ...initialBox };
let imageLayout = { left: 0, top: 0, width: 1, height: 1, scale: 1 };
let controllerPosition = { left: 0, top: 0 };
let activeEdge = "";
let pointerOperation = null;
let repeatDelay = null;
let repeatTimer = null;

function text(key) {
  return String(strings[key] || "");
}

function applyTheme(theme) {
  const systemTheme = window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
  document.documentElement.dataset.theme = theme && theme.base
    ? theme.base
    : systemTheme;
}

function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), maximum);
}

function normalizedBox(box) {
  const width = clamp(Number(box.width) || minCropSize, minCropSize, imageWidth);
  const height = clamp(Number(box.height) || minCropSize, minCropSize, imageHeight);
  return {
    left: clamp(Number(box.left) || 0, 0, imageWidth - width),
    top: clamp(Number(box.top) || 0, 0, imageHeight - height),
    width,
    height,
  };
}

function calculateImageLayout() {
  const workspaceWidth = workspace.clientWidth;
  const workspaceHeight = workspace.clientHeight;
  const scale = Math.min(workspaceWidth / imageWidth, workspaceHeight / imageHeight);
  const width = imageWidth * scale;
  const height = imageHeight * scale;
  imageLayout = {
    left: (workspaceWidth - width) / 2,
    top: (workspaceHeight - height) / 2,
    width,
    height,
    scale,
  };
  Object.assign(sourceImage.style, {
    left: `${imageLayout.left}px`,
    top: `${imageLayout.top}px`,
    width: `${imageLayout.width}px`,
    height: `${imageLayout.height}px`,
  });
}

function renderSelection() {
  selection = normalizedBox(selection);
  Object.assign(selectionElement.style, {
    left: `${imageLayout.left + selection.left * imageLayout.scale}px`,
    top: `${imageLayout.top + selection.top * imageLayout.scale}px`,
    width: `${selection.width * imageLayout.scale}px`,
    height: `${selection.height * imageLayout.scale}px`,
  });
}

function clampControllerPosition(position) {
  return {
    left: clamp(position.left, 0, workspace.clientWidth - precisionPad.offsetWidth),
    top: clamp(position.top, 0, workspace.clientHeight - precisionPad.offsetHeight),
  };
}

function defaultControllerPosition() {
  return clampControllerPosition({
    left: imageLayout.left + imageLayout.width - precisionPad.offsetWidth - 12,
    top: imageLayout.top + imageLayout.height - precisionPad.offsetHeight - 12,
  });
}

function renderController() {
  controllerPosition = clampControllerPosition(controllerPosition);
  precisionPad.style.left = `${controllerPosition.left}px`;
  precisionPad.style.top = `${controllerPosition.top}px`;
}

function resetWorkspace() {
  selection = normalizedBox(initialBox);
  controllerPosition = defaultControllerPosition();
  renderSelection();
  renderController();
}

function updateArrowState() {
  const allowedDirections = {
    top: new Set(["up", "down"]),
    bottom: new Set(["up", "down"]),
    left: new Set(["left", "right"]),
    right: new Set(["left", "right"]),
  }[activeEdge] || new Set();

  arrowButtons.forEach((button) => {
    const direction = button.dataset.direction;
    button.disabled = !allowedDirections.has(direction);
    button.tabIndex = button.disabled ? -1 : 0;
    const labelKey = activeEdge && allowedDirections.has(direction)
      ? `adjust_${activeEdge}_${direction}`
      : `move_${direction}`;
    button.setAttribute("aria-label", text(labelKey));
  });
}

function setActiveEdge(edge) {
  activeEdge = ["top", "right", "bottom", "left"].includes(edge) ? edge : "";
  selectionElement.dataset.activeEdge = activeEdge;
  edgeHandles.forEach((handle) => {
    handle.setAttribute("aria-pressed", String(handle.dataset.edge === activeEdge));
  });
  updateArrowState();
}

function renderStrings() {
  document.documentElement.lang = text("html_lang") || "en";
  sourceImage.alt = text("image_alt");
  selectionElement.setAttribute("aria-label", text("selection_label"));
  confirmButton.textContent = text("confirm");
  resetButton.textContent = text("reset");
  cancelButton.textContent = text("cancel");
  padCentre.setAttribute("aria-label", text("move_controller"));
  edgeHandles.forEach((handle) => {
    handle.setAttribute("aria-label", text(`resize_${handle.dataset.edge}`));
  });
  updateArrowState();
}

function setControllerActive(active) {
  precisionPad.classList.toggle("is-active", active);
}

function imageDelta(event, operation) {
  return {
    x: (event.clientX - operation.startX) / imageLayout.scale,
    y: (event.clientY - operation.startY) / imageLayout.scale,
  };
}

function startSelectionOperation(event, type, edge = "") {
  event.preventDefault();
  event.stopPropagation();
  const target = event.currentTarget;
  target.setPointerCapture(event.pointerId);
  pointerOperation = {
    kind: type,
    edge,
    pointerId: event.pointerId,
    target,
    startX: event.clientX,
    startY: event.clientY,
    startBox: { ...selection },
  };
}

selectionElement.addEventListener("pointerdown", (event) => {
  if (event.target !== selectionElement) {
    return;
  }
  startSelectionOperation(event, "move-selection");
});

edgeHandles.forEach((handle) => {
  handle.addEventListener("pointerdown", (event) => {
    setActiveEdge(handle.dataset.edge);
    startSelectionOperation(event, "resize-selection", handle.dataset.edge);
  });
});

padCentre.addEventListener("pointerdown", (event) => {
  event.preventDefault();
  event.stopPropagation();
  padCentre.setPointerCapture(event.pointerId);
  setControllerActive(true);
  pointerOperation = {
    kind: "move-controller",
    pointerId: event.pointerId,
    target: padCentre,
    startX: event.clientX,
    startY: event.clientY,
    startController: { ...controllerPosition },
  };
});

window.addEventListener("pointermove", (event) => {
  if (!pointerOperation || event.pointerId !== pointerOperation.pointerId) {
    return;
  }
  event.preventDefault();

  if (pointerOperation.kind === "move-controller") {
    controllerPosition = clampControllerPosition({
      left: pointerOperation.startController.left + event.clientX - pointerOperation.startX,
      top: pointerOperation.startController.top + event.clientY - pointerOperation.startY,
    });
    renderController();
    return;
  }

  const delta = imageDelta(event, pointerOperation);
  const start = pointerOperation.startBox;
  if (pointerOperation.kind === "move-selection") {
    selection = {
      ...start,
      left: clamp(start.left + delta.x, 0, imageWidth - start.width),
      top: clamp(start.top + delta.y, 0, imageHeight - start.height),
    };
  } else if (pointerOperation.edge === "left") {
    const right = start.left + start.width;
    const left = clamp(start.left + delta.x, 0, right - minCropSize);
    selection = { ...start, left, width: right - left };
  } else if (pointerOperation.edge === "right") {
    selection = {
      ...start,
      width: clamp(start.width + delta.x, minCropSize, imageWidth - start.left),
    };
  } else if (pointerOperation.edge === "top") {
    const bottom = start.top + start.height;
    const top = clamp(start.top + delta.y, 0, bottom - minCropSize);
    selection = { ...start, top, height: bottom - top };
  } else if (pointerOperation.edge === "bottom") {
    selection = {
      ...start,
      height: clamp(start.height + delta.y, minCropSize, imageHeight - start.top),
    };
  }
  renderSelection();
});

function finishPointerOperation(event) {
  if (!pointerOperation || event.pointerId !== pointerOperation.pointerId) {
    return;
  }
  if (pointerOperation.target.hasPointerCapture(event.pointerId)) {
    pointerOperation.target.releasePointerCapture(event.pointerId);
  }
  if (pointerOperation.kind === "move-controller") {
    setControllerActive(false);
  }
  pointerOperation = null;
}

window.addEventListener("pointerup", finishPointerOperation);
window.addEventListener("pointercancel", finishPointerOperation);

function adjustSelectionEdge(direction) {
  const displayPixel = 1 / imageLayout.scale;
  if (activeEdge === "left" && direction === "left") {
    const right = selection.left + selection.width;
    const left = clamp(selection.left - displayPixel, 0, right - minCropSize);
    selection = { ...selection, left, width: right - left };
  } else if (activeEdge === "left" && direction === "right") {
    const right = selection.left + selection.width;
    const left = clamp(selection.left + displayPixel, 0, right - minCropSize);
    selection = { ...selection, left, width: right - left };
  } else if (activeEdge === "right" && direction === "left") {
    selection = {
      ...selection,
      width: clamp(selection.width - displayPixel, minCropSize, imageWidth - selection.left),
    };
  } else if (activeEdge === "right" && direction === "right") {
    selection = {
      ...selection,
      width: clamp(selection.width + displayPixel, minCropSize, imageWidth - selection.left),
    };
  } else if (activeEdge === "top" && direction === "up") {
    const bottom = selection.top + selection.height;
    const top = clamp(selection.top - displayPixel, 0, bottom - minCropSize);
    selection = { ...selection, top, height: bottom - top };
  } else if (activeEdge === "top" && direction === "down") {
    const bottom = selection.top + selection.height;
    const top = clamp(selection.top + displayPixel, 0, bottom - minCropSize);
    selection = { ...selection, top, height: bottom - top };
  } else if (activeEdge === "bottom" && direction === "up") {
    selection = {
      ...selection,
      height: clamp(selection.height - displayPixel, minCropSize, imageHeight - selection.top),
    };
  } else if (activeEdge === "bottom" && direction === "down") {
    selection = {
      ...selection,
      height: clamp(selection.height + displayPixel, minCropSize, imageHeight - selection.top),
    };
  } else {
    return;
  }
  renderSelection();
}

function stopArrowRepeat() {
  window.clearTimeout(repeatDelay);
  window.clearInterval(repeatTimer);
  repeatDelay = null;
  repeatTimer = null;
  setControllerActive(false);
}

arrowButtons.forEach((button) => {
  button.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    event.stopPropagation();
    button.setPointerCapture(event.pointerId);
    setControllerActive(true);
    adjustSelectionEdge(button.dataset.direction);
    repeatDelay = window.setTimeout(() => {
      repeatTimer = window.setInterval(() => {
        adjustSelectionEdge(button.dataset.direction);
      }, 70);
    }, 400);
  });
  button.addEventListener("pointerup", stopArrowRepeat);
  button.addEventListener("pointercancel", stopArrowRepeat);
  button.addEventListener("lostpointercapture", stopArrowRepeat);
});

window.addEventListener("blur", stopArrowRepeat);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    stopArrowRepeat();
  }
});
window.addEventListener("pagehide", stopArrowRepeat);

["contextmenu", "selectstart", "dragstart"].forEach((eventName) => {
  precisionPad.addEventListener(eventName, (event) => {
    event.preventDefault();
    event.stopPropagation();
    stopArrowRepeat();
  });
});

["touchstart", "touchmove"].forEach((eventName) => {
  precisionPad.addEventListener(eventName, (event) => {
    event.preventDefault();
  }, { passive: false });
});

["touchend", "touchcancel"].forEach((eventName) => {
  precisionPad.addEventListener(eventName, stopArrowRepeat, { passive: true });
});

selectionElement.addEventListener("keydown", (event) => {
  const direction = {
    ArrowUp: "up",
    ArrowDown: "down",
    ArrowLeft: "left",
    ArrowRight: "right",
  }[event.key];
  if (direction) {
    event.preventDefault();
    adjustSelectionEdge(direction);
  }
});

resetButton.addEventListener("click", resetWorkspace);

cancelButton.addEventListener("click", () => {
  Streamlit.setComponentValue({
    action: "cancel",
    action_id: `${Date.now()}-${Math.random()}`,
    image_signature: imageSignature,
  });
});

confirmButton.addEventListener("click", () => {
  Streamlit.setComponentValue({
    action: "confirm",
    action_id: `${Date.now()}-${Math.random()}`,
    image_signature: imageSignature,
    box: { ...selection },
  });
});

function layoutWorkspace(resetController = false) {
  calculateImageLayout();
  renderSelection();
  if (resetController) {
    controllerPosition = defaultControllerPosition();
  }
  renderController();
  Streamlit.setFrameHeight();
}

function onRender(event) {
  const args = event.detail.args || {};
  const nextSignature = String(args.image_signature || "");
  const isNewSession = nextSignature !== imageSignature;

  strings = args.strings || {};
  applyTheme(event.detail.theme);
  renderStrings();

  if (isNewSession) {
    imageSignature = nextSignature;
    imageWidth = Math.max(1, Number(args.image_width) || 1);
    imageHeight = Math.max(1, Number(args.image_height) || 1);
    minCropSize = Math.max(1, Number(args.min_crop_size) || 50);
    initialBox = normalizedBox(args.initial_box || {});
    selection = { ...initialBox };
    setActiveEdge("right");
    sourceImage.onload = () => layoutWorkspace(true);
    sourceImage.src = String(args.image_data || "");
  } else if (sourceImage.complete) {
    layoutWorkspace(false);
  }
}

window.addEventListener("resize", () => layoutWorkspace(false));
Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, onRender);
Streamlit.setComponentReady();
