"""Built-in configuration for the Xiaomi provider.

``PROVIDER_CONFIG`` is the config entry for ``xiaomi``.  See
:mod:`janito.providers.template.config` for the full reference of every
CONFIG option.

Model facts (as of the 2026-09-22 V2.6 release announcement,
https://mimo.mi.com/docs/en-US/news/latest/v2-6):

- The series comprises ``mimo-v2.6-pro`` and ``mimo-v2.6-flash``, plus the
  ``mimo-v2.6-pro-ultraspeed`` variant (up to 20x inference speed).
- API model names are all-lowercase.
- 1M context / 128K max output (unchanged from V2.5).
- Flash keeps the V2.5 pricing; Pro and UltraSpeed bill at higher
  flagship rates -- see :mod:`janito.providers.xiaomi.cost`.
"""

#: The config entry for the ``xiaomi`` provider.
PROVIDER_CONFIG: dict = {
    "default_model": "mimo-v2.6-flash",
    "endpoint": "https://api.xiaomimimo.com/v1",
    "models": {
        "mimo-v2.6-pro": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",  # built-in default (the first supported type)
            "max_input_tokens": 1048576,  # 1M
            "max_output_tokens": 131072,  # 128k
        },
        "mimo-v2.6-flash": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",  # built-in default (the first supported type)
            "max_input_tokens": 1048576,  # 1M
            "max_output_tokens": 131072,  # 128k
        },
        "mimo-v2.6-pro-ultraspeed": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",  # built-in default (the first supported type)
            "max_input_tokens": 1048576,  # 1M
            "max_output_tokens": 131072,  # 128k
        },
    },
}
