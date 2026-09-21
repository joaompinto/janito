"""Built-in configuration for the Google (Gemini) provider.

``PROVIDER_CONFIG`` is the config entry for ``google``.  See
:mod:`janito.providers.template.config` for the full reference of every
CONFIG option.

The Gemini models can be accessed two ways:

- through Google's OpenAI-compatibility layer (see
  https://ai.google.dev/gemini-api/docs/openai): the OpenAI SDK is pointed
  at ``https://generativelanguage.googleapis.com/v1beta/openai/`` with a
  Gemini API key from Google AI Studio (``GEMINI_API_KEY``), so the provider
  talks to Gemini through the standard Chat Completions API
  (``"Completions"`` API type, the built-in default);
- through the **native** Gemini API (``"Gemini"`` API type): the optional
  ``google-genai`` package talks directly to the Gemini API
  (``https://generativelanguage.googleapis.com``) with the same API key.
  The native type is selectable with ``--set api-type=Gemini`` or
  ``--api-type Gemini``; it requires the optional ``google-genai`` package
  (see ``REQUIRES_BY_API_TYPE``).
"""

#: The config entry for the ``google`` provider.
PROVIDER_CONFIG: dict = {
    "default_model": "gemini-3.7-flash",
    # Google's OpenAI-compatible base URL: the OpenAI SDK appends
    # /chat/completions to it.  Only the Chat Completions API is documented
    # by the OpenAI-compatibility layer, so the provider is Completions-only.
    "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai/",
    # Per-API-type endpoints: the OpenAI-compatible Chat Completions URL and
    # the native Gemini API base URL (the google-genai SDK's default, so the
    # native type also works with no base URL at all).  A provider whose dict
    # holds a single entry uses that URL as the default for *any* API type
    # (unless a config endpoint is set); see get_endpoint_for_api_type.
    "endpoint_by_api_type": {
        "Completions": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "Gemini": "https://generativelanguage.googleapis.com",
    },
    # Gemini-flavored API: Google's OpenAI-compatibility layer has
    # provider-specific behaviours that differ from the standard
    # OpenAI-compatible surface.  In particular, the ``enable_thinking``
    # extra-body flag is **not** accepted (Gemini 3.x models reason by
    # default and the field does not exist); thinking depth is controlled
    # through the resolved reasoning level (``reasoning_effort``), which
    # the API maps to the model's ``thinking_level``.
    "gemini_flavor": True,
    "models": {
        "gemini-3.8-flash": {
            # Completions is the built-in default (Google's OpenAI-
            # compatibility layer, which works out of the box with the
            # hard `openai` dependency).  The native Gemini API type is
            # selectable with --set api-type=Gemini / --api-type Gemini
            # (it requires the optional `google-genai` package; see
            # REQUIRES_BY_API_TYPE).
            "supported_api_types": ["Completions", "Gemini"],
            "default_api_type": "Completions",  # built-in default (the first supported type)
            "max_input_tokens": 1048576,  # 1M
            "max_output_tokens": 65536,  # 64k
            # Gemini 3.x models reason by default and thinking cannot be
            # disabled for them.  Per the Gemini Flash reference,
            # reasoning_effort maps to the model's thinking_level, which
            # accepts low/medium/high (default medium).
            "default_reasoning_effort": "medium",
            "supported_reasoning_efforts": [
                {
                    "effort": "low",
                    "description": "Lighter reasoning for fast responses",
                },
                {
                    "effort": "medium",
                    "description": "Standard reasoning depth",
                },
                {
                    "effort": "high",
                    "description": "Deep reasoning for complex problems",
                },
            ],
        },
        "gemini-3.7-flash": {
            # Completions is the built-in default (Google's OpenAI-
            # compatibility layer, which works out of the box with the
            # hard `openai` dependency).  The native Gemini API type is
            # selectable with --set api-type=Gemini / --api-type Gemini
            # (it requires the optional `google-genai` package; see
            # REQUIRES_BY_API_TYPE).
            "supported_api_types": ["Completions", "Gemini"],
            "default_api_type": "Completions",  # built-in default (the first supported type)
            "max_input_tokens": 1048576,  # 1M
            "max_output_tokens": 65536,  # 64k
            # Gemini 3.x models reason by default and thinking cannot be
            # disabled for them.  Per the Gemini 3.7 Flash reference,
            # reasoning_effort maps to the model's thinking_level, which
            # accepts low/medium/high (default medium).
            "default_reasoning_effort": "medium",
            "supported_reasoning_efforts": [
                {
                    "effort": "low",
                    "description": "Lighter reasoning for fast responses",
                },
                {
                    "effort": "medium",
                    "description": "Standard reasoning depth",
                },
                {
                    "effort": "high",
                    "description": "Deep reasoning for complex problems",
                },
            ],
        },
    },
}
