Run the VERA test suites (backend + frontend).

```bash
# Backend tests
cd backend && pytest --tb=short

# Frontend tests
cd frontend && npm test
```

Report results for both suites: total tests, passed, failed. If any tests fail, show the failure output.
