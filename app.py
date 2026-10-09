import os
import re
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


def search_web(error, technology, language, environment, context, api_key):
    """Search Google through SerpApi and return organic results."""
    query_parts = [
        f'"{error}"',
        technology,
        language,
        "fix troubleshooting",
    ]
    if environment.strip():
        query_parts.append(environment.strip())

    query = " ".join(part for part in query_parts if part)

    response = requests.get(
        SERPAPI_URL,
        params={
            "engine": "google",
            "q": query,
            "api_key": api_key,
            "num": 8,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    if payload.get("error"):
        raise RuntimeError(payload["error"])

    results = []
    for item in payload.get("organic_results", []):
        results.append({
            "title": item.get("title", "Untitled result"),
            "link": item.get("link", ""),
            "snippet": item.get("snippet", "No preview available."),
        })

    return query, results


def fallback_analysis(error, technology, results):
    """Give cautious suggestions if no AI key is configured."""
    text = error.lower()
    suggestions = []

    if "modulenotfounderror" in text or "no module named" in text:
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
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {
                    "role": "system",
                    "content": "Be accurate, cautious, practical, and transparent about uncertainty.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    return None, content


def render_fallback(report):
    st.markdown("### Initial assessment")
    st.write(report["summary"])

    st.markdown("### Possible causes")
    for cause in report["causes"]:
        st.write(f"- {cause}")

    st.markdown("### Suggested fixes")
    for index, fix in enumerate(report["fixes"], start=1):
        st.write(f"{index}. {fix}")

    st.markdown("### How to verify")
    for step in report["verification"]:
        st.checkbox(step, key="verify_" + str(abs(hash(step))))


def main():
    st.title("🐛 FieldDebug")
    st.subheader("Know what might be broken. Find evidence. Test the fix.")
    st.write(
        "A debugging research assistant that searches the web for relevant "
        "troubleshooting evidence and helps you test possible solutions."
    )

    with st.sidebar:
        st.header("Configuration")
        serp_key = st.text_input(
            "SerpApi API key",
            value=os.getenv("SERPAPI_API_KEY", ""),
            type="password",
            help="Get a key from your SerpApi account. Never share it publicly.",
        )
        groq_key = st.text_input(
            "Groq API key (optional)",
            value=os.getenv("GROQ_API_KEY", ""),
            type="password",
            help="Optional: enables AI-generated evidence summaries.",
        )
        st.caption(
            "Without a Groq key, FieldDebug uses rule-based troubleshooting hints. "
            "Web search requires a SerpApi key."
        )
        st.divider()
        st.caption("Prototype: suggestions are hypotheses, not guaranteed diagnoses.")

    with st.form("debug_form"):
        error = st.text_area(
            "Paste the error message",
            placeholder="Example: ModuleNotFoundError: No module named 'pandas'",
            height=130,
        )
        col1, col2 = st.columns(2)
        with col1:
            technology = st.selectbox(
                "Technology / framework",
                [
                    "Python",
                    "Java",
                    "JavaScript",
                    "React",
                    "Node.js",
                    "FastAPI",
                    "SQL / Database",
                    "AWS / Cloud",
                    "Other",
                ],
            )
            language = st.selectbox(
                "Programming language",
                ["Python", "Java", "JavaScript", "TypeScript", "SQL", "Other"],
            )
        with col2:
            environment = st.text_input(
                "Environment (optional)",
                placeholder="e.g. Windows 11, Python 3.13, VS Code",
            )
            context = st.text_input(
                "What were you trying to do? (optional)",
                placeholder="e.g. Install dependencies in a virtual environment",
            )
        submitted = st.form_submit_button(
            "🔎 Investigate error",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        if not error.strip():
            st.warning("Please paste the error message first.")
            return
        if not serp_key.strip():
            st.error("Add your SerpApi key in the sidebar to run a live search.")
            st.info("You can get a key from https://serpapi.com/")
            return

        try:
            with st.spinner("Searching the web for relevant troubleshooting evidence..."):
                query, results = search_web(
                    error.strip(),
                    technology,
                    language,
                    environment,
                    context,
                    serp_key.strip(),
                )

            st.session_state["fielddebug_query"] = query
            st.session_state["fielddebug_results"] = results
            st.session_state["fielddebug_error"] = error.strip()

            st.success(f"Search complete — found {len(results)} organic results.")
            with st.expander("See the exact search query"):
                st.code(query)

            if not results:
                st.warning(
                    "No organic results were returned. Try a shorter error message "
                    "or include the exact exception name."
                )

            with st.spinner("Preparing troubleshooting guidance..."):
                fallback, ai_text = ai_analysis(
                    error.strip(),
                    technology,
                    language,
                    environment,
                    context,
                    results,
                    groq_key.strip(),
                )

            st.divider()
            st.header("Investigation report")
            if ai_text:
                st.markdown(ai_text)
                st.caption("AI-generated analysis. Verify each suggestion against the sources.")
            else:
                render_fallback(fallback)
                st.caption("Rule-based guidance. Add a Groq key for an AI evidence summary.")

            st.divider()
            st.header("Evidence from the web")
            if results:
                for index, item in enumerate(results, start=1):
                    with st.container(border=True):
                        st.markdown(f"**{index}. [{item['title']}]({item['link']})**")
                        st.write(item["snippet"])
                        st.caption("Open the source to verify whether it matches your environment.")
            else:
                st.write("No sources to display.")

            st.download_button(
                "Download investigation report",
                data=(
                    f"FieldDebug investigation\n\n"
                    f"Error: {error.strip()}\n"
                    f"Search query: {query}\n\n"
                    + "\n\n".join(
                        f"{i}. {r['title']}\n{r['link']}\n{r['snippet']}"
                        for i, r in enumerate(results, start=1)
                    )
                ),
                file_name="fielddebug_report.txt",
                mime="text/plain",
            )

        except requests.HTTPError as exc:
            st.error(
                f"An API request returned an HTTP error: {exc}. "
                "Check your API key, quota, and account status."
            )
            if exc.response is not None:
                st.code(exc.response.text[:1500])
        except requests.RequestException as exc:
            st.error(f"Network request failed: {exc}")
        except (KeyError, ValueError, RuntimeError) as exc:
            st.error(f"Could not process the response: {exc}")
        except Exception as exc:
            st.error(f"Unexpected error: {exc}")

    else:
        st.divider()
        st.markdown("### What FieldDebug does")
        col1, col2, col3 = st.columns(3)
        col1.markdown("**1. Search**\n\nFind current web pages related to the error.")
        col2.markdown("**2. Investigate**\n\nGenerate cautious troubleshooting hypotheses.")
        col3.markdown("**3. Verify**\n\nRead the sources and test one fix at a time.")


if __name__ == "__main__":
    main()
