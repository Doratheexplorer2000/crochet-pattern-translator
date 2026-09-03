import { displayBoxToImage, normalizedCropBox, readExifOrientation, resizeCropBox } from "/static/crop_coordinates.js";
import { modeLabelFor, resolveUiLang, stringsFor } from "/static/translations.js";
import { MODE_VALUES, adaptApiError, applyQualityResponse, beginTranslation, canTranslate, confirmPoorQuality, diagnosticFilename, discardCompletedResult, forceRunForCurrentQuality, hasCurrentQuality, invalidateQuality, invalidateRequest, isCurrentDiagnosticRequest, isCurrentImage, isCurrentQualityRequest, isCurrentRequest, isValidQualityResponse, isValidTranslationResponse, postDiagnosticReport, qualityFormEntries, qualityIdentity, restartCropWorkflow, translationFormEntries, validateImageFile } from "/static/workflow_state.js";

const MAX_BYTES = 25 * 1024 * 1024;
const state = {
  file: null, source: "", target: "", area: "Whole Pattern", crop: null, imageState: "empty",
  generation: 0, loading: false, controller: null, imageUrl: null, pngUrl: null, txtUrl: null,
  diagnosticContext: null, diagnosticLoading: false, diagnosticController: null,
  qualityAssessment: null, qualityFile: null, qualityArea: null, qualityCrop: null,
  qualityConfirmed: false, qualityError: false, qualityGeneration: 0,
  qualityLoading: false, qualityController: null,
  image: { orientation: 1, rawWidth: 0, rawHeight: 0, width: 1, height: 1 },
  selection: null, initialSelection: null, layout: null, controllerPosition: { left: 0, top: 0 },
  activeEdge: "right", pointer: null, repeatDelay: null, repeatTimer: null,
};
const $ = (id) => document.getElementById(id);
const input = $("image-input");
const zone = $("drop-zone");
const sourceImage = $("source-image");
const selectionEl = $("selection");
const workspace = $("workspace");
const precisionPad = $("precision-pad");
const arrowButtons = [...document.querySelectorAll("#precision-pad [data-direction]")];
const edgeButtons = [...document.querySelectorAll(".edge")];
let uiLang;
let text;

function clearObjectUrl(key) {
  if (state[key]) URL.revokeObjectURL(state[key]);
  state[key] = null;
}

function updateTranslateAvailability() {
  const translate = $("translate-button");
  $("translation-action").hidden = !state.file || state.imageState !== "ready" || (state.area === "Select Area" && !state.crop);
  translate.disabled = state.loading || !canTranslate(state);
  translate.textContent = state.loading ? text.runningAction : text.translate;
}

function renderQuality() {
  const section = $("quality-section");
  const usable = state.file
    && state.imageState === "ready"
    && (state.area === "Whole Pattern" || state.crop);
  section.hidden = !usable;
  section.className = "quality-section";
  $("quality-block-warning").hidden = true;
  $("force-ocr-control").hidden = true;
  $("force-ocr").checked = forceRunForCurrentQuality(state);
  if (!usable) return;
  if (state.qualityLoading) {
    section.classList.add("quality-pending");
    $("quality-label").textContent = text.qualityAssessing;
    $("quality-message").textContent = "";
    return;
  }
  if (state.qualityError || !hasCurrentQuality(state)) {
    section.classList.add("quality-error");
    $("quality-label").textContent = text.qualityAssessmentError;
    $("quality-message").textContent = "";
    return;
  }
  const level = state.qualityAssessment.level;
  section.classList.add(`quality-${level}`);
  $("quality-label").textContent = text[`quality${level[0].toUpperCase()}${level.slice(1)}`];
  $("quality-message").textContent = text[`quality${level[0].toUpperCase()}${level.slice(1)}Message`];
  if (level === "poor") {
    $("quality-block-warning").hidden = false;
    $("force-ocr-control").hidden = false;
  }
}

function updateDiagnosticAvailability() {
  const button = $("diagnostic-download");
  button.hidden = !state.diagnosticContext;
  button.disabled = state.diagnosticLoading || !state.diagnosticContext;
  button.textContent = state.diagnosticLoading ? text.diagnosticLoading : text.downloadDiagnostic;
}

