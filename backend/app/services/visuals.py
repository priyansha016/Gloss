"""Visual designer: purpose-built illustrations for the hardest sections.

Some sections describe a MECHANISM that words alone explain poorly — convolution
arithmetic, backprop through a graph, a request routed through a cluster. A generic
flowchart doesn't cut it there.

Two-step agent, run after the verifier (content is stable):
1. Triage (one call): which sections teach a mechanism a reader would struggle to
   picture? Returns at most MAX_VISUALS sections with a one-line brief of what to show.
2. Designer (one call per flagged section): build a step-by-step visual walkthrough —
   each step a caption plus KaTeX math (real matrices/numbers) and/or a small Mermaid
   diagram. Steps are validated; invalid diagrams are dropped rather than shipped.

Grounding: a tiny concrete example (e.g. a 3×3 patch with real numbers) is allowed —
and encouraged — but it must faithfully implement the mechanism the transcript teaches,
never introduce claims beyond it.
"""

import asyncio

from app.config import get_settings
from app.services.llm import _as_list, _as_str, _clean_mermaid, chat_json
from app.services.llm_context import llm_available
from app.services.verifier import mermaid_lint

MAX_VISUALS = 4
MAX_STEPS = 6


def coerce_visual(data: dict) -> dict | None:
    """Validate/clean a designer response into {focus, steps[]} or None if unusable."""
    steps: list[dict] = []
    for step in _as_list(data.get("steps"))[:MAX_STEPS]:
        if not isinstance(step, dict):
            continue
        caption = _as_str(step.get("caption"))
        math = _as_str(step.get("math"))
        diagram = _clean_mermaid(_as_str(step.get("diagram")))
        if diagram and mermaid_lint(diagram):
            diagram = ""  # invalid diagram: keep the step, drop the drawing
        if caption and (math or diagram or len(caption) > 30):
            steps.append({"caption": caption, "math": math, "diagram": diagram})
    if not any(s["math"] or s["diagram"] for s in steps):
        return None  # captions alone add nothing over key points
    return {"focus": _as_str(data.get("focus")), "steps": steps}


async def triage_complex_sections(
    title: str | None,
    section_defs: list[dict],
    section_contents: list[dict],
) -> list[tuple[int, str]]:
    """One call: pick the sections whose mechanism genuinely needs a visual. [(idx, brief)]"""
    if not llm_available() or not section_contents:
        return []

    digest = "\n".join(
        f'{d["idx"]}. {d["title"]}: {c.get("headline", "")} — {"; ".join(c.get("key_points", [])[:3])}'
        for d, c in zip(section_defs, section_contents)
    )
    prompt = f"""Video: {title or "Untitled"}

Sections:
{digest}

Which sections teach a MECHANISM or PROCESS that a beginner would struggle to picture from
text alone — e.g. sliding-window arithmetic, gradients flowing through a graph, a request
routed across components, memory layouts, geometric transformations?

Return JSON: {{"sections": [{{"idx": <index>, "brief": "one line: exactly what to visualize"}}]}}
Pick AT MOST {MAX_VISUALS}, hardest first. Return {{"sections": []}} if none truly need it.
Do NOT pick sections that are introductions, recaps, or lists of facts."""

    data = await chat_json(
        "You decide which study-note sections need a purpose-built visual. Respond with valid JSON only.",
        prompt,
        # Reasoning models (gpt-oss) spend hidden thinking tokens from this same budget
        # BEFORE emitting JSON — a tight cap truncates the JSON and reads as "no picks".
        max_tokens=1400,
    )
    picked: list[tuple[int, str]] = []
    for item in _as_list(data.get("sections"))[:MAX_VISUALS]:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("idx", -1))
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(section_contents):
            picked.append((idx, _as_str(item.get("brief"))))
    return picked


async def design_visual(
    title: str | None,
    section_title: str,
    brief: str,
    transcript: str,
) -> dict | None:
    """Design one section's visual walkthrough (steps of caption + math + diagram)."""
    prompt = f"""Video: {title or "Untitled"}
Section: {section_title}
What to visualize: {brief or "the core mechanism of this section"}

Section transcript:
{transcript[:8000]}

Design a SHORT visual walkthrough (2-{MAX_STEPS} steps) that lets a beginner SEE the mechanism.
Return JSON:
{{
  "focus": "3-6 word label of what is being visualized",
  "steps": [{{
    "caption": "one sentence: what this step shows",
    "math": "LaTeX WITHOUT $ delimiters — use real small numbers and matrices (pmatrix) to show the actual arithmetic, or empty",
    "diagram": "small Mermaid diagram (flowchart/graph with labelled edges) if spatial/flow, or empty"
  }}]
}}

Rules:
- Implement the EXACT mechanism the transcript teaches. A tiny concrete example with real
  numbers is encouraged (e.g. an actual 3×3 patch ⊙ filter = value), but never contradict
  or go beyond what the video explains.
- Each step must have math OR a diagram — captions alone are not a visual.
- Prefer LaTeX matrices for arithmetic (\\begin{{pmatrix}}...\\end{{pmatrix}}), Mermaid for flow/structure.
- Keep every diagram under ~8 nodes; label edges with what happens."""

    data = await chat_json(
        "You design step-by-step visual explanations with concrete numbers. Respond with valid JSON only.",
        prompt,
        max_tokens=1600,
    )
    return coerce_visual(data)


async def add_visuals(
    title: str | None,
    section_defs: list[dict],
    section_inputs: list[tuple[str, str]],
    section_contents: list[dict],
) -> tuple[list[dict], list[str]]:
    """Triage + design; returns (section_contents with `visual` set, unresolved notes).

    Visuals are an enhancement — failures never break the pipeline — but they must be
    VISIBLE in the quality report, not silently absent (learned when a quota 429 made
    the whole stage vanish without a trace).
    """
    settings = get_settings()
    if not llm_available():
        return section_contents, []

    unresolved: list[str] = []
    try:
        picked = await triage_complex_sections(title, section_defs, section_contents)
        if not picked:
            # Empty is ambiguous: legit for fact-list videos, but also what a JSON parse
            # miss looks like (reasoning models sometimes bury the JSON). One retry.
            picked = await triage_complex_sections(title, section_defs, section_contents)
    except Exception as exc:
        return section_contents, [f"visuals/triage failed: {str(exc)[:120]}"]
    if not picked:
        return section_contents, ["visuals: triage selected no sections"]

    sem = asyncio.Semaphore(max(1, settings.llm_concurrency))
    enriched = list(section_contents)

    async def run_one(idx: int, brief: str) -> None:
        _, text = section_inputs[idx]
        try:
            async with sem:
                visual = await design_visual(title, section_defs[idx]["title"], brief, text)
        except Exception as exc:
            unresolved.append(f"section {idx}/visual failed: {str(exc)[:120]}")
            return
        if visual:
            enriched[idx] = {**enriched[idx], "visual": visual}
        else:
            unresolved.append(f"section {idx}/visual: designer output unusable, skipped")

    await asyncio.gather(*[run_one(idx, brief) for idx, brief in picked])
    return enriched, unresolved
