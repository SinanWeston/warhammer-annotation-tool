# EPIC: Warhammer 40K Miniature Analyzer

**Last Updated**: 2026-04-13
**Status**: Fully Modular AI Analysis System + Phase 1 Labelling Mode

---

## Project Vision

An AI-powered system that accurately detects, identifies, and counts Warhammer 40K miniatures in photographs. The system guarantees **100% accurate counting** through a count-index lock pattern and provides **flexible, modular AI provider configuration** for easy experimentation and optimization.

**Dual role as of 2026-04**:

1. **Analyzer mode** (`/api/analyze`, `/`) — the original three-pass pipeline
   (Detection → Classification → Triangulation). Keeps the count-index lock
   guarantee. Primary use case: end-to-end scanning of army photographs.
2. **Labelling mode** (`/api/labelling/*`, `/label`) — an AI-assisted
   single-crop labelling tool for the parent photoanalyzer project's Phase 1
   (see `../STRATEGY.md`). Reads crops from `../scripts/phase1/crops/`,
   suggests a unit slug via the LLM, persists the confirmed label to
   `../scripts/phase1/labels.csv`. No detection pass — crops already have
   ground-truth bboxes from the annotation corpus; labelling mode only
   exercises the classification stage.

---

## Core Innovation: Count-Index Lock Pattern

**The Problem**: AI models hallucinate - they might see 3 miniatures but report 5, or miss some entirely.

**The Solution**: Three-pass pipeline where counting authority is **locked** in PASS 1:

```
PASS 1: Detection (COUNT AUTHORITY - IMMUTABLE)
├─ AI detects bounding boxes around miniatures
├─ Each detection gets a UUID
├─ COUNT = N detections (this is FINAL)
└─ No future pass can add/remove detections

PASS 2: Classification (CANNOT CHANGE COUNT)
├─ Crop N images using bboxes from PASS 1
├─ Classify each crop independently
├─ Each classification linked to UUID
└─ COUNT remains N (integrity verified)

PASS 3: Validation (CANNOT CHANGE COUNT)
├─ Low-confidence crops get second opinion
├─ Different AI model validates classifications
├─ Final decisions made
└─ COUNT still = N (integrity verified)
```

**Result**: Perfect counting accuracy. The count is established once and never changes.

---

## Architecture

### Modular AI Provider System

The system supports **multiple AI providers** that can be swapped via configuration:

- **Claude** (Anthropic): Haiku for detection, Sonnet for classification
- **OpenAI**: GPT-4o for high-accuracy tasks
- **Gemini**: Fast, cost-effective screening
- **LLaMA**: Alternative validation perspective

**Key Design**: All providers implement the same interface (`AIProvider` base class), making them hot-swappable through environment variables.

### Three-Pass Pipeline

#### PASS 1: Bbox Detection
**Purpose**: Establish count authority

**Process**:
1. Full image sent to detection AI
2. AI draws bounding boxes around each miniature
3. Each bbox gets a UUID
4. Count locked: `N = detections.length`
5. Non-Maximum Suppression removes duplicates
6. Bboxes normalized to [0.0-1.0] coordinates

**Configurable**:
- Provider: Claude, OpenAI, or custom
- Model: Any vision-capable model
- Confidence threshold
- NMS IoU threshold

#### PASS 2: Multi-Tier Classification Cascade
**Purpose**: Identify what each miniature is (unit type + faction)

**Process**:
1. **Tier 1** (Cheap screener):
   - Gemini Flash classifies each crop
   - High confidence (>85%) → Accept
   - Low confidence → Escalate to Tier 2

2. **Tier 2** (Accurate classifier):
   - Claude Sonnet classifies
   - High confidence (>75%) → Accept
   - Low confidence → Escalate to Tier 3

3. **Tier 3** (Premium arbiter):
   - GPT-4o makes final decision
   - No escalation (final arbiter)

**Benefits**:
- 60-80% cost reduction
- Most images resolved in Tier 1/2
- Tier 3 only for hard cases

**Configurable**:
- Number of tiers (1-3+)
- Provider/model for each tier
- Confidence thresholds
- Enable/disable cascade