function invalidateTranslationRequest() {
  const controller = invalidateRequest(state);
  controller?.abort();
  state.controller = null;
  state.diagnosticController?.abort();
  state.diagnosticController = null;
  state.diagnosticLoading = false;
  setMessage();
  setDiagnosticMessage();
  updateDiagnosticAvailability();
  updateTranslateAvailability();
}

function clearCompletedResult() {
  discardCompletedResult(state, (url) => URL.revokeObjectURL(url));
  $("overlay-image").removeAttribute("src");
  $("png-download").removeAttribute("href");
  $("txt-download").removeAttribute("href");
  $("translation-text").textContent = "";
  $("result-section").hidden = true;
  setDiagnosticMessage();
  updateDiagnosticAvailability();
}

function invalidateQualityForInput() {
  invalidateQuality(state)?.abort();
  renderQuality();
  updateTranslateAvailability();
}

function setMessage(status = "", error = "") {
  $("status").textContent = status;
  $("error").textContent = error;
}

function surfaceTranslationError(error) {
  setMessage("", error);
  $("error").scrollIntoView({ block: "center" });
}

function setDiagnosticMessage(message = "") {
  $("diagnostic-status").textContent = message;
}

function renderWorkflow() {
  const reading = state.imageState === "reading";
  const ready = state.imageState === "ready";
  $("upload-empty").hidden = state.imageState !== "empty";
  $("upload-reading").hidden = !reading;
  $("upload-selected").hidden = !ready;
  $("settings").hidden = !ready;
  $("original-preview").hidden = !ready;
  $("crop-confirmed").hidden = !ready || state.area !== "Select Area" || !state.crop;
  $("file-name").textContent = state.file?.name || "";
  $("preview-image").src = ready ? state.imageUrl : "";
  $("preview-image").alt = ready ? text.originalImage : "";
  renderHints();
  renderQuality();
  updateTranslateAvailability();
}

function renderHints() {
  const hintFor = (mode, us, uk) => mode === "English — US" ? text[us] : mode === "English — UK" ? text[uk] : "";
  const sourceHint = hintFor(state.source, "sourceHintUs", "sourceHintUk");
  const targetHint = hintFor(state.target, "targetHintUs", "targetHintUk");
  $("source-hint").textContent = sourceHint;
  $("source-hint").hidden = !sourceHint;
  $("target-hint").textContent = targetHint;
  $("target-hint").hidden = !targetHint;
  $("area-tip").hidden = state.area !== "Select Area";
}

function renderLanguage() {
  uiLang = resolveUiLang(new URLSearchParams(location.search).get("ui_lang"), navigator.languages || [navigator.language]);
  text = stringsFor(uiLang);
  document.documentElement.lang = uiLang;
  document.title = text.title;
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = text[element.dataset.i18n] || "";
  });
  $("portal-link").href = `https://crochetintelligence.com?ui_lang=${encodeURIComponent(uiLang)}`;
  sourceImage.alt = text.imageAlt;
  $("preview-image").alt = text.originalImage;
  selectionEl.setAttribute("aria-label", text.selection);
  $("move-pad").setAttribute("aria-label", text.moveControls);
  $("move-pad").title = text.moveControls;
  edgeButtons.forEach((button) => {
    const edge = button.dataset.edge;
    button.setAttribute("aria-label", text[`resize${edge[0].toUpperCase()}${edge.slice(1)}`]);
  });
  updateDiagnosticAvailability();
  updateArrowState();
}

function populateModeSelects() {
  for (const id of ["source-mode", "output-mode"]) {
    const select = $(id);
    const placeholder = new Option(text.chooseOption, "", true, true);
    placeholder.disabled = true;
    select.replaceChildren(placeholder, ...MODE_VALUES.map((mode) => new Option(modeLabelFor(mode, uiLang), mode)));
    select.value = id === "source-mode" ? state.source : state.target;
  }
}

function validateFile(file) {
  const reason = validateImageFile(file, MAX_BYTES);
  return {
    empty: text.errorEmpty,
    large: text.errorLarge,
    unsupported: text.errorUnsupported,
  }[reason] || "";
}

