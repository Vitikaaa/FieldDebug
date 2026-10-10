import pytest

import app


def test_build_query_includes_environment_context():
    query = app.build_query("ModuleNotFoundError: pandas", "Python", "Python", "Windows 11", "install package")
    assert '"ModuleNotFoundError: pandas"' in query
    assert "Windows 11" in query
    assert "troubleshooting" in query


def test_parse_search_results_handles_empty_and_malformed():
    assert app.parse_search_results({"organic_results": []}) == []
    assert app.parse_search_results({"organic_results": [{"title": "x"}, None]}) == []
    with pytest.raises(ValueError):
        app.parse_search_results([])


@pytest.mark.parametrize("error,expected", [
    ("ModuleNotFoundError: no module named pandas", "same Python environment"),
    ("SyntaxError: invalid syntax", "line and column"),
    ("HTTP 429 rate limit", "exponential backoff"),
    ("Java cannot find symbol", "classpath"),
    ("database connection refused", "database service"),
])
def test_fallback_has_error_specific_guidance(error, expected):
    report = app.fallback_analysis(error, "Other", [])
    assert any(expected in item for item in report["fixes"])


def test_report_contains_current_findings_and_sources():
    content = app.make_report("Oops", "Python", "Python", "Windows", "context", '"Oops"',
                              [{"title": "Doc", "link": "https://example.com", "snippet": "Evidence"}],
                              app.fallback_analysis("Oops", "Python", []))
    for expected in ("Oops", "Windows", "https://example.com", "Evidence", "must be verified"):
        assert expected in content


def test_serpapi_error_does_not_echo_provider_secret():
    with pytest.raises(RuntimeError) as exc:
        app.parse_search_results({"error": "bad key SECRET_VALUE"})
    assert "SECRET_VALUE" not in str(exc.value)


def test_search_web_uses_api_params_and_parses_results(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"organic_results": [{"title": "Guide", "link": "https://example.org", "snippet": "text"}]}

    captured = {}

    def fake_get(url, params, timeout):
        captured.update(params=params, timeout=timeout)
        return Response()

    monkeypatch.setattr(app.requests, "get", fake_get)
    query, results = app.search_web("error", "Python", "Python", "Win", "", "dummy")
    assert "Win" in query
    assert captured["params"]["engine"] == "google"
    assert captured["timeout"] > 0
    assert results[0]["title"] == "Guide"


def test_missing_serpapi_configuration_is_reported():
    assert not app.has_serpapi_key("")
    assert not app.has_serpapi_key("  ")
    assert app.has_serpapi_key("configured")
