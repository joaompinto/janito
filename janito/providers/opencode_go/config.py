"""Built-in configuration for the OpenCode Go provider.

``PROVIDER_CONFIG`` is the config entry for ``opencode-go``.

OpenCode Go is a subscription plan on the OpenCode Console gateway.  Go and
pay-as-you-go are served from different base URLs: Go lives under
``https://opencode.ai/inference/go`` and speaks every Console API (OpenAI
Responses, OpenAI Chat Completions, Anthropic Messages, Gemini).  This
provider uses the OpenAI-compatible Chat Completions endpoint
(``.../go/openai/v1``), which the gateway translates to each model's native
API when needed, so every text model in the Go catalog works through one
API type.

The rate card is *not* the per-provider list price: Go enforces monthly
usage limits per model (see :mod:`janito.providers.opencode_go.cost`).

The model catalog below mirrors the Go model list published at
https://opencode.ai/docs/console/go and https://models.dev (provider
``opencode-go``), excluding deprecated models.  Context windows, output
limits and reasoning efforts are the values published there.

See :mod:`janito.providers.template.config` for the full reference of every
CONFIG option.
"""

#: The config entry for the ``opencode-go`` provider.
PROVIDER_CONFIG: dict = {
    "default_model": "glm-5.3-flash",
    "endpoint": "https://opencode.ai/inference/go/openai/v1",
    "models": {
        "beam-free": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1048576,  # 1M
            "max_output_tokens": 131072,  # 128K
            "supported_reasoning_efforts": [
                {"effort": "low", "description": "Lighter reasoning for fast responses"},
                {"effort": "medium", "description": "Standard reasoning depth"},
                {"effort": "high", "description": "Deeper reasoning"},
                {"effort": "xhigh", "description": "Extra-high reasoning depth"},
                {"effort": "max", "description": "Maximum reasoning depth for complex problems"},
            ],
        },
        "claude-haiku-5-5": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1000000,  # 1M
            "max_output_tokens": 128000,  # 128K
            "supported_reasoning_efforts": [
                {"effort": "low", "description": "Lighter reasoning for fast responses"},
                {"effort": "medium", "description": "Standard reasoning depth"},
                {"effort": "high", "description": "Deeper reasoning"},
                {"effort": "xhigh", "description": "Extra-high reasoning depth"},
                {"effort": "max", "description": "Maximum reasoning depth for complex problems"},
            ],
        },
        "deepseek-v4-pro": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1000000,  # 1M
            "max_output_tokens": 384000,  # 384K
            "supported_reasoning_efforts": [
                {"effort": "high", "description": "Deeper reasoning"},
                {"effort": "max", "description": "Maximum reasoning depth for complex problems"},
            ],
        },
        "deepseek-v4.1-flash": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1000000,  # 1M
            "max_output_tokens": 384000,  # 384K
            "supported_reasoning_efforts": [
                {"effort": "low", "description": "Lighter reasoning for fast responses"},
                {"effort": "high", "description": "Deeper reasoning"},
                {"effort": "max", "description": "Maximum reasoning depth for complex problems"},
            ],
        },
        "gemini-4-argon": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1048576,  # 1M
            "max_output_tokens": 65536,  # 64K
            "supported_reasoning_efforts": [
                {"effort": "low", "description": "Lighter reasoning for fast responses"},
                {"effort": "medium", "description": "Standard reasoning depth"},
                {"effort": "high", "description": "Deeper reasoning"},
            ],
        },
        "glm-5.2": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1000000,  # 1M
            "max_output_tokens": 131072,  # 128K
            "supported_reasoning_efforts": [
                {"effort": "high", "description": "Deeper reasoning"},
                {"effort": "max", "description": "Maximum reasoning depth for complex problems"},
            ],
        },
        "glm-5.3": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1000000,  # 1M
            "max_output_tokens": 131072,  # 128K
            "supported_reasoning_efforts": [
                {"effort": "low", "description": "Lighter reasoning for fast responses"},
                {"effort": "high", "description": "Deeper reasoning"},
                {"effort": "max", "description": "Maximum reasoning depth for complex problems"},
            ],
        },
        "glm-5.3-flash": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1000000,  # 1M
            "max_output_tokens": 131072,  # 128K
            "supported_reasoning_efforts": [
                {"effort": "low", "description": "Lighter reasoning for fast responses"},
                {"effort": "high", "description": "Deeper reasoning"},
                {"effort": "max", "description": "Maximum reasoning depth for complex problems"},
            ],
        },
        "gpt-5.6-luna": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1050000,  # 1.05M
            "max_output_tokens": 128000,  # 128K
            "supported_reasoning_efforts": [
                {"effort": "none", "description": "No reasoning"},
                {"effort": "low", "description": "Lighter reasoning for fast responses"},
                {"effort": "medium", "description": "Standard reasoning depth"},
                {"effort": "high", "description": "Deeper reasoning"},
                {"effort": "xhigh", "description": "Extra-high reasoning depth"},
                {"effort": "max", "description": "Maximum reasoning depth for complex problems"},
            ],
        },
        "gpt-6-luna": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1050000,  # 1.05M
            "max_output_tokens": 128000,  # 128K
            "supported_reasoning_efforts": [
                {"effort": "none", "description": "No reasoning"},
                {"effort": "low", "description": "Lighter reasoning for fast responses"},
                {"effort": "medium", "description": "Standard reasoning depth"},
                {"effort": "high", "description": "Deeper reasoning"},
                {"effort": "xhigh", "description": "Extra-high reasoning depth"},
                {"effort": "max", "description": "Maximum reasoning depth for complex problems"},
            ],
        },
        "grok-4.7": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 500000,
            "max_output_tokens": 500000,
            "supported_reasoning_efforts": [
                {"effort": "low", "description": "Lighter reasoning for fast responses"},
                {"effort": "medium", "description": "Standard reasoning depth"},
                {"effort": "high", "description": "Deeper reasoning"},
                {"effort": "xhigh", "description": "Extra-high reasoning depth"},
            ],
        },
        "hy3": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 256000,
            "max_output_tokens": 128000,  # 128K
            "supported_reasoning_efforts": [
                {"effort": "none", "description": "No reasoning"},
                {"effort": "low", "description": "Lighter reasoning for fast responses"},
                {"effort": "high", "description": "Deeper reasoning"},
            ],
        },
        "hy4": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1048576,  # 1M
            "max_output_tokens": 65536,  # 64K
            "supported_reasoning_efforts": [
                {"effort": "none", "description": "No reasoning"},
                {"effort": "high", "description": "Deeper reasoning"},
            ],
        },
        "hy4-preview": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1024000,
            "max_output_tokens": 64000,  # 64K
            "supported_reasoning_efforts": [
                {"effort": "none", "description": "No reasoning"},
                {"effort": "high", "description": "Deeper reasoning"},
            ],
        },
        "iceman-contributor-free": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 262144,  # 256K
            "max_output_tokens": 131072,  # 128K
        },
        "kimi-k2.7-code": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 262144,  # 256K
            "max_output_tokens": 262144,  # 256K
        },
        "kimi-k3": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1048576,  # 1M
            "max_output_tokens": 1048576,  # 1M
            "supported_reasoning_efforts": [
                {"effort": "max", "description": "Maximum reasoning depth for complex problems"},
            ],
        },
        "kimi-k3.1-pro": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1048576,  # 1M
            "max_output_tokens": 1048576,  # 1M
            "supported_reasoning_efforts": [
                {"effort": "low", "description": "Lighter reasoning for fast responses"},
                {"effort": "high", "description": "Deeper reasoning"},
                {"effort": "max", "description": "Maximum reasoning depth for complex problems"},
            ],
        },
        "longcat-2.0": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1000000,  # 1M
            "max_output_tokens": 131072,  # 128K
        },
        "longcat-2.5-free": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1000000,  # 1M
            "max_output_tokens": 262144,  # 256K
        },
        "mimo-v2.5": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1000000,  # 1M
            "max_output_tokens": 128000,  # 128K
        },
        "mimo-v2.5-pro": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1048576,  # 1M
            "max_output_tokens": 128000,  # 128K
        },
        "mimo-v2.6-flash": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1048576,  # 1M
            "max_output_tokens": 131072,  # 128K
        },
        "mimo-v2.6-pro": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1048576,  # 1M
            "max_output_tokens": 131072,  # 128K
        },
        "minimax-m3": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1000000,  # 1M
            "max_output_tokens": 131072,  # 128K
        },
        "minimax-m3.1-flash": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1000000,  # 1M
            "max_output_tokens": 512000,  # 512K
            "supported_reasoning_efforts": [
                {"effort": "low", "description": "Lighter reasoning for fast responses"},
                {"effort": "medium", "description": "Standard reasoning depth"},
                {"effort": "high", "description": "Deeper reasoning"},
                {"effort": "xhigh", "description": "Extra-high reasoning depth"},
                {"effort": "max", "description": "Maximum reasoning depth for complex problems"},
            ],
        },
        "muse-spark-1.2-contributor": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1048576,  # 1M
            "max_output_tokens": 131072,  # 128K
            "supported_reasoning_efforts": [
                {"effort": "minimal", "description": "Minimal reasoning"},
                {"effort": "low", "description": "Lighter reasoning for fast responses"},
                {"effort": "medium", "description": "Standard reasoning depth"},
                {"effort": "high", "description": "Deeper reasoning"},
                {"effort": "xhigh", "description": "Extra-high reasoning depth"},
            ],
        },
        "muse-spark-1.3-contributor": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1048576,  # 1M
            "max_output_tokens": 131072,  # 128K
            "supported_reasoning_efforts": [
                {"effort": "minimal", "description": "Minimal reasoning"},
                {"effort": "low", "description": "Lighter reasoning for fast responses"},
                {"effort": "medium", "description": "Standard reasoning depth"},
                {"effort": "high", "description": "Deeper reasoning"},
                {"effort": "xhigh", "description": "Extra-high reasoning depth"},
            ],
        },
        "qwen3.7-plus": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1000000,  # 1M
            "max_output_tokens": 65536,  # 64K
        },
        "qwen3.8-flash": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1000000,  # 1M
            "max_output_tokens": 131072,  # 128K
            "supported_reasoning_efforts": [
                {"effort": "low", "description": "Lighter reasoning for fast responses"},
                {"effort": "medium", "description": "Standard reasoning depth"},
                {"effort": "xhigh", "description": "Extra-high reasoning depth"},
            ],
        },
        "qwen3.8-max": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1000000,  # 1M
            "max_output_tokens": 131072,  # 128K
            "supported_reasoning_efforts": [
                {"effort": "low", "description": "Lighter reasoning for fast responses"},
                {"effort": "medium", "description": "Standard reasoning depth"},
                {"effort": "xhigh", "description": "Extra-high reasoning depth"},
            ],
        },
        "step-5-preview": {
            "supported_api_types": ["Completions"],
            "default_api_type": "Completions",
            "max_input_tokens": 1000000,  # 1M
            "max_output_tokens": 65536,  # 64K
            "supported_reasoning_efforts": [
                {"effort": "low", "description": "Lighter reasoning for fast responses"},
                {"effort": "medium", "description": "Standard reasoning depth"},
                {"effort": "high", "description": "Deeper reasoning"},
            ],
        },
    },
}
