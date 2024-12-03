# Janito CLI

A CLI tool for software development tasks.

## Usage

```bash
janito WORKDIR REQUEST [OPTIONS]
```

### Arguments

- `WORKDIR`: Working directory containing the files (required)
- `REQUEST`: The modification request (required)

### Options

- `--raw`: Print raw response instead of markdown format
- `--play PATH`: Replay a saved prompt file
- `-i, --include PATH`: Additional paths to include in analysis (can be specified multiple times)

### Examples

```bash
# Basic usage
janito ./myproject "add error handling"

# Include additional paths in analysis
janito ./myproject "update tests" -i ./tests -i ./lib

# Show raw output
janito ./myproject "refactor code" --raw

# Replay saved prompt
janito ./myproject "update docs" --play .janito/history/20240101_123456_selected_.txt
```