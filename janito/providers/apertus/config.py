"""Built-in configuration for the Apertus provider (Swisscom).

``PROVIDER_CONFIG`` is the config entry for ``apertus``.  Apertus 1.5 70B
(Swiss AI Initiative) is served through Swisscom's OpenAI-compatible
gateway, so only the Chat Completions API type is declared.  See
:mod:`janito.providers.template.config` for the full reference of every
CONFIG option.
"""

#: The config entry for the ``apertus`` provider.
PROVIDER_CONFIG: dict = {
    "default_model": "swiss-ai/Apertus-v1.5-70B",
    "endpoint": "https://api.swisscom.com/products/swiss-ai-weeks/apertus-1.5-70b/v1",
    "models": {
        "swiss-ai/Apertus-v1.5-70B": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",  # built-in default (the first supported type)
            "max_input_tokens": 262144,  # 262K context window
        },
    },
}
