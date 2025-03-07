import os

# Try to determine backend from available API keys if not explicitly set
ai_backend = os.getenv('AI_BACKEND', '').lower()

if not ai_backend:
    if os.getenv('ANTHROPIC_API_KEY'):
        ai_backend = 'claudeai'
    elif os.getenv('OPENAI_API_KEY'):
        ai_backend = 'openai'
    elif os.getenv('GROQ_API_KEY'):
        ai_backend = 'groqcloud'
    else:
        raise ValueError("No AI backend API keys found. Please set either ANTHROPIC_API_KEY, OPENAI_API_KEY, or GROQ_API_KEY")

if ai_backend == "openai":
    from .openai import OpenAIAgent as AIAgent
elif ai_backend == 'claudeai':
    from .claudeai import ClaudeAIAgent as AIAgent
elif ai_backend == 'groqcloud':
    from .groqcloud import GroqCloudAgent as AIAgent
else:
    raise ValueError(f"Unsupported AI_BACKEND: {ai_backend}")

# Create a singleton instance
agent = AIAgent()