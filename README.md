# 🤖 Janito

[![PyPI version](https://badge.fury.io/py/janito.svg)](https://badge.fury.io/py/janito)
[![Python Versions](https://img.shields.io/pypi/pyversions/janito.svg)](https://pypi.org/project/janito/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Janito is an AI-powered CLI tool designed to help developers manage and modify their codebase with ease. It leverages advanced AI models to understand and transform your code intelligently.

## ✨ Features

### 🔄 Code Modifications
- **Smart Code Changes**: Automated code modifications with AI understanding
- **Context-Aware**: Considers your entire codebase for accurate changes
- **Preview & Validate**: Review changes before applying them

### 💡 Code Analysis
- **Intelligent Queries**: Ask questions about your codebase
- **Deep Understanding**: Get detailed explanations about code functionality
- **Context-Rich Responses**: Answers based on your actual code

### ⚙️ Easy Configuration
- **Multiple AI Backends**: Support for Claude and DeepSeek AI
- **Flexible Setup**: Simple environment variable configuration
- **Workspace Control**: Fine-grained control over scanned files

## 🚀 Installation

### Prerequisites
- Python 3.8 or higher
- pip package manager

### Install from PyPI
```bash
pip install janito
```

## 🔧 Configuration

Set up your preferred AI backend using environment variables:

### For Claude AI
```bash
export ANTHROPIC_API_KEY=your_api_key
export AI_BACKEND=claudeai  # Optional, detected from API key
```

### For DeepSeek AI
```bash
export DEEPSEEK_API_KEY=your_api_key
export AI_BACKEND=deepseekai  # Optional, detected from API key
```

## 📖 Usage

### Basic Commands

1. **Ask Questions**
```bash
janito --ask "How does the error handling work in this codebase?"
```

2. **Request Changes**
```bash
janito "Add error handling to the process_data function"
```

3. **Preview Files**
```bash
janito --scan
```

### Advanced Options

- **Workspace Directory**: `-w, --workspace_dir PATH`
- **Include Paths**: `-i, --include PATH`
- **Recursive Scan**: `-r, --recursive PATH`
- **Debug Mode**: `--debug`
- **Verbose Output**: `--verbose`

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.