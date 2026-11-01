# Roblox Username Checker — Web Version

## Run locally
1. Install Python 3.10 or newer.
2. Open a terminal in this folder.
3. Run: `pip install -r requirements.txt`
4. Run: `streamlit run app.py`
5. Open the local URL shown in the terminal.

## Deploy free with Streamlit Community Cloud
1. Create a GitHub repository and upload `app.py` and `requirements.txt`.
2. Visit https://share.streamlit.io/ and sign in with GitHub.
3. Choose the repository, branch, and `app.py` as the main file.
4. Deploy. Streamlit will install the dependency from `requirements.txt`.

## Notes
- This is a browser-based rewrite of the original Tkinter desktop app.
- It checks usernames sequentially and includes a delay and retry handling for HTTP 429 rate limits.
- Roblox may change its endpoint, enforce additional limits, or return results that differ by signup/change context.
- Do not use this to spam Roblox or make automated account-creation attempts.
