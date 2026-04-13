---
name: debug
description: Debug photoanalyzer issues. Log locations, common problems, iOS Safari gotchas, mobile-specific issues.
---

# Debugging photoanalyzer

## Log Files

```bash
tail -f backend/logs/all.log
tail -f backend/logs/error.log
```

## Common Issues

### Images not loading
- Check `backend/training_data/` exists and has images
- Check backend is running on port 3001
- Check browser console for CORS errors

### Save failing
- Check write permissions on `backend/training_data_annotations/`
- Check backend logs for validation errors

### Progress not updating
- Refresh frontend or check backend logs
- Dashboard stats cached with 60s TTL — wait or restart backend

### sharp module errors
- sharp needs platform-specific rebuild after switching OS
- Run `cd backend && npm rebuild sharp`

### crypto.randomUUID() errors
- Requires HTTPS — fails silently on `http://192.168.x.x`
- Use `generateId()` from `lib/id.ts` which falls back to `crypto.getRandomValues()`

## iOS Safari / Mobile PWA Gotchas

These apply to `annotator-mobile/` and `consumer/`:

### 1. crypto.randomUUID() requires HTTPS
Fails silently on `http://192.168.x.x`. Always use `generateId()` from `lib/id.ts` which falls back to `crypto.getRandomValues()` using a Uint8Array to hex conversion.

### 2. Buttons over canvas don't receive touches
iOS Safari routes touch events to the canvas underneath when it has `touch-action: none`. The fix: move interactive buttons (confirm, cancel) OUTSIDE the canvas container element entirely. They cannot be overlaid as children or siblings within the same touch-action container.

### 3. setPointerCapture + preventDefault() breaks pointerup
Pointer events API is unreliable on iOS Safari. `setPointerCapture()` causes `pointerup` to never fire. Use native touch events (`touchstart`, `touchmove`, `touchend`) with `{ passive: false }` instead. All touch handlers in `TouchCanvas.tsx` use this pattern.

### 4. IndexedDB limit ~1GB on iOS Safari
OS can evict storage under pressure. There is no reliable way to check remaining quota. Mitigate by:
- Batching imports to 500-1000 images
- Providing "clear synced images" button to free space
- Showing storage usage estimates in the UI

### 5. overscroll-behavior: none
Set on body/html to prevent pull-to-refresh interfering with canvas gestures. Without this, dragging down on the canvas triggers the browser's pull-to-refresh animation on iOS.

### 6. Safe area insets
Use `env(safe-area-inset-bottom)` on bottom toolbars for iPhone notch/home indicator. The bottom toolbar in `AnnotatePage` has `padding-bottom: calc(8px + env(safe-area-inset-bottom))`.

### 7. Touch targets
Minimum 44px height for all tappable elements (Apple HIG). Faction chips, toolbar buttons, and prediction cards all enforce this. If adding new interactive elements, verify they meet this minimum.

## Mobile Annotator Architecture Notes

- IndexedDB stores images as blobs + annotations as JSON
- Coordinates stored in resized dimensions (max 1200px from export)
- Backend scales coordinates back to original dimensions on sync via sharp
- Sync happens in batches of 25 annotations per POST
- `touch-action: none` canvas with native touch events (NOT pointer events)
- Confirm/cancel buttons live OUTSIDE canvas container
