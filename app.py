import csv
import io
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import streamlit as st

APP_TITLE = "Roblox Username Checker"
API_URL = "https://auth.roblox.com/v1/usernames/validate"
SPLIT_RE = re.compile(r"[^A-Za-z0-9_]+")
CODE_VALID = 0
CODE_IN_USE = 1


def parse_usernames(raw_text):
    return [token for token in SPLIT_RE.split(raw_text or "") if token]


def check_username(username, context="UsernameChange", timeout=15):
    query = urllib.parse.urlencode({
        "request.username": username,
        "request.birthday": "2000-01-01T00:00:00.000Z",
        "request.context": context,
    })
    request = urllib.request.Request(
        API_URL + "?" + query,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                return "RATE_LIMITED", max(float(retry_after), 5.0)
            except (TypeError, ValueError):
                return "RATE_LIMITED", 10.0
        return "ERROR", f"HTTP {exc.code}"
    except (urllib.error.URLError, ValueError, TimeoutError, OSError) as exc:
        return "ERROR", f"{type(exc).__name__}: {exc}"

    code = payload.get("code")
    message = payload.get("message", "")
    if code == CODE_VALID:
        return "AVAILABLE", message or "Username is valid"
    if code == CODE_IN_USE:
        return "TAKEN", message or "Username is already in use"
    return "INVALID", message or f"Rejected (code {code})"


def run_checker(job, names, delay, context, timeout, max_retries):
    for index, name in enumerate(names, start=1):
        while job["pause_event"].is_set() is False and not job["stop_event"].is_set():
            time.sleep(0.15)
        if job["stop_event"].is_set():
            break

        attempt = 0
        while True:
            if job["stop_event"].is_set():
                break
            status, detail = check_username(name, context, timeout)
            if status != "RATE_LIMITED":
                break
            attempt += 1
            if attempt > max_retries:
                status, detail = "ERROR", f"Rate limited (gave up after {max_retries} retries)"
                break
            wait_seconds = max(float(detail), delay, 5.0) * attempt
            with job["lock"]:
                job["notice"] = f"Roblox rate-limited the request. Waiting {wait_seconds:.0f}s before retrying."
            end_time = time.time() + wait_seconds
            while time.time() < end_time and not job["stop_event"].is_set():
                time.sleep(0.2)

        if job["stop_event"].is_set():
            break
        with job["lock"]:
            job["results"].append({
                "number": index,
                "username": name,
                "status": status,
                "detail": detail,
            })
            job["notice"] = ""
        if delay > 0 and index < len(names):
            end_time = time.time() + delay
            while time.time() < end_time and not job["stop_event"].is_set():
                while not job["pause_event"].is_set() and not job["stop_event"].is_set():
                    time.sleep(0.15)
                time.sleep(0.1)

    with job["lock"]:
        job["running"] = False
        job["finished"] = not job["stop_event"].is_set()
        job["stopped"] = job["stop_event"].is_set()


st.set_page_config(page_title=APP_TITLE, page_icon="🔎", layout="wide")
st.title("🔎 Roblox Username Checker")
st.caption("Bulk-check candidate usernames using Roblox's public username validation endpoint.")

with st.sidebar:
    st.subheader("Settings")
    delay = st.number_input("Delay between checks (seconds)", min_value=0.0, max_value=60.0, value=1.0, step=0.5)
    timeout = st.number_input("Request timeout (seconds)", min_value=1, max_value=120, value=15)
    retries = st.number_input("Rate-limit retries", min_value=0, max_value=10, value=3)
    context_label = st.selectbox("Check as", ["UsernameChange", "Signup"])
    dedupe = st.checkbox("Skip duplicates", value=True)
    st.caption("This version checks one username at a time to reduce the chance of rate limiting.")

st.subheader("1. Add usernames")
pasted = st.text_area(
    "Paste usernames (separate them with commas, spaces, semicolons, or new lines)",
    height=160,
    placeholder="CoolName123\nAnother_Name\nExampleUser",
)
uploaded = st.file_uploader("Or upload a .txt or .csv file", type=["txt", "csv"])
raw = pasted
if uploaded is not None:
    try:
        uploaded_text = uploaded.getvalue().decode("utf-8-sig", errors="replace")
        raw = (raw + "\n" + uploaded_text).strip()
    except Exception as exc:
        st.error(f"Could not read uploaded file: {exc}")

names = parse_usernames(raw)
if dedupe:
    unique_names = []
    seen = set()
    for item in names:
        if item.lower() not in seen:
            seen.add(item.lower())
            unique_names.append(item)
    names = unique_names

st.caption(f"{len(names)} username(s) ready to check.")

if "job" not in st.session_state:
    st.session_state.job = None


def start_job():
    job = {
        "results": [],
        "running": True,
        "finished": False,
        "stopped": False,
        "notice": "",
        "lock": threading.Lock(),
        "pause_event": threading.Event(),
        "stop_event": threading.Event(),
    }
    job["pause_event"].set()
    thread = threading.Thread(
        target=run_checker,
        args=(job, list(names), float(delay), context_label, int(timeout), int(retries)),
        daemon=True,
    )
    job["thread"] = thread
    st.session_state.job = job
    thread.start()


col1, col2 = st.columns([1, 3])
with col1:
    if st.button("Start checking", type="primary", disabled=not names or (st.session_state.job and st.session_state.job.get("running"))):
        start_job()
        st.rerun()
with col2:
    if names:
        st.write(f"Estimated minimum time: about {max(0, len(names)-1) * delay:.0f} seconds, excluding network delays.")

job = st.session_state.job
if job is not None:
    @st.fragment(run_every="1s")
    def live_results():
        with job["lock"]:
            results = list(job["results"])
            running = job["running"]
            notice = job["notice"]
            stopped = job["stopped"]
            finished = job["finished"]

        total = len(names) if names else max(len(results), 1)
        st.subheader("2. Results")
        st.progress(min(len(results) / max(total, 1), 1.0), text=f"{len(results)} / {total} checked")
        if notice:
            st.warning(notice)
        if running:
            left, right = st.columns(2)
            with left:
                if st.button("Pause" if job["pause_event"].is_set() else "Resume", key="pause_resume"):
                    if job["pause_event"].is_set():
                        job["pause_event"].clear()
                    else:
                        job["pause_event"].set()
                    st.rerun()
            with right:
                if st.button("Stop", key="stop_check"):
                    job["stop_event"].set()
                    job["pause_event"].set()
                    st.rerun()
            st.info("Checking in the background. You can pause or stop the run.")
        elif stopped:
            st.warning("Checking stopped. Results collected so far are shown below.")
        elif finished:
            st.success("All usernames checked.")

        if results:
            st.dataframe(results, use_container_width=True, hide_index=True)
            counts = {}
            for row in results:
                counts[row["status"]] = counts.get(row["status"], 0) + 1
            metric_cols = st.columns(4)
            for col, label in zip(metric_cols, ["AVAILABLE", "TAKEN", "INVALID", "ERROR"]):
                col.metric(label.title(), counts.get(label, 0))

            available = [r["username"] for r in results if r["status"] == "AVAILABLE"]
            all_csv = io.StringIO()
            writer = csv.DictWriter(all_csv, fieldnames=["number", "username", "status", "detail"])
            writer.writeheader()
            writer.writerows(results)
            dl1, dl2 = st.columns(2)
            with dl1:
                st.download_button(
                    "Download available usernames (.txt)",
                    data=("\n".join(available) + ("\n" if available else "")),
                    file_name="available_usernames.txt",
                    mime="text/plain",
                    disabled=not available,
                )
            with dl2:
                st.download_button(
                    "Download all results (.csv)",
                    data=all_csv.getvalue(),
                    file_name="username_results.csv",
                    mime="text/csv",
                )

    live_results()
