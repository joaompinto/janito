# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased](https://github.com/joaompinto/janito/compare/v4.52.0...HEAD)

Changes since `v4.52.0` (2026-11-16).

### Added

- Tools can now contribute text to the system prompt: declare the optional
  `system_prompt_hint` class attribute on a `BaseTool` subclass (built-in or
  plugin) and its hint is collected — for the tools the session may actually
  use — into a new `tools` section rendered as `## Tool Usage Notes`. The
  section is omitted when no available tool declares a hint and appears as its
  own row in `/prompt` and `--show-system-prompt`. `RunPythonCode` uses it to
  recommend document libraries (`python-docx`, `openpyxl`/`pandas`, `xlrd`,
  `pdfplumber`/`pypdf`) instead of manual parsing. See `docs/TOOL.md`.
- Alibaba provider: `qwen4-max` model (GA 2026-11-16, MoE 2.4T/71B active,
  native vision, 1M context; thinking-mode ceilings 983,616 in / 262,144
  out; reasoning efforts low/high/xhigh, default high) with cost rates
  $1.50 input / $0.075 cache-hit / $4.50 output per 1M tokens and
  multimodal-endpoint routing.
