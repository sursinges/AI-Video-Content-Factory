import pytest
from core.script_cleaner import clean_script_text, parse_subtitles_file


def test_clean_timestamp_ranges():
    raw = "01:15-01:45 В древнем городе наступила тихая ночь.\n02:00 - 02:30 [01:15 - 01:45] Жители засыпали."
    cleaned = clean_script_text(raw)
    assert "01:15" not in cleaned
    assert "01:45" not in cleaned
    assert "02:00" not in cleaned
    assert "02:30" not in cleaned
    assert "В древнем городе наступила тихая ночь." in cleaned
    assert "Жители засыпали." in cleaned


def test_clean_single_timestamps():
    raw = "[01:15] Когда луна взошла над башнями (02:45), всё стихло. 12:30 Город погрузился в сон."
    cleaned = clean_script_text(raw)
    assert "[01:15]" not in cleaned
    assert "(02:45)" not in cleaned
    assert "12:30" not in cleaned
    assert "Когда луна взошла над башнями, всё стихло." in cleaned
    assert "Город погрузился в сон." in cleaned


def test_clean_speaker_and_cues():
    raw = """
    Диктор 1: Приветствуем всех.
    [Музыка]
    Голос за кадром: За стенами замка было тихо.
    (смех)
    Спикер: Вдали мерцали факелы.
    """
    cleaned = clean_script_text(raw)
    assert "Диктор 1:" not in cleaned
    assert "[Музыка]" not in cleaned
    assert "Голос за кадром:" not in cleaned
    assert "(смех)" not in cleaned
    assert "Спикер:" not in cleaned
    assert "Приветствуем всех." in cleaned
    assert "За стенами замка было тихо." in cleaned
    assert "Вдали мерцали факелы." in cleaned


def test_clean_srt_format():
    srt = """
    1
    00:00:01,000 --> 00:00:04,500
    Добро пожаловать в историю.

    2
    00:00:05,000 --> 00:00:09,000
    Мы отправляемся в Римскую империю.
    """
    cleaned = parse_subtitles_file(srt)
    assert "-->" not in cleaned
    assert "00:00:01" not in cleaned
    assert "Добро пожаловать в историю. Мы отправляемся в Римскую империю." == cleaned.strip()


def test_empty_or_none():
    assert clean_script_text("") == ""
    assert clean_script_text(None) == ""
