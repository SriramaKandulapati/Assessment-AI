from app.shortener import ShortenerError, create_link, link_analytics, resolve_link


def test_create_resolve_and_aggregate_clicks(client):
    link = create_link("https://example.com/path", "sample")
    assert link["code"] == "sample"
    assert resolve_link("sample") == "https://example.com/path"
    assert resolve_link("sample") == "https://example.com/path"
    assert link_analytics("sample")["total_clicks"] == 2


def test_rejects_non_http_and_duplicate_alias(client):
    try:
        create_link("file:///etc/passwd")
        assert False, "unsafe scheme should be rejected"
    except ShortenerError as exc:
        assert exc.code == "invalid_url"
    create_link("https://example.com", "same")
    try:
        create_link("https://example.org", "same")
        assert False, "duplicate alias should be rejected"
    except ShortenerError as exc:
        assert exc.code == "alias_taken"
