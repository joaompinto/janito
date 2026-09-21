# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased](https://github.com/joaompinto/janito/compare/v4.41.0...HEAD)

Changes since `v4.41.0` (2026-09-16).

### Changed

- Default reasoning effort is now `medium` for every model that supports it
  (openai, google, alibaba, meta); moonshot/deepseek unchanged since they do
  not support `medium` (close #147).
