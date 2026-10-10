import os
import html
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


def inject_styles():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@400;500;600;700&display=swap');
    :root{--bg:#0b0d12;--panel:#11141b;--line:#252a36;--text:#edf0f6;--muted:#9299aa;--blue:#7892ff}
    html,body,[class*="css"]{font-family:'DM Sans',sans-serif}.stApp{background:radial-gradient(ellipse at 50% -25%,#19223a 0%,#0b0d12 44%);color:var(--text)}
    [data-testid="stHeader"]{background:transparent}.block-container{max-width:1080px;padding:1.2rem 2rem 4rem}
    [data-testid="stSidebar"]{background:#0d1016;border-right:1px solid var(--line)}[data-testid="stSidebar"]>div:first-child{padding-top:1.5rem}
    h1,h2,h3,p{color:var(--text)}h1{letter-spacing:-.055em}h2{letter-spacing:-.035em}label,[data-testid="stCaptionContainer"]{color:var(--muted)!important}
    [data-testid="stTextArea"] textarea,[data-testid="stTextInput"] input,[data-testid="stSelectbox"] [data-baseweb="select"]>div{background:#0c0f15!important;border:1px solid #2a3040!important;border-radius:9px!important;color:#edf0f6!important}
    [data-testid="stTextArea"] textarea:focus,[data-testid="stTextInput"] input:focus{border-color:#718dff!important;box-shadow:0 0 0 1px #718dff55!important}
    [data-testid="stForm"]{border:0;padding:0}.stButton>button,[data-testid="stFormSubmitButton"] button{min-height:42px;border-radius:9px;border:1px solid #7894ff;background:#6b88f5;color:#08101f;font-weight:700;transition:filter .15s,transform .15s}
    .stButton>button:hover,[data-testid="stFormSubmitButton"] button:hover{filter:brightness(1.08);transform:translateY(-1px)}a{color:#9ab0ff!important}
    [data-testid="stVerticalBlockBorderWrapper"]{background:#11141b;border-color:#282e3a!important;border-radius:12px!important}code,pre{font-family:'DM Mono',monospace!important}
    .fd-nav{display:flex;align-items:center;gap:12px;min-height:48px;border-bottom:1px solid #282e3a;margin-bottom:3.8rem;padding-bottom:12px}
    .fd-mark{width:28px;height:28px;border-radius:8px;display:inline-flex;align-items:center;justify-content:center;background:#6f8cff;color:#080d18;font:700 12px 'DM Mono',monospace}
    .fd-brand{font-size:15px;font-weight:700;letter-spacing:-.03em}.fd-navitem{color:#a2a9b8;font-size:12px;padding:7px 10px;border-radius:7px;text-decoration:none!important}.fd-navitem.active{color:#edf0f6!important;background:#1a1f2a}
    .fd-status{margin-left:auto;color:#9ca5b7;font-size:11px;display:flex;align-items:center;gap:7px}.fd-dot{width:7px;height:7px;border-radius:50%;background:#555c6c;display:inline-block}.fd-dot.ready{background:#53d6a0;box-shadow:0 0 10px #53d6a055}
    .fd-eyebrow,.fd-section-label{color:#8da4ff;font:500 10px 'DM Mono',monospace;letter-spacing:.13em;margin-bottom:12px}.fd-title{font-size:clamp(36px,5vw,54px);font-weight:600;line-height:1.04;letter-spacing:-.065em;margin:0 0 12px}
    .fd-subtitle{max-width:610px;color:#a1a8b7;font-size:15px;line-height:1.65;margin-bottom:34px}.fd-lead,.fd-snippet{color:#b2b8c5;font-size:13px;line-height:1.65}.fd-card-title{color:#e9edf5;font-size:14px;font-weight:600;margin:0 0 7px}.fd-step{color:#7893ff;font:500 11px 'DM Mono',monospace;margin-bottom:14px}
    .fd-summary{padding:18px 20px;border:1px solid #293247;border-radius:12px;background:linear-gradient(120deg,#141a27,#11141b)}.fd-source-title{font-size:14px;font-weight:600;line-height:1.4}.fd-domain{font:11px 'DM Mono',monospace;color:#8e98ad;margin:5px 0 9px}
    @media(max-width:700px){.block-container{padding:1rem 1rem 3rem}.fd-nav{margin-bottom:2.5rem}.fd-navitem{display:none}.fd-status{font-size:10px}.fd-subtitle{margin-bottom:25px}}
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


def render_investigation(error, technology, language, environment, context, serp_key, groq_key):
    if not error.strip():
        st.error("Add an error message to start the investigation.")
        return
    if not has_serpapi_key(serp_key):
        st.error("Web search is not configured. Add a SerpApi key in Settings to investigate.")
        return
    try:
        with st.spinner("Searching Google for relevant troubleshooting evidence…"):
            query, results = search_web(error.strip(), technology, language, environment, context, serp_key.strip())
        with st.spinner("Preparing evidence-aware guidance…"):
            try:
                fallback, ai_text = ai_analysis(error.strip(), technology, language, environment, context, results, groq_key.strip())
                ai_unavailable = False
            except (requests.RequestException, KeyError, ValueError):
                fallback, ai_text, ai_unavailable = fallback_analysis(error.strip(), technology, results), None, True

        st.markdown('<div class="fd-section-label">Investigation report</div>', unsafe_allow_html=True)
        st.markdown('<h2 style="font-size:25px;margin:0 0 12px">Evidence for your error</h2>', unsafe_allow_html=True)
        st.markdown(f'<div class="fd-summary"><div class="fd-section-label">SEARCH COMPLETE · {len(results)} RESULTS</div><div class="fd-lead">{html.escape(error.strip()[:420])}</div></div>', unsafe_allow_html=True)
        with st.expander("View search query"):
            st.code(query)
        if ai_unavailable:
            st.warning("Groq analysis is unavailable right now. Search succeeded; showing rule-based hypotheses.")
        elif not groq_key.strip():
            st.caption("Groq is not configured. Guidance below is rule-based and does not confirm a root cause.")

        st.markdown("### Analysis")
        if ai_text:
            st.markdown('<div class="fd-section-label">AI-GENERATED ANALYSIS · REVIEW AGAINST SOURCES</div>', unsafe_allow_html=True)
            st.markdown(ai_text)
        else:
            render_fallback(fallback)

        st.markdown("### Web evidence")
        render_sources(results)
        report = make_report(error.strip(), technology, language, environment, context, query, results, ai_text or fallback, is_ai=bool(ai_text))
        st.download_button("Download investigation report", data=report, file_name="fielddebug_report.txt", mime="text/plain")
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "unknown"
        st.error(f"Search failed with HTTP {code}. Check the SerpApi key, quota, and account status.")
    except requests.RequestException:
        st.error("The search request could not reach SerpApi. Check your network and try again.")
    except (KeyError, ValueError, RuntimeError):
        st.error("The search response could not be processed. Check the API key and try again.")
    except Exception:
        st.error("An unexpected error occurred. Check configuration and try again.")


def main():
    inject_styles()
    with st.sidebar:
        st.markdown("### Settings")
        st.caption("Provider credentials are stored only in this session or your local environment.")
        serp_key = st.text_input("SerpApi API key", value=os.getenv("SERPAPI_API_KEY", ""), type="password", help="Required for live Google Search.")
        groq_key = st.text_input("Groq API key · optional", value=os.getenv("GROQ_API_KEY", ""), type="password", help="Enables evidence-aware AI analysis.")
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
    st.markdown('<h1 class="fd-title">Every error has a trail.</h1>', unsafe_allow_html=True)
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
        render_investigation(error, technology, language, environment, context, serp_key, groq_key)

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
