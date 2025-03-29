"""
Predefined parameter profiles for Janito.
"""
from typing import Dict, Any

# Predefined parameter profiles
PROFILES = {
    "precise": {
        "temperature": 0.2,
        "top_p": 0.85,
        "top_k": 20,
        "description": "Factual answers, documentation, structured data, avoiding hallucinations"
    },
    "balanced": {
        "temperature": 0.5,
        "top_p": 0.9,
        "top_k": 40,
        "description": "Professional writing, summarization, everyday tasks with moderate creativity"
    },
    "conversational": {
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 45,
        "description": "Natural dialogue, educational content, support conversations"
    },
    "creative": {
        "temperature": 0.9,
        "top_p": 0.95,
        "top_k": 70,
        "description": "Storytelling, brainstorming, marketing copy, poetry"
    },
    "technical": {
        "temperature": 0.3,
        "top_p": 0.95,
        "top_k": 15,
        "description": "Code generation, debugging, decision analysis, technical problem-solving"
    }
}