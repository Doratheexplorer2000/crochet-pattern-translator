import { Streamlit } from "streamlit-component-lib";

const input = document.getElementById("image-input");
const root = document.getElementById("upload-root");
const emptyState = document.getElementById("empty-state");
const readingState = document.getElementById("reading-state");
const selectedState = document.getElementById("selected-state");
const instruction = document.getElementById("upload-instruction");
const chooseButton = document.getElementById("choose-button");
const dropHint = document.getElementById("drop-hint");
const readingText = document.getElementById("reading-text");
const selectedLabel = document.getElementById("selected-label");
const fileName = document.getElementById("file-name");
const error = document.getElementById("upload-error");
const replaceButton = document.getElementById("replace-button");
const removeButton = document.getElementById("remove-button");

let allowedExtensions = ["jpeg", "jpg", "png", "webp"];
let allowedMimeTypes = ["image/jpeg", "image/png", "image/webp"];
let maxUploadBytes = 0;
let strings = {};
let selectedFile = null;
let selectedPayload = null;
let reading = false;
let backendImagePresent = false;
let backendImageName = "";

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

function setState(state) {
  emptyState.hidden = state !== "empty";
  readingState.hidden = state !== "reading";
  selectedState.hidden = state !== "selected";
  chooseButton.disabled = reading;
  replaceButton.disabled = reading;
  removeButton.disabled = reading;
  Streamlit.setFrameHeight();
}

function hasActiveImage() {
  return Boolean(selectedFile || selectedPayload || backendImagePresent);
}

function renderActiveFileName() {
  fileName.textContent = selectedFile ? selectedFile.name : backendImageName;
}

function renderStrings() {
  document.documentElement.lang = text("html_lang") || "en";
  instruction.textContent = text("instruction");
  chooseButton.textContent = text("choose");
  dropHint.textContent = emptyState.classList.contains("drag-over")
    ? text("drop_active")
    : text("drop_hint");
  readingText.textContent = text("reading");
  selectedLabel.textContent = text("selected");
  replaceButton.textContent = text("replace");
  removeButton.textContent = text("remove");
}

function showError(errorCode) {
  error.textContent = text(errorCode);
  Streamlit.setComponentValue(
    selectedPayload
      ? { ...selectedPayload, frontend_error_code: errorCode }
      : { error_code: errorCode },
  );
  renderActiveFileName();
  setState(hasActiveImage() ? "selected" : "empty");
}

function clearError() {
  error.textContent = "";
}

function validateFile(file) {
  if (!file || file.size === 0) {
    return "error_empty";
  }
  if (!allowedExtensions.includes(extensionFor(file.name))) {
    return "error_unsupported";
  }
  if (file.type && !allowedMimeTypes.includes(file.type.toLowerCase())) {
    return "error_unsupported";
  }
  if (maxUploadBytes > 0 && file.size > maxUploadBytes) {
    return "error_too_large";
  }
  return "";
}

function finishReading() {
  reading = false;
  renderActiveFileName();
  setState(hasActiveImage() ? "selected" : "empty");
}

function processFile(file) {
  const previousFile = selectedFile;
  const previousPayload = selectedPayload;
  const validationError = validateFile(file);
  if (validationError) {
    input.value = "";
    showError(validationError);
    return;
  }

  selectedFile = file;
  fileName.textContent = file.name;
  clearError();
  reading = true;
  setState("reading");

  const reader = new FileReader();
  reader.onerror = () => {
    selectedFile = previousFile;
    selectedPayload = previousPayload;
    renderActiveFileName();
    input.value = "";
    finishReading();
    showError("error_unreadable");
  };
  reader.onload = () => {
    const result = String(reader.result || "");
    const commaIndex = result.indexOf(",");
    if (commaIndex < 0) {
      selectedFile = previousFile;
      selectedPayload = previousPayload;
      renderActiveFileName();
      input.value = "";
      finishReading();
      showError("error_unreadable");
      return;
    }
    selectedPayload = {
      name: file.name,
      type: file.type,
      size: file.size,
      data_base64: result.slice(commaIndex + 1),
      action_id: createActionId(),
    };
    Streamlit.setComponentValue(selectedPayload);
    finishReading();
  };
  reader.readAsDataURL(file);
}

function openPicker() {
  if (reading) {
    return;
  }
  input.value = "";
  input.click();
}

function clearDragState() {
  emptyState.classList.remove("drag-over");
  renderStrings();
  Streamlit.setFrameHeight();
}

function extensionFor(name) {
  const parts = name.toLowerCase().split(".");
  return parts.length > 1 ? parts.pop() : "";
}

function createActionId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function onRender(event) {
  const args = event.detail.args || {};
  strings = args.strings || {};
  allowedExtensions = args.allowed_extensions || allowedExtensions;
  allowedMimeTypes = args.allowed_mime_types || allowedMimeTypes;
  maxUploadBytes = args.max_upload_bytes || maxUploadBytes;
  backendImagePresent = Boolean(args.active_image_present);
  backendImageName = String(args.active_image_name || "");
  applyTheme(event.detail.theme);
  renderStrings();
  renderActiveFileName();
  setState(reading ? "reading" : hasActiveImage() ? "selected" : "empty");
}

chooseButton.addEventListener("click", openPicker);
replaceButton.addEventListener("click", openPicker);

removeButton.addEventListener("click", () => {
  if (reading) {
    return;
  }
  selectedFile = null;
  selectedPayload = null;
  backendImagePresent = false;
  backendImageName = "";
  input.value = "";
  fileName.textContent = "";
  clearError();
  setState("empty");
  Streamlit.setComponentValue({ removed: true, action_id: Date.now() });
});

input.addEventListener("change", () => {
  const file = input.files && input.files[0];
  processFile(file);
});

root.addEventListener("dragenter", (event) => {
  event.preventDefault();
  if (!reading && !selectedFile) {
    emptyState.classList.add("drag-over");
    renderStrings();
  }
});

root.addEventListener("dragover", (event) => {
  event.preventDefault();
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = "copy";
  }
});

root.addEventListener("dragleave", (event) => {
  if (!root.contains(event.relatedTarget)) {
    clearDragState();
  }
});

root.addEventListener("drop", (event) => {
  event.preventDefault();
  clearDragState();
  if (reading) {
    return;
  }
  const file = event.dataTransfer && event.dataTransfer.files
    ? event.dataTransfer.files[0]
    : null;
  processFile(file);
});

window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && emptyState.classList.contains("drag-over")) {
    clearDragState();
  }
});

Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, onRender);
Streamlit.setComponentReady();
setState("empty");
