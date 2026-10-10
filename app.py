import os
import html
import re
from datetime import datetime
from urllib.parse import urlparse
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="FieldDebug | Evidence-backed debugging",
    page_icon="🐛",
    layout="wide",
)

SERPAPI_URL = "https://serpapi.com/search.json"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def build_query(error, technology, language, environment="", context=""):
    parts = [f'"{error.strip()}"', technology, language]
    if environment.strip():
        parts.append(environment.strip())
    parts.append("troubleshooting")
    return " ".join(part for part in parts if part)


def has_serpapi_key(api_key):
    return bool(api_key and api_key.strip())


def parse_search_results(payload):
    if not isinstance(payload, dict):
        raise ValueError("Search provider returned an unexpected response.")
    if payload.get("error"):
        raise RuntimeError("SerpApi could not complete the search. Check the key, quota, and request.")
    organic = payload.get("organic_results", [])
    results = []
    if not isinstance(organic, list):
        return results
    for item in organic:
        if not isinstance(item, dict):
            continue
        link = item.get("link")
        if not isinstance(link, str) or not link.startswith(("https://", "http://")):
            continue
        results.append({"title": str(item.get("title") or "Untitled result"), "link": link,
                        "snippet": str(item.get("snippet") or "No preview available.")})
    return results


def search_web(error, technology, language, environment, context, api_key):
    """Search Google through SerpApi and return organic results."""
    query = build_query(error, technology, language, environment, context)

    response = requests.get(
        SERPAPI_URL,
        params={
            "engine": "google",
            "q": query,
            "api_key": api_key,
            "num": 8,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()

    return query, parse_search_results(payload)


def fallback_analysis(error, technology, results):
    """Give cautious suggestions if no AI key is configured."""
    text = error.lower()
    suggestions = []

    if "modulenotfounderror" in text or "no module named" in text or "importerror" in text:
        suggestions = [
            "Check the exact package/module name in the error.",
            "Install the required package in the same Python environment used to run the program.",
            "Verify the active environment with `python -m pip show PACKAGE_NAME`.",
        ]
    elif "401" in text or "unauthorized" in text or "invalid token" in text:
        suggestions = [
            "Check whether the credential or token is correct and has not expired.",
            "Verify how the API expects authentication to be sent.",
            "Avoid printing secrets in logs or sharing them publicly.",
        ]
    elif "403" in text or "forbidden" in text or "permission" in text:
        suggestions = [
            "Check the account permissions and required API scopes.",
            "Confirm that the resource is available to your account.",
            "Check whether an organization policy or network restriction applies.",
        ]
    elif "404" in text or "not found" in text:
        suggestions = [
            "Check the URL, endpoint, file path, and spelling.",
            "Verify that the resource exists in the environment you are using.",
            "Check the current documentation for endpoint or version changes.",
        ]
    elif "429" in text or "rate limit" in text or "too many requests" in text:
        suggestions = [
            "Check the service's rate-limit and quota information.",
            "Retry with exponential backoff where appropriate.",
            "Avoid rapid repeated requests and check whether your quota is exhausted.",
        ]
    elif "timeout" in text or "timed out" in text or "connectionerror" in text:
        suggestions = [
            "Check network connectivity and whether the remote service is reachable.",
            "Inspect proxy, firewall, DNS, and timeout configuration.",
            "Retry cautiously and check the service's status page if available.",
        ]
    elif "500" in text or "internal server error" in text:
        suggestions = [
            "Inspect server-side logs and the full traceback if you control the service.",
            "Check whether the service is experiencing an outage.",
            "Retry cautiously; repeated failures may need escalation to the service owner.",
        ]
    elif "syntaxerror" in text or "syntax error" in text:
        suggestions = [
            "Read the exact line and column mentioned in the error.",
            "Check delimiters, brackets, quotes, indentation, and language-specific syntax.",
            "Compare the failing line with a minimal working example.",
        ]
    elif "cannot find symbol" in text or "javac" in text or "exception in thread" in text:
        suggestions = ["Check the first compiler/runtime diagnostic and its file and line.", "Confirm the class name, imports, package, and classpath.", "For runtime exceptions, inspect the first application frame in the stack trace."]
    elif "referenceerror" in text or "typeerror" in text or "cannot find module" in text or "npm err" in text:
        suggestions = ["Check the exact symbol, property, or module named in the message.", "Confirm dependencies are installed in this project and inspect package.json and its lockfile.", "Check the Node.js version and whether the code expects CommonJS or ES modules."]
    elif "database" in text or "connection refused" in text or "could not connect" in text or "sqlstate" in text:
        suggestions = ["Confirm the database service is running and reachable from this machine.", "Check host, port, database name, TLS settings, and firewall rules.", "Verify credentials through a secret-safe configuration check; do not print them."]
    elif "environment variable" in text or "not set" in text or "undefined variable" in text or "keyerror" in text:
        suggestions = ["Check the exact variable name and whether the process receives it.", "Load local environment configuration before reading values.", "Fail with a clear message when required configuration is absent; keep secrets out of logs."]
    elif "version conflict" in text or "incompatible" in text or "dependency conflict" in text or "requires:" in text:
        suggestions = ["Read the package manager's required and installed versions in the full output.", "Inspect the lockfile and runtime version, then update compatible dependencies deliberately.", "Recreate an isolated environment and install from the lockfile to check reproducibility."]
    else:
        suggestions = [
            "Read the complete traceback and identify the first relevant application-code line.",
            "Reproduce the problem with the smallest possible input.",
            "Check the source results below for the same error and matching software version.",
        ]

    return {
        "summary": (
            "These are initial troubleshooting hypotheses based on the error text. "
            "They are not a confirmed root cause."
        ),
        "causes": [
            "The runtime, configuration, input, or external dependency may differ "
            "from what the code expects.",
            "A version mismatch or environment-specific issue may be involved.",
        ],
        "fixes": suggestions,
        "verification": [
            "Apply one change at a time.",
            "Run the smallest reproducible example again.",
            "Compare the new output with the original error and keep the relevant logs.",
        ],
    }


def ai_analysis(error, technology, language, environment, context, results, api_key):
    """Ask Groq to summarize the supplied evidence, not invent sources."""
    if not api_key:
        return fallback_analysis(error, technology, results), None

    evidence = "\n\n".join(
        f"Source {i + 1}: {item['title']}\n"
        f"URL: {item['link']}\n"
        f"Snippet: {item['snippet']}"
        for i, item in enumerate(results)
    )

    prompt = f"""
You are FieldDebug, a cautious debugging research assistant.

Analyze the user's error using only the supplied search-result evidence and user context.
Search snippets may be incomplete or misleading. Do not claim a root cause is confirmed.
Do not invent documentation, quotes, URLs, or facts. Cite relevant evidence by source
number, for example [Source 2]. If evidence is insufficient, say so.

Return these headings:
## Initial assessment
## Possible causes
## Suggested fixes
## How to verify
## What to share next if it still fails

User error:
{error}

Technology: {technology}
Language: {language}
Environment: {environment or "Not specified"}
Additional context: {context or "Not supplied"}

Search evidence:
{evidence or "No organic search results were returned."}
"""

    response = requests.post(
        GROQ_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            "messages": [
                {
                    "role": "system",
                    "content": "Be accurate, cautious, practical, and transparent about uncertainty.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        },
        timeout=40,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Groq returned an empty analysis.")
    return None, content


def make_report(error, technology, language, environment, context, query, results, analysis, is_ai=False):
    """Build a complete report from this investigation's actual findings."""
    if isinstance(analysis, dict):
        lines = [analysis["summary"], "Possible causes:"]
        lines.extend(f"- {cause}" for cause in analysis["causes"])
        lines.append("Recommended actions:")
        lines.extend(f"- {fix}" for fix in analysis["fixes"])
        lines.append("Verification:")
        lines.extend(f"- [ ] {step}" for step in analysis["verification"])
        findings = "\n".join(lines)
    else:
        findings = str(analysis)
    sources = "\n\n".join(f"{i}. {item['title']}\n{item['link']}\n{item['snippet']}" for i, item in enumerate(results, 1)) or "No organic sources were returned."
    return ("FieldDebug investigation report\n"
            f"Analysis type: {'Groq AI (verify against sources)' if is_ai else 'Rule-based hypotheses'}\n\n"
            f"Original error:\n{error}\n\nTechnology: {technology}\nLanguage: {language}\n"
            f"Environment: {environment or 'Not specified'}\nContext: {context or 'Not supplied'}\n\n"
            f"Search query:\n{query}\n\nFindings and suggested actions:\n{findings}\n\nSources:\n{sources}\n\n"
            "Disclaimer: Suggested fixes are hypotheses and must be verified in your environment.")


def classify_verification(output, user_reports_success=False):
    """Classify user-provided evidence without executing or inferring a code fix."""
    text = (output or "").strip()
    if user_reports_success:
        return "Resolved", "You reported that the issue is resolved. FieldDebug did not independently run the fix."
    if not text:
        return "Needs review", "Add the resulting output or explicitly confirm that the issue is resolved."
    failure_markers = (
        r"traceback \(most recent call last\)", r"\b[A-Za-z_]*(?:Error|Exception):",
        r"\bException in thread\b",
        r"(?im)^\s*(?:error|exception|failed|failure)\b", r"\btests?\s+(?:have\s+)?failed\b",
        r"\b\d+\s+failed\b", r"\bBUILD FAILED\b", r"\bnpm ERR!", r"assertionerror",
        r"\b(?:Failures|Errors):\s*[1-9]\d*\b",
        r"\bexit code [1-9]\d*\b",
    )
    if any(re.search(pattern, text) for pattern in failure_markers):
        return "Still failing", "The submitted output contains an error, exception, or failure marker. The new issue has not been verified as resolved."
    success_markers = (
        r"\b\d+\s+passed\b", r"\ball tests passed\b", r"\btests? passed\b",
        r"\bRan\s+\d+\s+tests?\b[\s\S]{0,100}\bOK\b",
    )
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in success_markers):
        return "Resolved", "The output contains a recognizable successful test, build, or compilation result. FieldDebug did not execute it."
    return "Needs review", "The output does not clearly show success or a continuing failure. Review it and run a relevant test."


def add_verification_history(state, original_error, selected_fix, output, status, reason, timestamp=None):
    """Append one verification attempt to the current Streamlit session history."""
    entry = {
        "original_error": original_error,
        "selected_fix": selected_fix,
        "output": output,
        "status": status,
        "reason": reason,
        "timestamp": timestamp or datetime.now().astimezone().isoformat(timespec="minutes"),
    }
    state.setdefault("fielddebug_history", []).append(entry)
    return entry


def add_investigation_history(state, investigation, timestamp=None):
    """Record a completed search in session history before any fix is selected."""
    entry = {
        "original_error": investigation["error"],
        "selected_fix": "No fix selected",
        "output": "",
        "status": "Not verified",
        "reason": "Investigation completed. Choose a suggested fix and submit outcome evidence to verify it.",
        "timestamp": timestamp or datetime.now().astimezone().isoformat(timespec="minutes"),
    }
    state.setdefault("fielddebug_history", []).append(entry)
    return entry


def clear_verification_history(state):
    state["fielddebug_history"] = []


def clear_verification_widget_state(state):
    for key in ("verification_selected_fix", "verification_output", "verification_user_success", "verification_new_error"):
        state.pop(key, None)


def next_investigation_payload(current, new_error):
    """Reuse the active investigation context for a user-supplied follow-up error."""
    new_error = (new_error or "").strip()
    if not new_error:
        raise ValueError("Enter the new error or failure output before investigating it.")
    return {
        "error": new_error,
        "technology": current["technology"],
        "language": current["language"],
        "environment": current["environment"],
        "context": current["context"],
    }


def suggested_fix_options(analysis, fallback):
    """Extract selectable fix choices from the analysis actually shown to the user."""
    if isinstance(analysis, dict):
        options = analysis.get("fixes", [])
    else:
        match = re.search(r"(?im)^#{1,4}\s*(?:suggested fixes|recommended fixes)\s*$([\s\S]*?)(?=^#{1,4}\s|\Z)", analysis or "")
        section = match.group(1) if match else ""
        options = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
                   for line in section.splitlines()
                   if re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()]
    return list(dict.fromkeys(str(option).strip() for option in options if str(option).strip())) or list(fallback.get("fixes", []))


def inject_styles():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@400;500;600;700&display=swap');

    :root {
        --bg: #F5F1E8;
        --panel: #FFFCF5;
        --line: #DED6C8;
        --text: #202723;
        --muted: #686D65;
        --accent: #C65D36;
    }

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
    }

    .stApp {
        background: var(--bg);
        color: var(--text);
    }

    [data-testid="stHeader"] {
        background: transparent;
    }

    .block-container {
        max-width: 1160px;
        padding: 1.5rem 2rem 3rem;
    }

    /* Sidebar */
    [data-testid="stSidebar"],
    [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
        background: #EAE3D5 !important;
    }

    [data-testid="stSidebar"] {
        border-right: 1px solid #D8CEBD !important;
    }

    [data-testid="stSidebar"] > div:first-child {
        padding-top: 1.5rem;
    }

    [data-testid="stSidebar"] .block-container {
        padding: 1.5rem 1.1rem 2rem;
    }

    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: #242923 !important;
        letter-spacing: -0.025em;
    }

    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] span {
        color: #55594F;
        line-height: 1.65;
    }

    /* Typography */
    h1, h2, h3, p {
        color: var(--text);
    }

    h1 {
        letter-spacing: -0.045em;
        font-weight: 700;
    }

    h2 {
        letter-spacing: -0.03em;
    }

    label,
    [data-testid="stCaptionContainer"] {
        color: var(--muted) !important;
    }

    /* Inputs */
    [data-testid="stTextArea"] textarea,
    [data-testid="stTextInput"] input,
    [data-testid="stSelectbox"] [data-baseweb="select"] > div,
    [data-testid="stMultiSelect"] [data-baseweb="select"] > div {
        background: #FFFCF5 !important;
        border: 1px solid #CFC5B5 !important;
        border-radius: 8px !important;
        color: #202723 !important;
        -webkit-text-fill-color: #202723 !important;
        transition: border-color 200ms ease, box-shadow 200ms ease;
    }

    [data-testid="stTextArea"] textarea::placeholder,
    [data-testid="stTextInput"] input::placeholder {
        color: #77786F !important;
        -webkit-text-fill-color: #77786F !important;
        opacity: 1 !important;
    }

    [data-testid="stTextArea"] textarea:focus,
    [data-testid="stTextInput"] input:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 3px rgba(198, 93, 54, 0.12) !important;
        outline: none !important;
    }

    /* Form */
    [data-testid="stForm"] {
        border: 0;
        padding: 0;
    }

    /* Buttons */
    .stButton > button,
    [data-testid="stFormSubmitButton"] button {
        position: relative;
        overflow: hidden;
        min-height: 44px;
        border-radius: 8px;
        border: 1px solid var(--accent);
        background: var(--accent);
        color: #FFFFFF !important;
        font-weight: 700;
        box-shadow: 0 2px 5px rgba(75, 49, 30, 0.08);
        transition: transform 220ms ease, box-shadow 220ms ease,
                    background 220ms ease, border-color 220ms ease;
    }

    .stButton > button:hover,
    [data-testid="stFormSubmitButton"] button:hover {
        background: linear-gradient(110deg, #D76A43 0%, #C65D36 55%, #B9502D 100%) !important;
        border-color: #E7A080 !important;
        color: #FFFFFF !important;
        transform: translateY(-2px);
        box-shadow: 0 5px 14px rgba(103, 59, 37, 0.16),
                    0 0 12px rgba(198, 93, 54, 0.12),
                    inset 0 1px 0 rgba(255, 255, 255, 0.35);
        filter: none;
    }

    .stButton > button:active,
    [data-testid="stFormSubmitButton"] button:active {
        transform: translateY(0);
        box-shadow: 0 1px 3px rgba(75, 49, 30, 0.1);
    }

    @media (prefers-reduced-motion: reduce) {
        .stButton > button,
        [data-testid="stFormSubmitButton"] button,
        [data-testid="stTextArea"] textarea,
        [data-testid="stTextInput"] input {
            transition: none !important;
        }
    }

    a {
        color: #9C4529 !important;
    }

    code, pre {
        font-family: 'DM Mono', monospace !important;
    }

    [data-testid="stVerticalBlockBorderWrapper"] {
        background: var(--panel);
        border-color: var(--line) !important;
        border-radius: 8px !important;
    }

    /* Navigation */
    .fd-nav {
        display: flex;
        align-items: center;
        gap: 12px;
        min-height: 48px;
        border-bottom: 1px solid var(--line);
        margin-bottom: 2.2rem;
        padding-bottom: 12px;
    }

    .fd-mark {
        width: 30px;
        height: 30px;
        border-radius: 6px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: var(--text);
        color: var(--bg);
        font: 700 12px 'DM Mono', monospace;
    }

    .fd-brand {
        font-size: 16px;
        font-weight: 700;
        letter-spacing: -0.03em;
    }

    .fd-navitem {
        color: var(--muted);
        font-size: 12px;
        padding: 7px 10px;
        border-radius: 5px;
        text-decoration: none !important;
    }

    .fd-navitem.active {
        color: var(--text) !important;
        background: #E7DFD0;
    }

    .fd-status {
        margin-left: auto;
        color: var(--muted);
        font-size: 11px;
        display: flex;
        align-items: center;
        gap: 7px;
    }

    .fd-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: #A6A79F;
        display: inline-block;
    }

    .fd-dot.ready {
        background: #47745B;
    }

    /* Hero and section labels */
    .fd-eyebrow, .fd-section-label {
        color: var(--accent);
        font: 500 10px 'DM Mono', monospace;
        letter-spacing: 0.10em;
        margin-bottom: 12px;
    }

    .fd-hero {
        position: relative;
        padding: 18px 0 30px;
        margin-bottom: 24px;
        border-bottom: 1px solid var(--line);
    }

    .fd-hero .fd-eyebrow {
        margin-bottom: 22px;
    }

    .fd-hero .fd-eyebrow span {
        color: #A9A08F;
        padding: 0 5px;
    }

    .fd-hero .fd-title {
        font-size: clamp(46px, 6vw, 72px);
        max-width: 760px;
        line-height: 0.99;
        letter-spacing: -0.075em;
        margin-bottom: 20px;
    }

    .fd-hero .fd-subtitle {
        max-width: 570px;
        font-size: 16px;
        line-height: 1.8;
        margin-bottom: 22px;
    }

    .fd-hero-meta {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 9px;
        color: var(--muted);
        font: 500 9px 'DM Mono', monospace;
        letter-spacing: 0.08em;
    }

    .fd-meta-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: #47745B;
    }

    .fd-meta-divider {
        color: #B5AA99;
    }

    .fd-section-label {
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 11px;
        margin-bottom: 16px;
    }

    .fd-section-number {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 25px;
        height: 25px;
        border: 1px solid var(--line);
        border-radius: 5px;
        color: var(--text);
        letter-spacing: 0;
    }

    .fd-title {
        font-size: clamp(34px, 4vw, 48px);
        font-weight: 700;
        line-height: 1.08;
        letter-spacing: -0.055em;
        margin: 0 0 10px;
    }

    .fd-subtitle {
        max-width: 640px;
        color: var(--muted);
        font-size: 15px;
        line-height: 1.65;
        margin-bottom: 24px;
    }

    .fd-lead, .fd-snippet {
        color: var(--muted);
        font-size: 13px;
        line-height: 1.7;
    }

    .fd-card-title {
        color: var(--text);
        font-size: 14px;
        font-weight: 700;
        margin: 0 0 7px;
    }

    .fd-step {
        color: var(--accent);
        font: 500 11px 'DM Mono', monospace;
        margin-bottom: 10px;
    }

    .fd-summary {
        padding: 18px 20px;
        border: 1px solid var(--line);
        border-radius: 8px;
        background: var(--panel);
    }

    .fd-source-title {
        font-size: 14px;
        font-weight: 700;
        line-height: 1.5;
    }

    .fd-domain {
        font: 11px 'DM Mono', monospace;
        color: var(--muted);
        margin: 5px 0 9px;
    }

    /* Dropdowns */
    [data-testid="stSelectbox"] [data-baseweb="select"] > div {
        background-color: #FFFCF5 !important;
        border: 1px solid #CFC5B5 !important;
        color: #202723 !important;
        box-shadow: none !important;
    }

    [data-testid="stSelectbox"] [data-baseweb="select"] input,
    [data-testid="stSelectbox"] [data-baseweb="select"] span {
        color: #202723 !important;
        -webkit-text-fill-color: #202723 !important;
    }

    [data-testid="stSelectbox"] svg {
        fill: #686D65 !important;
        color: #686D65 !important;
    }

    [data-baseweb="popover"] ul,
    [data-baseweb="menu"] {
        background-color: #FFFCF5 !important;
    }

    [data-baseweb="popover"] li,
    [data-baseweb="menu"] li {
        background-color: #FFFCF5 !important;
        color: #202723 !important;
    }

    [data-baseweb="popover"] li:hover,
    [data-baseweb="menu"] li:hover {
        background-color: #EDE7DA !important;
        color: #202723 !important;
    }

    /* Download report button */
    [data-testid="stDownloadButton"] button,
    [data-testid="stDownloadButton"] button p,
    [data-testid="stDownloadButton"] button span {
        background: #C65D36 !important;
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
        border: 1px solid #C65D36 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        opacity: 1 !important;
    }

    [data-testid="stDownloadButton"] button:hover,
    [data-testid="stDownloadButton"] button:hover p,
    [data-testid="stDownloadButton"] button:hover span {
        background: #A94727 !important;
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
        border-color: #A94727 !important;
        box-shadow: 0 4px 12px rgba(198, 93, 54, 0.25) !important;
        transform: translateY(-1px);
    }

    /* Verification checklist */
    [data-testid="stCheckbox"] div[data-baseweb="checkbox"] > div {
        background-color: #FFFCF5 !important;
        border: 1.5px solid #C65D36 !important;
        border-radius: 4px !important;
    }

    [data-testid="stCheckbox"] div[data-baseweb="checkbox"] > div[aria-checked="true"] {
        background-color: #C65D36 !important;
        border-color: #C65D36 !important;
    }

    [data-testid="stCheckbox"] label p {
        color: #202723 !important;
    }

    @media (max-width: 700px) {
        .block-container {
            padding: 1rem 1rem 2rem;
        }

        .fd-nav {
            margin-bottom: 1.5rem;
        }

        .fd-navitem {
            display: none;
        }

        .fd-status {
            font-size: 10px;
        }

        .fd-hero .fd-title {
            font-size: 46px;
        }

        .fd-hero {
            padding-top: 8px;
        }

        .fd-subtitle {
            margin-bottom: 20px;
        }
    }
        .fd-summary pre { white-space: pre-wrap; overflow-wrap: anywhere; color: var(--text); font-size: 12px; }
    </style>
    """, unsafe_allow_html=True)



def render_fallback(report):
    st.markdown('<div class="fd-section-label">Initial assessment · Rule-based hypotheses</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="fd-summary">{html.escape(report["summary"])}</div>', unsafe_allow_html=True)
    st.markdown("#### Possible causes")
    for cause in report["causes"]:
        st.markdown(f"- {cause}")
    st.markdown("#### Recommended fixes")
    for index, fix in enumerate(report["fixes"], start=1):
        st.markdown(f"**{index:02d}** &nbsp; {fix}")
    st.markdown("#### Verification checklist")
    for index, step in enumerate(report["verification"]):
        st.checkbox(step, key=f"verify_{index}_{abs(hash(step))}")


def render_sources(results):
    if not results:
        st.info("No organic results came back for this query. Try a shorter error excerpt or add the exact exception name.")
        return
    st.markdown(f'<div class="fd-section-label">Retrieved evidence · {len(results)} sources</div>', unsafe_allow_html=True)
    for index, item in enumerate(results, 1):
        domain = html.escape(urlparse(item["link"]).netloc)
        title, snippet = html.escape(item["title"]), html.escape(item["snippet"])
        link = html.escape(item["link"], quote=True)
        st.markdown(
            f'<div class="fd-summary" style="margin:10px 0;padding:16px 18px">'
            f'<div class="fd-section-label">SOURCE {index:02d} &nbsp; · &nbsp; {domain}</div>'
            f'<div class="fd-source-title"><a href="{link}" target="_blank" rel="noopener">{title} ↗</a></div>'
            f'<div class="fd-snippet" style="margin-top:8px">{snippet}</div></div>',
            unsafe_allow_html=True,
        )


def perform_investigation(error, technology, language, environment, context, serp_key, groq_key):
    """Run the existing search and analysis pipeline and return session-ready results."""
    with st.spinner("Searching Google for relevant troubleshooting evidence…"):
        query, results = search_web(error.strip(), technology, language, environment, context, serp_key.strip())
    ai_unavailable = False
    with st.spinner("Preparing evidence-aware guidance…"):
        try:
            fallback, ai_text = ai_analysis(error.strip(), technology, language, environment, context, results, groq_key.strip())
        except (requests.RequestException, KeyError, ValueError):
            fallback, ai_text, ai_unavailable = fallback_analysis(error.strip(), technology, results), None, True
    if fallback is None:
        fallback = fallback_analysis(error.strip(), technology, results)
    return {
        "error": error.strip(), "technology": technology, "language": language,
        "environment": environment, "context": context, "query": query,
        "results": results, "fallback": fallback, "ai_text": ai_text,
        "ai_unavailable": ai_unavailable,
    }


def render_fix_verification(investigation):
    st.markdown("## Fix Verification Lab")
    st.caption("Apply a suggested fix in your own environment, then share the result. FieldDebug never executes submitted code.")
    original = investigation["error"]
    st.markdown("#### 1 · Original error")
    st.code(original, language="text")
    st.caption(" · ".join(part for part in [investigation["technology"], investigation["language"], investigation["environment"], investigation["context"]] if part) or "No additional context provided")

    analysis_for_fixes = investigation["ai_text"] or investigation["fallback"]
    fix_options = suggested_fix_options(analysis_for_fixes, investigation["fallback"])
    if not fix_options:
        st.info("No selectable fix suggestions are available for this investigation yet.")
        return

    st.markdown("#### 2–4 · Choose, apply, and verify")
    with st.form("fix_verification_form"):
        selected_fix = st.selectbox("Choose one of the suggested fixes", fix_options, key="verification_selected_fix")
        st.markdown("**3 · Apply the fix**")
        st.info(selected_fix)
        code_parts = re.findall(r"`([^`]+)`", selected_fix)
        if code_parts:
            st.code("\n".join(code_parts), language="text")
        st.markdown("**4 · Verify the outcome**")
        outcome = st.text_area("New terminal output, error, or test result", placeholder="Paste what happened after you tried the fix. FieldDebug will classify the evidence, not execute it.", height=105, key="verification_output")
        user_reports_success = st.checkbox("I applied the fix and can confirm the original issue is resolved", key="verification_user_success")
        new_error = st.text_area("New error to investigate", placeholder="Paste the new error or failure output", height=72, key="verification_new_error")
        button_col, next_col = st.columns(2)
        with button_col:
            save_verification = st.form_submit_button("Compare results", type="primary", use_container_width=True)
        with next_col:
            investigate_again = st.form_submit_button("Investigate a new error", use_container_width=True)

    if save_verification or investigate_again:
        status, reason = classify_verification(outcome, user_reports_success)
        entry = add_verification_history(st.session_state, original, selected_fix, outcome, status, reason)
        st.session_state["fielddebug_latest_verification"] = entry
    if investigate_again:
        try:
            request = next_investigation_payload(investigation, new_error.strip() or outcome.strip())
            serp_key = st.session_state.get("serpapi_api_key", os.getenv("SERPAPI_API_KEY", ""))
            groq_key = st.session_state.get("groq_api_key", os.getenv("GROQ_API_KEY", ""))
            if not has_serpapi_key(serp_key):
                st.warning("For a follow-up search, make sure the SerpApi key is available in Settings.")
                return
            next_result = perform_investigation(
                request["error"], request["technology"], request["language"],
                request["environment"], request["context"],
                serp_key, groq_key,
            )
            st.session_state["fielddebug_current_investigation"] = next_result
            add_investigation_history(st.session_state, next_result)
            st.session_state.pop("fielddebug_latest_verification", None)
            st.session_state["_reset_verification_widgets"] = True
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
        except requests.RequestException:
            st.error("The follow-up search could not reach SerpApi. Check connectivity and try again.")
        except (KeyError, RuntimeError, ValueError):
            st.error("The follow-up search response could not be processed.")

    latest = st.session_state.get("fielddebug_latest_verification")
    if latest and latest["original_error"] == original:
        render_verification_comparison(latest)


def render_verification_comparison(entry):
    status_colors = {"Resolved": "#51d6a0", "Still failing": "#ff8a8a", "Needs review": "#f0c36b"}
    color = status_colors.get(entry["status"], "#aab1c0")
    st.markdown("### Before and after")
    st.markdown(
        f'<div class="fd-summary"><div style="color:{color};font-weight:700;margin-bottom:14px">● {html.escape(entry["status"])}</div>'
        f'<div class="fd-section-label">ORIGINAL ERROR</div><pre>{html.escape(entry["original_error"])}</pre>'
        f'<div class="fd-section-label">SELECTED FIX</div><pre>{html.escape(entry["selected_fix"])}</pre>'
        f'<div class="fd-section-label">NEW OUTPUT</div><pre>{html.escape(entry["output"] or "No output supplied")}</pre>'
        f'<div class="fd-lead">{html.escape(entry["reason"])}</div></div>', unsafe_allow_html=True,
    )
    if entry["status"] == "Still failing":
        st.info("Next: paste the new error above and choose Investigate a new error to search for updated evidence.")
    elif entry["status"] == "Needs review":
        st.info("Next: provide clearer output or run a relevant test before treating the fix as resolved.")


def render_investigation(investigation):
    error = investigation["error"]
    results = investigation["results"]
    ai_text = investigation["ai_text"]
    fallback = investigation["fallback"]
    st.markdown('<div class="fd-section-label">Investigation report</div>', unsafe_allow_html=True)
    st.markdown('<h2 style="font-size:25px;margin:0 0 12px">Evidence for your error</h2>', unsafe_allow_html=True)
    st.markdown(f'<div class="fd-summary"><div class="fd-section-label">SEARCH COMPLETE · {len(results)} RESULTS</div><div class="fd-lead">{html.escape(error[:420])}</div></div>', unsafe_allow_html=True)
    with st.expander("View search query"):
        st.code(investigation["query"])
    if investigation["ai_unavailable"]:
        st.warning("Groq analysis is unavailable right now. Search succeeded; showing rule-based hypotheses.")
    elif not ai_text:
        st.caption("Groq is not configured. Guidance below is rule-based and does not confirm a root cause.")

    st.markdown("### Analysis")
    if ai_text:
        st.markdown('<div class="fd-section-label">AI-GENERATED ANALYSIS · REVIEW AGAINST SOURCES</div>', unsafe_allow_html=True)
        st.markdown(ai_text)
    else:
        render_fallback(fallback)
    st.markdown("### Web evidence")
    render_sources(results)
    report = make_report(error, investigation["technology"], investigation["language"],
                         investigation["environment"], investigation["context"], investigation["query"],
                         results, ai_text or fallback, is_ai=bool(ai_text))
    st.download_button("Download investigation report", data=report, file_name="fielddebug_report.txt", mime="text/plain")
    st.divider()
    render_fix_verification(investigation)


def render_session_history():
    history = st.session_state.get("fielddebug_history", [])
    if not history:
        return
    st.markdown("### Session history")
    labels = [f'{item["timestamp"]} · {item["status"]} · {item["original_error"][:70]}' for item in history]
    selected_index = st.selectbox("Revisit a verification attempt", range(len(history)),
                                  format_func=lambda index: labels[index], key="history_selection")
    render_verification_comparison(history[selected_index])
    if st.button("Clear session history", key="clear_history"):
        clear_verification_history(st.session_state)
        st.rerun()


def main():
    if st.session_state.pop("_reset_verification_widgets", False):
        clear_verification_widget_state(st.session_state)
    inject_styles()
    with st.sidebar:
        st.markdown("### Settings")
        st.caption("Provider credentials are stored only in this session or your local environment.")
        serp_key = st.text_input("SerpApi API key", value=os.getenv("SERPAPI_API_KEY", ""), type="password", help="Required for live Google Search.", key="serpapi_api_key")
        groq_key = st.text_input("Groq API key · optional", value=os.getenv("GROQ_API_KEY", ""), type="password", help="Enables evidence-aware AI analysis.", key="groq_api_key")
        st.caption("Without Groq, FieldDebug uses rule-based troubleshooting guidance.")

    ready = has_serpapi_key(serp_key)
    repo_url = os.getenv("FIELDEBUG_GITHUB_URL", "").strip()
    github_link = f'<a class="fd-navitem" href="{html.escape(repo_url, quote=True)}" target="_blank" rel="noopener">GitHub ↗</a>' if repo_url.startswith("https://github.com/") else ""
    st.markdown(
        '<div class="fd-nav"><span class="fd-mark">fd</span><span class="fd-brand">FieldDebug</span>'
        '<a class="fd-navitem active" href="#investigate">Investigate</a><a class="fd-navitem" href="#about">About</a>'
        f'{github_link}<span class="fd-status"><i class="fd-dot {"ready" if ready else ""}"></i>Search {"ready" if ready else "not configured"}</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div id="investigate"></div><div class="fd-eyebrow">AI-ASSISTED DEBUGGING WORKSPACE</div>', unsafe_allow_html=True)
    st.markdown('<h1 class="fd-title">Let’s trace the failure.</h1>', unsafe_allow_html=True)
    st.markdown('<div class="fd-subtitle">Investigate errors with real-world evidence, actionable fixes, and verification steps.</div>', unsafe_allow_html=True)
    st.markdown('<div class="fd-section-label">Start an investigation</div>', unsafe_allow_html=True)

    with st.form("debug_form"):
        error = st.text_area("Error message or traceback", placeholder="Paste the exact error. Example: ModuleNotFoundError: No module named 'pandas'", height=112)
        first, second = st.columns(2, gap="medium")
        with first:
            technology = st.selectbox("Technology / framework", ["Python", "Java", "JavaScript", "React", "Node.js", "FastAPI", "SQL / Database", "AWS / Cloud", "Other"])
        with second:
            language = st.selectbox("Programming language", ["Python", "Java", "JavaScript", "TypeScript", "SQL", "Other"])
        with st.expander("Environment and what you were trying to do · optional"):
            env_col, context_col = st.columns(2, gap="medium")
            with env_col:
                environment = st.text_input("Environment", placeholder="Windows 11 · Python 3.13 · VS Code")
            with context_col:
                context = st.text_input("Intended action", placeholder="Installing a package in a virtual environment")
        submitted = st.form_submit_button("⌕  Investigate error", type="primary", use_container_width=True)

    if submitted:
        if not error.strip():
            st.error("Add an error message to start the investigation.")
        elif not has_serpapi_key(serp_key):
            st.error("Web search is not configured. Add a SerpApi key in Settings to investigate.")
        else:
            try:
                result = perform_investigation(error, technology, language, environment, context, serp_key, groq_key)
                st.session_state["fielddebug_current_investigation"] = result
                add_investigation_history(st.session_state, result)
                st.session_state.pop("fielddebug_latest_verification", None)
                st.session_state["_reset_verification_widgets"] = True
            except requests.HTTPError as exc:
                code = exc.response.status_code if exc.response is not None else "unknown"
                st.error(f"Search failed with HTTP {code}. Check the SerpApi key, quota, and account status.")
            except requests.RequestException:
                st.error("The search request could not reach SerpApi. Check your network and try again.")
            except (KeyError, ValueError, RuntimeError):
                st.error("The search response could not be processed. Check the API key and try again.")
            except Exception:
                st.error("An unexpected error occurred. Check configuration and try again.")

    current_investigation = st.session_state.get("fielddebug_current_investigation")
    if current_investigation:
        st.divider()
        render_investigation(current_investigation)
    render_session_history()

    st.markdown('<div id="about"></div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown('<div class="fd-section-label">A clearer path from error to resolution</div>', unsafe_allow_html=True)
    st.markdown("## From error to evidence")
    cards = st.columns(3, gap="medium")
    items = [
        ("01 · SEARCH", "Real search results", "FieldDebug sends the error and environment to Google through SerpApi, then returns current pages with source links."),
        ("02 · INVESTIGATE", "Evidence, then hypotheses", "Optional AI analysis uses retrieved snippets. Without Groq, careful rule-based checks keep the workflow useful."),
        ("03 · VERIFY", "Verify before you ship", "Read the sources, test one suggested change at a time, and use the checklist to confirm the result."),
    ]
    for column, (step, title, description) in zip(cards, items):
        with column:
            st.markdown(f'<div class="fd-step">{step}</div><div class="fd-card-title">{title}</div><p class="fd-snippet">{description}</p>', unsafe_allow_html=True)
    st.caption("Suggested fixes are hypotheses, not confirmed diagnoses. Avoid pasting secrets or confidential code.")


if __name__ == "__main__":
    main()
