"""Test prompt definitions for exercising whyllm observability."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TestPrompt:
    name: str
    system: str
    user: str
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 2048


PROMPTS: list[TestPrompt] = [
    TestPrompt(
        name="summarise",
        system="You are a concise summariser.",
        user="Summarise the benefits of LLM observability in two sentences.",
    ),
    TestPrompt(
        name="translate",
        system="You are a translator. Reply only with the translation.",
        user="Translate to French: 'Monitoring large language models is essential for production reliability.'",
    ),
    TestPrompt(
        name="classify",
        system="Classify the sentiment as positive, negative, or neutral. Reply with one word.",
        user="Our LLM pipeline has been running flawlessly for three months straight.",
    ),
    TestPrompt(
        name="code_gen",
        system="You are a Python expert. Reply with only code, no explanation.",
        user="Write a function that calculates the cost of an LLM call given input_tokens, output_tokens, and price_per_1k_tokens.",
        max_tokens=4096,
    ),
    TestPrompt(
        name="creative",
        system="You are a creative writer.",
        user="Write a haiku about debugging a language model in production.",
        temperature=1.0,
        max_tokens=1024,
    ),
]

PROMPT_MAP: dict[str, TestPrompt] = {p.name: p for p in PROMPTS}