function acceptFile(file) {
  const error = validateFile(file);
  if (error) {
    setMessage("", error);
    return;
  }
  invalidateTranslationRequest();
  invalidateQualityForInput();
  clearCompletedResult();
  clearObjectUrl("imageUrl");
  state.file = file;
  state.imageState = "reading";
  state.crop = null;
  state.selection = null;
  state.initialSelection = null;
  state.imageUrl = URL.createObjectURL(file);
  sourceImage.src = state.imageUrl;
  setMessage();
  renderWorkflow();
  track("pattern_image_uploaded");
}

function removeFile() {
  invalidateTranslationRequest();
  invalidateQualityForInput();
  clearCompletedResult();
  clearObjectUrl("imageUrl");
  state.file = null;
  state.imageState = "empty";
  state.crop = null;
  state.selection = null;
  state.initialSelection = null;
  sourceImage.removeAttribute("src");
  $("preview-image").removeAttribute("src");
  $("crop-preview").removeAttribute("src");
  input.value = "";
  closeCropper();
  setMessage();
  renderWorkflow();
}

async function initializeImage() {
  const file = state.file;
  const token = state.generation;
  if (!file) return;
  let orientation = 1;
  try {
    orientation = readExifOrientation(await file.arrayBuffer());
  } catch (_) {
    // A browser-read failure is non-fatal; display defaults to orientation 1.
  }
  if (!isCurrentImage(state, token, file)) return;
  const width = sourceImage.naturalWidth;
  const height = sourceImage.naturalHeight;
  if (!width || !height) {
    state.imageState = "empty";
    invalidateQualityForInput();
    setMessage("", text.errorUnreadable);
    renderWorkflow();
    return;
  }
  state.image = {
    orientation,
    width,
    height,
    rawWidth: [5, 6, 7, 8].includes(orientation) ? height : width,
    rawHeight: [5, 6, 7, 8].includes(orientation) ? width : height,
  };
  state.initialSelection = normalizedCropBox(
    { left: Math.floor(width * 0.25), top: Math.floor(height * 0.25), width: Math.floor(width * 0.5), height: Math.floor(height * 0.5) },
    width, height,
  );
  state.selection = { ...state.initialSelection };
  state.imageState = "ready";
  $("preview-image").src = state.imageUrl;
  setMessage();
  if (state.area === "Select Area") openCropper();
  renderWorkflow();
  if (state.area === "Whole Pattern") assessCurrentImageQuality();
}

function calculateLayout() {
  const scale = Math.min(workspace.clientWidth / state.image.width, workspace.clientHeight / state.image.height);
  return {
    scale,
    left: (workspace.clientWidth - state.image.width * scale) / 2,
    top: (workspace.clientHeight - state.image.height * scale) / 2,
  };
}

function clampControllerPosition(position) {
  return {
    left: Math.max(0, Math.min(workspace.clientWidth - precisionPad.offsetWidth, position.left)),
    top: Math.max(0, Math.min(workspace.clientHeight - precisionPad.offsetHeight, position.top)),
  };
}

function defaultControllerPosition() {
  const { left, top, scale } = state.layout;
  return clampControllerPosition({
    left: left + state.image.width * scale - precisionPad.offsetWidth - 12,
    top: top + state.image.height * scale - precisionPad.offsetHeight - 12,
  });
}

function renderSelection() {
  if (!state.layout || !state.selection) return;
  state.selection = normalizedCropBox(state.selection, state.image.width, state.image.height);
  const { left, top, scale } = state.layout;
  const box = state.selection;
  Object.assign(selectionEl.style, {
    left: `${left + box.left * scale}px`,
    top: `${top + box.top * scale}px`,
    width: `${box.width * scale}px`,
    height: `${box.height * scale}px`,
  });
}

function renderPrecisionPad() {
  state.controllerPosition = clampControllerPosition(state.controllerPosition);
  precisionPad.style.left = `${state.controllerPosition.left}px`;
  precisionPad.style.top = `${state.controllerPosition.top}px`;
}

function layoutCropper(resetController = false) {
  if (!state.selection || $("crop-section").hidden) return;
  state.layout = calculateLayout();
  Object.assign(sourceImage.style, {
    left: `${state.layout.left}px`, top: `${state.layout.top}px`,
    width: `${state.image.width * state.layout.scale}px`, height: `${state.image.height * state.layout.scale}px`,
  });
  renderSelection();
  if (resetController) state.controllerPosition = defaultControllerPosition();
  renderPrecisionPad();
}

