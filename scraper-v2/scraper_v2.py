"""
Fast Dolphin LATAM Lead Finder — Scraper V2
Multi-prompt, consultant-specific, Google Sheet driven.
"""

import os
import re
import json
import time
import random
import smtplib
import anthropic
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo
from html import escape as html_escape

import gspread
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ─── Constants ────────────────────────────────────────────────────────────────
EASTERN = ZoneInfo("America/New_York")
SHEET_ID = os.environ["V2_SHEET_ID"]
GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
MAX_DAYS = 30
MAX_PAGES = 5
MAX_JOBS_PER_KEYWORD = 50  # Safety limit per keyword
MAX_RUN_MINUTES = 18
MIN_DESCRIPTION_CHARS = 100                 # shorter than this = description "not captured"
UNVERIFIED_MARKER = "Description not captured"   # text in AI Reason that flags a job for manual review
ERROR_PAGE_PATTERN = re.compile(
    r"^\s*(40\d|50\d)\b|bad gateway|service unavailable|access denied|just a moment|page not found",
    re.IGNORECASE)
DEFAULT_EMP_FILTER = "CONTRACTS%7CTHIRD_PARTY"

# Consultant notification settings
INTERNAL_DOMAIN = "fastdolphin.com"
DEFAULT_CONSULTANT_CC = "mariana.esparza@fastdolphin.com"
DEFAULT_CONSULTANT_BCC = ("ramon.osuna@fastdolphin.com, daniel.riojas@fastdolphin.com, "
                          "carlos.guerrero@fastdolphin.com")
CONSULTANT_EMAIL_MAX_JOBS = 30   # jobs listed in the consultant email (rest: "and N more")

# Rows every prompt tab has / extra rows only the Consultant 1-5 tabs have.
# Each is inserted once, just above the "Prompt" row.
LAST_RUN_ROW = ["Last Run", ""]
CONSULTANT_ROWS = [
    ["Share Sheet ID", ""],
    ["Consultant Email", ""],
    ["Consultant CC", DEFAULT_CONSULTANT_CC],
    ["Consultant BCC", DEFAULT_CONSULTANT_BCC],
    ["Notify Consultant", "NO"],
]

# Tab names
PROMPT_TABS = [
    ("LATAM Prompt",        "LATAM Results"),
    ("Consultant 1 Prompt", "Consultant 1 Results"),
    ("Consultant 2 Prompt", "Consultant 2 Results"),
    ("Consultant 3 Prompt", "Consultant 3 Results"),
    ("Consultant 4 Prompt", "Consultant 4 Results"),
    ("Consultant 5 Prompt", "Consultant 5 Results"),
]

RESULTS_HEADERS = [
    "Job Title", "Company", "Recruiter", "Location", "Employment Type",
    "Work Type", "Corp to Corp", "Contract Duration", "Pay",
    "Posted Date", "Keyword", "AI Reason", "Run Date", "Run Time",
    "Job URL", "FD Notes"
]

def is_unverified(reason):
    """True when a job was kept only because its description could not be captured."""
    return UNVERIFIED_MARKER in str(reason or "")[:60]

