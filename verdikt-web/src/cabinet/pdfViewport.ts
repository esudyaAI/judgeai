/** Fit one page and bound raster dimensions and memory after integer rounding. */
export function pageScale(pageWidth: number, pageHeight: number, availableWidth: number, pixelRatio: number) {
  if (![pageWidth,pageHeight,availableWidth,pixelRatio].every(n => Number.isFinite(n) && n > 0)
    || pageWidth < 1 || pageHeight < 1 || pageWidth > 14400 || pageHeight > 14400) throw new Error('Invalid page dimensions');
  const scale = Math.min(availableWidth / pageWidth, 1.6);
  const width = pageWidth * scale, height = pageHeight * scale;
  const ratio = Math.min(pixelRatio, 2, 4096 / width, 4096 / height, Math.sqrt(3990000 / (width * height)));
  const pixelWidth = Math.max(1,Math.floor(width * ratio));
  const pixelHeight = Math.max(1,Math.floor(height * ratio));
  if (pixelWidth * pixelHeight > 4000000) throw new Error('Page raster exceeds preview limits');
  return {scale,width,height,ratio,pixelWidth,pixelHeight};
}
