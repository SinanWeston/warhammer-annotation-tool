# warhammer-analyzer

Modular AI system for detecting and identifying Warhammer 40K miniatures.

**Core Feature**: Three-pass bbox pipeline with count-index lock pattern for 100% accurate counting.
**Key Innovation**: Fully modular AI provider system — swap providers via .env configuration.

## Documentation — MUST UPDATE AFTER EVERY CODE CHANGE

Update after ANY change: EPIC.md, STATUS.md, README.md. Use format templates in each file. No exceptions.

- **EPIC.md**: Source of truth — what, why, how everything works
- **STATUS.md**: Factual changelog (date, files, line counts, functions changed)
- **README.md**: Quick start guide, usage, config examples

## Development Workflow

1. Read EPIC.md before starting work
2. Check STATUS.md for recent changes
3. Follow modular architecture (providers, services, utils)
4. Test with multiple AI providers
5. Update all three docs after completing work

## Architecture

### Three-Pass Pipeline
- **PASS 1**: Detection (establish count authority)
- **PASS 2**: Classification (multi-tier cascade)
- **PASS 3**: Validation (triangulation for low confidence)

### Modular Provider System
All AI providers extend `AIProvider` base class in `backend/src/providers/base.js`.
Providers: claude.js, openai.js, gemini.js, llama.js.

### Configuration
Everything via `.env`: detection provider/model, classification tiers, validation provider/model, API keys.

## Code Organization

- `backend/src/services/` — detectionService, classificationService, validationService
- `backend/src/providers/` — base.js + provider implementations
- `backend/src/config/pipeline.js` — centralized configuration
- `backend/src/utils/` — bbox, imageProcessing, logger

## Testing

```bash
npm run dev                              # Start server on port 3002
DETECTION_PROVIDER=claude npm run dev    # Test with specific provider
ENABLE_MULTI_TIER=true npm run dev       # Enable all classification tiers
```

## Best Practices

- Keep providers modular — never hardcode AI-specific logic outside providers
- Make everything configurable via pipeline.js
- Test with multiple providers to ensure modularity
