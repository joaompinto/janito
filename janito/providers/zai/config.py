"""Built-in configuration for the Zhipu (z.ai) provider.

``PROVIDER_CONFIG`` is the config entry for ``zai``.  See
:mod:`janito.providers.template.config` for the full reference of every
CONFIG option.
"""

#: The config entry for the ``zai`` provider.
PROVIDER_CONFIG: dict = {
    "default_model": "glm-5.3-flash",
    "endpoint": "https://api.z.ai/api/paas/v4/",
    "models": {
        "glm-5.3-flash": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",  # built-in default (the first supported type)
            "max_input_tokens": 1000000,  # 1M context window
            "max_output_tokens": 128000,  # 128K
        },
        "glm-5.3-flashx": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",  # built-in default (the first supported type)
            "max_input_tokens": 1000000,  # 1M context window
            "max_output_tokens": 128000,  # 128K
        },
        "glm-5.3": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",  # built-in default (the first supported type)
            "max_input_tokens": 1000000,  # 1M context window
            "max_output_tokens": 128000,  # 128K
        },
    },
}