# ─── Google Sheets ────────────────────────────────────────────────────────────
def get_sheets_client():
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def with_retry(func, retries=3, delay=10):
    """Retry a function on API errors."""
    for attempt in range(retries):
        try:
            return func()
        except Exception as e:
            if attempt < retries - 1:
                print(f"  ⚠️ API error (attempt {attempt+1}/{retries}): {e}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                raise

def reformat_existing_prompt_tab(ws, tab_name):
    """Completely rebuild an existing prompt tab with new structure."""
    # Expand columns if needed
    if ws.col_count < 26:
        ws.spreadsheet.batch_update({"requests": [{
            "appendDimension": {
                "sheetId": ws.id,
                "dimension": "COLUMNS",
                "length": max(0, 26 - ws.col_count)
            }
        }]})
    # Wipe and re-setup from scratch
    ws.clear()
    setup_prompt_tab(ws, tab_name)
    print(f"✅ Reformatted: {tab_name}")

def yes_no_validation_request(sheet_id, row_idx):
    """Data-validation request: a YES/NO dropdown on column B of the given row (0-based)."""
    return {"setDataValidation": {
        "range": {"sheetId": sheet_id, "startRowIndex": row_idx, "endRowIndex": row_idx + 1,
                  "startColumnIndex": 1, "endColumnIndex": 2},
        "rule": {"condition": {"type": "ONE_OF_LIST", "values": [
            {"userEnteredValue": "YES"}, {"userEnteredValue": "NO"}
        ]}, "showCustomUi": True, "strict": True}
    }}

def format_new_rows(ws, start_idx, labels):
    """Style newly inserted label cells like the others and add the YES/NO dropdown."""
    requests = [{"repeatCell": {
        "range": {"sheetId": ws.id, "startRowIndex": start_idx,
                  "endRowIndex": start_idx + len(labels),
                  "startColumnIndex": 0, "endColumnIndex": 1},
        "cell": {"userEnteredFormat": {
            "textFormat": {"bold": True},
            "backgroundColor": {"red": 0.85, "green": 0.90, "blue": 0.97}}},
        "fields": "userEnteredFormat(textFormat,backgroundColor)"
    }}]
    if "Notify Consultant" in labels:
        requests.append(yes_no_validation_request(ws.id, start_idx + labels.index("Notify Consultant")))
    ws.spreadsheet.batch_update({"requests": requests})

def ensure_sheet_structure(gc):
    """Make sure all 12 tabs exist with correct structure."""
    sh = gc.open_by_key(SHEET_ID)
    existing = [ws.title for ws in sh.worksheets()]

    for prompt_tab, results_tab in PROMPT_TABS:
        # Create prompt tab if missing
        if prompt_tab not in existing:
            ws = sh.add_worksheet(title=prompt_tab, rows=1000, cols=26)
            setup_prompt_tab(ws, prompt_tab)
            print(f"✅ Created prompt tab: {prompt_tab}")
        else:
            # Ensure the extra rows exist in existing tabs (each inserted only once,
            # all in a single API call, just above the "Prompt" row).
            ws = sh.worksheet(prompt_tab)
            data = ws.get_all_values()
            fields = [row[0].strip() for row in data if row]
            wanted = [LAST_RUN_ROW] + ([] if prompt_tab.startswith("LATAM") else CONSULTANT_ROWS)
            missing = [list(r) for r in wanted if r[0] not in fields]
            if missing:
                for i, row in enumerate(data):
                    if row and row[0].strip() == "Prompt":
                        ws.insert_rows(missing, row=i + 1)
                        print(f"✅ Added rows to {prompt_tab}: {', '.join(r[0] for r in missing)}")
                        try:
                            format_new_rows(ws, i, [r[0] for r in missing])
                        except Exception as e:   # cosmetic only — never fail the run for this
                            print(f"  ⚠️ Could not style new rows in {prompt_tab}: {e}")
                        break
            print(f"ℹ️  Tab exists: {prompt_tab}")

        # Create results tab if missing
        if results_tab not in existing:
            ws = sh.add_worksheet(title=results_tab, rows=2000, cols=20)
            setup_results_tab(ws)
            print(f"✅ Created results tab: {results_tab}")

def setup_prompt_tab(ws, tab_name):
    """Initialize a prompt tab with default structure."""
    is_latam = "LATAM" in tab_name
    default_keywords = "mexico,spanish,brazil,brasil,argentina,colombia,ecuador,costa rica,panama,portuguese,latam,latin america,maquiladora,chile,bolivia,peru" if is_latam else ""
    default_prompt = LATAM_PROMPT if is_latam else ""

    rows = [
        ["Field", "Value"],
        ["Status", "OFF"],
        ["Name", "LATAM" if is_latam else ""],
        ["Frequency", "2x daily"],
        ["Time 1", "08:00 AM ET"],
        ["Time 2", "03:30 PM ET"],
        ["Time 3", ""],
        ["Emails", ""],
        ["Notification", "Email on completion"],
        ["Keywords", default_keywords],
        ["Date Range", "1"],
        ["Job Retention", "30"],
        ["Employment Type", "(select below)"],
        ["→ Contract W2", True],
        ["→ Third Party", True],
        ["→ Contract Independent", False],
        ["→ Full Time", False],
        ["→ Part Time", False],
        list(LAST_RUN_ROW),
    ]
    if not is_latam:
        rows += [list(r) for r in CONSULTANT_ROWS]
    rows.append(["Prompt", default_prompt])
    ws.update('A1', rows)

    # Header row: dark background, white bold text
    ws.format("A1:B1", {
        "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
        "backgroundColor": {"red": 0.13, "green": 0.29, "blue": 0.53}
    })
    # Field labels: bold, light blue background (every row above "Prompt")
    prompt_row_idx = next(i for i, r in enumerate(rows) if r[0] == "Prompt")
    ws.format(f"A2:A{prompt_row_idx}", {
        "textFormat": {"bold": True},
        "backgroundColor": {"red": 0.85, "green": 0.90, "blue": 0.97}
    })
    # Employment type sub-rows: slightly indented style
    ws.format("A14:A18", {
        "textFormat": {"bold": False, "italic": True},
        "backgroundColor": {"red": 0.92, "green": 0.95, "blue": 0.99}
    })
    # Employment Type header row
    ws.format("A13:B13", {
        "textFormat": {"bold": True},
        "backgroundColor": {"red": 0.75, "green": 0.85, "blue": 0.95}
    })

    # Dropdowns and checkboxes
    ws.spreadsheet.batch_update({"requests": [
        # Status: ON/OFF dropdown
        {"setDataValidation": {
            "range": {"sheetId": ws.id, "startRowIndex": 1, "endRowIndex": 2,
                      "startColumnIndex": 1, "endColumnIndex": 2},
            "rule": {"condition": {"type": "ONE_OF_LIST", "values": [
                {"userEnteredValue": "ON"}, {"userEnteredValue": "OFF"}
            ]}, "showCustomUi": True, "strict": True}
        }},
        # Frequency dropdown
        {"setDataValidation": {
            "range": {"sheetId": ws.id, "startRowIndex": 3, "endRowIndex": 4,
                      "startColumnIndex": 1, "endColumnIndex": 2},
            "rule": {"condition": {"type": "ONE_OF_LIST", "values": [
                {"userEnteredValue": "1x daily"},
                {"userEnteredValue": "2x daily"},
                {"userEnteredValue": "3x daily"},
                {"userEnteredValue": "weekdays only 1x"},
                {"userEnteredValue": "weekdays only 2x"}
            ]}, "showCustomUi": True, "strict": True}
        }},
        # Notification dropdown
        {"setDataValidation": {
            "range": {"sheetId": ws.id, "startRowIndex": 8, "endRowIndex": 9,
                      "startColumnIndex": 1, "endColumnIndex": 2},
            "rule": {"condition": {"type": "ONE_OF_LIST", "values": [
                {"userEnteredValue": "Email on completion"},
                {"userEnteredValue": "No email"}
            ]}, "showCustomUi": True, "strict": True}
        }},
        # Date Range dropdown (rows 1-30)
        {"setDataValidation": {
            "range": {"sheetId": ws.id, "startRowIndex": 10, "endRowIndex": 11,
                      "startColumnIndex": 1, "endColumnIndex": 2},
            "rule": {"condition": {"type": "ONE_OF_LIST", "values": [
                {"userEnteredValue": str(i)} for i in range(1, 31)
            ]}, "showCustomUi": True, "strict": True}
        }},
        # Job Retention dropdown
        {"setDataValidation": {
            "range": {"sheetId": ws.id, "startRowIndex": 11, "endRowIndex": 12,
                      "startColumnIndex": 1, "endColumnIndex": 2},
            "rule": {"condition": {"type": "ONE_OF_LIST", "values": [
                {"userEnteredValue": str(i)} for i in [1,5,10,15,20,25,30,35,40,45]
            ]}, "showCustomUi": True, "strict": True}
        }},
        # Employment Type checkboxes (rows 14-18, index 13-17)
        {"setDataValidation": {
            "range": {"sheetId": ws.id, "startRowIndex": 13, "endRowIndex": 18,
                      "startColumnIndex": 1, "endColumnIndex": 2},
            "rule": {"condition": {"type": "BOOLEAN"}, "showCustomUi": True}
        }},
    ]})

    # Notify Consultant: YES/NO dropdown (Consultant 1-5 tabs only)
    if not is_latam:
        notify_idx = next(i for i, r in enumerate(rows) if r[0] == "Notify Consultant")
        ws.spreadsheet.batch_update({"requests": [yes_no_validation_request(ws.id, notify_idx)]})

def setup_results_tab(ws):
    """Initialize a results tab with headers."""
    ws.append_row(RESULTS_HEADERS)
    ws.format(f"A1:P1", {"textFormat": {"bold": True}})
    ws.set_basic_filter()

def read_prompt_config(gc, prompt_tab):
    """Read config from a prompt tab. Returns None if OFF or invalid."""
    sh = gc.open_by_key(SHEET_ID)
    try:
        ws = sh.worksheet(prompt_tab)
    except:
        return None

    data = ws.get_all_values()
    config = {}
    for row in data:
        if len(row) >= 2 and row[0].strip():
            config[row[0].strip()] = row[1].strip() if len(row) > 1 else ""

    if config.get("Status", "OFF").upper() != "ON":
        return None

    # Employment types from checkboxes
    emp_types = []
    emp_map = {
        "→ Contract W2": "CONTRACTS",
        "→ Third Party": "THIRD_PARTY",
        "→ Contract Independent": "CONTRACT_INDEPENDENT",
        "→ Full Time": "FULLTIME",
        "→ Part Time": "PARTTIME",
    }
    for label, code in emp_map.items():
        val = config.get(label, "FALSE").upper()
        if val in ("TRUE", "YES", "1"):
            emp_types.append(code)
    if not emp_types:
        emp_types = ["CONTRACTS", "THIRD_PARTY"]  # default

    # Date range
    try:
        date_range = int(config.get("Date Range", "1"))
        date_range = max(1, min(30, date_range))
    except:
        date_range = 1

    # Job retention
    try:
        job_retention = int(config.get("Job Retention", "30"))
    except:
        job_retention = 30

    # Notification
    send_email = config.get("Notification", "Email on completion") != "No email"

    return {
        "name": config.get("Name", ""),
        "frequency": config.get("Frequency", "2x daily"),
        "time1": config.get("Time 1", ""),
        "time2": config.get("Time 2", ""),
        "time3": config.get("Time 3", ""),
        "emails": [e.strip() for e in config.get("Emails", "").split(",") if e.strip()],
        "send_email": send_email,
        "keywords": [k.strip() for k in config.get("Keywords", "").split(",") if k.strip()],
        "date_range": date_range,
        "job_retention": job_retention,
        "emp_types": emp_types,
        "prompt": config.get("Prompt", ""),
        "last_run": config.get("Last Run", ""),
        "share_sheet_id": extract_sheet_id(config.get("Share Sheet ID", "")),
        "consultant_email": parse_email_list(config.get("Consultant Email", "")),
        "consultant_cc": parse_email_list(config.get("Consultant CC", "")),
        "consultant_bcc": parse_email_list(config.get("Consultant BCC", "")),
        "notify_consultant": config.get("Notify Consultant", "NO").strip().upper() == "YES",
    }

def parse_email_list(value):
    """Split a cell into email addresses (commas, semicolons or new lines). Drops junk."""
    out = []
    for token in re.split(r"[,;\n]", value or ""):
        token = token.strip()
        if not token:
            continue
        if "@" in token and " " not in token:
            out.append(token)
        else:
            print(f"  ⚠️ Ignoring invalid email address: '{token}'")
    return out

def extract_sheet_id(value):
    """Accept either a bare Google Sheet ID or a full sheet URL; return the ID."""
    value = (value or "").strip()
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", value)
    return m.group(1) if m else value

def is_due_to_run(config):
    """Check if this prompt is due to run based on scheduled times and last run."""
    now = datetime.now(EASTERN)

    times = [config["time1"], config["time2"], config["time3"]]
    times = [t for t in times if t.strip()]

    if not times:
        return False

    # Parse all scheduled times into today's datetime objects
    scheduled_times = []
    for t in times:
        try:
            t_clean = t.replace(" ET", "").strip()
            scheduled = datetime.strptime(t_clean, "%I:%M %p").replace(
                year=now.year, month=now.month, day=now.day, tzinfo=EASTERN
            )
            scheduled_times.append(scheduled)
        except:
            continue

    if not scheduled_times:
        return False

    # Find the most recent scheduled time that has already passed today
    past_times = [t for t in scheduled_times if t <= now]
    if not past_times:
        return False

    most_recent_scheduled = max(past_times)

    # Check if we already ran after this scheduled time
    last_run_str = config.get("last_run", "").strip()
    if last_run_str:
        try:
            last_run = datetime.fromisoformat(last_run_str)
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=EASTERN)
            # If last run was AFTER the most recent scheduled time, skip
            if last_run >= most_recent_scheduled:
                return False
        except:
            pass

    # Due to run — scheduled time has passed and we haven't run since then
    return True

