# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased](https://github.com/joaompinto/janito/compare/v4.40.0...HEAD)

Changes since `v4.40.0` (2026-09-10).

### Added

- **Apertus provider** — new `apertus` provider for Apertus models (Swiss AI
  Initiative) via Swisscom's OpenAI-compatible gateway
  (`https://api.swisscom.com/products/swiss-ai-weeks/apertus-1.5-70b/v1`),
  with `swiss-ai/Apertus-v1.5-70B` (262K-token context) as the built-in
  default model over the Chat Completions API. Select it with
  `janito --set provider=apertus`. See `docs/configuration/providers.md`.
