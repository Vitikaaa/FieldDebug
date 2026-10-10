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


def test_successful_verification_requires_success_evidence_or_user_confirmation():
    status, reason = app.classify_verification("12 passed in 0.42s")
    assert status == "Resolved"
    assert "did not execute" in reason

    status, reason = app.classify_verification("", user_reports_success=True)
    assert status == "Resolved"
    assert "You reported" in reason


def test_continuing_failure_is_not_resolved_when_text_changes():
    status, reason = app.classify_verification("ValueError: still cannot parse input")
    assert status == "Still failing"
    assert "not been verified as resolved" in reason
    assert app.classify_verification("BUILD FAILED in 2s")[0] == "Still failing"
    assert app.classify_verification("Tests run: 4, Failures: 1, Errors: 0")[0] == "Still failing"


def test_ambiguous_and_empty_verification_need_review():
    assert app.classify_verification("Command completed") [0] == "Needs review"
    assert app.classify_verification("  ") [0] == "Needs review"


def test_verification_history_can_be_created_and_cleared():
    state = {}
    investigation = {"error": "ImportError"}
    initial = app.add_investigation_history(state, investigation, timestamp="2026-10-10T12:29+05:30")
    assert initial["status"] == "Not verified"
    assert initial["selected_fix"] == "No fix selected"
    entry = app.add_verification_history(
        state, "ImportError", "Install package in active venv", "2 passed", "Resolved",
        "Successful tests reported", timestamp="2026-10-10T12:30+05:30",
    )
    assert state["fielddebug_history"] == [initial, entry]
    assert entry["timestamp"] == "2026-10-10T12:30+05:30"
    app.clear_verification_history(state)
    assert state["fielddebug_history"] == []

    widget_state = {"verification_output": "old", "verification_new_error": "next", "other": "preserved"}
    app.clear_verification_widget_state(widget_state)
    assert widget_state == {"other": "preserved"}

def test_new_error_reuses_existing_environment_for_search():
    current = {
        "technology": "Python", "language": "Python", "environment": "Windows 11",
        "context": "running tests",
    }
    request = app.next_investigation_payload(current, "  AssertionError: expected 1  ")
    assert request == {
        "error": "AssertionError: expected 1", "technology": "Python",
        "language": "Python", "environment": "Windows 11", "context": "running tests",
    }
    with pytest.raises(ValueError, match="new error"):
        app.next_investigation_payload(current, " ")


def test_fix_options_come_from_displayed_analysis():
    options = app.suggested_fix_options(
        "## Suggested fixes\n1. Run `python -m pip install pandas`\n2. Check the active interpreter\n## How to verify\nRun tests.",
        app.fallback_analysis("other", "Python", []),
    )
    assert options == ["Run `python -m pip install pandas`", "Check the active interpreter"]
