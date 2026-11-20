# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased](https://github.com/joaompinto/janito/compare/v4.54.0...HEAD)

Changes since `v4.54.0` (2026-11-19).

### Added

- Web chat: Enter steers an active response at the next safe model step;
  Ctrl/Cmd+Enter queues a follow-up after the response. The composer includes
  Steer/Queue buttons with shortcut badges and a per-conversation pending-message list.

### Fixed

- Web chat shortcut discovery: keep Queue visible beside Send/Steer and display
  shortcuts directly on the two buttons, without a separate help block.
- Web chat cancellation and errors clear pending messages and roll back the
  entire active turn, including steering instructions, without removing earlier turns.

## [v4.54.0](https://github.com/joaompinto/janito/compare/v4.53.0...v4.54.0) - 2026-11-19

Changes since `v4.53.0` (2026-11-18).

### Changed

- System prompt: the `tools` section now carries only the `## Tool Usage
  Notes` header; each tool's usage hint lives in its own `tools:<Toolname>`
  section (mirroring `plugins:<name>`), shown as a separate row by `/prompt`
  and `--show-system-prompt`. Hints no longer carry a `- <Tool>:` prefix and
  are written function-first (e.g. "read PDFs with pdfplumber or pypdf");
  `RunPythonCode.system_prompt_hint` reworded accordingly (#207).
