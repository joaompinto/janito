#!/bin/bash
set -e  # Exit on error

# Helper functions
print_status() {
    local status=$1
    local message=$2
    if [ "$status" == "ok" ]; then
        echo "✓ $message"
    else
        echo "✗ $message"
        exit 1
    fi
}

check_pypi_version() {
    local package=$1
    pip index versions "$package" 2>/dev/null | grep -Po '(?<='"$package"' \()[0-9.]+' | head -n1 || echo "not found"
}

echo "Starting release validation pipeline..."

# Check PyPI version first
echo -e "\nChecking current PyPI version..."
PYPI_VERSION=$(check_pypi_version "janito")
echo "Current version on PyPI: $PYPI_VERSION"

# Phase 1: Version Validation
echo -e "\nValidating versions..."
# Get current version from pyproject.toml
CURRENT_VERSION=$(grep -Po '(?<=version = ")[^"]*' pyproject.toml)
echo "Current version in pyproject.toml: $CURRENT_VERSION"

# Phase 2: Git Status Checks
echo -e "\nValidating Git status..."
# Check if we're on a tagged commit
CURRENT_TAG=$(git describe --exact-match --tags HEAD 2>/dev/null || echo "")
if [ -z "$CURRENT_TAG" ]; then
    print_status "error" "Current commit is not tagged"
else
    print_status "ok" "Git tag found: $CURRENT_TAG"
fi

# Verify tag matches version in pyproject.toml
if [ "$CURRENT_TAG" != "v$CURRENT_VERSION" ]; then
    print_status "error" "Git tag ($CURRENT_TAG) doesn't match version in pyproject.toml (v$CURRENT_VERSION)"
else
    print_status "ok" "Version numbers match"
fi

# Check if working tree is clean
if [ -n "$(git status --porcelain)" ]; then
    print_status "error" "Working tree is not clean"
else
    print_status "ok" "Working tree is clean"
fi

# Phase 3: PyPI Version Check
echo -e "\nChecking PyPI status..."
PYPI_VERSION=$(pip index versions janito 2>/dev/null | grep -Po '(?<=janito \()[0-9.]+' | head -n1 || echo "not found")
echo "Current version on PyPI: $PYPI_VERSION"

# Phase 4: Release Confirmation
echo -e "\nRelease preparation..."
echo "Ready to release version $CURRENT_VERSION"
read -p "Do you want to proceed with the release? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Release cancelled"
    exit 1
fi

# Phase 5: Build and Upload
echo -e "\nExecuting release..."
echo "Cleaning previous build artifacts..."
rm -rf dist/ build/ *.egg-info
print_status "ok" "Clean build environment prepared"

echo "Building package..."
python -m build
print_status "ok" "Package built successfully"

echo "Uploading to PyPI..."
python -m twine upload dist/*
print_status "ok" "Package uploaded to PyPI"

echo -e "\nRelease completed successfully!"