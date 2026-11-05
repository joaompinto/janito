# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased](https://github.com/joaompinto/janito/compare/v4.50.0...HEAD)

Changes since `v4.50.0` (2026-10-19).

### Security

- Replace public web-token injection with explicit browser login and signed,
  HttpOnly session cookies; protect the chat page and API documentation too.
- Reject cross-origin cookie-authenticated writes and WebSockets. API clients
  retain bearer-header authentication; query-string tokens are no longer accepted.
