"""Built-in configuration for the Alibaba (DashScope) provider.

``PROVIDER_CONFIG`` is the config entry for ``alibaba``.  See
:mod:`janito.providers.template.config` for the full reference of every
CONFIG option.
"""

#: The config entry for the ``alibaba`` provider.
PROVIDER_CONFIG: dict = {
    "default_model": "qwen3.8-flash",
    "endpoint": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    # Per-API-type endpoints: the OpenAI-compatible Chat Completions /
    # Responses base URL (DashScope's plain compatible-mode gateway, the
    # same URL the OpenAI SDK appends /chat/completions and /responses
    # to) and the native DashScope SDK base URL (the SDK talks to the
    # DashScope native API, not the compatible-mode gateway). The
    # "apps-protocol" compatible-mode URL
    # (dashscope-intl.aliyuncs.com/api/v2/apps/protocols/compatible-mode/v1)
    # only serves Model Studio *applications* and rejects ordinary
    # DashScope API keys with "Not support", so it must not be used here.
    "endpoint_by_api_type": {
        "Completions": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "Responses": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "DashScope": "https://dashscope-intl.aliyuncs.com/api/v1",
    },
    "models": {
        "qwen3.8-max": {
            # Responses is the built-in default API type. The Completions
            # API remains fully supported and can be selected with
            # --set api-type=Completions or --api-type completions. The
            # native DashScope SDK API type is selectable with
            # --set api-type=DashScope or --api-type DashScope (it
            # requires the optional `dashscope` package; see
            # REQUIRES_BY_API_TYPE).
            "supported_api_types": ["Completions", "Responses", "DashScope"],
            "default_api_type": "Responses",  # built-in default
            "max_input_tokens": 1000000,  # 1M
            "max_output_tokens": 131072,
            # Per the QwenCloud API reference, reasoning_effort accepts
            # low/medium/xhigh.  The built-in default is the standard
            # level (medium) instead of the API's xhigh.
            "default_reasoning_effort": "medium",
            "thinking": True,  # Qwen models reason by default
            # Qwen hybrid-thinking models keep their previous reasoning in
            # multi-turn context: preserve_thinking appends the assistant
            # messages' reasoning_content to the next input, so the model can
            # reference its own prior reasoning (per the QwenCloud Thinking
            # guide).  Sent as extra_body['preserve_thinking'] on the
            # OpenAI-compatible Completions / Responses calls (a Qwen
            # extension, not an OpenAI standard parameter).
            "preserve_thinking": True,
            # Built-in (native) tools, enabled per API type.  These are
            # *not* function tools: on the Responses API they are entries in
            # the ``tools`` array, on the Completions API they are extra_body
            # ``enable_code_interpreter`` / ``enable_search`` flags, and on
            # the native DashScope API they are ``enable_code_interpreter`` /
            # ``enable_search`` kwargs.  ``code_interpreter`` only supports
            # calls in thinking mode, so it also forces ``enable_thinking``
            # on.
            #
            # Only the Responses API is enabled: the qwen3.8-max deployment
            # rejects the built-in tools on the Completions API with ``400
            # InternalError.Algo.InvalidParameter: The current model does not
            # support the code_interpreter tool.``, and the DashScope native
            # endpoint is left off for the same reason until confirmed.
            # Re-enable per API type once the endpoint accepts them.
            "tools_by_api_type": {
                "Responses": [
                    {"type": "code_interpreter"},
                    {"type": "web_search"},
                    {"type": "web_extractor"},
                ],
            },
            "supported_reasoning_efforts": [
                {
                    "effort": "low",
                    "description": "Fast responses with lighter reasoning",
                },
                {
                    "effort": "medium",
                    "description": "Greater reasoning depth for complex problems",
                },
                {
                    "effort": "xhigh",
                    "description": "Extra high reasoning depth for complex problems",
                },
            ],
        },
        "qwen3.8-max-0902": {
            # Responses is the built-in default API type. The Completions
            # API remains fully supported and can be selected with
            # --set api-type=Completions or --api-type completions. The
            # native DashScope SDK API type is selectable with
            # --set api-type=DashScope or --api-type DashScope (it
            # requires the optional `dashscope` package; see
            # REQUIRES_BY_API_TYPE).
            "supported_api_types": ["Completions", "Responses", "DashScope"],
            "default_api_type": "Responses",  # built-in default
            "max_input_tokens": 1000000,  # 1M
            "max_output_tokens": 131072,
            # Per the QwenCloud API reference, reasoning_effort accepts
            # low/medium/xhigh.  The built-in default is the standard
            # level (medium) instead of the API's xhigh.
            "default_reasoning_effort": "medium",
            "thinking": True,  # Qwen models reason by default
            # Qwen hybrid-thinking models keep their previous reasoning in
            # multi-turn context: preserve_thinking appends the assistant
            # messages' reasoning_content to the next input, so the model can
            # reference its own prior reasoning (per the QwenCloud Thinking
            # guide).  Sent as extra_body['preserve_thinking'] on the
            # OpenAI-compatible Completions / Responses calls (a Qwen
            # extension, not an OpenAI standard parameter).
            "preserve_thinking": True,
            # Built-in (native) tools, enabled per API type.  These are
            # *not* function tools: on the Responses API they are entries in
            # the ``tools`` array, on the Completions API they are extra_body
            # ``enable_code_interpreter`` / ``enable_search`` flags, and on
            # the native DashScope API they are ``enable_code_interpreter`` /
            # ``enable_search`` kwargs.  ``code_interpreter`` only supports
            # calls in thinking mode, so it also forces ``enable_thinking``
            # on.
            #
            # Only the Responses API is enabled: the qwen3.8-max deployment
            # rejects the built-in tools on the Completions API with ``400
            # InternalError.Algo.InvalidParameter: The current model does not
            # support the code_interpreter tool.``, and the DashScope native
            # endpoint is left off for the same reason until confirmed.
            # Re-enable per API type once the endpoint accepts them.
            "tools_by_api_type": {
                "Responses": [
                    {"type": "code_interpreter"},
                    {"type": "web_search"},
                    {"type": "web_extractor"},
                ],
            },
            "supported_reasoning_efforts": [
                {
                    "effort": "low",
                    "description": "Fast responses with lighter reasoning",
                },
                {
                    "effort": "medium",
                    "description": "Greater reasoning depth for complex problems",
                },
                {
                    "effort": "xhigh",
                    "description": "Extra high reasoning depth for complex problems",
                },
            ],
        },
        "qwen3.8-flash": {
            # Same API-type surface as qwen3.8-max (see its entry for the
            # endpoint notes): the OpenAI-compatible Chat Completions /
            # Responses endpoints plus the native DashScope SDK, with
            # Responses as the built-in default API type.
            "supported_api_types": ["Completions", "Responses", "DashScope"],
            "default_api_type": "Responses",  # built-in default
            # Official QwenCloud page (https://www.qwencloud.com/models/
            # qwen3.8-flash): 1M context window with a 991K max input (the
            # rest is reserved for output/reasoning) and 131K max output.
            "max_input_tokens": 991000,  # 991K
            "max_output_tokens": 131072,  # 131K
            # qwen3.8-flash supports the same configurable reasoning depth
            # as qwen3.8-max (low/medium/xhigh per the QwenCloud API
            # reference); the built-in default is the standard level (medium).
            "default_reasoning_effort": "medium",
            "supported_reasoning_efforts": [
                {
                    "effort": "low",
                    "description": "Fast responses with lighter reasoning",
                },
                {
                    "effort": "medium",
                    "description": "Greater reasoning depth for complex problems",
                },
                {
                    "effort": "xhigh",
                    "description": "Extra high reasoning depth for complex problems",
                },
            ],
            "thinking": True,  # Qwen models reason by default
            # See the qwen3.8-max entry: multi-turn reasoning is preserved by
            # sending extra_body['preserve_thinking'] on the OpenAI-compatible
            # Completions / Responses calls.
            "preserve_thinking": True,
            # Built-in (native) tools, enabled per API type.  The official
            # page advertises code_interpreter / i2i_search / t2i_search /
            # web_extractor / web_search for the Responses API.  Like
            # qwen3.8-max, they are left off the Completions and native
            # DashScope APIs until the deployment is confirmed to accept
            # them there.
            "tools_by_api_type": {
                "Responses": [
                    {"type": "code_interpreter"},
                    {"type": "i2i_search"},
                    {"type": "t2i_search"},
                    {"type": "web_extractor"},
                    {"type": "web_search"},
                ],
            },
        },
    },
}
