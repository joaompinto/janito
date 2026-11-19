# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased](https://github.com/joaompinto/janito/compare/v4.53.0...HEAD)

Changes since `v4.53.0` (2026-11-18).

### Changed

- System prompt: the `tools` section now carries only the `## Tool Usage
  Notes` header; each tool's usage hint lives in its own `tools:<Toolname>`
  section (mirroring `plugins:<name>`), shown as a separate row by `/prompt`
  and `--show-system-prompt`. Hints no longer carry a `- <Tool>:` prefix and
  are written function-first (e.g. "read PDFs with pdfplumber or pypdf");
  `RunPythonCode.system_prompt_hint` reworded accordingly (#207).