def rename_tabs_if_needed(gc, prompt_tab, results_tab, consultant_name):
    """Rename tabs if consultant name has changed."""
    if not consultant_name or consultant_name in ("LATAM", ""):
        return prompt_tab, results_tab

    sh = gc.open_by_key(SHEET_ID)
    new_prompt = f"{consultant_name} Prompt"
    new_results = f"{consultant_name} Results"

    try:
        ws = sh.worksheet(prompt_tab)
        if ws.title != new_prompt:
            ws.update_title(new_prompt)
            print(f"✅ Renamed '{prompt_tab}' → '{new_prompt}'")
    except:
        pass

    try:
        ws = sh.worksheet(results_tab)
        if ws.title != new_results:
            ws.update_title(new_results)
            print(f"✅ Renamed '{results_tab}' → '{new_results}'")
    except:
        pass

    return new_prompt, new_results

# ─── Selenium ─────────────────────────────────────────────────────────────────
def create_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    return driver

def safe_text(driver, *selectors):
    for sel in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            text = el.text.strip()
            if text:
                return text
        except:
            continue
    return ""

def extract_posted_date(driver):
    selectors = ["li[data-cy='posted-date']", "[data-testid='posted-date']",
                 "span[data-cy='posted-date']", "time"]
    for sel in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            text = el.text.strip()
            if text:
                return text
            dt = el.get_attribute("datetime")
            if dt:
                return dt
        except:
            continue
    try:
        body = driver.find_element(By.TAG_NAME, "body").text
        for pattern in [r'Posted[:\s]+([^\n]+)', r'(\d+\s+days?\s+ago)',
                        r'(\d+\s+hours?\s+ago)', r'(Today|Yesterday)']:
            m = re.search(pattern, body, re.IGNORECASE)
            if m:
                return m.group(1).strip()
    except:
        pass
    return "Unknown"

