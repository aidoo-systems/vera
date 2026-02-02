# VERA Backend

FastAPI service for OCR, confidence analysis, validation, and summary generation.

## Run (local)
1. Install dependencies: `pip install -r requirements.txt`
2. Start API: `uvicorn app.main:app --reload --port 8000`

## API (v1 contract)
- `POST /documents/upload`
- `GET /documents/{id}`
- `POST /documents/{id}/validate`
- `GET /documents/{id}/summary`
- `GET /documents/{id}/export`

Validation requires an explicit `review_complete` flag before summaries or exports are available.

## Document lifecycle
`uploaded -> ocr_done -> review_in_progress -> validated -> summarized -> exported`
