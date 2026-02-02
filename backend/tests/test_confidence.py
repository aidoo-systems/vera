from app.services.confidence import classify_confidence, detect_forced_flags


def test_confidence_thresholds():
    assert classify_confidence(0.95) == "trusted"
    assert classify_confidence(0.90) == "medium"
    assert classify_confidence(0.75) == "low"


def test_forced_flags_currency():
    flags = detect_forced_flags("£24.60")
    assert "currency_amount" in flags


def test_forced_flags_date():
    flags = detect_forced_flags("31/01/2026")
    assert "date" in flags


def test_forced_flags_total_keyword():
    flags = detect_forced_flags("Total")
    assert "total_keyword" in flags
