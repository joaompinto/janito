"""Built-in configuration for the Anthropic provider.

``PROVIDER_CONFIG`` is the config entry for ``anthropic``.  See
:mod:`janito.providers.template.config` for the full reference of every
CONFIG option.
"""

#: The config entry for the ``anthropic`` provider.
PROVIDER_CONFIG: dict = {
    "default_model": "claude-sonnet-5",
    "endpoint": "https://api.anthropic.com/v1/",
    # Per-API-type endpoints: the OpenAI-compatible Chat Completions URL
    # and the native Anthropic SDK base URL. A provider whose dict holds a
    # single entry uses that URL as the default for *any* API type (unless
    # a config endpoint is set); see get_endpoint_for_api_type.
    "endpoint_by_api_type": {
        "Completions": "https://api.anthropic.com/v1/",
        "Anthropic": "https://api.anthropic.com",
    },
    "models": {
        "claude-sonnet-5": {
            "supported_api_types": [
                "Completions",
                "Anthropic",  # native Anthropic SDK (requires the `anthropic` package)
            ],  # Completions is the built-in default: Anthropic's
            # OpenAI-compatible /v1/chat/completions. The native Anthropic
            # SDK API type is selectable with --set api-type=Anthropic /
            # --api-type Anthropic (it requires the optional `anthropic`
            # package; see REQUIRES_BY_API_TYPE).
            "default_api_type": "Completions",  # built-in default (the first supported type)
            "max_input_tokens": 200000,
            "max_output_tokens": 64000,
        },
        "claude-opus-5-5": {
            "supported_api_types": [
                "Completions",
                "Anthropic",  # native Anthropic SDK (requires the `anthropic` package)
            ],
            "default_api_type": "Completions",  # built-in default (the first supported type)
            # Claude 4.6 and later include the full 1M-token context window
            # at standard pricing.
            "max_input_tokens": 1000000,
            "max_output_tokens": 128000,
        },
        "claude-fable-5-1": {
            "supported_api_types": [
                "Completions",
                "Anthropic",  # native Anthropic SDK (requires the `anthropic` package)
            ],
            "default_api_type": "Completions",  # built-in default (the first supported type)
            # Claude 4.6 and later include the full 1M-token context window
            # at standard pricing.
            "max_input_tokens": 1000000,
            "max_output_tokens": 128000,
        },
    },
}
