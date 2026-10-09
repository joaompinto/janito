# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased](https://github.com/joaompinto/janito/compare/v4.46.0...HEAD)

Changes since `v4.46.0` (2026-10-08).

### Added

- Claude Haiku 5.5 support for Anthropic (issue #185), with a 1M-token
  context window, 128K output limit, and tiered cost estimates above
  100,000 prompt tokens. Sonnet remains the default model.

- Configurable role in the built-in system prompt (issue #29), defaulting to
  `software developer`. Use `-R/--role` for a session override or
  `--set role=...` to persist it; CLI and new web sessions share resolution.
  Lowercase `-r/--read` is unchanged. Documentation explains why choosing a
  task-appropriate role matters and its limits. Custom prompts remain unchanged.

- **Apertus provider** — new `apertus` provider for Apertus models (Swiss AI
  Initiative) via Swisscom's OpenAI-compatible gateway
  (`https://api.swisscom.com/products/swiss-ai-weeks/apertus-1.5-70b/v1`),
  with `swiss-ai/Apertus-v1.5-70B` (262K-token context) as the built-in
  default model over the Chat Completions API. Select it with
  `janito --set provider=apertus`. See `docs/configuration/providers.md`.

### Fixed

- ChatGPT-plan login no longer strands users on "Already signed in" with an
  expired/revoked token: `janito --login` refreshes transparently when
  expired and re-authenticates when refresh fails; `-f/--force` forces
  re-authentication even when fresh.
- ChatGPT-plan `401 token_expired` failures now explain re-authentication
  (`--logout` + `--login`, or `--login -f`) instead of "verify your API key".
