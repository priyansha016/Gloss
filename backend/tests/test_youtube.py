from app.services.youtube import extract_youtube_id


def test_watch_url():
    assert extract_youtube_id("https://www.youtube.com/watch?v=s_o8dwzRlu4") == "s_o8dwzRlu4"


def test_short_url():
    assert extract_youtube_id("https://youtu.be/s_o8dwzRlu4") == "s_o8dwzRlu4"


def test_embed_url():
    assert extract_youtube_id("https://www.youtube.com/embed/s_o8dwzRlu4") == "s_o8dwzRlu4"


def test_shorts_url():
    assert extract_youtube_id("https://youtube.com/shorts/s_o8dwzRlu4") == "s_o8dwzRlu4"


def test_bare_id():
    assert extract_youtube_id("s_o8dwzRlu4") == "s_o8dwzRlu4"


def test_watch_url_with_extra_params():
    assert extract_youtube_id("https://www.youtube.com/watch?v=s_o8dwzRlu4&t=120s") == "s_o8dwzRlu4"


def test_invalid_url():
    assert extract_youtube_id("https://example.com/watch?v=nope") is None


def test_invalid_id_length():
    assert extract_youtube_id("https://youtu.be/tooshort") is None