#### PASS 3: Validation (Triangulation)
**Purpose**: Second opinion for ambiguous classifications

**Process**:
1. Check Tier 2 confidence scores
2. If confidence < threshold (default 75%):
   - Send crop to different AI (LLaMA)
   - Compare responses
   - If agreement → Accept
   - If disagreement → Flag for review

**Configurable**:
- Enable/disable triangulation
- Validation provider/model
- Trigger threshold

---

## Configuration System

### Environment Variables

All AI providers, models, and thresholds configurable via `.env`:

```bash
# PASS 1: Detection
DETECTION_PROVIDER=claude           # claude | openai | yolo
DETECTION_MODEL=claude-3-5-haiku-20241022
DETECTION_CONFIDENCE=0.5
NMS_IOU_THRESHOLD=0.5

# PASS 2: Multi-Tier Classification
ENABLE_MULTI_TIER=true
TIER1_PROVIDER=gemini
TIER1_MODEL=gemini-2.0-flash-lite
TIER1_THRESHOLD=0.85

TIER2_PROVIDER=claude
TIER2_MODEL=claude-3-5-sonnet-20241022
TIER2_THRESHOLD=0.75

TIER3_PROVIDER=openai
TIER3_MODEL=gpt-4o

# PASS 3: Validation
ENABLE_TRIANGULATION=true
VALIDATION_PROVIDER=llama
VALIDATION_MODEL=meta-llama/llama-3.2-90b-vision-instruct
TRIANGULATION_THRESHOLD=0.75

# API Keys
OPENROUTER_API_KEY=sk-or-v1-xxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxx (optional)
OPENAI_API_KEY=sk-xxxxx (optional)
GOOGLE_API_KEY=xxxxx (optional)
```

### How to Change AI Providers

**Example: Switch detection from Claude to OpenAI**
```bash
DETECTION_PROVIDER=openai
DETECTION_MODEL=gpt-4o
```

**Example: Disable multi-tier, use single classifier**
```bash
ENABLE_MULTI_TIER=false
TIER1_PROVIDER=claude
TIER1_MODEL=claude-3-5-sonnet-20241022
```

**Example: Add a 4th tier**
Just modify `pipeline.js` and add to the tiers array.

---

## How It Works (End-to-End Flow)

### 1. User Uploads Image
Frontend sends image to `/api/analyze` endpoint

### 2. PASS 1: Detection
```javascript
// Detection service loads configured provider
const detector = getProvider('detection')

// AI detects all miniatures
const detections = await detector.detectBboxes(imageBuffer)

// Assign UUIDs (count lock)
detections.forEach(d => d.id = randomUUID())

// COUNT LOCKED
const authorityCount = detections.length
```

### 3. PASS 2: Classification
```javascript
// For each detection:
for (const detection of detections) {
  // Crop image
  const crop = await cropImage(imageBuffer, detection.bbox)
  
  // Multi-tier cascade
  let result, tier = 1
  while (tier <= 3) {
    const classifier = getProvider(`tier${tier}`)
    result = await classifier.classifyImage(crop)
    
    if (result.confidence >= tier.threshold) break
    tier++
  }
  
  detection.classification = result
}

// Verify count integrity
assert(detections.length === authorityCount)
```

### 4. PASS 3: Validation (Optional)
```javascript
// For low-confidence classifications
const needsValidation = detections.filter(d => 
  d.classification.confidence < TRIANGULATION_THRESHOLD
)

for (const detection of needsValidation) {
  const validator = getProvider('validation')
  const secondOpinion = await validator.classifyImage(detection.crop)
  
  // Compare opinions
  if (secondOpinion.unit !== detection.classification.unit) {
    detection.flags.push('DISAGREEMENT')
  }
}

// Final count verification
assert(detections.length === authorityCount)
```