def extract_description(driver):
    description = ""
    for attempt in range(3):
        for sel in ["div.job-description", "[data-testid='jobDescriptionHtml']",
                    "div[class*='description']", "section[class*='description']"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                text = el.text.strip()
                if len(text) > 100:
                    return text
            except:
                continue
        if attempt < 2:
            time.sleep(2)
    # Fallback 1: the visible page text, starting at the "Job Details" section
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text.strip()
        idx = page_text.find("Job Details")
        chunk = page_text[idx:] if idx >= 0 else page_text
        if len(chunk) > MIN_DESCRIPTION_CHARS:
            print("  ⚠️ Used page-text fallback for the description")
            return chunk[:6000]
    except:
        pass
    # Fallback 2: the skills tags
    try:
        skills_els = driver.find_elements(By.CSS_SELECTOR,
            "div.skill-tag, span.skill, [data-testid='skill']")
        skills = [s.text.strip() for s in skills_els if s.text.strip()]
        if skills:
            description = f"Skills required: {', '.join(skills)}."
            print(f"  ⚠️ Skills fallback: {', '.join(skills[:5])}")
    except:
        pass
    return description

def extract_badges(driver):
    emp_types, pay, work_type, corp, duration = [], "", "", "", ""
    try:
        badges = driver.find_elements(By.CSS_SELECTOR, "div.SeuiInfoBadge div.font-medium")
        for b in badges:
            text = b.text.strip()
            if not text:
                continue
            tl = text.lower()
            if any(x in tl for x in ["$/hr", "$/year", "/hr", "/year", "k/yr"]):
                pay = text
            elif any(x in tl for x in ["remote", "hybrid", "on-site", "onsite"]):
                work_type = text
            elif "corp to corp" in tl or "c2c" in tl:
                corp = text
            elif "month" in tl:
                duration = text
            else:
                emp_types.append(text)
    except:
        pass
    return ", ".join(emp_types), pay, work_type, corp, duration

def _parse_card(card):
    """Return {url, title, company, location} for one search-result card, or None."""
    job_url = ""
    for url_sel in ['a[data-testid="job-search-job-card-link"]',
                    'a[data-testid="job-search-job-detail-link"]',
                    'a[href*="job-detail"]']:
        try:
            job_url = card.find_element(By.CSS_SELECTOR, url_sel).get_attribute("href")
            if job_url:
                break
        except:
            continue

    title = ""
    for title_sel in ['a[data-testid="job-search-job-detail-link"]',
                      'a[data-testid="job-search-job-card-link"]',
                      'h5', 'h4', 'h3']:
        try:
            title = card.find_element(By.CSS_SELECTOR, title_sel).text.strip()
            if title:
                break
        except:
            continue

    location = ""
    try:
        location = card.find_element(By.CSS_SELECTOR, 'p.text-sm.font-normal.text-zinc-600').text.strip()
        # Clean up - take only first line if multiline
        location = location.split('\n')[0].strip()
    except:
        pass

    company = ""
    try:
        company = card.find_element(By.CSS_SELECTOR, 'p.mb-0.line-clamp-2.text-sm').text.strip()
        company = company.split('\n')[0].strip()
    except:
        pass

    if job_url and title:
        return {"url": job_url, "title": title, "company": company, "location": location}
    return None

def get_cards_from_page(driver):
    """
    Extract job cards from a search results page. Works for any number of cards, including
    1 or 2. The first selector that yields at least one real job (link + title) wins, so
    unrelated page elements cannot hide the real results.
    """
    for sel in ['div[role="listitem"]', 'article', 'div.card', 'div[data-testid="job-card"]']:
        found = driver.find_elements(By.CSS_SELECTOR, sel)
        jobs = [j for j in (_parse_card(c) for c in found) if j]
        if jobs:
            return jobs
    return []

# ─── AI Filter ────────────────────────────────────────────────────────────────
def ai_filter_job(title, company, location, keyword, description, prompt_template):
    try:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        desc_truncated = description[:3000]

        # Fill in the prompt template
        prompt = prompt_template.format(
            title=title, company=company,
            location=location, keyword=keyword,
            description=desc_truncated
        )

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system="You are a strict JSON-only responder. Always respond with valid JSON only.",
            messages=[{"role": "user", "content": prompt}]
        )
        response_text = message.content[0].text.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        result = json.loads(response_text.strip())
        decision = result.get("decision", "NO").upper()
        reason = result.get("reason", "")
        print(f"  🤖 AI: {decision} — {reason[:300]}")
        return decision == "YES", reason
    except Exception as e:
        print(f"  ⚠️ AI error: {e}")
        return True, "AI error - included by default"

# ─── Scrape one prompt ────────────────────────────────────────────────────────
def scrape_for_prompt(config, driver):
    """Scrape Dice for a given prompt config. Returns list of job dicts."""
    now = datetime.now(EASTERN)
    run_date = now.strftime("%Y-%m-%d")
    run_time = now.strftime("%I:%M %p ET")

    jobs = []
    seen_urls = set()
    ai_checked = ai_rejected = flagged = 0
    start_time = time.time()

    # Build date filter
    date_map = {1:"ONE", 2:"TWO", 3:"THREE", 7:"SEVEN", 14:"FOURTEEN", 30:"THIRTY"}
    date_filter = date_map.get(config["date_range"], "ONE")

    # Build employment filter
    emp_filter = "%7C".join(config["emp_types"]) if config["emp_types"] else DEFAULT_EMP_FILTER

    for keyword in config["keywords"]:
        # Check if we've exceeded the max run time
        elapsed = (time.time() - start_time) / 60
        if elapsed > MAX_RUN_MINUTES:
            print(f"\n  ⏱️ Max run time ({MAX_RUN_MINUTES} min) reached after {elapsed:.1f} min. Stopping.")
            break

        # Build search URL - Dice handles multi-word keywords intelligently
        url = f"https://www.dice.com/jobs?filters.postedDate={date_filter}&filters.employmentType={emp_filter}&q={keyword.replace(' ', '+')}"
        print(f"\n  🔍 {keyword}")

        for page in range(1, MAX_PAGES + 1):
            page_url = f"{url}&page={page}"
            try:
                driver.get(page_url)
                time.sleep(random.uniform(2, 3))

                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, 'a[data-testid="job-search-job-detail-link"]'))
                    )
                except:
                    print(f"    📄 Page {page}: no results")
                    break

                page_jobs = get_cards_from_page(driver)
                if not page_jobs:
                    print(f"    📄 Page {page}: results found but no job cards could be read")
                    break

                print(f"    📄 Page {page}: {len(page_jobs)} cards")

                kw_count = sum(1 for j in jobs if j["Keyword"] == keyword)
                if kw_count >= MAX_JOBS_PER_KEYWORD:
                    print(f"    ⚠️ Max {MAX_JOBS_PER_KEYWORD} jobs reached for '{keyword}'")
                    break

                for info in page_jobs:
                    if info["url"] in seen_urls:
                        continue
                    kw_count = sum(1 for j in jobs if j["Keyword"] == keyword)
                    if kw_count >= MAX_JOBS_PER_KEYWORD:
                        break
                    seen_urls.add(info["url"])

                    try:
                        driver.get(info["url"])
                        time.sleep(random.uniform(1, 2))
                        WebDriverWait(driver, 15).until(
                            EC.presence_of_element_located((By.TAG_NAME, "h1"))
                        )

                        title    = safe_text(driver, "h1") or info["title"]
                        location = safe_text(driver,
                            "li[data-cy='location']",
                            "[data-testid='location']",
                            "span[class*='location']") or info["location"]
                        company  = safe_text(driver,
                            "a[data-wa-click='djv-job-company-profile-click']",
                            "a[data-cy='companyNameLink']",
                            "[data-testid='companyName']",
                            "a[class*='company']",
                            "[class*='employer']") or info["company"]
                        recruiter = safe_text(driver,
                            "p[data-testid='recruiterName']",
                            "[data-testid='recruiter']",
                            "span[class*='recruiter']",
                            "[class*='recruiter']")
                        if ERROR_PAGE_PATTERN.search(title):
                            print(f"  ⚠️ Skipping error page: {title[:40]}")
                            continue
                        posted   = extract_posted_date(driver)
                        desc     = extract_description(driver)

                        if len(desc) < MIN_DESCRIPTION_CHARS:
                            # One more try: reload the page in case it did not finish loading
                            try:
                                driver.get(info["url"])
                                time.sleep(random.uniform(1, 2))
                                WebDriverWait(driver, 15).until(
                                    EC.presence_of_element_located((By.TAG_NAME, "h1")))
                                desc = extract_description(driver)
                            except Exception:
                                pass

                        ai_checked += 1
                        kept, reason = ai_filter_job(
                            title, company, location, keyword, desc, config["prompt"]
                        )
                        needs_review = False
                        if not kept and len(desc) < MIN_DESCRIPTION_CHARS:
                            # Nothing to judge from: do not drop it, flag it for a human to review
                            kept, needs_review = True, True
                            reason = f"⚠️ {UNVERIFIED_MARKER} — review manually. (AI said: {reason})"
                            flagged += 1
                        if not kept:
                            ai_rejected += 1
                            print(f"  ❌ {title[:50]}")
                            continue

                        emp, pay, work, corp, dur = extract_badges(driver)
                        jobs.append({
                            "Job Title": title, "Company": company,
                            "Recruiter": recruiter, "Location": location,
                            "Employment Type": emp, "Work Type": work,
                            "Corp to Corp": corp, "Contract Duration": dur,
                            "Pay": pay, "Posted Date": posted,
                            "Keyword": keyword, "AI Reason": reason,
                            "Run Date": run_date, "Run Time": run_time,
                            "Job URL": info["url"], "FD Notes": "",
                        })
                        print(f"  🟡 {title[:60]}  (kept for review: description not captured)" if needs_review
                              else f"  ✅ {title[:60]}")

                    except Exception as e:
                        print(f"  ⚠️ Error: {e}")
                        continue

                    time.sleep(random.uniform(1, 2))

            except Exception as e:
                print(f"  ❌ Page error: {e}")
                break

    print(f"\n  📊 checked={ai_checked}, rejected={ai_rejected}, kept={len(jobs)}, "
          f"needs_review={flagged}")
    return jobs, run_date, run_time