function updateArrowState() {
  const allowed = {
    top: new Set(["up", "down"]),
    bottom: new Set(["up", "down"]),
    left: new Set(["left", "right"]),
    right: new Set(["left", "right"]),
  }[state.activeEdge] || new Set();
  arrowButtons.forEach((button) => {
    const direction = button.dataset.direction;
    button.disabled = !allowed.has(direction);
    button.tabIndex = button.disabled ? -1 : 0;
  });
  edgeButtons.forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.edge === state.activeEdge));
  });
  selectionEl.dataset.activeEdge = state.activeEdge;
}

function openCropper() {
  if (!state.initialSelection) return;
  stopCropperActivity();
  state.crop = null;
  state.selection = { ...state.initialSelection };
  $("crop-section").hidden = false;
  state.activeEdge = "right";
  updateArrowState();
  requestAnimationFrame(() => layoutCropper(true));
  renderWorkflow();
}

function closeCropper() {
  stopCropperActivity();
  $("crop-section").hidden = true;
}

function renderCropPreview() {
  if (!state.selection || !sourceImage.naturalWidth || !sourceImage.naturalHeight) return;
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(state.selection.width));
  canvas.height = Math.max(1, Math.round(state.selection.height));
  canvas.getContext("2d").drawImage(
    sourceImage,
    state.selection.left, state.selection.top, state.selection.width, state.selection.height,
    0, 0, canvas.width, canvas.height,
  );
  $("crop-preview").src = canvas.toDataURL("image/png");
  $("crop-preview").alt = text.cropPreviewCaption;
}

function startPointer(event, kind, edge = "") {
  event.preventDefault();
  event.stopPropagation();
  event.currentTarget.setPointerCapture(event.pointerId);
  if (edge) {
    state.activeEdge = edge;
    updateArrowState();
  }
  state.pointer = {
    kind, edge, id: event.pointerId, target: event.currentTarget,
    startX: event.clientX, startY: event.clientY,
    startSelection: { ...state.selection }, startController: { ...state.controllerPosition },
  };
  precisionPad.classList.add("is-active");
}

function movePointer(event) {
  const operation = state.pointer;
  if (!operation || operation.id !== event.pointerId) return;
  event.preventDefault();
  if (operation.kind === "move-controller") {
    state.controllerPosition = clampControllerPosition({
      left: operation.startController.left + event.clientX - operation.startX,
      top: operation.startController.top + event.clientY - operation.startY,
    });
    renderPrecisionPad();
    return;
  }
  const delta = operation.edge === "top" || operation.edge === "bottom"
    ? (event.clientY - operation.startY) / state.layout.scale
    : (event.clientX - operation.startX) / state.layout.scale;
  if (operation.kind === "move-selection") {
    state.selection = normalizedCropBox({
      ...operation.startSelection,
      left: operation.startSelection.left + (event.clientX - operation.startX) / state.layout.scale,
      top: operation.startSelection.top + (event.clientY - operation.startY) / state.layout.scale,
    }, state.image.width, state.image.height);
  } else {
    state.selection = resizeCropBox(operation.startSelection, operation.edge, delta, state.image.width, state.image.height);
  }
  renderSelection();
}

function finishPointer(event) {
  if (state.pointer && (!event || state.pointer.id === event.pointerId)) {
    const { target, id } = state.pointer;
    if (target.hasPointerCapture?.(id)) target.releasePointerCapture(id);
    state.pointer = null;
  }
  precisionPad.classList.remove("is-active");
}

function adjustSelection(direction) {
  const edge = state.activeEdge;
  const horizontal = edge === "left" || edge === "right";
  if ((horizontal && !["left", "right"].includes(direction)) || (!horizontal && !["up", "down"].includes(direction))) return;
  const amount = 1 / (state.layout?.scale || 1);
  const delta = ["left", "up"].includes(direction) ? -amount : amount;
  state.selection = resizeCropBox(state.selection, edge, delta, state.image.width, state.image.height);
  renderSelection();
}

