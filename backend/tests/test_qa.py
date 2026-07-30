"""Tests for the Ask retrieval layer (lexical scoring + excerpting)."""

from app.models import Section
from app.services.qa import _score_sections, _tokens, _transcript_excerpt


def make_section(idx: int, title: str, summary: str = "", key_points: list[str] | None = None) -> Section:
    return Section(
        idx=idx,
        title=title,
        start_s=idx * 100.0,
        end_s=(idx + 1) * 100.0,
        summary_short=summary,
        content={"explainer": "", "key_points": key_points or []},
    )


class TestTokens:
    def test_stopwords_removed(self):
        assert "the" not in _tokens("what is the pod")

    def test_keeps_technical_words(self):
        assert {"pod", "kubernetes"} <= _tokens("What is a Pod in Kubernetes?")


class TestScoreSections:
    def test_matching_section_ranks_first(self):
        sections = [
            make_section(0, "Intro", "welcome to the course"),
            make_section(1, "ConfigMap & Secret", "external configuration", ["ConfigMap stores URLs"]),
            make_section(2, "Volumes", "persistent storage"),
        ]
        top = _score_sections("what is a configmap used for?", sections)
        assert top[0].title == "ConfigMap & Secret"

    def test_no_match_falls_back_to_first_sections(self):
        sections = [make_section(i, f"Part {i}") for i in range(5)]
        top = _score_sections("quantum entanglement", sections)
        assert len(top) == 3
        assert top[0].idx == 0


class TestTranscriptExcerpt:
    def test_only_in_range_segments(self):
        segments = [
            {"start_s": 0, "end_s": 10, "text": "alpha"},
            {"start_s": 50, "end_s": 60, "text": "bravo"},
            {"start_s": 200, "end_s": 210, "text": "charlie"},
        ]
        excerpt = _transcript_excerpt(segments, 0, 100)
        assert "alpha" in excerpt and "bravo" in excerpt
        assert "charlie" not in excerpt