# ─── Write results ────────────────────────────────────────────────────────────
def update_last_run(gc, prompt_tab):
    """Write current timestamp to Last Run field in prompt tab."""
    try:
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(prompt_tab)
        data = ws.get_all_values()
        for i, row in enumerate(data):
            if row and row[0].strip() == "Last Run":
                now_str = datetime.now(EASTERN).isoformat()
                ws.update_cell(i + 1, 2, now_str)
                print(f"  ✅ Updated Last Run: {now_str}")
                return
    except Exception as e:
        print(f"  ⚠️ Could not update Last Run: {e}")

# Columns that stay internal and are never copied to a shared sheet
COPY_EXCLUDED_COLUMNS = {"FD Notes"}

def sync_results_copy(gc, results_tab, share_sheet_id):
    """
    Mirror a results tab into a separate spreadsheet (e.g. one shared with a consultant).
    - Internal columns (FD Notes) are left out of the copy.
    - The copy is rewritten only when its content differs from the source.
    - Safety: never touches the V2 master sheet, and refuses to overwrite a sheet
      whose first tab already holds unrelated data.
    Returns True when the shared copy is confirmed up to date (just updated, or already
    identical); False when nothing was copied. Raises on API errors after retries.
    """
    from gspread.utils import rowcol_to_a1

    if not share_sheet_id:
        return False
    if share_sheet_id == SHEET_ID:
        print(f"  ⚠️ Share Sheet ID for {results_tab} is the V2 master sheet itself — skipped to protect it")
        return False

    def _clean(rows):
        # Compare while ignoring trailing empty cells/rows (Sheets pads them)
        out = []
        for r in rows:
            r = list(r)
            while r and r[-1] == "":
                r.pop()
            out.append(r)
        while out and not out[-1]:
            out.pop()
        return out

    def _sync():
        source = gc.open_by_key(SHEET_ID).worksheet(results_tab).get_all_values()
        if not source:
            print(f"  ℹ️ {results_tab} returned no data — shared copy left unchanged")
            return False

        keep = [i for i, h in enumerate(source[0]) if h.strip() not in COPY_EXCLUDED_COLUMNS]
        # Jobs flagged "description not captured" stay internal until someone reviews them
        reason_idx = source[0].index("AI Reason") if "AI Reason" in source[0] else None
        body_rows = [r for r in source[1:]
                     if not (reason_idx is not None and len(r) > reason_idx and is_unverified(r[reason_idx]))]
        rows = [[(r[i] if i < len(r) else "") for i in keep] for r in [source[0]] + body_rows]

        dest_ws = gc.open_by_key(share_sheet_id).get_worksheet(0)
        existing = dest_ws.get_all_values()

        first_cell = existing[0][0].strip() if existing and existing[0] else ""
        if first_cell not in ("", "Job Title"):
            print(f"  ⚠️ First tab of the shared sheet already contains other data "
                  f"('{first_cell[:30]}') — not overwritten. Use a new blank sheet.")
            return False

        if _clean(existing) == _clean(rows):
            print(f"  ✅ Shared copy already up to date ({len(rows) - 1} jobs)")
            return True

        # Grow the grid if needed (never shrink it)
        need_rows, need_cols = len(rows) + 50, len(keep)
        if dest_ws.row_count < need_rows or dest_ws.col_count < need_cols:
            dest_ws.resize(rows=max(dest_ws.row_count, need_rows),
                           cols=max(dest_ws.col_count, need_cols))

        dest_ws.clear()
        dest_ws.update(range_name="A1", values=rows)
        dest_ws.format(f"A1:{rowcol_to_a1(1, len(keep))}", {"textFormat": {"bold": True}})
        dest_ws.freeze(rows=1)
        dest_ws.set_basic_filter()
        print(f"  ✅ Shared copy updated: {len(rows) - 1} jobs (FD Notes not included)")
        return True

    return with_retry(_sync)

