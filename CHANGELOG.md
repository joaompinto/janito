# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.14.0] - 2025-03-24

### Added
- New 'think' tool for agent reasoning without changing the database
- No-tools mode with `--no-tools` flag to disable all tools for a session
- Enhanced history display with `--history` flag
- Support for custom system instructions with `--system/-s` flag
- Improved conversation continuation with multiple `--continue` flag options
- Reorganized CLI architecture with modular components

### Changed
- Simplified fetch_webpage tool by removing unused extractors and utilities
- Enhanced search_text tool with improved pattern matching
- Updated documentation with new features and usage examples
- Improved error handling in str_replace_editor

### Removed
- Deprecated test files and unused components

## [0.13.0] - 2025-03-23

### Added
- Conversation history storage and retrieval functionality with timestamp-based IDs
- `--continue` flag to continue from the last conversation
- Trust mode with `--trust/-t` flag to suppress tool outputs for concise execution
- Improved error handling in str_replace_editor

### Changed
- Updated rich_console.py with emoji support and trust mode integration
- Enhanced bash tool with trust mode support
- Updated conversation history to use timestamp-based IDs

### Documentation
- Added documentation for conversation history, `--continue` flag, and trust mode in README
- Updated STRUCTURE.md with new components and features

## [0.12.0] - 2023-06-11

### Added
- Major framework enhancements and new tools
- Conversation persistence and parameter profiles
- Real-time output for tools and improved tracking

### Changed
- Refactored CLI architecture
- Added Ctrl+C handling for better user experience
- Simplified command output formatting in bash tool
- Fixed bash tool execution on Linux

## [0.11.0] - 2023-06-10

### Fixed
- Removed duplicated inclusion of data files

## [0.10.1] - 2023-06-09

### Added
- Initial versioned release