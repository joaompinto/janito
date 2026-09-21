# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased](https://github.com/joaompinto/janito/compare/v4.41.0...HEAD)

Changes since `v4.41.0` (2026-09-16).

### Changed

- Renamed the user-facing reasoning-depth setting to **effort** (close #148):
  the CLI flag is now `-e, --effort` (was `--reasoning-effort`) and the
  model-scoped config key is `effort` (was `reasoning-effort`, e.g.
  `janito --set effort=medium`). Breaking rename with no migration, following
  the #77 precedent. The API field (`reasoning_effort`), provider builtins
  (`default_reasoning_effort` / `supported_reasoning_efforts`) and the
  `/effort` shell command are unchanged.
- Default reasoning effort is now `medium` for every model that supports it
  (openai, google, alibaba, meta); moonshot/deepseek unchanged since they do
  not support `medium` (close #147).
