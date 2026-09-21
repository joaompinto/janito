"""Built-in configuration for the Meta provider (Meta Model API).

``PROVIDER_CONFIG`` is the config entry for ``meta``.  See
:mod:`janito.providers.template.config` for the full reference of every
CONFIG option.
"""

#: The config entry for the ``meta`` provider.
PROVIDER_CONFIG: dict = {
    "default_model": "muse-spark-1.3",
    # Meta Model API is drop-in compatible with the OpenAI SDK: the same
    # base URL serves the Chat Completions and Responses APIs (the OpenAI
    # SDK appends /chat/completions and /responses to it).  It also
    # exposes an Anthropic Messages-compatible endpoint whose exact path
    # is not documented yet, so the native Anthropic SDK API type is not
    # declared here.
    "endpoint": "https://api.meta.ai/v1",
    "models": {
        "muse-spark-1.3": {
            # Responses is the built-in default API type (Meta's
            # recommended agentic surface).  Meta's /responses endpoint is
            # stateless in practice for cross-turn continuity: per the docs
            # (https://dev.meta.ai/docs/protocols/responses), stateless
            # encrypted reasoning replay (store:false + include
            # reasoning.encrypted_content, full history re-sent every turn)
            # is the recommended agentic path and cannot be combined with
            # previous_response_id, so janito tracks the conversation
            # client-side like Chat Completions.  The Chat Completions API
            # remains fully supported and can be selected with --set
            # api-type=Completions or --api-type completions.
            "supported_api_types": ["Responses", "Completions"],
            "default_api_type": "Responses",  # built-in default (the first supported type)
            "stateless_mode": True,
            # Muse Spark exposes its chain of thought only in encrypted
            # form: request it on every call so the reasoning items returned
            # in `output` can be replayed in the next turn's `input`
            # (without replay the model loses chain-of-thought context
            # across turns).
            "responses_include": ["reasoning.encrypted_content"],
            # Request a human-readable reasoning summary on the Responses
            # API (reasoning.summary="auto", streamed as
            # response.reasoning_summary_text deltas and surfaced via
            # on_reasoning).  The raw chain of thought stays private.
            "thinking_summary": True,
            # Search grounding (issue #131): Responses-only web_search
            # builtin tool (https://dev.meta.ai/docs/search-grounding).
            # Not available through Chat Completions.
            "tools_by_api_type": {
                "Responses": [{"type": "web_search"}],
            },
            # 1M-token context window per the official model page
            # (https://developer.meta.com/ai/models/muse-spark/).
            "max_input_tokens": 1048576,  # 1M (2**20)
            # Muse Spark reasons internally; reasoning depth is set with
            # reasoning_effort.  Per the reasoning cookbook
            # (https://dev.meta.ai/docs/cookbook/reasoning-thinking-tokens)
            # the accepted values run minimal < low < medium < high
            # (xhigh is accepted but maps to the same strength as high,
            # and the string "none" is not reliably available on the
            # public endpoint yet).  The built-in default is the standard
            # level (medium).
            "default_reasoning_effort": "medium",
            "supported_reasoning_efforts": [
                {
                    "effort": "minimal",
                    "description": "Fewest reasoning tokens for simple tasks",
                },
                {
                    "effort": "low",
                    "description": "Lighter reasoning for fast responses",
                },
                {
                    "effort": "medium",
                    "description": "Greater reasoning depth for complex problems",
                },
                {
                    "effort": "high",
                    "description": "Maximum reasoning depth (the effective maximum)",
                },
            ],
        },
        "muse-spark-1.3-contributor": {
            # The contributor tier ships the same model capabilities under
            # a separate model ID (per the official model page: the
            # contributor tier data is used to improve Meta's products).
            # Same API-type surface, stateless Responses handling, context
            # window and reasoning efforts as the standard tier; only the
            # pricing differs (see janito/providers/meta/cost.py).  The
            # built-in default is the standard level (medium),
            # like the standard tier.
            "supported_api_types": ["Responses", "Completions"],
            "default_api_type": "Responses",
            "stateless_mode": True,
            "responses_include": ["reasoning.encrypted_content"],
            # Request a human-readable reasoning summary on the Responses
            # API (reasoning.summary="auto", streamed as
            # response.reasoning_summary_text deltas and surfaced via
            # on_reasoning).  The raw chain of thought stays private.
            "thinking_summary": True,
            # Search grounding (issue #131): Responses-only web_search
            # builtin tool (https://dev.meta.ai/docs/search-grounding).
            # Not available through Chat Completions.
            "tools_by_api_type": {
                "Responses": [{"type": "web_search"}],
            },
            "max_input_tokens": 1048576,  # 1M (2**20)
            "default_reasoning_effort": "medium",
            "supported_reasoning_efforts": [
                {
                    "effort": "minimal",
                    "description": "Fewest reasoning tokens for simple tasks",
                },
                {
                    "effort": "low",
                    "description": "Lighter reasoning for fast responses",
                },
                {
                    "effort": "medium",
                    "description": "Greater reasoning depth for complex problems",
                },
                {
                    "effort": "high",
                    "description": "Maximum reasoning depth (the effective maximum)",
                },
            ],
        },
    },
}