function stopArrowRepeat() {
  clearTimeout(state.repeatDelay);
  clearInterval(state.repeatTimer);
  state.repeatDelay = null;
  state.repeatTimer = null;
  precisionPad.classList.remove("is-active");
}

function stopCropperActivity() {
  stopArrowRepeat();
  finishPointer();
}

function startArrowRepeat(event, button) {
  event.preventDefault();
  event.stopPropagation();
  button.setPointerCapture(event.pointerId);
  stopArrowRepeat();
  precisionPad.classList.add("is-active");
  adjustSelection(button.dataset.direction);
  state.repeatDelay = window.setTimeout(() => {
    state.repeatTimer = window.setInterval(() => adjustSelection(button.dataset.direction), 70);
  }, 400);
}

function currentCropBox() {
  const box = state.selection;
  return displayBoxToImage({
    left: box.left, top: box.top, right: box.left + box.width, bottom: box.top + box.height,
  }, state.image.width, state.image.height);
}

async function responseJson(response) {
  try {
    return await response.json();
  } catch (_) {
    return null;
  }
}

async function assessCurrentImageQuality() {
  if (
    !state.file
    || state.imageState !== "ready"
    || (state.area === "Select Area" && !state.crop)
  ) return;
  invalidateQuality(state)?.abort();
  const identity = qualityIdentity(state);
  const token = state.qualityGeneration;
  const controller = new AbortController();
  state.qualityController = controller;
  state.qualityLoading = true;
  state.qualityError = false;
  renderQuality();
  updateTranslateAvailability();
  const data = new FormData();
  data.append("image", identity.file);
  qualityFormEntries(state).forEach(([name, value]) => data.append(name, value));
  try {
    const response = await fetch("/api/v1/image-quality", {
      method: "POST",
      body: data,
      signal: controller.signal,
    });
    const body = await responseJson(response);
    if (!isCurrentQualityRequest(state, token, identity)) return;
    if (!response.ok || !applyQualityResponse(state, body, identity)) {
      state.qualityError = true;
    }
  } catch (error) {
    if (
      isCurrentQualityRequest(state, token, identity)
      && error?.name !== "AbortError"
    ) state.qualityError = true;
  } finally {
    if (
      isCurrentQualityRequest(state, token, identity)
      && state.qualityController === controller
    ) {
      state.qualityLoading = false;
      state.qualityController = null;
      renderQuality();
      updateTranslateAvailability();
    }
  }
}

async function translate() {
  const controller = new AbortController();
  const token = beginTranslation(state, controller);
  if (token === null) return;
  const identity = qualityIdentity(state);
  setMessage(text.translating);
  updateTranslateAvailability();
  const data = new FormData();
  data.append("image", state.file);
  translationFormEntries(state).forEach(([name, value]) => data.append(name, value));
  try {
    const response = await fetch("/api/v1/translate", { method: "POST", body: data, signal: controller.signal });
    const body = await responseJson(response);
    if (!isCurrentRequest(state, token)) return;
    if (!response.ok) {
      const qualityConflict = (
        response.status === 409
        && isCurrentQualityRequest(state, state.qualityGeneration, identity)
        && isValidQualityResponse(body, identity)
      );
      if (qualityConflict) {
        applyQualityResponse(state, body, identity);
        renderQuality();
        setMessage();
      } else {
        surfaceTranslationError(adaptApiError(response.status, body, text));
      }
      return;
    }
    if (!isValidTranslationResponse(body, state, identity)) {
      surfaceTranslationError(text.errorGeneric);
      return;
    }
    try {
      showResult(body);
    } catch (_) {
      surfaceTranslationError(text.errorGeneric);
      return;
    }
    applyQualityResponse(state, body, identity, true);
    renderQuality();
    track("pattern_translation_completed");
    setMessage();
  } catch (error) {
    if (isCurrentRequest(state, token) && error?.name !== "AbortError") {
      surfaceTranslationError(text.errorNetwork);
    }
  } finally {
    if (isCurrentRequest(state, token) && state.controller === controller) {
      state.loading = false;
      state.controller = null;
      updateTranslateAvailability();
    }
  }
}

