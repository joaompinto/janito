# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased](https://github.com/joaompinto/janito/compare/v4.51.0...HEAD)

Changes since `v4.51.0` (2026-11-11).

## [v4.51.0](https://github.com/joaompinto/janito/compare/v4.50.0...v4.51.0) - 2026-11-11

Changes since `v4.50.0` (2026-10-19).

### Added

- Cloudflare Workers AI setup guide using the custom provider, with account
  and token setup, verified configuration keys, and streaming/API limitations (#32).

### Fixed

- Web session saves atomically replace metadata only after the full JSON has
  been written and flushed, preserving the last complete save on failure.
- Advanced web-settings tests isolate configuration, clients and workspaces
  per test and derive model-scoped keys from the provider registry.

### Security

- Confine web session storage to validated session IDs, reject symlinked
  session paths and ignore persisted IDs that do not match their directories.
- Replace public web-token injection with explicit browser login and signed,
  HttpOnly session cookies; protect the chat page and API documentation too.
- Reject cross-origin cookie-authenticated writes and WebSockets. API clients
  retain bearer-header authentication; query-string tokens are no longer accepted.
