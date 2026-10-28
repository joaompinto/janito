"""Built-in configuration for the Moonshot/Kimi provider.

``PROVIDER_CONFIG`` is the config entry for ``moonshot``.  See
:mod:`janito.providers.template.config` for the full reference of every
CONFIG option.
"""

#: The config entry for the ``moonshot`` provider.
PROVIDER_CONFIG: dict = {
    "default_model": "kimi-k3",
    "endpoint": "https://api.moonshot.ai/v1",
    "models": {
        "kimi-k3": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",  # built-in default (the first supported type)
            "max_input_tokens": 128000,
            "max_output_tokens": 250000,  # 256k
            # Per the Moonshot/Kimi API reference, reasoning_effort accepts
            # low/high/max (default max). Kimi K3 models always reason.
            "default_reasoning_effort": "max",
            "supported_reasoning_efforts": [
                {
                    "effort": "low",
                    "description": "Lighter reasoning for fast responses",
                },
                {
                    "effort": "high",
                    "description": "Standard reasoning depth",
                },
                {
                    "effort": "max",
                    "description": "Maximum reasoning depth (the API default)",
                },
            ],
        },
        "kimi-k3.1-pro": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",  # built-in default (the first supported type)
            "max_input_tokens": 1048576,  # 1M context window
            "max_output_tokens": 131072,  # 128k (API default)
            # Per the Moonshot/Kimi API reference, reasoning_effort accepts
            # low/high/max (default max). Kimi K3.1 models always reason.
            "default_reasoning_effort": "max",
            "supported_reasoning_efforts": [
                {
                    "effort": "low",
                    "description": "Lighter reasoning for fast responses",
                },
                {
                    "effort": "high",
                    "description": "Standard reasoning depth",
                },
                {
                    "effort": "max",
                    "description": "Maximum reasoning depth (the API default)",
                },
            ],
        },
        "kimi-k3.1-pro-highspeed": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",  # built-in default (the first supported type)
            "max_input_tokens": 1048576,  # 1M context window
            "max_output_tokens": 131072,  # 128k (API default)
            # Same reasoning levels as kimi-k3.1-pro: low/high/max,
            # default max. Higher-throughput deployment of K3.1 Pro.
            "default_reasoning_effort": "max",
            "supported_reasoning_efforts": [
                {
                    "effort": "low",
                    "description": "Lighter reasoning for fast responses",
                },
                {
                    "effort": "high",
                    "description": "Standard reasoning depth",
                },
                {
                    "effort": "max",
                    "description": "Maximum reasoning depth (the API default)",
                },
            ],
        },
    },
}
