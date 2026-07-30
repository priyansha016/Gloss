from app.services.verifier import (
    MAX_SECTION_REPAIRS,
    Finding,
    _describe,
    find_coverage_gaps,
    find_overview_issues,
    find_section_issues,
    mermaid_lint,
    transcript_looks_cli,
)


def good_section() -> dict:
    return {
        "headline": "h",
        "explainer": "A real explanation.",
        "key_points": ["point"],
        "walkthrough": [],
        "diagram": "graph TB; A[Client]-->|calls| B[Server]",
    }


class TestMermaidLint:
    def test_valid_diagram_passes(self):
        assert mermaid_lint("graph TB; A[Client]-->|calls| B[Server]") is None

    def test_empty_is_fine(self):
        assert mermaid_lint("") is None

    def test_unbalanced_brackets_flagged(self):
        assert "unbalanced" in mermaid_lint("graph TB; A[Client-->|calls| B[Server]")

    def test_edgeless_diagram_flagged(self):
        assert "no edges" in mermaid_lint("graph TB; JustOneNode")


class TestSectionIssues:
    def test_clean_content_no_findings(self):
        assert find_section_issues([good_section()]) == []

    def test_missing_explainer_flagged(self):
        bad = {**good_section(), "explainer": ""}
        findings = find_section_issues([bad])
        assert any(f.field == "explainer" for f in findings)

    def test_transcript_blob_keypoint_flagged(self):
        # Regression: fallback on unpunctuated auto-captions produced one 4.6k-char
        # "key point" (the raw transcript) that rendered as a wall of text.
        bad = {**good_section(), "key_points": ["word " * 200]}
        findings = find_section_issues([bad])
        assert any(f.field == "key_points" and "raw transcript" in f.problem for f in findings)

    def test_normal_length_keypoints_ok(self):
        ok = {**good_section(), "key_points": ["A perfectly reasonable takeaway about pooling." * 2]}
        assert not any(f.field == "key_points" for f in find_section_issues([ok]))

    def test_broken_diagram_flagged_with_index(self):
        bad = {**good_section(), "diagram": "graph TB; A[x-->B"}
        findings = find_section_issues([good_section(), bad])
        diagram = [f for f in findings if f.field == "diagram"]
        assert diagram and diagram[0].section_idx == 1


class TestOverviewIssues:
    def test_cli_video_without_commands_flagged(self):
        transcript = "run kubectl get all then kubectl describe pod then minikube start"
        findings = find_overview_issues({"summary": ["x"], "commands": []}, "teaches things", transcript)
        assert any(f.field == "commands" for f in findings)

    def test_non_cli_video_without_commands_ok(self):
        findings = find_overview_issues(
            {"summary": ["x"], "commands": []}, "teaches things", "a philosophy lecture about ethics"
        )
        assert not any(f.field == "commands" for f in findings)

    def test_empty_teaches_flagged(self):
        findings = find_overview_issues({"summary": ["x"], "commands": []}, "", "text")
        assert any(f.field == "teaches" for f in findings)


class TestCoverageGaps:
    # Regression: the CNN video's 12:00-18:00 section taught ReLU + the full
    # conv→ReLU→pool→dense architecture; the notes only covered pooling.
    RELU_TRANSCRIPT = (
        "you are capturing the main feature and filtering the noise. this is how a complete "
        "convolutional neural network looks like: you will have a convolution and ReLU layer "
        "then you'll have pooling, then another convolution and pooling, and in the end a "
        "fully connected dense neural network. the activation decides what fires. the "
        "activation is applied after each convolution. activation functions matter."
    )

    def test_named_concept_taught_but_missing_is_flagged(self):
        notes = {
            "headline": "Feature extraction with pooling",
            "explainer": "Pooling reduces the feature map size.",
            "key_points": ["Convolutional layers apply filters", "Max pooling captures key features"],
            "walkthrough": [],
        }
        missed = find_coverage_gaps(self.RELU_TRANSCRIPT, notes)
        assert any("relu" in m.lower() for m in missed)

    def test_concept_present_in_notes_not_flagged(self):
        notes = {
            "headline": "The full CNN stack",
            "explainer": "Convolution and ReLU layers alternate with pooling, ending in a dense network. The activation decides what fires.",
            "key_points": ["ReLU activation follows each convolution"],
            "walkthrough": [],
        }
        missed = find_coverage_gaps(self.RELU_TRANSCRIPT, notes)
        assert not any("relu" in m.lower() for m in missed)

    def test_empty_transcript_no_gaps(self):
        assert find_coverage_gaps("", {"headline": "x", "key_points": []}) == []

    def test_single_mention_of_plain_word_not_flagged(self):
        transcript = "we briefly note that gradient exists. now back to arrays for the rest: arrays arrays arrays."
        notes = {"headline": "Arrays", "explainer": "All about arrays", "key_points": ["arrays"], "walkthrough": []}
        missed = find_coverage_gaps(transcript, notes)
        assert not any("gradient" in m.lower() for m in missed)


class TestHelpers:
    def test_cli_detection_threshold(self):
        assert transcript_looks_cli("kubectl a kubectl b docker c")
        assert not transcript_looks_cli("kubectl mentioned once")

    def test_describe_targets(self):
        assert _describe(Finding(3, "diagram", "bad")) == "section 3/diagram: bad"
        assert _describe(Finding(-1, "teaches", "empty")) == "overview/teaches: empty"

    def test_sections_beyond_repair_cap_surface_as_unresolved(self):
        by_section = {
            i: [Finding(i, "explainer", f"weak section {i}")]
            for i in range(MAX_SECTION_REPAIRS + 2)
        }
        skipped = list(by_section.items())[MAX_SECTION_REPAIRS:]
        unresolved = [_describe(f) for _, fs in skipped for f in fs]
        assert len(unresolved) == 2
        assert "section 6/explainer" in unresolved[0]
        assert "section 7/explainer" in unresolved[1]
