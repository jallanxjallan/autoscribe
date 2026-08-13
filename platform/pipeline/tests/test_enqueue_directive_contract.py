from asc.enqueue.reader import _optional_directive


def test_directive_is_read_from_enqueue_ndjson_record():
    assert _optional_directive({"directive": "  Keep the ending.  "}, 1) == "Keep the ending."


def test_missing_or_blank_directive_is_absent():
    assert _optional_directive({}, 1) is None
    assert _optional_directive({"directive": "  "}, 1) is None


def test_non_string_directive_is_rejected():
    try:
        _optional_directive({"directive": ["invalid"]}, 7)
    except TypeError as exc:
        assert str(exc) == "row 7 field directive must be a string or null"
    else:
        raise AssertionError("non-string directive was accepted")
