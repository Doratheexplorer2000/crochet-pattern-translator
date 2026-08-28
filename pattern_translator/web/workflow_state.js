export const MODE_VALUES = [
  "English — US",
  "English — UK",
  "Traditional Chinese",
  "Simplified Chinese",
  "Japanese",
];

export function canTranslate(state) {
  return Boolean(
    state.file
    && MODE_VALUES.includes(state.source)
    && MODE_VALUES.includes(state.target)
    && (state.area === "Whole Pattern" || state.crop),
  );
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

export function adaptApiError(status, body, strings) {
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

export function translationFormEntries(state) {
  const entries = [
    ["source_mode", state.source],
    ["output_mode", state.target],
    ["area_mode", state.area],
  ];
  if (state.crop) {
    ["crop_left", "crop_top", "crop_right", "crop_bottom"].forEach((name, index) => {
      entries.push([name, String(state.crop[index])]);
    });
  }
  return entries;
}
