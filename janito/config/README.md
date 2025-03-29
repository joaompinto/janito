# Janito Configuration System

This directory contains the configuration system for Janito. The configuration system is designed to be modular, extensible, and easy to use.

## Directory Structure

```
janito/config/
├── __init__.py                 # Re-exports and backward compatibility
├── README.md                   # This file
├── core/                       # Core configuration functionality
│   ├── __init__.py             # Re-exports core components
│   ├── singleton.py            # Singleton implementation
│   ├── properties.py           # Property getters and setters
│   └── file_operations.py      # File I/O operations
├── profiles/                   # Profile management
│   ├── __init__.py             # Re-exports profile components
│   ├── definitions.py          # Profile definitions
│   └── manager.py              # Profile management functions
└── cli/                        # CLI integration
    ├── __init__.py             # Re-exports CLI components
    ├── commands.py             # Command handling functions
    └── validators.py           # Input validation functions
```

## Core Components

The core configuration functionality is implemented in the `core` directory:

- `singleton.py`: Implements the `Config` class as a singleton to ensure only one instance exists
- `properties.py`: Contains property getters and setters for the `Config` class
- `file_operations.py`: Handles file I/O operations for loading and saving configuration files

## Profiles

The `profiles` directory contains functionality related to parameter profiles:

- `definitions.py`: Defines predefined parameter profiles (precise, balanced, conversational, creative, technical)
- `manager.py`: Provides functions for managing profiles, including getting available profiles and creating custom profiles

## CLI Integration

The `cli` directory contains functionality related to CLI integration:

- `commands.py`: Implements command handling functions for configuration-related CLI commands
- `validators.py`: Provides validation functions for configuration inputs

## Usage

### Basic Usage

```python
from janito.config import Config

# Get the singleton instance
config = Config()

# Access configuration properties
workspace_dir = config.workspace_dir
temperature = config.temperature
role = config.role

# Set configuration properties
config.temperature = 0.7  # Set runtime value only
config.temperature = (0.7, "local")  # Set in local config
config.temperature = (0.7, "global")  # Set in global config
```

### Working with Profiles

```python
from janito.config import Config, get_available_profiles, get_profile

# Get available profiles
profiles = get_available_profiles()
for name, data in profiles.items():
    print(f"{name}: {data['description']}")

# Get a specific profile
technical_profile = get_profile("technical")
print(f"Temperature: {technical_profile['temperature']}")

# Set a profile
config = Config()
config.set_profile("creative", "local")
```

### Configuration Files

The configuration system uses two configuration files:

- Global configuration file: `~/.janito/config.json`
- Local configuration file: `.janito/config.json` (in the current workspace directory)

Local configuration overrides global configuration when both are present.

## Extending the Configuration System

To add a new configuration property:

1. Add a property getter and setter in `core/properties.py`
2. Update the `_apply_config` method in `core/singleton.py` to handle the new property
3. Add validation in `cli/validators.py` if needed
4. Update the command handling in `cli/commands.py` to support the new property