# FieldDebug

**Let’s trace the failure.**

FieldDebug helps developers investigate an error by searching Google through SerpApi, displaying source links and snippets, and presenting cautious troubleshooting guidance. Search is central to the workflow: the user can inspect current evidence before testing a suggested fix.

## Features

- Error, technology, language, environment, and task context inputs
- Live Google Search API requests through SerpApi, with source attribution
- Optional Groq analysis grounded in retrieved snippets; rule-based fallback when absent or unavailable
- Specific fallback checks for common Python, Java, JavaScript/Node, HTTP, network, database, configuration, and dependency errors
- Downloadable report containing the actual investigation and evidence
- **Fix Verification Lab:** choose a suggested fix, paste the result from your own run, compare before and after, and keep a session-only verification history

## Architecture and data flow

Streamlit form → query builder → SerpApi Google Search API → normalized organic results → optional Groq evidence analysis or local rule-based guidance → source cards, verification checklist, and text report. API keys are read from local environment variables or password fields in the sidebar. The app does not persist investigations.

## Setup (Windows PowerShell)

Python 3.10 or newer is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `SERPAPI_API_KEY` in `.env` for live search. `GROQ_API_KEY` is optional. The default Groq model is `llama-3.3-70b-versatile`; set `GROQ_MODEL` to a model available to your Groq account if needed. Keys can also be entered privately in the sidebar. Never commit `.env` or paste secrets into issue reports, screenshots, or chat.

Launch:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests mock outbound search requests and do not consume API quota.

## Example

Enter `ModuleNotFoundError: No module named 'pandas'`, choose Python, and specify the active OS/runtime. FieldDebug searches that error with the selected context, shows matching web evidence, then suggests checks such as installing into the same interpreter environment and verifying with `python -m pip show pandas`.

After reviewing the suggestions, use Fix Verification Lab to select one, apply it yourself, and paste the output or explicitly confirm the issue is resolved. FieldDebug classifies the supplied evidence as resolved, still failing, or needing review; it never executes user code and does not claim to have independently run a fix. Verification attempts remain in Streamlit session state and are cleared when the session ends or the user clears history.

## Limitations, security, and privacy

Search snippets can be incomplete or outdated, and keyword-based guidance is not a diagnosis. Open the linked source and verify every change in the target environment. Do not submit passwords, access tokens, private keys, confidential source code, or sensitive user data. The error/context and search query go to SerpApi; if Groq is enabled, the error, context, and retrieved result snippets are sent to Groq. Review both providers' terms and privacy policies. API usage is subject to account quotas and possible charges. No live provider call is claimed by this repository documentation.

## Hackathon disclosure and readiness

SerpApi's Google Search API is used to retrieve live, relevant troubleshooting pages; those sources materially inform the investigation and are shown to the user. Optional inference uses Groq. Development AI tools must be disclosed in the submission form according to the current rules.

The official rules currently specify a public GitHub repository, project details submitted through the authenticated hackathon website, a publicly accessible demo video under three minutes, SerpApi usage explanation, and AI-tool disclosure. Deadline: **October 10, 2026 at 23:59 IST**. A saved draft is not a submission; complete the form and select Submit project. See [official rules](https://serpapi.github.io/serpapi-india-hackathon-2026/rules.html) and [event page](https://serpapi.github.io/serpapi-india-hackathon-2026/).

## Screenshots

Screenshots will be added after capturing the working application. No placeholder images are presented as real product screenshots.

## Deployment

The app can be hosted on Streamlit Community Cloud or another Streamlit host by configuring `SERPAPI_API_KEY` as a platform secret and optionally `GROQ_API_KEY`/`GROQ_MODEL`. No deployment is currently claimed or configured in this repository.