def write_results(gc, results_tab, new_jobs, run_date, job_retention=30):
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(results_tab)

    existing_data = ws.get_all_values()
    if existing_data and existing_data[0][0] == "Job Title":
        existing_rows = existing_data[1:]
        existing_headers = existing_data[0]
    else:
        existing_rows = []
        existing_headers = RESULTS_HEADERS

    url_idx = existing_headers.index("Job URL") if "Job URL" in existing_headers else 14
    run_date_idx = existing_headers.index("Run Date") if "Run Date" in existing_headers else 12

    existing_urls = set(r[url_idx] for r in existing_rows if len(r) > url_idx)

    # Cleanup by Run Date using job_retention setting
    cutoff = datetime.now().date() - timedelta(days=job_retention)
    kept_rows = []
    for row in existing_rows:
        padded = row + [""] * max(0, len(RESULTS_HEADERS) - len(row))
        try:
            rd = datetime.fromisoformat(padded[run_date_idx]).date()
            if rd < cutoff:
                continue
        except:
            pass
        while len(row) < len(RESULTS_HEADERS):
            row.append("")
        kept_rows.append(row)

    # Add new jobs (dedup within this tab)
    added = 0
    new_rows = []
    added_jobs = []   # the jobs that were genuinely new (used for the consultant email)
    for job in new_jobs:
        if job["Job URL"] in existing_urls:
            print(f"  ⏭️ Duplicate: {job['Job Title'][:40]}")
            continue
        existing_urls.add(job["Job URL"])
        new_rows.append([job.get(h, "") for h in RESULTS_HEADERS])
        added_jobs.append(job)
        added += 1

    all_rows = new_rows + kept_rows
    ws.clear()
    ws.append_row(RESULTS_HEADERS)
    if all_rows:
        ws.append_rows(all_rows, value_input_option='RAW')
    ws.format("A1:P1", {"textFormat": {"bold": True}})
    ws.set_basic_filter()

    print(f"  ✅ Added {added} new, kept {len(kept_rows)} existing = {len(all_rows)} total")
    return added, len(all_rows), added_jobs

# ─── Email ────────────────────────────────────────────────────────────────────
def send_notification(config, results_tab, new_count, total_count, run_time):
    if not config["emails"]:
        return

    name = config["name"] or "LATAM"
    today = datetime.now(EASTERN).strftime("%B %d, %Y")
    subject = f"Fast Dolphin Leads — {name} — {today} ({new_count} new)"

    sheet_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"

    body = f"""
<html>
<body style="font-family: Arial, sans-serif; background: #f4f6f9; padding: 20px;">
  <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
    <div style="background: #0A1628; padding: 28px 32px;">
      <h1 style="color: white; margin: 0; font-size: 22px;">Fast Dolphin · Lead Finder V2</h1>
      <p style="color: #7B93B8; margin: 6px 0 0;">{name} · {today} at {run_time}</p>
    </div>
    <div style="padding: 28px 32px;">
      <p style="font-size: 16px; color: #333;">Your contract leads have been updated — <strong>AI verified</strong> for quality.</p>
      <div style="display: flex; gap: 16px; margin: 20px 0;">
        <div style="flex: 1; background: #f0f4ff; border-radius: 8px; padding: 20px; text-align: center;">
          <div style="font-size: 36px; font-weight: bold; color: #1B6CF2;">{new_count}</div>
          <div style="color: #666; font-size: 13px;">new leads added</div>
        </div>
        <div style="flex: 1; background: #f0fff4; border-radius: 8px; padding: 20px; text-align: center;">
          <div style="font-size: 36px; font-weight: bold; color: #30C88A;">{total_count}</div>
          <div style="color: #666; font-size: 13px;">total active leads</div>
        </div>
      </div>
      <div style="text-align: center; margin: 24px 0;">
        <a href="{sheet_url}" style="background: #1B6CF2; color: white; padding: 14px 28px; border-radius: 6px; text-decoration: none; font-weight: bold; font-size: 14px; display: inline-block;">
          📊 Open Google Sheet — {results_tab}
        </a>
      </div>
    </div>
    <div style="background: #f9f9f9; padding: 16px 32px; text-align: center; border-top: 1px solid #eee;">
      <p style="color: #aaa; font-size: 12px; margin: 0;">Fast Dolphin Consulting Group · Internal use only</p>
    </div>
  </div>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = ", ".join(config["emails"])
    msg.attach(MIMEText(body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, config["emails"], msg.as_string())

    print(f"  📧 Email sent to: {', '.join(config['emails'])}")

# ─── Consultant notification ──────────────────────────────────────────────────
def dedupe_addresses(*lists):
    """Remove repeated addresses across To/CC/BCC (case-insensitive); first list wins."""
    seen, result = set(), []
    for lst in lists:
        cur = []
        for addr in lst:
            key = addr.lower()
            if key not in seen:
                seen.add(key)
                cur.append(addr)
        result.append(cur)
    return result

def internal_recipients(config):
    """
    Recipients for Fast Dolphin's own email. A consultant's (outside) address is never
    allowed here, even if someone typed it into the Emails row by mistake.
    @fastdolphin.com addresses are never removed, so internal testing works.
    """
    consultant = {e.lower() for e in config.get("consultant_email", [])}
    keep, removed = [], []
    for e in config.get("emails", []):
        if e.lower() in consultant and not e.lower().endswith("@" + INTERNAL_DOMAIN):
            removed.append(e)
        else:
            keep.append(e)
    if removed:
        print(f"  ⚠️ Removed consultant address(es) from the internal email: {', '.join(removed)}")
    return keep

def build_consultant_email(config, added_jobs, total_count, run_time):
    """Returns (subject, plain_text, html) for the consultant's email. English only."""
    name = (config.get("name") or "").strip()
    today = datetime.now(EASTERN).strftime("%B %d, %Y")
    n = len(added_jobs)
    plural = "" if n == 1 else "s"
    sheet_url = f"https://docs.google.com/spreadsheets/d/{config['share_sheet_id']}"
    subject = (f"New job matches for {name} — {today} ({n} new)" if name
               else f"New job matches — {today} ({n} new)")

    shown = added_jobs[:CONSULTANT_EMAIL_MAX_JOBS]
    more = n - len(shown)

    items_html, items_text = [], []
    for j in shown:
        title = str(j.get("Job Title") or "Job")
        url = str(j.get("Job URL") or "")
        details = " · ".join(str(x) for x in (j.get("Company"), j.get("Location"),
                                               j.get("Work Type"), j.get("Pay")) if x)
        if url.startswith("http"):
            title_html = (f'<a href="{html_escape(url, quote=True)}" '
                          f'style="color:#1B6CF2;text-decoration:none;font-weight:bold;">'
                          f'{html_escape(title)}</a>')
        else:
            title_html = f"<strong>{html_escape(title)}</strong>"
        items_html.append(
            f'<div style="padding:12px 0;border-bottom:1px solid #eee;">{title_html}'
            f'<div style="color:#666;font-size:13px;margin-top:3px;">{html_escape(details)}</div></div>')
        items_text.append(f"- {title}\n  {details}\n  {url}".rstrip())

    more_html = (f'<p style="color:#666;font-size:13px;">…and {more} more in your sheet.</p>'
                 if more > 0 else "")
    more_text = f"\n…and {more} more in your sheet." if more > 0 else ""
    greeting = f"Hello {name}," if name else "Hello,"

    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; background: #f4f6f9; padding: 20px;">
  <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
    <div style="background: #0A1628; padding: 28px 32px;">
      <h1 style="color: white; margin: 0; font-size: 22px;">New job matches</h1>
      <p style="color: #7B93B8; margin: 6px 0 0;">{html_escape(today)} at {html_escape(run_time)}</p>
    </div>
    <div style="padding: 28px 32px;">
      <p style="font-size: 16px; color: #333;">{html_escape(greeting)}</p>
      <p style="font-size: 16px; color: #333;">We found <strong>{n} new contract job{plural}</strong> that match your skills:</p>
      {''.join(items_html)}
      {more_html}
      <div style="text-align: center; margin: 28px 0 8px;">
        <a href="{html_escape(sheet_url, quote=True)}" style="background: #1B6CF2; color: white; padding: 14px 28px; border-radius: 6px; text-decoration: none; font-weight: bold; font-size: 14px; display: inline-block;">
          📊 Open your job sheet
        </a>
      </div>
      <p style="color: #888; font-size: 12px; text-align: center;">Your sheet updates automatically and always shows all current matches.</p>
    </div>
    <div style="background: #f9f9f9; padding: 16px 32px; text-align: center; border-top: 1px solid #eee;">
      <p style="color: #aaa; font-size: 12px; margin: 0;">Fast Dolphin Consulting Group</p>
    </div>
  </div>
