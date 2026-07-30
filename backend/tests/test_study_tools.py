from app.services.study_tools import coerce_flashcards, coerce_quiz


class TestCoerceFlashcards:
    def test_valid_cards(self):
        cards = coerce_flashcards({"cards": [{"front": "What is a Pod?", "back": "The smallest deployable unit."}]})
        assert cards == [{"front": "What is a Pod?", "back": "The smallest deployable unit."}]

    def test_incomplete_cards_dropped(self):
        cards = coerce_flashcards({"cards": [{"front": "x", "back": ""}, {"front": "", "back": "y"}, "junk"]})
        assert cards == []

    def test_caps_at_max(self):
        cards = coerce_flashcards({"cards": [{"front": f"q{i}", "back": f"a{i}"} for i in range(30)]})
        assert len(cards) == 16


class TestCoerceQuiz:
    def _q(self, **over):
        base = {"question": "Why pool?", "options": ["a", "b", "c", "d"], "answer": 2, "explanation": "because"}
        base.update(over)
        return base

    def test_valid_question(self):
        qs = coerce_quiz({"questions": [self._q()]})
        assert len(qs) == 1 and qs[0]["answer"] == 2

    def test_wrong_option_count_dropped(self):
        assert coerce_quiz({"questions": [self._q(options=["a", "b"])]}) == []

    def test_out_of_range_answer_dropped(self):
        assert coerce_quiz({"questions": [self._q(answer=7)]}) == []
        assert coerce_quiz({"questions": [self._q(answer="not a number")]}) == []

    def test_garbage_survives(self):
        assert coerce_quiz({}) == []
        assert coerce_quiz({"questions": ["nope", 3]}) == []
