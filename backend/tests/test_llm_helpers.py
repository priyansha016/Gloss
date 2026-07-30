"""Pure-function tests for llm.py — the coercion/sanitization layer that broke silently before."""

from app.services.llm import (
    _as_bool,
    _as_list,
    _as_str,
    _clean_mermaid,
    _loads_lenient,
    _transcript_windows,
    _ts,
    build_document_overview,
    key_points_to_text,
    nav_to_tldr_text,
)


class TestLoadsLenient:
    def test_plain_json(self):
        assert _loads_lenient('{"a": 1}') == {"a": 1}

    def test_fenced_json(self):
        assert _loads_lenient('```json\n{"a": 1}\n```') == {"a": 1}

    def test_prose_wrapped_json(self):
        assert _loads_lenient('Here you go: {"a": 1} hope that helps!') == {"a": 1}

    def test_garbage_returns_empty(self):
        assert _loads_lenient("total nonsense") == {}

    def test_json_array_returns_empty_dict(self):
        assert _loads_lenient("[1, 2, 3]") == {}


class TestCoercion:
    def test_as_str_none(self):
        assert _as_str(None) == ""

    def test_as_str_number(self):
        assert _as_str(42) == "42"

    def test_as_str_list_rejected(self):
        assert _as_str(["a"]) == ""

    def test_as_list_passthrough(self):
        assert _as_list([1, 2]) == [1, 2]

    def test_as_list_wraps_scalar(self):
        assert _as_list("x") == ["x"]

    def test_as_list_empty_for_none(self):
        assert _as_list(None) == []

    def test_as_bool_true_values(self):
        assert _as_bool(True) is True
        assert _as_bool("true") is True
        assert _as_bool("TRUE") is True
        assert _as_bool(1) is True

    def test_as_bool_false_values(self):
        assert _as_bool(False) is False
        assert _as_bool("false") is False
        assert _as_bool("no") is False
        assert _as_bool(0) is False
        assert _as_bool(None) is False


class TestCleanMermaid:
    def test_valid_flowchart_kept(self):
        assert _clean_mermaid("flowchart TD; A-->B") == "flowchart TD; A-->B"

    def test_fence_stripped(self):
        assert _clean_mermaid("```mermaid\ngraph TB; A-->B\n```") == "graph TB; A-->B"

    def test_prose_rejected(self):
        assert _clean_mermaid("here is a diagram of A to B") == ""

    def test_empty_rejected(self):
        assert _clean_mermaid("") == ""

    def test_label_pipe_artifact_fixed(self):
        # The `-->|label|>Target` mistake Groq makes — must sanitize, not reject.
        cleaned = _clean_mermaid("graph TB; Node-->|runs|>Kubelet")
        assert "|>" not in cleaned
        assert cleaned.startswith("graph TB")


class TestTranscriptWindows:
    def test_short_text_unchanged(self):
        assert _transcript_windows("short text") == "short text"

    def test_long_text_samples_across(self):
        text = "A" * 10000 + "MIDDLE" + "B" * 10000 + "END-COMMANDS" + "C" * 5000
        windowed = _transcript_windows(text, n=3, size=6000)
        # Late content must be reachable (this was the empty-commands bug).
        assert "C" in windowed
        assert "[...]" in windowed
        assert len(windowed) < len(text)


class TestDocOverview:
    def test_timestamp_format(self):
        assert _ts(65) == "1:05"
        assert _ts(3700) == "1:01:40"

    def test_overview_and_tldr(self):
        outline = {"teaches": "X", "prerequisites": ["p"]}
        defs = [{"idx": 0, "title": "Intro", "start_s": 0.0}]
        ov = build_document_overview(outline, defs, ["Sets it up"])
        assert ov["nav"] == [{"t": 0.0, "label": "Intro", "one_liner": "Sets it up"}]
        assert nav_to_tldr_text(ov["nav"]) == "- [0:00] Intro: Sets it up"

    def test_key_points_to_text(self):
        assert key_points_to_text(["a", "b"]) == "- a\n- b"
