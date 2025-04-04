#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# Check if hatch is installed
if ! command -v hatch &> /dev/null; then
    print_error "hatch is not installed. Please install it first."
fi

# Check if twine is installed
if ! command -v twine &> /dev/null; then
    print_error "twine is not installed. Please install it first."
fi

# Get version from pyproject.toml
if [ ! -f "pyproject.toml" ]; then
    print_error "pyproject.toml not found. Are you running this from the project root?"
fi

PROJECT_VERSION=$(grep -E "^version = \"[0-9]+\.[0-9]+\.[0-9]+\"" pyproject.toml | cut -d'"' -f2)
if [ -z "$PROJECT_VERSION" ]; then
    print_error "Could not find version in pyproject.toml"
fi

print_info "Project version from pyproject.toml: $PROJECT_VERSION"

# Check PyPI for existing version and compare with latest
print_info "Checking PyPI for version information..."
PYPI_INFO=$(curl -s "https://pypi.org/pypi/janito/json" 2>/dev/null)
if [ $? -eq 0 ]; then
    LATEST_VERSION=$(echo "$PYPI_INFO" | grep -o '"version":"[^"]*"' | head -1 | cut -d'"' -f4)
    print_info "Latest version on PyPI: $LATEST_VERSION"
    
    # Check if current version already exists on PyPI
    if curl -f -s "https://pypi.org/pypi/janito/$PROJECT_VERSION/json" > /dev/null 2>&1; then
        print_error "Version $PROJECT_VERSION already exists on PyPI. Please update the version in pyproject.toml."
    fi
    
    # Compare versions using proper version comparison
    # Split versions into components
    IFS='.' read -r -a PROJECT_PARTS <<< "$PROJECT_VERSION"
    IFS='.' read -r -a LATEST_PARTS <<< "$LATEST_VERSION"
    
    # Compare major version
    if [[ ${PROJECT_PARTS[0]} -lt ${LATEST_PARTS[0]} ]]; then
        print_error "Version $PROJECT_VERSION is older than the latest version $LATEST_VERSION on PyPI. Please update the version in pyproject.toml."
    elif [[ ${PROJECT_PARTS[0]} -eq ${LATEST_PARTS[0]} ]]; then
        # Compare minor version
        if [[ ${PROJECT_PARTS[1]} -lt ${LATEST_PARTS[1]} ]]; then
            print_error "Version $PROJECT_VERSION is older than the latest version $LATEST_VERSION on PyPI. Please update the version in pyproject.toml."
        elif [[ ${PROJECT_PARTS[1]} -eq ${LATEST_PARTS[1]} ]]; then
            # Compare patch version
            if [[ ${PROJECT_PARTS[2]} -lt ${LATEST_PARTS[2]} ]]; then
                print_error "Version $PROJECT_VERSION is older than the latest version $LATEST_VERSION on PyPI. Please update the version in pyproject.toml."
            elif [[ ${PROJECT_PARTS[2]} -eq ${LATEST_PARTS[2]} ]]; then
                print_error "Version $PROJECT_VERSION is the same as the latest version $LATEST_VERSION on PyPI. Please update the version in pyproject.toml."
            fi
        fi
    fi
else
    print_warning "Could not fetch information from PyPI. Will attempt to publish anyway."
fi

# Get current git tag
CURRENT_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
if [ -z "$CURRENT_TAG" ]; then
    print_warning "No git tags found. A new tag will be created during the release process."
else
    # Remove 'v' prefix if present
    CURRENT_TAG_VERSION=${CURRENT_TAG#v}
    print_info "Current git tag: $CURRENT_TAG (version: $CURRENT_TAG_VERSION)"
    
    if [ "$PROJECT_VERSION" != "$CURRENT_TAG_VERSION" ]; then
        print_error "Version mismatch: pyproject.toml ($PROJECT_VERSION) != git tag ($CURRENT_TAG_VERSION)"
    fi
    
    # Check if the tag points to the current commit
    CURRENT_COMMIT=$(git rev-parse HEAD)
    TAG_COMMIT=$(git rev-parse "$CURRENT_TAG")
    if [ "$CURRENT_COMMIT" != "$TAG_COMMIT" ]; then
        print_error "Tag $CURRENT_TAG does not point to the current commit. Please update the tag or create a new one."
    fi
fi

# Check if the working directory is clean
if [ -n "$(git status --porcelain)" ]; then
    print_error "Working directory is not clean. Please commit all changes before releasing."
fi

# Confirm with the user
echo ""
echo "Ready to publish version $PROJECT_VERSION to PyPI."
read -p "Do you want to continue? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_info "Release cancelled."
    exit 0
fi

# Clean the dist directory
print_info "Cleaning dist directory..."
if [ -d "dist" ]; then
    rm -rf dist/*
    print_info "Dist directory cleaned."
else
    mkdir -p dist
    print_info "Dist directory created."
fi

# Build the package
print_info "Building package..."
hatch build

# Publish to PyPI
print_info "Publishing to PyPI..."
twine upload dist/*

# Create a new git tag if one doesn't exist for this version
if [ -z "$CURRENT_TAG" ] || [ "$CURRENT_TAG_VERSION" != "$PROJECT_VERSION" ]; then
    print_info "Creating git tag v$PROJECT_VERSION..."
    git tag -a "v$PROJECT_VERSION" -m "Release version $PROJECT_VERSION"
    git push origin "v$PROJECT_VERSION"
fi

print_info "Release completed successfully!"