</body>
</html>"""

    text_body = (f"{greeting}\n\nWe found {n} new contract job{plural} that match your skills:\n\n"
                 + "\n".join(items_text) + more_text
                 + f"\n\nOpen your job sheet: {sheet_url}\n"
                 "Your sheet updates automatically and always shows all current matches.\n\n"
                 "Fast Dolphin Consulting Group\n")
    return subject, text_body, html_body

def send_consultant_notification(config, added_jobs, total_count, run_time):
    """Send the consultant's own email: To = consultant, CC = Mariana, BCC = internal team."""
    to_list, cc_list, bcc_list = dedupe_addresses(
        config["consultant_email"], config.get("consultant_cc", []), config.get("consultant_bcc", []))
    subject, text_body, html_body = build_consultant_email(config, added_jobs, total_count, run_time)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    # No Bcc header on purpose: BCC recipients go in the SMTP envelope only, so the
    # consultant cannot see them.
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, to_list + cc_list + bcc_list, msg.as_string())

    print(f"  📧 Consultant email sent — To: {', '.join(to_list)} | "
          f"CC: {', '.join(cc_list) or '-'} | BCC: {len(bcc_list)} hidden")

def notify_consultant(config, added_jobs, total_count, run_time, copy_ok):
    """Send the consultant's email only when everything is in place. Never raises."""
    if not config.get("notify_consultant"):
        return False
    if not config.get("consultant_email"):
        print("  ℹ️ Notify Consultant is YES but 'Consultant Email' is empty — consultant email not sent")
        return False
    if not config.get("share_sheet_id"):
        print("  ℹ️ Notify Consultant is YES but 'Share Sheet ID' is empty — consultant email not sent")
        return False
    added_jobs = [j for j in added_jobs if not is_unverified(j.get("AI Reason"))]
    if not added_jobs:
        print("  ℹ️ No new verified leads this run — consultant email not sent")
        return False
    if not copy_ok:
        print("  ⚠️ Shared copy was not confirmed up to date — consultant email held back")
        return False
    try:
        send_consultant_notification(config, added_jobs, total_count, run_time)
        return True
    except Exception as e:
        print(f"  ⚠️ Could not send consultant email: {e}")
        return False

def deliver_results(gc, results_tab, config, added, total, added_jobs, run_time, synced_tabs):
    """
    After a scrape: (1) update the consultant's shared copy, (2) send Fast Dolphin's own
    email (same as before, never includes the consultant), (3) send the consultant's own
    separate email. The copy goes first so the consultant's link already shows the new jobs.
    """
    copy_ok = False
    if config.get("share_sheet_id"):
        try:
            copy_ok = bool(sync_results_copy(gc, results_tab, config["share_sheet_id"]))
        except Exception as e:
            print(f"  ⚠️ Could not update shared copy for {results_tab}: {e}")
        if copy_ok:
            synced_tabs.add(results_tab)

    if config.get("send_email", True):
        internal_config = dict(config)
        internal_config["emails"] = internal_recipients(config)
        send_notification(internal_config, results_tab, added, total, run_time)
    else:
        print("  📧 Email skipped (Notification = No email)")

    notify_consultant(config, added_jobs, total, run_time, copy_ok)

