# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased](https://github.com/joaompinto/janito/compare/v4.54.0...HEAD)

Changes since `v4.54.0` (2026-11-19).

### Added

- `JANITO_WEB_PORT` environment variable sets the default web server port
  (overridden by `--web-port`). The Docker image uses it so the container port
  can be changed without overriding the command.
- `JANITO_SESSIONS_DIR` environment variable overrides where web chat history
  is persisted, so it can point at a mounted volume. The Docker image uses it
  to keep history in the persisted `~/.janito` volume.
- Docker docs: how to change the container port and map the sessions directory
  to a host path or separate volume.

### Fixed

- Docker `HEALTHCHECK` no longer reports the container unhealthy when
  `JANITO_WEB_TOKEN` is set: the health check moved from the protected
  `/api/health` to the public `/health`.
- Docker: web chat history is now actually persisted. Sessions no longer write
  to the read-only `/app` workspace; the image stores them in the
  `/home/appuser/.janito` volume via `JANITO_SESSIONS_DIR`.

## [v4.54.0](https://github.com/joaompinto/janito/compare/v4.53.0...v4.54.0) - 2026-11-19

Changes since `v4.53.0` (2026-11-18).

### Changed

- System prompt: the `tools` section now carries only the `## Tool Usage
  Notes` header; each tool's usage hint lives in its own `tools:<Toolname>`
  section (mirroring `plugins:<name>`), shown as a separate row by `/prompt`
  and `--show-system-prompt`. Hints no longer carry a `- <Tool>:` prefix and
  are written function-first (e.g. "read PDFs with pdfplumber or pypdf");
  `RunPythonCode.system_prompt_hint` reworded accordingly (#207).
