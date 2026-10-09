# FieldDebug 🐛

**An evidence-backed debugging research assistant powered by SerpApi.**

FieldDebug searches the web for troubleshooting information related to a user's error, shows source links, and provides cautious debugging suggestions. It is a prototype: it does not guarantee the root cause.

## Features

- Live Google search results through SerpApi
- Error, technology, language, and environment inputs
- Optional Groq-powered evidence summarization
- Rule-based troubleshooting fallback when Groq is not configured
- Source links and downloadable investigation notes

## Requirements

- Python 3.10 or newer
- A SerpApi API key
- Optional Groq API key for AI-generated analysis

## Run locally (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `.env` and add your keys:

```text
SERPAPI_API_KEY=your_serpapi_key_here
GROQ_API_KEY=your_groq_key_here
```

The Groq key is optional. Do not commit `.env` or expose API keys in screenshots, recordings, or GitHub.

Start the app:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Streamlit prints a local URL, usually http://localhost:8501.

## How it works

1. The user enters an error and optional environment details.
2. FieldDebug sends a Google search query to SerpApi.
3. It displays organic result titles, snippets, and links.
4. If Groq is configured, the app asks the model to analyze the supplied evidence. Otherwise, it uses basic rule-based troubleshooting hints.
5. The user checks sources and verifies a fix.

## Responsible use

- Suggestions are hypotheses, not confirmed diagnoses.
- Search snippets can be incomplete or outdated. Open the source before acting.
- Never paste passwords, tokens, private keys, or confidential code into the app.
- API usage may incur costs or be subject to provider quotas.

## Technology stack

Python, Streamlit, Requests, SerpApi Google Search API, python-dotenv, optional Groq API.

## AI/tool disclosure

This project uses SerpApi for web search. When a Groq API key is configured, it uses a Groq-hosted language model to summarize evidence. Without that key, it uses rule-based hints. Development assistance from AI tools should be disclosed according to the hackathon's current rules.
