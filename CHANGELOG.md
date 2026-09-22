# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased](https://github.com/joaompinto/janito/compare/v4.43.0...HEAD)

Changes since `v4.43.0` (2026-09-22).

### Changed

- ci: pin both workflows to the `ubuntu-24.04` runner instead of the
  floating `ubuntu-latest` label, which migrates to Ubuntu 26.04 starting
  2026-10-19 (actions/runner-images#14748) — release/publish pipelines
  should not track a moving OS baseline; and bump `astral-sh/setup-uv`
  from v9.0.0 to v10 in `release.yaml` and `documentation.yml` (the v10
  breaking change only affects the default `enable-cache: auto` mode,
  which this repo does not use).
