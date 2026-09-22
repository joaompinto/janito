# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased](https://github.com/joaompinto/janito/compare/v4.42.0...HEAD)

Changes since `v4.42.0` (2026-09-21).

### Added

- providers(zai): new `glm-5.3-flashx` model — the ~200 tokens/s FlashX
  variant of GLM-5.3, with the same limits as `glm-5.3-flash`
  (1M context / 128K output); pricing (USD per 1M tokens)
  $0.37/$0.075 (cache hit)/$1.25.

### Changed

- tests: rewrite the usage-line rendering tests to comply with
  dev-docs/testing.md Rule 6 (numbers over words).  `test_turn_report.py`
  and `test_usage_line_style.py` now parse the `=== ... ===` summary line
  into labeled parts and assert values composed from the source-of-truth
  `format_tokens()` / `format_elapsed()` instead of pinning
  `"In: 60/65.5k"`-style strings; `test_input_tokens_info.py` drops its
  local replica of the parts-building logic and renders through the real
  `janito.ui.usage._display_usage` (close #152).
- providers(xiaomi): replace MiMo-V2.5 with the MiMo-V2.6 series
  (`mimo-v2.6-pro`, `mimo-v2.6-flash`, `mimo-v2.6-pro-ultraspeed`);
  the default model is now `mimo-v2.6-flash`.  Limits are unchanged
  (1M context / 128K output); per-model pricing (USD per 1M tokens):
  Flash $0.14/$0.0028 (cache hit)/$0.28, Pro $0.435/$0.0036/$0.87,
  UltraSpeed $4.35/$0.036/$8.7 (close #150).