function showResult(body) {
  if (!body.overlay_png?.base64) throw new Error("missing overlay");
  const binary = atob(body.overlay_png.base64);
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  let pngUrl;
  let txtUrl;
  try {
    pngUrl = URL.createObjectURL(new Blob([bytes], { type: "image/png" }));
    txtUrl = URL.createObjectURL(new Blob([body.translation_txt || ""], { type: "text/plain;charset=utf-8" }));
  } catch (error) {
    if (pngUrl) URL.revokeObjectURL(pngUrl);
    if (txtUrl) URL.revokeObjectURL(txtUrl);
    throw error;
  }
  const previousPngUrl = state.pngUrl;
  const previousTxtUrl = state.txtUrl;
  state.diagnosticController?.abort();
  state.diagnosticController = null;
  state.diagnosticLoading = false;
  state.pngUrl = pngUrl;
  state.txtUrl = txtUrl;
  $("overlay-image").src = state.pngUrl;
  $("png-download").href = state.pngUrl;
  $("png-download").download = "crochet_ocr_overlay_translation.png";
  $("txt-download").href = state.txtUrl;
  $("txt-download").download = "crochet_translation.txt";
  $("translation-text").textContent = body.readable_translation || body.translation_txt || "";
  state.diagnosticContext = body.diagnostic_context && typeof body.diagnostic_context === "object"
    ? body.diagnostic_context
    : null;
  setDiagnosticMessage();
  updateDiagnosticAvailability();
  $("result-section").hidden = false;
  if (previousPngUrl) URL.revokeObjectURL(previousPngUrl);
  if (previousTxtUrl) URL.revokeObjectURL(previousTxtUrl);
}

