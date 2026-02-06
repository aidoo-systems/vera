from __future__ import annotations

from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "vera_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
REQUEST_LATENCY = Histogram(
    "vera_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
)
OCR_DURATION = Histogram(
    "vera_ocr_page_duration_seconds",
    "OCR page processing duration",
    ["status"],
)
SUMMARY_DURATION = Histogram(
    "vera_summary_duration_seconds",
    "Summary generation duration",
    ["scope"],
)

SUMMARY_LLM_FAILURES = Counter(
    "vera_summary_llm_failures_total",
    "LLM summary failures",
    ["reason"],
)
