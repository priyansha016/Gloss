from app.services.embeddings import extract_candidate_terms, normalize_term
from app.services.glossary import extract_chapter_terms, is_term_relevant_in_section


class TestNormalizeTerm:
    def test_lowercases_and_strips(self):
        assert normalize_term("ReLU") == "relu"
        assert normalize_term("Config Map!") == "configmap"


class TestChapterTerms:
    def test_splits_and_dedupes(self):
        terms = extract_chapter_terms(["Service & Ingress", "Ingress deep-dive"])
        lowered = [t.lower() for t in terms]
        assert "service" in lowered and "ingress" in lowered
        assert lowered.count("ingress") == 1

    def test_preserves_acronym_case(self):
        assert "CNN" in extract_chapter_terms(["CNN basics"])


class TestSectionRelevance:
    def test_title_mention_is_relevant(self):
        assert is_term_relevant_in_section(
            "Ingress", section_title="Service & Ingress", section_summary="", section_text=""
        )

    def test_ambiguous_term_needs_title_or_summary(self):
        # "Service" is generic English — a raw transcript hit alone must NOT link it.
        assert not is_term_relevant_in_section(
            "Service", section_title="Intro", section_summary="", section_text="we provide a service"
        )

    def test_specific_term_ok_from_transcript(self):
        assert is_term_relevant_in_section(
            "kubectl", section_title="Demo", section_summary="", section_text="run kubectl get all"
        )


class TestCandidateExtraction:
    def test_finds_acronyms_and_camelcase(self):
        text = "We use YAML files and a ConfigMap. YAML is everywhere. kubectl applies YAML."
        candidates = [c.lower() for c in extract_candidate_terms(text)]
        assert "yaml" in candidates
        assert "configmap" in candidates
