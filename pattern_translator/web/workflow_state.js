export const MODE_VALUES = [
  "English — US",
  "English — UK",
  "Traditional Chinese",
  "Simplified Chinese",
  "Japanese",
];

const IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp"];
const IMAGE_CONTENT_TYPES = [
  "image/jpeg",
  "image/jpg",
  "image/png",
  "image/x-png",
  "image/webp",
  "application/octet-stream",
];

export function validateImageFile(file, maxBytes) {
  if (!file || !file.size) return "empty";
  if (file.size > maxBytes) return "large";
  const extension = (file.name.split(".").pop() || "").trim().toLowerCase();
  const contentType = String(file.type || "").trim().toLowerCase();
  const allowedType = !contentType || IMAGE_CONTENT_TYPES.includes(contentType);
  return IMAGE_EXTENSIONS.includes(extension) && allowedType ? "" : "unsupported";
}

export function discardCompletedResult(state, revokeObjectUrl = () => {}) {
  state.diagnosticController?.abort();
  state.diagnosticController = null;
  state.diagnosticLoading = false;
  for (const key of ["pngUrl", "txtUrl"]) {
    if (state[key]) revokeObjectUrl(state[key]);
    state[key] = null;
  }
  state.diagnosticContext = null;
}

export function restartCropWorkflow(state, wholePatternControl) {
  wholePatternControl.checked = true;
  state.area = "Whole Pattern";
  state.crop = null;
}

function matchingCrop(first, second) {
  if (first === null || second === null) return first === second;
  return Array.isArray(first)
    && Array.isArray(second)
    && first.length === 4
    && second.length === 4
    && first.every((value, index) => value === second[index]);
}

function qualityCrop(state) {
  return state.area === "Select Area" && Array.isArray(state.crop)
    ? state.crop.map(Number)
    : null;
}

export function qualityIdentity(state) {
  return {
    file: state.file,
    area: state.area,
    crop: qualityCrop(state),
  };
}

export function hasCurrentQuality(state) {
  return Boolean(
    state.qualityAssessment
    && state.qualityFile === state.file
    && state.qualityArea === state.area
    && matchingCrop(state.qualityCrop, qualityCrop(state)),
  );
}

export function forceRunForCurrentQuality(state) {
  return Boolean(
    hasCurrentQuality(state)
    && state.qualityAssessment.level === "poor"
    && state.qualityConfirmed,
  );
}

export function canTranslate(state) {
  const qualityAllowsTranslation = hasCurrentQuality(state)
    && (
      state.qualityAssessment.level !== "poor"
      || forceRunForCurrentQuality(state)
    );
  return Boolean(
    state.file
    && MODE_VALUES.includes(state.source)
    && MODE_VALUES.includes(state.target)
    && (state.area === "Whole Pattern" || state.crop)
    && !state.qualityLoading
    && qualityAllowsTranslation
  );
}

export function invalidateQuality(state) {
  const controller = state.qualityController;
  state.qualityGeneration = (state.qualityGeneration || 0) + 1;
  state.qualityLoading = false;
  state.qualityController = null;
  state.qualityAssessment = null;
  state.qualityFile = null;
  state.qualityArea = null;
  state.qualityCrop = null;
  state.qualityConfirmed = false;
  state.qualityError = false;
  return controller;
}

export function isCurrentQualityRequest(state, token, identity) {
  const current = qualityIdentity(state);
  return state.qualityGeneration === token
    && current.file === identity.file
    && current.area === identity.area
    && matchingCrop(current.crop, identity.crop);
}

export function isValidQualityResponse(body, identity) {
  const quality = body?.quality;
  if (
    !body
    || typeof body !== "object"
    || body.area_mode !== identity.area
    || !quality
    || typeof quality !== "object"
    || !["good", "fair", "poor"].includes(quality.level)
    || typeof quality.label !== "string"
    || typeof quality.requires_confirmation !== "boolean"
    || quality.requires_confirmation !== (quality.level === "poor")
    || !quality.metrics
    || typeof quality.metrics !== "object"
    || Array.isArray(quality.metrics)
    || !Array.isArray(quality.errors)
    || !quality.errors.every((value) => typeof value === "string")
    || !Array.isArray(quality.warnings)
    || !quality.warnings.every((value) => typeof value === "string")
  ) return false;
  return identity.area !== "Select Area" || matchingCrop(body.crop_box, identity.crop);
}

