import logging
import re
from collections import Counter

import httpx

from app.config import get_settings
from app.services.llm import get_llm_client

logger = logging.getLogger(__name__)

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "you", "your", "are", "was", "were",
    "have", "has", "had", "will", "would", "can", "could", "should", "about", "into", "also",
    "just", "like", "when", "what", "how", "why", "who", "where", "then", "than", "them", "they",
    "our", "all", "one", "two", "new", "now", "here", "there", "very", "youtube", "video", "course",
    "tutorial", "learn", "learning", "let", "going", "today", "hello", "welcome", "thanks",
    "music", "going", "thing", "things", "actually", "basically", "really", "mean", "means",
    "kind", "some", "other", "first", "second", "third", "talk", "talking", "look", "see",
    "want", "need", "know", "think", "right", "left", "back", "good", "well", "much", "many",
    "more", "most", "make", "made", "take", "get", "got", "use", "used", "using", "example",
    "examples", "part", "parts", "section", "sections", "start", "end", "little", "bit",
    "which", "because", "create", "mini", "name", "port", "cube", "data", "let", "also",
    "then", "when", "there", "here", "very", "some", "such", "each", "both", "into",
    "these", "those", "would", "could", "should", "about", "being", "been", "being",
    "does", "done", "doing", "work", "works", "working", "called", "call", "every",
}

ACRONYM_RE = re.compile(r"\b[A-Z]{2,}[0-9]*\b")
CAP_WORD_RE = re.compile(r"\b[A-Z][a-z]{2,}\b")
CAP_PHRASE_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")
CAMEL_RE = re.compile(r"\b[a-z]+[A-Z][A-Za-z0-9]+\b")
# PascalCase compounds (ConfigMap, StatefulSet) — CAP_WORD stops at internal capitals
# and CAMEL requires a lowercase start, so without this they were never extracted.
PASCAL_RE = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b")
# Mixed-case terms with interior capital runs (ReLU, ResNET, IPv6-style): not an
# acronym, not PascalCase, not camelCase — every other pattern misses them.
MIXED_ACRONYM_RE = re.compile(r"\b[A-Za-z][a-z0-9]*[A-Z]{2,}[A-Za-z0-9]*\b")
LOWERCASE_WORD_RE = re.compile(r"\b[a-z][a-z0-9-]{3,}\b")
ACRONYM_LOWER_RE = re.compile(r"\b[a-z]*[0-9][a-z0-9-]*\b")


def normalize_term(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _display_form(raw: str) -> str:
    if raw.isupper() or any(ch.isdigit() for ch in raw):
        return raw
    if sum(ch.isupper() for ch in raw) >= 2:
        return raw  # preserve ReLU / ConfigMap-style casing — capitalize() would mangle it
    if " " in raw:
        return raw.title()
    return raw.capitalize()


def extract_candidate_terms(text: str, limit: int = 80) -> list[str]:
    """Heuristic extraction of possible jargon from transcript text."""
    candidates: dict[str, str] = {}
    lower_text = text.lower()

    def add(raw: str) -> None:
        raw = raw.strip()
        if len(raw) < 2 or len(raw) > 64:
            return
        norm = normalize_term(raw)
        if not norm or norm in STOPWORDS or len(norm) < 2:
            return
        if norm not in candidates:
            candidates[norm] = _display_form(raw)

    for pattern in (ACRONYM_RE, CAP_PHRASE_RE, PASCAL_RE, MIXED_ACRONYM_RE, CAP_WORD_RE, CAMEL_RE):
        for match in pattern.finditer(text):
            add(match.group(0))

    for match in ACRONYM_LOWER_RE.finditer(lower_text):
        add(match.group(0))

    word_counts: Counter[str] = Counter()
    for match in LOWERCASE_WORD_RE.finditer(lower_text):
        word = match.group(0)
        if word in STOPWORDS:
            continue
        word_counts[word] += 1

    min_count = 4 if len(lower_text) > 20000 else 2
    for word, count in word_counts.most_common(60):
        if count < min_count:
            break
        add(word)

    ranked = sorted(
        candidates.values(),
        key=lambda term: (-lower_text.count(normalize_term(term)), term),
    )
    return ranked[:limit]


def _validate_dimensions(embedding: list[float] | None) -> list[float] | None:
    """Reject embeddings whose size won't fit the fixed-width `embedding` column.

    The glossary_terms.embedding column is vector(embedding_dimensions). Inserting a
    vector of a different length raises a pgvector error that would kill the whole job.
    Switching embedding models (e.g. Ollama nomic-embed-text=768 → OpenAI
    text-embedding-3-small=1536) changes the size, so guard here and skip instead.
    """
    if not embedding:
        return None
    expected = get_settings().embedding_dimensions
    if len(embedding) != expected:
        logger.warning(
            "Skipping embedding: got %d dims, column expects %d. "
            "Set EMBEDDING_DIMENSIONS to match your embedding model and migrate the column.",
            len(embedding),
            expected,
        )
        return None
    return embedding


async def embed_text(text: str) -> list[float] | None:
    settings = get_settings()
    if not settings.llm_configured:
        return None

    ollama_root = settings.openai_base_url.rstrip("/").removesuffix("/v1")
    payload = {"model": settings.embedding_model, "prompt": text[:2000]}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(f"{ollama_root}/api/embeddings", json=payload)
            response.raise_for_status()
            data = response.json()
            embedding = data.get("embedding")
            if isinstance(embedding, list) and embedding:
                return _validate_dimensions(embedding)
    except Exception:
        pass

    try:
        client = get_llm_client()
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=text[:2000],
        )
        return _validate_dimensions(response.data[0].embedding)
    except Exception:
        return None