# ─── LATAM Default Prompt ─────────────────────────────────────────────────────
LATAM_PROMPT = """You are a strict recruiting analyst for an IT and engineering staffing firm. Your job is to decide if a job posting meets BOTH of these conditions:
(1) It has a GENUINE Latin America connection: the actual job requirements, candidate work location, or language skills involve Latin America.
(2) It is a role in scope for our firm (see SCOPE below).

STEP 1: Read the ENTIRE job description carefully. If the description is empty or very short, judge from the title, company and location alone.

STEP 2: Decide if the job relates to Latin America or the Spanish/Portuguese language. The following is a partial list of keywords: Latin America, Mexico, Brazil, Colombia, Argentina, Chile, Peru, Ecuador, Costa Rica, Panama, Bolivia, LATAM, Maquiladora, Spanish, Portuguese. Any other Latin American country (such as Paraguay, Uruguay, Venezuela, Honduras, Guatemala, Nicaragua, Dominican Republic) counts too, as long as it appears in the context explained below.

STEP 3: For EACH mention, determine its context.

AUTOMATICALLY REJECT (answer NO) if Latin America, Spanish, Portuguese or any related keyword ONLY appears in:
- Email signature or footer listing office locations such as "USA | CANADA | Mexico | INDIA" or "offices in New York, Mexico, India"
- Company boilerplate like "we have offices in..." or "presence in..." or "locations in..." or "internationally in..."
- Equal opportunity employment statements
- The US state of New Mexico (not the country Mexico)
- The word "Perl" (a programming language), which is NOT "Peru"
- Recruiter contact information or a company address
- Phrases describing where the COMPANY operates, NOT where the CANDIDATE works

ACCEPT (answer YES) only if Latin America, Spanish, Portuguese or any related keyword appears in:
- The actual job requirements such as "must be bilingual" or "Spanish required" or "based in Mexico City"
- The candidate work location such as "position located in Bogota", "remote from LATAM" or "Brazil Remote"
- Required skills or experience such as "LATAM market experience" or "serve Latin American clients"
- Language requirements such as "fluent Spanish", "Portuguese required" or "bilingual English/Spanish"
- The role description itself mentioning LATAM work, teams or clients
- Any Latin American country, even if not in the keyword list above, as long as it is part of the job requirement and not just a company office mention

SCOPE: the role must ALSO be one of the following. If it is not, answer NO even when the Latin America connection is genuine.
IN SCOPE:
- Technology and IT: software development, data and analytics, cybersecurity, cloud, DevOps, infrastructure, networking, QA and testing, IT project and program management, IT and business systems analysts (software, ERP, Salesforce), and IT support (desktop support, IT support technician, deskside or field technician).
- ERP and enterprise applications: SAP, Oracle, Workday, Salesforce, QAD, JD Edwards, Microsoft Dynamics, ServiceNow and similar. BOTH technical AND functional or business-process consultants are IN scope (for example SAP FICO, SAP SD, SAP MM or Oracle finance system consultants). This is our core business.
- Engineering: mechanical, electrical, civil, industrial, manufacturing, chemical, structural, systems engineering, etc.
OUT OF SCOPE (answer NO):
- Help desk, service desk or call-center style first-level user support (for example "Help Desk Analyst", "Service Desk Agent", "Help Desk Specialist", or a "Technical Support Representative" answering customer calls)
- Teaching or tutoring, social work, healthcare or clinical roles, sales, customer service, administrative or clerical roles, legal or regulatory affairs, HR or recruiting, marketing
- Non-IT accounting or finance work (for example bookkeeper or accounts payable clerk). Note that SAP or Oracle finance SYSTEM consultants are IN scope.
- Do NOT reject a role only because of its industry (healthcare, finance, retail, etc.). A software developer or ERP consultant is in scope in any industry.

CONCRETE EXAMPLES:
- "USA | CANADA | Mexico | INDIA" in a footer = NO
- "Support Benefits implementation within the USA" with Mexico only in footer = NO
- "offices in Mexico City and India" = NO
- "PruTech has nearshore offices in Mexico City" but job is in Brooklyn NY = NO
- "Must be fluent in Spanish" for a Java developer = YES
- "Position based in Guadalajara" for a DevOps engineer = YES
- "Serve LATAM clients" for an SAP consultant = YES
- "Senior SAP FICO consultant, remote Brazil, fluent Portuguese required" = YES
- "QAD ERP Functional Support Consultant (Portuguese speaking)" = YES
- "Desktop Support Technician, bilingual English/Spanish required" = YES
- "Nearshore delivery from Mexico" for a software project = YES
- "Candidate must have experience working with teams in Paraguay" for an IT role = YES
- "Help Desk Analyst, must be bilingual Spanish/English" = NO (help desk)
- "Spanish teacher" or "Social worker, Spanish speaking" = NO (not IT or engineering)
- "Sales representative, Spanish required" = NO (not IT or engineering)

Job Title: {title}
Company: {company}
Location: {location}
Keyword that matched: {keyword}

Job Description:
{description}

Think step by step. Understand the nature of the job. Check the Latin America connection and the scope. Then decide.

Respond with ONLY a JSON object in this exact format with no other text:
{{"decision": "YES" or "NO", "reason": "one sentence explaining the specific mention and why it does or does not qualify"}}"""

# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    now = datetime.now(EASTERN)
    print(f"Fast Dolphin Scraper V2 — {now.strftime('%Y-%m-%d %H:%M ET')}")
    print("=" * 60)

    gc = get_sheets_client()

    # Ensure all tabs exist
    with_retry(lambda: ensure_sheet_structure(gc))

    # Check which prompts are due to run
    prompts_to_run = []
    mirror_targets = []  # (results_tab, config) for ON prompts that have a shared copy
    synced_tabs = set()  # results tabs whose shared copy was already refreshed this run
    sh = gc.open_by_key(SHEET_ID)
    all_tabs = [ws.title for ws in sh.worksheets()]

    for i, (prompt_tab, results_tab) in enumerate(PROMPT_TABS):
        # Find actual tab name — could be renamed if consultant name was set
        actual_prompt_tab = prompt_tab  # default
        actual_results_tab = results_tab  # default

        # Check if tab was renamed (e.g. "Ramon Osuna Prompt")
        for tab in all_tabs:
            if tab.endswith(" Prompt") and tab not in [p for p, r in PROMPT_TABS]:
                # This is a renamed tab — check if it corresponds to this slot
                ws_check = sh.worksheet(tab)
                data = ws_check.get_all_values()
                config_map = {r[0]: r[1] for r in data if len(r) >= 2}
                # Match by checking if original tab no longer exists
                if prompt_tab not in all_tabs:
                    actual_prompt_tab = tab
                    actual_results_tab = tab.replace("Prompt", "Results")
                    break

        if actual_prompt_tab not in all_tabs:
            print(f"⚠️  Tab not found: {actual_prompt_tab}")
            continue

        config = read_prompt_config(gc, actual_prompt_tab)
        if config is None:
            print(f"⏸️  {actual_prompt_tab}: OFF or not configured")
            continue

        if config.get("share_sheet_id"):
            mirror_targets.append((results_tab, config))

        if not is_due_to_run(config):
            print(f"⏰  {actual_prompt_tab}: not due yet (times: {config['time1']}, {config['time2']})")
            continue

        if not config["keywords"]:
            print(f"⚠️  {actual_prompt_tab}: no keywords configured")
            continue

        if not config["prompt"]:
            print(f"⚠️  {actual_prompt_tab}: no prompt configured")
            continue

        if actual_results_tab not in all_tabs:
            actual_results_tab = results_tab

        prompts_to_run.append((prompt_tab, results_tab, config))
        print(f"✅  {prompt_tab}: DUE — {len(config['keywords'])} keywords")

    if not prompts_to_run:
        print("\nNo prompts due to run at this time.")
    else:
        print(f"\n🚀 Running {len(prompts_to_run)} prompt(s)...")
        driver = create_driver()
        try:
            for prompt_tab, results_tab, config in prompts_to_run:
                print(f"\n{'='*60}")
                print(f"Running: {prompt_tab}")
                print(f"{'='*60}")

                jobs, run_date, run_time = scrape_for_prompt(config, driver)
                added, total, added_jobs = write_results(gc, results_tab, jobs, run_date, config.get("job_retention", 30))
                update_last_run(gc, prompt_tab)
                deliver_results(gc, results_tab, config, added, total, added_jobs, run_time, synced_tabs)

        finally:
            driver.quit()

    # Keep shared copies (e.g. a consultant's own sheet) in sync with their results tabs.
    # Runs every time; only rewrites when something changed. Never fails the whole run.
    for results_tab, config in mirror_targets:
        if results_tab in synced_tabs:
            continue   # already refreshed right after its scrape
        print(f"\n🔁 Checking shared copy for: {results_tab}")
        try:
            sync_results_copy(gc, results_tab, config["share_sheet_id"])
        except Exception as e:
            print(f"  ⚠️ Could not update shared copy for {results_tab}: {e}")
            print("     Check that the sheet is shared with the service account as Editor "
                  "and that the Share Sheet ID is correct.")

    print("\nDone!")