export function isValidTranslationResponse(body, state, identity) {
  return Boolean(
    isValidQualityResponse(body, identity)
    && typeof body.request_id === "string"
    && body.request_id
    && body.source_mode === state.source
    && body.output_mode === state.target
    && typeof body.readable_translation === "string"
    && typeof body.translation_txt === "string"
    && body.overlay_png
    && body.overlay_png.media_type === "image/png"
    && typeof body.overlay_png.base64 === "string"
    && body.overlay_png.base64
    && (
      body.diagnostic_context === null
      || (
        typeof body.diagnostic_context === "object"
        && !Array.isArray(body.diagnostic_context)
      )
    )
  );
}

export function applyQualityResponse(state, body, identity, preserveConfirmation = false) {
  if (!isValidQualityResponse(body, identity)) return false;
  const confirmed = preserveConfirmation && forceRunForCurrentQuality(state);
  state.qualityAssessment = body.quality;
  state.qualityFile = identity.file;
  state.qualityArea = identity.area;
  state.qualityCrop = identity.crop ? [...identity.crop] : null;
  state.qualityConfirmed = Boolean(confirmed && body.quality.level === "poor");
  state.qualityError = false;
  return true;
}

export function confirmPoorQuality(state) {
  if (!hasCurrentQuality(state) || state.qualityAssessment.level !== "poor") {
    state.qualityConfirmed = false;
    return false;
  }
  state.qualityConfirmed = true;
  return true;
}

export function invalidateRequest(state) {
  state.generation += 1;
  state.loading = false;
  return state.controller;
}

export function isCurrentRequest(state, token) {
  return state.generation === token;
}

export function isCurrentImage(state, token, file) {
  return state.generation === token && state.file === file;
}

export function isCurrentDiagnosticRequest(state, token, context) {
  return state.generation === token && state.diagnosticContext === context;
}

export function diagnosticFilename(response) {
  const disposition = response.headers.get("content-disposition") || "";
  const match = disposition.match(/filename="?([^";]+)"?/i);
  return match?.[1] || "PatternOCR_DiagnosticReport.txt";
}

export function postDiagnosticReport(fetchImpl, context, uiLang, signal) {
  return fetchImpl("/api/v1/diagnostic-report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ diagnostic_context: context, ui_lang: uiLang }),
    signal,
  });
}

export function adaptApiError(status, body, strings) {
  if (status === 409 && body?.quality?.level === "poor") {
    return strings.qualityBlockWarning;
  }
  if (status === 400) {
    const detail = String(body?.detail || "");
    if (detail === "Image too large") return strings.errorLarge;
    if (detail === "Unsupported image format") return strings.errorUnsupported;
    if (detail === "Invalid image") return strings.errorUnreadable;
    if (detail.includes("crop")) return strings.errorCrop;
    return strings.errorValidation;
  }
  if (status === 422) return strings.errorValidation;
  if (status >= 500) {
    return body?.request_id
      ? `${strings.errorRequest}${body.request_id}`
      : strings.errorGeneric;
  }
  return strings.errorGeneric;
}

export function qualityFormEntries(state) {
  const entries = [["area_mode", state.area]];
  if (state.crop) {
    ["crop_left", "crop_top", "crop_right", "crop_bottom"].forEach((name, index) => {
      entries.push([name, String(state.crop[index])]);
    });
  }
  return entries;
}

export function translationFormEntries(state) {
  const entries = [
    ["source_mode", state.source],
    ["output_mode", state.target],
    ...qualityFormEntries(state),
  ];
  entries.push(["force_run", String(forceRunForCurrentQuality(state))]);
  return entries;
}

export function beginTranslation(state, controller) {
  if (state.loading || !canTranslate(state)) return null;
  state.loading = true;
  state.controller = controller;
  return state.generation;
}
