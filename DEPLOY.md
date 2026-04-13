# Deployment Guide — Multi-User Annotator

How to expose the annotation tool so multiple people can annotate simultaneously from any browser.

## Prerequisites

- ngrok installed at `~/.local/bin/ngrok` (already done)
- ngrok authtoken configured (already done)
- Backend dependencies installed (`npm install` in repo root)

---

## Quick Start

### 1. Start the ngrok tunnel

```bash
~/.local/bin/ngrok http 3001
```

Note the HTTPS URL it gives you (e.g. `https://abc123.ngrok-free.app`).
Keep this terminal open — closing it kills the tunnel.

### 2. Build the frontend with the tunnel URL

```bash
cd /home/sinan/Active/Projects/photoanalyzer
VITE_API_URL=https://abc123.ngrok-free.app npx --prefix frontend vite build
```

Replace `https://abc123.ngrok-free.app` with your actual ngrok URL.

### 3. Start the backend

```bash
npm run dev:backend
```

The backend serves the built frontend at `/` and all API routes at `/api/*`.

### 4. Share the URL

Send `https://abc123.ngrok-free.app` to your annotators.
They open it, enter their name, and start annotating.

---

## How Multi-User Works

- Each annotator enters a name on first visit (stored in localStorage)
- The backend reserves images per-annotator with a 15-minute TTL
- No two annotators ever receive the same image simultaneously
- Annotations are saved with the annotator's name in the JSON
- Check who's currently active: `GET /api/annotate/who`

---

## Optional: Password Protection

To prevent strangers from using the tool if the URL leaks:

```bash
# Add to .env in the project root
ANNOTATOR_PASSWORD=yourpassword
```

Restart the backend. Browsers will show a native Basic Auth prompt.

---

## Limitations of ngrok Free Tier

- **URLs are ephemeral** — the URL changes every time ngrok restarts
- **Bandwidth limit** — 1 GB/month on free tier (images are base64-encoded, ~200KB each)
- **One tunnel** at a time on free plan

To get a **stable URL**, claim a free static domain in the ngrok dashboard:
`ngrok.com/dashboard` → Domains → New Domain

Then use:
```bash
~/.local/bin/ngrok http 3001 --domain=your-static-domain.ngrok-free.app
```

---

## Rebuild After URL Change

If ngrok restarts and you get a new URL, just rebuild the frontend:

```bash
VITE_API_URL=https://new-url.ngrok-free.app npx --prefix frontend vite build
```

No backend restart needed.

---

## Getting the Current ngrok URL Programmatically

```bash
curl -s http://localhost:4040/api/tunnels | python3 -c \
  "import sys,json; print(json.load(sys.stdin)['tunnels'][0]['public_url'])"
```

---

## Faction Label Remapping

Annotations are stored with the original faction label (e.g. `death_guard`).
At YOLO export time, factions are remapped to canonical classes:

| Stored as | Exported as |
|-----------|-------------|
| blood_angels, dark_angels, space_wolves, black_templars, deathwatch, grey_knights | `space_marines` |
| death_guard, thousand_sons, world_eaters, emperors_children | `chaos_space_marines` |

This is non-destructive and reversible — edit `EXPORT_LABEL_REMAP` in
`backend/src/services/annotationService.ts` to change the mapping.
