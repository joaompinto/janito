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

- **ACP (Agent Client Protocol) v1 agent** â€” `janito --acp` runs as an ACP
  subprocess agent over stdio (newline-delimited JSON-RPC 2.0) for ACP-compatible
  editors (e.g. Zed). Implements `initialize`, `session/new`, `session/prompt`,
  and `session/cancel`; streams token/reasoning/tool updates; honors the
  session `cwd`, ignores client-provided `mcpServers`, and keeps stdout clean by
  redirecting all non-protocol output to stderr. See `docs/usage/acp.md`.

### Fixed

- ACP turn safety: cancellation now stops streaming promptly but waits for
  tracked sync workers (tool execution, MCP discovery, sync SDK chunks) to
  finish before restoring the session `cwd` and releasing the turn lock, so
  repeated cancels cannot strand background threads on the wrong directory;
  stdin shutdown also waits for turn cleanup before closing the event loop;
  cancelled, failed, and error-event turns roll history back to before the
  turn while completed turns keep the system prompt and prior messages;
  overlapping `session/prompt` calls on one session are rejected; and
  `session/new` resolves the project prompt (including `AGENTS.md`) under
  the requested `cwd` while waiting for any active turn.
- ChatGPT-plan login no longer strands users on "Already signed in" with an
  expired/revoked token: `janito --login` refreshes transparently when
  expired and re-authenticates when refresh fails; `-f/--force` forces
  re-authentication even when fresh.
- ChatGPT-plan `401 token_expired` failures now explain re-authentication
  (`--logout` + `--login`, or `--login -f`) instead of "verify your API key".
