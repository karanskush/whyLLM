"""HallucinationScorer — fast, stateless heuristic hallucination detection.

Design:
  - Pure Python, zero external calls, zero I/O.
  - Must complete in < 10ms on any reasonable response length.
  - 5 independent heuristics, each scoring 0.0–1.0.
  - Weighted average → final score 0.00–1.00 (Decimal, 2dp).
  - A heuristic "fires" (appears in flags) if its individual score > 0.3.
  - Never raises — returns (Decimal("0.00"), {}) on any error.

Heuristics:
  1. token_repetition       — trigram duplication ratio
  2. hedge_confident_mismatch — hedge phrases vs confident assertions
  3. overconfident_language  — absolute-claim word density
  4. unknown_entity_density  — mid-sentence capitalized word ratio
  5. length_anomaly          — unusually short/long relative to input

Usage:
    scorer = HallucinationScorer()
    score, flags = scorer.score(response_dict, request_dict, input_tokens=150)
"""

from __future__ import annotations

import re
import logging
from collections import Counter
from decimal import Decimal
from typing import Any, Optional

log = logging.getLogger(__name__)

# ── Heuristic weights ─────────────────────────────────────────────────────────
_WEIGHTS = {
    "token_repetition": 0.25,
    "hedge_confident_mismatch": 0.20,
    "overconfident_language": 0.20,
    "unknown_entity_density": 0.20,
    "length_anomaly": 0.15,
}

# Score threshold for a heuristic to "fire" and appear in flags
_FLAG_THRESHOLD = 0.3

# ── Word / phrase lists ───────────────────────────────────────────────────────
_HEDGE_PHRASES = {
    "i think", "i believe", "i'm not sure", "i am not sure",
    "possibly", "might be", "might ", "may be", "perhaps",
    "probably", "i cannot confirm", "it seems", "it appears",
    "i'm not certain", "i am not certain", "i'm not 100%",
    "not sure", "could be", "uncertain", "supposedly",
}

_OVERCONFIDENT_WORDS = {
    "definitely", "certainly", "absolutely", "guaranteed", "100%",
    "always", "never", "impossible", "undoubtedly", "unquestionably",
    "without doubt", "without a doubt", "for sure", "no doubt",
    "obviously", "clearly", "undeniably", "indisputably",
}

# Sentence-ending punctuation for splitting
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _extract_response_text(response: dict[str, Any]) -> str:
    """Extract plain text from OpenAI or Anthropic response dict."""
    # OpenAI format: choices[0].message.content
    choices = response.get("choices")
    if choices and isinstance(choices, list):
        first = choices[0]
        if isinstance(first, dict):
            msg = first.get("message") or first.get("delta") or {}
            content = msg.get("content")
            if isinstance(content, str):
                return content
            # Tool call only — no text content
            return ""

    # Anthropic format: content[0].text
    content_blocks = response.get("content")
    if content_blocks and isinstance(content_blocks, list):
        texts = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
        if texts:
            return " ".join(texts)

    # Fallback: try response as string
    if isinstance(response, str):
        return response

    return ""


def _tokenize(text: str) -> list[str]:
    """Simple whitespace tokenizer, lowercased."""
    return re.findall(r"\b\w+\b", text.lower())


# ── Heuristic functions ───────────────────────────────────────────────────────

def _token_repetition(text: str) -> float:
    """Trigram duplication ratio — high repetition signals hallucination loops."""
    words = _tokenize(text)
    if len(words) < 6:
        return 0.0

    trigrams = [tuple(words[i:i+3]) for i in range(len(words) - 2)]
    if not trigrams:
        return 0.0

    counts = Counter(trigrams)
    total = len(trigrams)
    # Count trigrams that appear more than once
    repeated = sum(count - 1 for count in counts.values() if count > 1)
    ratio = repeated / total
    # Score scales: 0.3 duplication → ~0.5 score; 0.6 duplication → ~1.0
    return min(1.0, ratio * 1.67)


def _hedge_confident_mismatch(text: str) -> float:
    """Presence of hedge phrases when the overall tone is confident."""
    lower = text.lower()
    words = _tokenize(lower)
    if not words:
        return 0.0

    # Count hedge phrase occurrences
    hedge_count = sum(1 for phrase in _HEDGE_PHRASES if phrase in lower)

    # Count sentences that look like confident factual claims
    # (end in '.', contain numbers or capitalized proper nouns, no hedge)
    sentences = _SENT_SPLIT.split(text.strip())
    confident_sentences = 0
    for sent in sentences:
        sent_lower = sent.lower()
        has_hedge = any(phrase in sent_lower for phrase in _HEDGE_PHRASES)
        has_number = bool(re.search(r"\d", sent))
        has_caps = bool(re.search(r"\b[A-Z][a-z]{2,}", sent[1:]))  # skip first char
        if not has_hedge and (has_number or has_caps) and len(sent.split()) >= 5:
            confident_sentences += 1

    if confident_sentences == 0:
        return 0.0

    # High ratio of hedges relative to confident sentences is suspicious
    ratio = hedge_count / max(1, confident_sentences)
    return min(1.0, ratio * 0.6)


