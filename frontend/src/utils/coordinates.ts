/**
 * Coordinate transforms for the annotation canvas.
 *
 * Screen space = canvas pixel coordinates (what mouse/touch events report).
 * Image space  = original image pixel coordinates (what annotations are stored in).
 *
 * The canvas is drawn at `imageWidth * scale` pixels wide. `scale` < 1 when
 * the image is downscaled to fit the container.
 */

export interface Point {
  x: number
  y: number
}

export interface Bbox {
  x: number
  y: number
  width: number
  height: number
}

/** Convert a screen-space point to image-space. */
export function screenToImage(screenX: number, screenY: number, scale: number): Point {
  return { x: screenX / scale, y: screenY / scale }
}

/** Convert an image-space point to screen-space. */
export function imageToScreen(imageX: number, imageY: number, scale: number): Point {
  return { x: imageX * scale, y: imageY * scale }
}

/** Scale a bbox by a factor (image→screen when scale>0, screen→image when using 1/scale). */
export function scaleBbox(box: Bbox, scale: number): Bbox {
  return {
    x: box.x * scale,
    y: box.y * scale,
    width: box.width * scale,
    height: box.height * scale,
  }
}

/**
 * Compute the display scale needed to fit `imageWidth` into `availableWidth`,
 * preserving aspect ratio. Always returns a positive number.
 */
export function fitScale(imageWidth: number, availableWidth: number): number {
  if (imageWidth <= 0) return 1
  return availableWidth / imageWidth
}

/** Clamp a bbox so it stays within [0..imageWidth] × [0..imageHeight]. */
export function clampBbox(box: Bbox, imageWidth: number, imageHeight: number): Bbox {
  const x = Math.max(0, Math.min(box.x, imageWidth))
  const y = Math.max(0, Math.min(box.y, imageHeight))
  const width = Math.max(0, Math.min(box.width, imageWidth - x))
  const height = Math.max(0, Math.min(box.height, imageHeight - y))
  return { x, y, width, height }
}
