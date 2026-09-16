"""Built-in configuration for the Atria provider.

``PROVIDER_CONFIG`` is the config entry for ``atria``.  See
:mod:`janito.providers.template.config` for the full reference of every
CONFIG option.
"""

#: The config entry for the ``atria`` provider.
PROVIDER_CONFIG: dict = {
    "default_model": "Atria-Dawn-Preview",
    "endpoint": "https://api.atria-asi.ai/v1",
    "models": {
        "Atria-Dawn-Preview": {
            "supported_api_types": ["Responses", "Completions"],
            "default_api_type": "Responses",
            # The docs describe single request/response calls with the full
            # messages/input sent each time and no previous_response_id
            # chaining, so the Responses endpoint is treated as stateless.
            "stateless_mode": True,
            "max_input_tokens": 256000,
            "max_output_tokens": 65536,
        },
    },
}
