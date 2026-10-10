# FieldDebug demo (under 3 minutes)

Use a SerpApi key configured privately in the local environment. Do not show key fields, environment files, or terminal secrets in the recording. Confirm live search is working before recording; do not present a mocked response as live.

1. **0:00–0:20 — Problem and goal.** Introduce FieldDebug: “Know what might be broken. Find evidence. Test the fix.” Explain that a traceback alone may not identify which environment or version matters.
2. **0:20–0:45 — Enter a real investigation.** Paste `ModuleNotFoundError: No module named 'pandas'`; select Python for technology and language; provide the actual OS/runtime and context “running a script from a virtual environment.”
3. **0:45–1:25 — Live search.** Click Investigate Error. Show the query and organic search results with titles, snippets, and clickable sources. Open a source and briefly check that its instructions match the scenario.
4. **1:25–2:15 — Guidance and verification.** Show Groq analysis if configured, otherwise clearly show the rule-based label. Walk through the likely environment mismatch hypothesis, the `python -m pip show pandas` check, and the verification checklist. State that the hypothesis is not a confirmed diagnosis.
5. **2:15–2:40 — Report and close.** Download the report and show that it contains this error, environment, query, findings, and source URLs. Remind viewers to verify fixes against the evidence.

Record the app running locally. Keep the final video below three minutes and test its share link in a private browser window before submission. If no API key is available, do not claim a live search; record after configuring one or clearly disclose the limitation.
