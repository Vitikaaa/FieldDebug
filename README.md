# FieldDebug 🔎
**Let’s trace the failure.**

An AI-assisted debugging workspace that connects real-world search evidence with actionable fixes and outcome verification.

### What Makes FieldDebug Different?

- **Evidence-backed debugging:** Uses SerpApi to find relevant Google Search results, including original source links.
- **Actionable troubleshooting:** Turns an error into possible causes, suggested fixes, and verification steps.
- **Fix Verification Lab:** Developers apply fixes in their own environment and submit the resulting output for review.
- **Transparent results:** Distinguishes possible causes from verified outcomes instead of pretending every suggestion is correct.

### Tech Stack
Python · Streamlit · SerpApi · Groq (optional)

### Setup
Clone the repository, install dependencies, configure your API key in `.env`, and launch the Streamlit app.

```bash
git clone https://github.com/Vitikaaa/FieldDebug.git
cd FieldDebug
python -m venv .venv
```

Install dependencies on Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Create `.env` using `.env.example`, add your `SERPAPI_API_KEY`, then run:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

### Important
FieldDebug does not execute submitted code. Users apply fixes themselves and provide evidence for review.