def _overconfident_language(text: str) -> float:
    """Density of absolute-claim words in the response."""
    lower = text.lower()
    words = _tokenize(lower)
    if not words:
        return 0.0

    overconfident_count = sum(1 for word in _OVERCONFIDENT_WORDS if word in lower)
    # Score: 1 hit per 50 words is mildly suspicious; 1 per 20 is high
    density = overconfident_count / (len(words) / 50)
    return min(1.0, density * 0.4)


def _unknown_entity_density(text: str) -> float:
    """Ratio of mid-sentence capitalized words (potential invented entities)."""
    words = _tokenize(text)
    if len(words) < 10:
        return 0.0

    # Find words that are capitalized but not at sentence starts
    sentences = _SENT_SPLIT.split(text.strip())
    mid_cap_count = 0
    for sent in sentences:
        # Skip the first word of the sentence (it's always capitalized)
        inner_words = sent.split()[1:]
        for w in inner_words:
            if w and w[0].isupper() and len(w) > 2 and w.isalpha():
                mid_cap_count += 1

    density = mid_cap_count / len(words)
    # Threshold: > 15% is suspicious (normal English is ~5–10% for proper nouns)
    return min(1.0, max(0.0, (density - 0.15) * 4.0))


def _length_anomaly(
    text: str,
    input_tokens: Optional[int] = None,
) -> float:
    """Flag responses that are suspiciously short or excessively long."""
    words = text.split()
    word_count = len(words)

    if word_count < 5:
        # Extremely short (probably an error or truncation)
        return 0.6

    if word_count < 15:
        # Short but possible (e.g. "yes", "no", one-liners)
        return 0.2

    if word_count > 2000:
        # Very long response — suspicious if prompt was short
        if input_tokens is not None and input_tokens < 50:
            return 0.5
        return 0.2

    if word_count > 3000:
        return 0.35

    return 0.0


# ── Main scorer class ─────────────────────────────────────────────────────────

class HallucinationScorer:
    """Stateless hallucination heuristic scorer.

    Thread-safe: no instance state — create once, call concurrently.
    """

    def score(
        self,
        response: dict[str, Any],
        request: Optional[dict[str, Any]] = None,
        input_tokens: Optional[int] = None,
    ) -> tuple[Decimal, dict[str, Any]]:
        """Score a response for potential hallucination signals.

        Returns:
            (score, flags) — score is Decimal 0.00–1.00, flags is a dict
            mapping heuristic name → individual score (only fired heuristics).

        Never raises — returns (Decimal("0.00"), {}) on any internal error.
        """
        try:
            return self._score_internal(response, request, input_tokens)
        except Exception as exc:
            log.debug("HallucinationScorer internal error (returning 0): %s", exc)
            return Decimal("0.00"), {}

    def _score_internal(
        self,
        response: dict[str, Any],
        request: Optional[dict[str, Any]],
        input_tokens: Optional[int],
    ) -> tuple[Decimal, dict[str, Any]]:
        text = _extract_response_text(response)

        if not text or not text.strip():
            return Decimal("0.00"), {}

        # ── Run all 5 heuristics ──────────────────────────────────────────────
        raw_scores: dict[str, float] = {
            "token_repetition": _token_repetition(text),
            "hedge_confident_mismatch": _hedge_confident_mismatch(text),
            "overconfident_language": _overconfident_language(text),
            "unknown_entity_density": _unknown_entity_density(text),
            "length_anomaly": _length_anomaly(text, input_tokens),
        }

        # ── Weighted average ──────────────────────────────────────────────────
        combined = sum(
            raw_scores[name] * weight
            for name, weight in _WEIGHTS.items()
        )
        combined = min(1.0, max(0.0, combined))

        # ── Flags: only heuristics that fired ────────────────────────────────
        flags: dict[str, Any] = {
            name: round(score, 3)
            for name, score in raw_scores.items()
            if score > _FLAG_THRESHOLD
        }

        return Decimal(str(round(combined, 2))), flags
