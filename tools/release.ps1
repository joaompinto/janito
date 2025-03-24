#!/usr/bin/env pwsh
# PowerShell version of the release tool
# Set strict mode to catch errors
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Function to print colored messages
function Print-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Green
}

function Print-Warning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Print-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
    exit 1
}

# Check if hatch is installed
if (-not (Get-Command "hatch" -ErrorAction SilentlyContinue)) {
    Print-Error "hatch is not installed. Please install it first."
}

# Check if twine is installed
if (-not (Get-Command "twine" -ErrorAction SilentlyContinue)) {
    Print-Error "twine is not installed. Please install it first."
}

# Get version from pyproject.toml
if (-not (Test-Path "pyproject.toml")) {
    Print-Error "pyproject.toml not found. Are you running this from the project root?"
}

$ProjectVersionMatch = Select-String -Path "pyproject.toml" -Pattern '^version = "(\d+\.\d+\.\d+)"'
if (-not $ProjectVersionMatch) {
    Print-Error "Could not find version in pyproject.toml"
}
$ProjectVersion = $ProjectVersionMatch.Matches.Groups[1].Value

Print-Info "Project version from pyproject.toml: $ProjectVersion"

# Check PyPI for existing version and compare with latest
Print-Info "Checking PyPI for version information..."
try {
    $PypiInfo = Invoke-RestMethod -Uri "https://pypi.org/pypi/janito/json" -ErrorAction SilentlyContinue
    $LatestVersion = $PypiInfo.info.version
    Print-Info "Latest version on PyPI: $LatestVersion"
    
    # Check if current version already exists on PyPI
    try {
        $null = Invoke-RestMethod -Uri "https://pypi.org/pypi/janito/$ProjectVersion/json" -ErrorAction SilentlyContinue
        Print-Error "Version $ProjectVersion already exists on PyPI. Please update the version in pyproject.toml."
    } catch {
        # Version doesn't exist on PyPI, which is good
    }
    
    # Compare versions using proper version comparison
    $ProjectVersionObj = [Version]$ProjectVersion
    $LatestVersionObj = [Version]$LatestVersion
    
    if ($ProjectVersionObj -lt $LatestVersionObj) {
        Print-Error "Version $ProjectVersion is older than the latest version $LatestVersion on PyPI. Please update the version in pyproject.toml."
    } elseif ($ProjectVersionObj -eq $LatestVersionObj) {
        Print-Error "Version $ProjectVersion is the same as the latest version $LatestVersion on PyPI. Please update the version in pyproject.toml."
    }
} catch {
    Print-Warning "Could not fetch information from PyPI. Will attempt to publish anyway."
}

# Get current git tag
try {
    $CurrentTag = git describe --tags --abbrev=0 2>$null
} catch {
    $CurrentTag = ""
}

if ([string]::IsNullOrEmpty($CurrentTag)) {
    Print-Warning "No git tags found. A new tag will be created during the release process."
    $CurrentTagVersion = ""
} else {
    # Remove 'v' prefix if present
    $CurrentTagVersion = $CurrentTag -replace '^v', ''
    Print-Info "Current git tag: $CurrentTag (version: $CurrentTagVersion)"
    
    if ($ProjectVersion -ne $CurrentTagVersion) {
        Print-Error "Version mismatch: pyproject.toml ($ProjectVersion) != git tag ($CurrentTagVersion)"
    }
    
    # Check if the tag points to the current commit
    $CurrentCommit = git rev-parse HEAD
    $TagCommit = git rev-parse "$CurrentTag"
    if ($CurrentCommit -ne $TagCommit) {
        Print-Error "Tag $CurrentTag does not point to the current commit. Please update the tag or create a new one."
    }
}

# Check if the working directory is clean
$GitStatus = git status --porcelain
if (-not [string]::IsNullOrEmpty($GitStatus)) {
    Print-Error "Working directory is not clean. Please commit all changes before releasing."
}

# Confirm with the user
Write-Host ""
Write-Host "Ready to publish version $ProjectVersion to PyPI."
$Confirmation = Read-Host "Do you want to continue? (y/n)"
if ($Confirmation -notmatch '^[Yy]$') {
    Print-Info "Release cancelled."
    exit 0
}

# Clean the dist directory
Print-Info "Cleaning dist directory..."
if (Test-Path "dist") {
    Remove-Item -Path "dist\*" -Force -Recurse
    Print-Info "Dist directory cleaned."
} else {
    New-Item -Path "dist" -ItemType Directory | Out-Null
    Print-Info "Dist directory created."
}

# Build the package
Print-Info "Building package..."
hatch build

# Publish to PyPI
Print-Info "Publishing to PyPI..."
twine upload dist\*

# Create a new git tag if one doesn't exist for this version
if ([string]::IsNullOrEmpty($CurrentTag) -or ($CurrentTagVersion -ne $ProjectVersion)) {
    Print-Info "Creating git tag v$ProjectVersion..."
    git tag -a "v$ProjectVersion" -m "Release version $ProjectVersion"
    git push origin "v$ProjectVersion"
}

Print-Info "Release completed successfully!"