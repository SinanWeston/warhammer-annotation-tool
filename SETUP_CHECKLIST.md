# What Claude needs from you — setup checklist

Work top-down. Each item says what it unblocks, how long, the cost, and exactly
where to put the result. When an item's done, tell Claude the phrase in **"→ say:"**.

Everything goes in `.env` (already gitignored — keys never get committed) unless
noted. Open it with: `gnome-text-editor /home/sinan/Active/Projects/photoanalyzer/.env`

---

## 1. CVAT account — unblocks the 50-image gold set  ✅ DONE 2026-06-04
Gold set frozen: `data/gold/gold_v1.json` (35 images, 124 boxes). CVAT creds live in
`.env` (CVAT_USERNAME/PASSWORD). The QA reference for *everything* now exists.

<details><summary>(original steps, kept for reference)</summary>
The gold set is the QA reference for *everything* (measures detection, faction, unit).

1. Go to **https://app.cvat.ai** → Sign up (email or Google) → verify email → log in once.
2. In your terminal, create the credentials file (keeps your password out of chat):
   ```bash
   mkdir -p ~/.fiftyone
   gnome-text-editor ~/.fiftyone/annotation_config.json
   ```
   Paste, filling in your CVAT login:
   ```json
   { "backends": { "cvat": {
       "url": "https://app.cvat.ai",
       "username": "YOUR_CVAT_USERNAME",
       "password": "YOUR_CVAT_PASSWORD"
   } } }
   ```
**→ say: "cvat ready"** — Claude uploads the 50 images and gives you the labeling link.
</details>

---

## 2. One image-search key — unblocks Wave 1 (per-unit depth, the accuracy lever)  ⏱️ 10 min · free tier
Pick **ONE** (SerpApi is the easier signup):

**Option A — SerpApi** (one key, instant; 100 searches/month free)
1. Sign up at **https://serpapi.com** → Dashboard → copy your **Private API Key**.
2. In `.env` add a line: `SERPAPI_KEY=your_key_here`

**Option B — Google Custom Search** (more free volume — 100/day — but 2 values + setup)
1. Make a search engine at **https://programmablesearchengine.google.com** (search the whole web, enable Image search) → copy the **Search engine ID (cx)**.
2. In **Google Cloud Console** → enable "Custom Search API" → create an **API key**.
3. In `.env` add: `GOOGLE_CSE_KEY=your_key` and `GOOGLE_CSE_CX=your_cx`

> Note: free tiers are small (100/day or /month). Enough to prove the depth engine on a few units; we pace/prioritise thin units first, and you can upgrade later if it's working.

**→ say: "search key in"** — Claude builds + runs the query-by-taxonomy depth engine for the v1 factions.

---

## 3. Decision — Death Guard's empty gallery  ⏱️ 1 min · free
Death Guard has **0** clean reference crops in the corpus. Choose:
- **Keep it** → Claude scrapes GW's official photos for it (you'll need to be at the keyboard for ~30s to clear a Cloudflare check), **or**
- **Swap it** for Orks or Astra Militarum (both already have corpus depth — zero extra work).

**→ say: "keep death guard" or "swap death guard for <faction>"**

---

## 4. (Optional) Reddit app creds — supplements Wave 1 depth  ⏱️ 5 min · free
Adds faction-subreddit + r/minipainting harvesting (faction known for free).
1. Go to **https://www.reddit.com/prefs/apps** → "create another app" → type **script**.
2. Copy the **client ID** (under the app name) and the **secret**.
3. In `.env` add:
   ```
   REDDIT_CLIENT_ID=...
   REDDIT_CLIENT_SECRET=...
   REDDIT_USER_AGENT=battlescanner by u/yourusername
   ```
**→ say: "reddit creds in"**

---

## 5. (Later / optional) Apify token — Wave 3 marketplace volume  ⏱️ 5 min · paid above free credits
Only when you want eBay/Vinted/etc. at scale. Higher ToS/ban risk — runs supervised, not overnight.
Sign up at **https://apify.com** → Settings → API tokens. `.env`: `APIFY_TOKEN=...`
**→ say: "apify in"** (and we'll talk through the risk first)

---

## Recommended order
**1 → 2 → 3** gets you the measurable, accuracy-moving core. 4 and 5 are bonus volume.
Smallest first step that moves the needle: **#1 (CVAT)** — your model can't be honestly
scored without the gold set, and Claude's side is already built and waiting.
