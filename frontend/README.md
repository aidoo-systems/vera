# VERA Frontend

Next.js frontend for the VERA verification-first OCR flow.

Core responsibilities:
- Image preview
- OCR overlay rendering
- Highlight low-confidence tokens
- Inline correction UI
- Validation submission
- Page summaries + exports (offline detailed summaries; optional AI summaries via Ollama)
- Document summary + export (multi-page PDFs)

Status updates use per-page polling with SSE fallback when available.

## Tests
Run from `frontend/`:
- `npm run test`
