# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased](https://github.com/joaompinto/janito/compare/v4.50.0...HEAD)

Changes since `v4.50.0` (2026-10-19).

### Fixed

- Web session saves atomically replace metadata only after the full JSON has
  been written and flushed, preserving the last complete save on failure.

### Security

- Confine web session storage to validated session IDs, reject symlinked
  session paths and ignore persisted IDs that do not match their directories.
