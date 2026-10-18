# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased](https://github.com/joaompinto/janito/compare/v4.49.0...HEAD)

Changes since `v4.49.0` (2026-10-15).

### Changed

- Shell `/provider <name>` and `/model <name>` now persist the selection to
  the project-local config (`./.janito/config.json`) — the flat `provider`
  key and `providers.<provider>.model` respectively — so the next session
  started in the same project resumes with the chosen provider/model. The
  global `~/.janito/config.json` is never modified from the shell;
  `janito --set provider=...` / `--set model=...` still write the
  machine-level default. Persistence is best-effort: a failed local write is
  reported but never breaks the running session.