async function downloadDiagnostic() {
  if (!state.diagnosticContext || state.diagnosticLoading) return;
  const token = state.generation;
  const diagnosticContext = state.diagnosticContext;
  const controller = new AbortController();
  state.diagnosticController = controller;
  state.diagnosticLoading = true;
  setDiagnosticMessage(text.diagnosticLoading);
  updateDiagnosticAvailability();
  try {
    const response = await postDiagnosticReport(
      fetch,
      diagnosticContext,
      uiLang,
      controller.signal,
    );
    if (!isCurrentDiagnosticRequest(state, token, diagnosticContext)) return;
    if (!response.ok) throw new Error("diagnostic request failed");
    const reportText = await response.text();
    if (!isCurrentDiagnosticRequest(state, token, diagnosticContext)) return;
    const reportUrl = URL.createObjectURL(new Blob([reportText], { type: "text/plain;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = reportUrl;
    anchor.download = diagnosticFilename(response);
    anchor.hidden = true;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(reportUrl), 1000);
    setDiagnosticMessage();
  } catch (error) {
    if (
      isCurrentDiagnosticRequest(state, token, diagnosticContext)
      && error?.name !== "AbortError"
    ) {
      setDiagnosticMessage(text.diagnosticError);
    }
  } finally {
    if (
      isCurrentDiagnosticRequest(state, token, diagnosticContext)
      && state.diagnosticController === controller
    ) {
      state.diagnosticLoading = false;
      state.diagnosticController = null;
      updateDiagnosticAvailability();
    }
  }
}

function track(event) {
  try {
    window.plausible?.(event, { url: location.href });
  } catch (_) {
    // Analytics is observational.
  }
}

async function initialiseAnalytics() {
  try {
    const response = await fetch("/api/v1/browser-config");
    const config = await responseJson(response);
    const scriptUrl = String(config?.plausible_script_url || "").trim();
    if (!scriptUrl) return;
    window.plausible = window.plausible || ((...args) => {
      (window.plausible.q = window.plausible.q || []).push(args);
    });
    window.plausible.init = window.plausible.init || ((options) => {
      window.plausible.o = options || {};
    });
    window.plausible.init();
    const script = document.createElement("script");
    script.async = true;
    script.src = scriptUrl;
    script.id = "ci-plausible-script";
    document.head.append(script);
  } catch (_) {}
}

input.addEventListener("change", () => acceptFile(input.files?.[0]));
["choose-button", "replace-button"].forEach((id) => $(id).addEventListener("click", () => { input.value = ""; input.click(); }));
$("remove-button").addEventListener("click", removeFile);
["dragenter", "dragover"].forEach((type) => zone.addEventListener(type, (event) => { event.preventDefault(); zone.classList.add("drag-over"); }));
["dragleave", "drop"].forEach((type) => zone.addEventListener(type, (event) => { event.preventDefault(); zone.classList.remove("drag-over"); }));
zone.addEventListener("drop", (event) => acceptFile(event.dataTransfer?.files?.[0]));
$("source-mode").addEventListener("change", (event) => { state.source = event.target.value; renderHints(); invalidateTranslationRequest(); });
$("output-mode").addEventListener("change", (event) => { state.target = event.target.value; renderHints(); invalidateTranslationRequest(); });
document.querySelectorAll("[name=area-mode]").forEach((radio) => radio.addEventListener("change", (event) => {
  state.area = event.target.value;
  invalidateTranslationRequest();
  invalidateQualityForInput();
  if (state.area === "Select Area") openCropper();
  else {
    state.crop = null;
    closeCropper();
    renderWorkflow();
    assessCurrentImageQuality();
  }
}));
sourceImage.addEventListener("load", initializeImage);
selectionEl.addEventListener("pointerdown", (event) => { if (event.target === selectionEl) startPointer(event, "move-selection"); });
edgeButtons.forEach((button) => button.addEventListener("pointerdown", (event) => startPointer(event, "resize-selection", button.dataset.edge)));
$("move-pad").addEventListener("pointerdown", (event) => startPointer(event, "move-controller"));
arrowButtons.forEach((button) => {
  button.addEventListener("pointerdown", (event) => startArrowRepeat(event, button));
  ["pointerup", "pointercancel", "lostpointercapture"].forEach((type) => button.addEventListener(type, stopArrowRepeat));
});
window.addEventListener("pointermove", movePointer);
window.addEventListener("pointerup", finishPointer);
window.addEventListener("pointercancel", finishPointer);
window.addEventListener("blur", stopCropperActivity);
window.addEventListener("pagehide", stopCropperActivity);
document.addEventListener("visibilitychange", () => { if (document.hidden) stopCropperActivity(); });
["contextmenu", "selectstart", "dragstart"].forEach((type) => precisionPad.addEventListener(type, (event) => { event.preventDefault(); event.stopPropagation(); stopCropperActivity(); }));
["touchstart", "touchmove"].forEach((type) => precisionPad.addEventListener(type, (event) => event.preventDefault(), { passive: false }));
selectionEl.addEventListener("keydown", (event) => {
  const direction = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right" }[event.key];
  if (direction) { event.preventDefault(); adjustSelection(direction); }
});
$("reset-button").addEventListener("click", () => {
  stopCropperActivity();
  state.selection = { ...state.initialSelection };
  state.controllerPosition = defaultControllerPosition();
  renderSelection();
  renderPrecisionPad();
});
$("start-over-button").addEventListener("click", () => {
  restartCropWorkflow(state, document.querySelector("#settings input[value='Whole Pattern']"));
  invalidateTranslationRequest();
  invalidateQualityForInput();
  closeCropper();
  renderWorkflow();
  assessCurrentImageQuality();
});
$("use-area-button").addEventListener("click", () => {
  state.crop = currentCropBox();
  renderCropPreview();
  invalidateTranslationRequest();
  invalidateQualityForInput();
  closeCropper();
  renderWorkflow();
  assessCurrentImageQuality();
});
$("edit-area-button").addEventListener("click", () => {
  state.crop = null;
  invalidateTranslationRequest();
  invalidateQualityForInput();
  openCropper();
});
$("force-ocr").addEventListener("change", (event) => {
  if (event.target.checked) confirmPoorQuality(state);
  else state.qualityConfirmed = false;
  renderQuality();
  updateTranslateAvailability();
});
$("translate-button").addEventListener("click", translate);
$("diagnostic-download").addEventListener("click", downloadDiagnostic);
$("png-download").addEventListener("click", () => track("pattern_png_downloaded"));
$("txt-download").addEventListener("click", () => track("pattern_txt_downloaded"));
$("feedback-link").addEventListener("click", () => track("pattern_feedback_clicked"));
window.addEventListener("resize", () => layoutCropper(false));

renderLanguage();
populateModeSelects();
renderWorkflow();
initialiseAnalytics();