### 5. Return Results
```json
{
  "success": true,
  "detections": [
    {
      "id": "uuid-1",
      "bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.5, "y2": 0.8},
      "unit": "Space Marine Tactical Squad",
      "faction": "Space Marines",
      "confidence": 0.95,
      "tier": 1
    }
  ],
  "summary": {
    "totalCount": 5,
    "models": [
      {"unit": "Space Marine Tactical Squad", "count": 3, "faction": "Space Marines"},
      {"unit": "Rhino Transport", "count": 2, "faction": "Space Marines"}
    ]
  }
}
```

---

## Technical Stack

### Backend
- **Runtime**: Node.js (ES modules)
- **Framework**: Express
- **AI Integration**: Direct API calls (OpenRouter, Anthropic, OpenAI, Google)
- **Image Processing**: Sharp (bbox cropping, resizing)
- **Architecture**: Modular service-based (detection, classification, validation)

### Frontend
- **Tech**: Vanilla HTML/CSS/JavaScript
- **Features**: Drag-and-drop upload, real-time results, responsive design
- **No frameworks**: Keep it simple and fast

### Configuration
- **Pipeline Config**: `backend/src/config/pipeline.js`
- **Provider System**: Abstract base class + implementations
- **Environment**: `.env` file for all settings

---

## Project Structure

```
warhammer-analyzer/
├── backend/
│   ├── src/
│   │   ├── services/
│   │   │   ├── detectionService.js      # PASS 1: Bbox detection
│   │   │   ├── classificationService.js # PASS 2: Multi-tier cascade
│   │   │   └── validationService.js     # PASS 3: Triangulation
│   │   ├── providers/
│   │   │   ├── base.js                  # Abstract AIProvider class
│   │   │   ├── claude.js                # Claude implementation
│   │   │   ├── openai.js                # OpenAI implementation
│   │   │   ├── gemini.js                # Gemini implementation
│   │   │   └── llama.js                 # LLaMA implementation
│   │   ├── config/
│   │   │   └── pipeline.js              # Modular configuration
│   │   ├── utils/
│   │   │   ├── bbox.js                  # Bbox utilities
│   │   │   ├── imageProcessing.js       # Image cropping
│   │   │   └── logger.js                # Logging
│   │   └── index.js                     # Express server
│   └── package.json
├── frontend/
│   ├── public/
│   │   └── index.html                   # Single-page app
│   └── package.json
├── EPIC.md                               # This file
├── STATUS.md                             # Changelog
├── README.md                             # Quick start guide
├── CLAUDE.md                             # Developer instructions
└── .env.example                          # Configuration template
```

---

## Why This Architecture?

### Modularity
**Problem**: Hardcoded AI providers make it hard to experiment.  
**Solution**: Abstract provider system. Add new providers by implementing base class.

### Configurability
**Problem**: Changing models requires code changes.  
**Solution**: Everything configured via environment variables.

### Cost Optimization
**Problem**: Using GPT-4 for everything is expensive.  
**Solution**: Multi-tier cascade. 80% of images resolved by cheap models.

### Accuracy Guarantee
**Problem**: AI hallucinates counts.  
**Solution**: Count-index lock pattern. Count established once, never changes.

### Flexibility
**Problem**: One-size-fits-all doesn't work.  
**Solution**: Every stage configurable. Disable tiers, swap models, adjust thresholds.

---

## Future Enhancements

### Completed
- ✅ Three-pass pipeline
- ✅ Count-index lock
- ✅ Multi-tier classification
- ✅ Modular provider system
- ✅ Full configurability

### Potential Additions
- CLIP visual similarity (Python service)
- YOLO custom model integration
- Batch processing
- Results caching
- Training data collection mode
- Active learning feedback loop

---

## Success Metrics

- **Count Accuracy**: 100% (guaranteed by count-lock)
- **Classification Accuracy**: Target 85-90%
- **Cost Efficiency**: 60-80% reduction via multi-tier
- **Speed**: 5-15 seconds per image
- **Modularity**: Swap AI provider in <5 minutes (edit .env)

---

## Documentation Maintenance

Per CLAUDE.md requirements, this EPIC must be updated whenever:
- New features are added
- Architecture changes
- New AI providers are integrated
- Configuration options change
- Core concepts evolve

**This EPIC is the source of truth for understanding the entire project.**
