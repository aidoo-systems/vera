# Changelog

All notable changes to VERA will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Ollama connectivity switched from `host.docker.internal:11434` to the shared `ollama_network` Docker network — fixes Linux Docker Engine where `host.docker.internal` is not available
- Default `OLLAMA_URL` in `docker-compose.yml` changed from `http://host.docker.internal:11434` to `http://ollama:11434` (internal DNS via `ollama_network`)
- `backend` and `worker` services now join both `default` and `ollama_network` networks; `frontend` is unchanged (it never calls Ollama directly)
- Ollama is managed by the standalone [OLLAMA repo](../OLLAMA) rather than run separately per-app

### Added

- `OLLAMA_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT` documented in `.env.example` with comments distinguishing Docker vs native dev usage
