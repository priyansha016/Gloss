from app.services.captions import CaptionSegment
from app.services.gatekeeper import ACCEPT_CATEGORIES, music_heuristic
from app.services.llm import _as_bool, _as_str


def seg(i: int, text: str) -> CaptionSegment:
    return CaptionSegment(start_s=i * 5.0, end_s=i * 5.0 + 5.0, text=text)


class TestMusicHeuristic:
    def test_music_marker_video_rejected(self):
        segments = [seg(i, "[Music]") for i in range(8)] + [seg(9, "yeah"), seg(10, "oh baby")]
        verdict = music_heuristic(segments, duration_s=240)
        assert verdict is not None and not verdict.suitable
        assert verdict.category == "music"

    def test_sparse_speech_rejected(self):
        # 20 short segments over a 30-minute video → way below teaching wpm
        segments = [seg(i, "hello world") for i in range(20)]
        verdict = music_heuristic(segments, duration_s=1800)
        assert verdict is not None and not verdict.suitable
        assert verdict.category == "low_speech"

    def test_dense_lecture_inconclusive(self):
        # ~150 wpm over 10 minutes → clearly speech; heuristic defers to the LLM
        words = "in this lecture we will study how the model learns from data step by step"
        segments = [seg(i, words) for i in range(100)]  # 100 * 15 words / 10 min = 150 wpm
        assert music_heuristic(segments, duration_s=600) is None

    def test_empty_segments_inconclusive(self):
        assert music_heuristic([], duration_s=600) is None

    def test_short_video_skips_wpm_check(self):
        segments = [seg(0, "hi")]
        assert music_heuristic(segments, duration_s=60) is None


class TestClassifySuitableParsing:
    def test_string_false_not_accepted(self):
        data = {"category": "tutorial", "suitable": "false"}
        category = _as_str(data.get("category")).lower() or "other"
        suitable = _as_bool(data.get("suitable")) and category in ACCEPT_CATEGORIES
        assert not suitable

    def test_string_true_with_accept_category(self):
        data = {"category": "lecture", "suitable": "true"}
        category = _as_str(data.get("category")).lower() or "other"
        suitable = _as_bool(data.get("suitable")) and category in ACCEPT_CATEGORIES
        assert suitable
