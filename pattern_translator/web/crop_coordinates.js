function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), maximum);
}

function displayToOriginalPoint(x, y, orientation, rawWidth, rawHeight) {
  switch (orientation) {
    case 2: return [rawWidth - x, y];
    case 3: return [rawWidth - x, rawHeight - y];
    case 4: return [x, rawHeight - y];
    case 5: return [y, x];
    case 6: return [y, rawHeight - x];
    case 7: return [rawWidth - y, rawHeight - x];
    case 8: return [rawWidth - y, x];
    default: return [x, y];
  }
}

// The browser displays EXIF-oriented JPEGs; Pillow receives raw file pixels.
// Map all four display-box corners back to that original Pillow coordinate space.
export function displayBoxToOriginal(box, orientation, rawWidth, rawHeight) {
  const points = [
    [box.left, box.top],
    [box.right, box.top],
    [box.left, box.bottom],
    [box.right, box.bottom],
  ].map(([x, y]) => displayToOriginalPoint(x, y, orientation, rawWidth, rawHeight));
  const left = clamp(Math.floor(Math.min(...points.map(([x]) => x))), 0, rawWidth);
  const top = clamp(Math.floor(Math.min(...points.map(([, y]) => y))), 0, rawHeight);
  const right = clamp(Math.ceil(Math.max(...points.map(([x]) => x))), 0, rawWidth);
  const bottom = clamp(Math.ceil(Math.max(...points.map(([, y]) => y))), 0, rawHeight);
  return [left, top, Math.max(left, right), Math.max(top, bottom)];
}

export function displayBoxToImage(box, width, height) {
  const left = clamp(Math.floor(box.left), 0, width);
  const top = clamp(Math.floor(box.top), 0, height);
  const right = clamp(Math.ceil(box.right), 0, width);
  const bottom = clamp(Math.ceil(box.bottom), 0, height);
  return [left, top, Math.max(left, right), Math.max(top, bottom)];
}

export function normalizedCropBox(box, width, height, minSize = 50) {
  const minimum = Math.min(minSize, width, height);
  const cropWidth = clamp(Number(box.width) || minimum, minimum, width);
  const cropHeight = clamp(Number(box.height) || minimum, minimum, height);
  return {
    left: clamp(Number(box.left) || 0, 0, width - cropWidth),
    top: clamp(Number(box.top) || 0, 0, height - cropHeight),
    width: cropWidth,
    height: cropHeight,
  };
}

export function resizeCropBox(start, edge, delta, width, height, minSize = 50) {
  const min = Math.min(minSize, width, height);
  if (edge === "left") {
    const right = start.left + start.width;
    const left = clamp(start.left + delta, 0, right - min);
    return { ...start, left, width: right - left };
  }
  if (edge === "top") {
    const bottom = start.top + start.height;
    const top = clamp(start.top + delta, 0, bottom - min);
    return { ...start, top, height: bottom - top };
  }
  if (edge === "right") {
    return { ...start, width: clamp(start.width + delta, min, width - start.left) };
  }
  if (edge === "bottom") {
    return { ...start, height: clamp(start.height + delta, min, height - start.top) };
  }
  return normalizedCropBox(start, width, height, min);
}

export function readExifOrientation(buffer) {
  const bytes = new Uint8Array(buffer);
  let start = -1;
  for (let i = 0; i + 6 < bytes.length; i += 1) {
    if (bytes[i] === 0x45 && bytes[i + 1] === 0x78 && bytes[i + 2] === 0x69
      && bytes[i + 3] === 0x66 && bytes[i + 4] === 0 && bytes[i + 5] === 0) {
      start = i + 6;
      break;
    }
  }
  if (start < 0 || start + 8 > bytes.length) return 1;
  const view = new DataView(buffer);
  const little = view.getUint16(start) === 0x4949;
  const u16 = (at) => view.getUint16(at, little);
  const u32 = (at) => view.getUint32(at, little);
  try {
    const ifd = start + u32(start + 4);
    const count = u16(ifd);
    for (let i = 0; i < count; i += 1) {
      const at = ifd + 2 + i * 12;
      if (u16(at) === 0x0112) return clamp(u16(at + 8), 1, 8);
    }
  } catch (_) {
    // Missing or malformed EXIF is intentionally treated as orientation 1.
  }
  return 1;
}
