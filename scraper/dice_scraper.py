import time
import random
import os
import json
import smtplib
import anthropic
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import gspread
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ─── Default config ────────────────────────────────────────────────────────────
DEFAULT_KEYWORDS = [
    "mexico", "spanish", "brazil", "brasil", "argentina", "colombia",
    "ecuador", "costa rica", "panama", "portuguese", "latam",
    "latin america", "maquiladora", "chile", "bolivia", "peru",
]

DEFAULT_EMPLOYMENT_TYPES = "CONTRACTS|THIRD_PARTY|CONTRACT_INDEPENDENT"
DEFAULT_DATE_RANGE = 2

MAX_PAGES = 5
SHEET_ID = "14Gjeh1TiJTIq0IhhAA0cKumraUy1Q0d99hmbhI1AtV8"
SHEET_TAB = "Dice Leads"
MAX_DAYS = 30  # Remove jobs with posted date older than 30 days

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
NOTIFY_EMAILS = [
    "carlos.guerrero@fastdolphin.com",
    "ramon.osuna@fastdolphin.com",
    "daniel.riojas@fastdolphin.com",
    "mariana.esparza@fastdolphin.com",
]
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
APP_URL = "https://fastdolphin-cg.github.io/dice-leads"

# ─── Runtime config ────────────────────────────────────────────────────────────
def get_config():
    kw_env = os.environ.get("SCRAPER_KEYWORDS", "").strip()
    keywords = [k.strip() for k in kw_env.split(",")] if kw_env else DEFAULT_KEYWORDS

    et_env = os.environ.get("SCRAPER_EMPLOYMENT_TYPES", "").strip()
    emp_filter = et_env if et_env else DEFAULT_EMPLOYMENT_TYPES
    emp_filter_encoded = emp_filter.replace("|", "%7C")

    dr_env = os.environ.get("SCRAPER_DATE_RANGE", str(DEFAULT_DATE_RANGE)).strip()
    try:
        days = max(1, min(30, int(dr_env)))
    except:
        days = DEFAULT_DATE_RANGE

    date_map = {1:"ONE", 2:"TWO", 3:"THREE", 7:"SEVEN", 14:"FOURTEEN", 30:"THIRTY"}
    date_filter = date_map.get(days, "TWO")

    model_env = os.environ.get("SCRAPER_AI_MODEL", "haiku").strip().lower()
    ai_model = "claude-sonnet-4-6" if model_env == "sonnet" else "claude-haiku-4-5-20251001"

    send_email = os.environ.get("SCRAPER_SEND_EMAIL", "true").strip().lower() != "false"
    run_label = os.environ.get("SCRAPER_RUN_LABEL", "").strip()

    search_urls = [
        f"https://www.dice.com/jobs?filters.postedDate={date_filter}&filters.employmentType={emp_filter_encoded}&q={kw.replace(' ', '+')}"
        for kw in keywords
    ]

    print(f"📋 Config: {len(keywords)} keywords, emp={emp_filter}, days={days}, model={ai_model}, email={send_email}")
    if run_label:
        print(f"🏷️  Run label: {run_label}")

    return {
        "keywords": keywords,
        "search_urls": search_urls,
        "ai_model": ai_model,
        "send_email": send_email,
        "run_label": run_label,
        "date_filter": date_filter,
        "emp_filter": emp_filter,
    }

_cfg = get_config()
SEARCH_URLS = _cfg["search_urls"]

# ─── AI Prompt ────────────────────────────────────────────────────────────────
AI_PROMPT = """You are a strict recruiting analyst. Your job is to decide if a job posting has a GENUINE Latin America connection meaning the actual job requirements, candidate location, or language skills involve Latin America.

STEP 1: Read the ENTIRE job description carefully.

STEP 2: Understand the nature of the job description and decide if it is related with Latin America or Spanish/Portuguese language. The following is a partial list of keywords: Latin America, Mexico, Brazil, Colombia, Argentina, Chile, Peru, Ecuador, Costa Rica, Panama, Bolivia, LATAM, Maquiladora, Spanish, or Portuguese. If the job mentions any other Latin American country not listed here (such as Paraguay, Uruguay, Venezuela, Honduras, Guatemala, Nicaragua, Dominican Republic, etc.), please include it, as long as it is under the context explained in this prompt.

STEP 3: For EACH mention, determine its context.

AUTOMATICALLY REJECT - answer NO - if Latin America, Spanish, Portuguese, or any related keyword ONLY appears in:
- Email signature or footer listing office locations such as "USA | CANADA | Mexico | INDIA" or "offices in New York, Mexico, India"
- Company boilerplate like "we have offices in..." or "presence in..." or "locations in..." or "internationally in..."
- Equal opportunity employment statements
- The US state of New Mexico - not the country Mexico
- The word "Perl" which is a programming language - this is NOT "Peru"
- A recruiter contact information or company address
- Phrases describing where the COMPANY operates, NOT where the CANDIDATE works

ACCEPT - answer YES - ONLY if Latin America, Spanish, Portuguese, or any related keyword appears in:
- The actual job requirements such as "must be bilingual" or "Spanish required" or "based in Mexico City"
- The candidate work location such as "position located in Bogota" or "remote from LATAM"
- Required skills or experience such as "LATAM market experience" or "serve Latin American clients"
- Language requirements such as "fluent Spanish" or "Portuguese required" or "bilingual English/Spanish"
- The role description itself mentioning LATAM work or clients
- Any Latin American country even if not in the keyword list above, as long as it is in the context of the job requirement and not just a company office mention

CONCRETE EXAMPLES:
- "USA | CANADA | Mexico | INDIA" in a footer = NO
- "Support Benefits implementation within the USA" with Mexico only in footer = NO
- "offices in Mexico City and India" = NO
- "PruTech has nearshore offices in Mexico City" but job is in Brooklyn NY = NO
- "Must be fluent in Spanish" = YES
- "Position based in Guadalajara" = YES
- "Serve LATAM clients" = YES
- "Bilingual English/Spanish required" = YES
- "Nearshore delivery from Mexico" = YES
- "Candidate must have experience working with teams in Paraguay" = YES

Job Title: {title}
Company: {company}
Location: {location}
Keyword that matched: {keyword}

Job Description:
{description}

Think step by step. Understand the nature of the job. Find every relevant mention. Determine its context. Then decide.

Respond with ONLY a JSON object in this exact format with no other text:
{{"decision": "YES" or "NO", "reason": "one sentence explaining the specific mention and why it does or does not qualify"}}"""


def ai_filter_job(title, company, location, keyword, description):
    try:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        desc_truncated = description[:3000] if len(description) > 3000 else description
        prompt = AI_PROMPT.format(
            title=title, company=company, location=location,
            keyword=keyword, description=desc_truncated
        )
        message = client.messages.create(
            model=_cfg["ai_model"],
            max_tokens=500,
            system="You are a strict JSON-only responder. Always respond with valid JSON only, no other text.",
            messages=[{"role": "user", "content": prompt}]
        )
        response_text = message.content[0].text.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        response_text = response_text.strip()
        result = json.loads(response_text)
        decision = result.get("decision", "NO").upper()
        reason = result.get("reason", "")
        print(f"  🤖 AI: {decision} — {reason}")
        return decision == "YES", reason
    except Exception as e:
        print(f"  ⚠️ AI filter error: {e} — keeping job by default")
        return True, f"AI filter error - included by default"


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

def smart_pause(min_sec=2, max_sec=4):
    time.sleep(random.uniform(min_sec, max_sec))

def safe_text(driver, selector):
    try:
        return driver.find_element(By.CSS_SELECTOR, selector).text.strip()
    except:
        return ""

def extract_posted_date(driver):
    """Try multiple selectors to find posted date on job detail page."""
    selectors = [
        "li[data-cy='posted-date']",
        "[data-testid='posted-date']",
        "span[data-cy='posted-date']",
        "li.posted-date",
        "[class*='posted']",
        "time",
    ]
    for sel in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            text = el.text.strip()
            if text:
                return text
            # Try datetime attribute
            dt = el.get_attribute("datetime")
            if dt:
                return dt
        except:
            continue

    # Last resort: search page text for "Posted" patterns
    try:
        body = driver.find_element(By.TAG_NAME, "body").text
        import re
        patterns = [
            r'Posted[:\s]+([^\n]+)',
            r'(\d+\s+days?\s+ago)',
            r'(\d+\s+hours?\s+ago)',
            r'(Today|Yesterday)',
        ]
        for pattern in patterns:
            m = re.search(pattern, body, re.IGNORECASE)
            if m:
                return m.group(1).strip()
    except:
        pass

    return "Unknown"

def extract_badges(driver):
    emp_types = []
    pay = work_type = corp = duration = ""
    try:
        badges = driver.find_elements(By.CSS_SELECTOR, "div.SeuiInfoBadge div.font-medium")
        for b in badges:
            text = b.text.strip()
            if not text:
                continue
            tl = text.lower()
            if any(x in tl for x in ["$/hr", "$/year", "/hr", "/year", "k/yr", "per hour"]):
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


# ─── Scraping ─────────────────────────────────────────────────────────────────
def scrape_all():
    from zoneinfo import ZoneInfo
    eastern = ZoneInfo("America/New_York")
    run_time = datetime.now(eastern)
    run_date_str = run_time.strftime("%Y-%m-%d")
    run_time_str = run_time.strftime("%I:%M %p ET")

    driver = create_driver()
    jobs = []
    seen_urls = set()
    ai_checked = 0
    ai_rejected = 0

    try:
        for base_url in SEARCH_URLS:
            keyword = base_url.split("&q=")[-1].replace("+", " ")
            print(f"\n🔍 Searching: {keyword}")

            for page in range(1, MAX_PAGES + 1):
                url = f"{base_url}&page={page}"
                print(f"  📄 Page {page}...")

                try:
                    driver.get(url)
                    smart_pause(3, 5)

                    try:
                        WebDriverWait(driver, 15).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="listitem"]'))
                        )
                    except:
                        print(f"  ⚠️ No results on page {page}, stopping.")
                        break

                    cards = driver.find_elements(By.CSS_SELECTOR, 'div[role="listitem"]')
                    if not cards:
                        break

                    page_jobs = []
                    for card in cards:
                        try:
                            job_url = card.find_element(By.CSS_SELECTOR, 'a[data-testid="job-search-job-card-link"]').get_attribute("href")
                        except:
                            job_url = ""
                        try:
                            title = card.find_element(By.CSS_SELECTOR, 'a[data-testid="job-search-job-detail-link"]').text.strip()
                        except:
                            title = ""
                        try:
                            location = card.find_element(By.CSS_SELECTOR, 'p.text-sm.font-normal.text-zinc-600').text.strip()
                        except:
                            location = ""
                        try:
                            company = card.find_element(By.CSS_SELECTOR, 'p.mb-0.line-clamp-2.text-sm').text.strip()
                        except:
                            company = ""

                        if job_url and job_url not in seen_urls and title:
                            page_jobs.append({
                                "url": job_url, "title": title,
                                "company": company, "location": location,
                                "keyword": keyword,
                            })

                    if not page_jobs:
                        break

                    print(f"  🔗 Found {len(page_jobs)} cards")

                    for info in page_jobs:
                        if info["url"] in seen_urls:
                            continue
                        seen_urls.add(info["url"])

                        if "job-detail" not in info["url"]:
                            jobs.append(build_basic_row(info, keyword, run_date_str, run_time_str))
                            continue

                        try:
                            driver.get(info["url"])
                            smart_pause(2, 4)
                            WebDriverWait(driver, 15).until(
                                EC.presence_of_element_located((By.TAG_NAME, "h1"))
                            )

                            title = safe_text(driver, "h1") or info["title"]
                            location = safe_text(driver, "li[data-cy='location']") or info["location"]
                            company = safe_text(driver, "a[data-cy='companyNameLink']") or info["company"]
                            recruiter = safe_text(driver, "p[data-testid='recruiterName']")
                            posted_date = extract_posted_date(driver)

                            description = ""
                            try:
                                desc_el = driver.find_element(By.CSS_SELECTOR, "div.job-description")
                                description = desc_el.text
                            except:
                                pass

                            # ── AI FILTER ──────────────────────────────────
                            ai_checked += 1
                            is_genuine, reason = ai_filter_job(
                                title, company, location, keyword, description
                            )
                            if not is_genuine:
                                ai_rejected += 1
                                print(f"  ❌ Rejected: {title[:50]}")
                                continue
                            # ───────────────────────────────────────────────

                            emp_types, pay, work_type, corp, duration = extract_badges(driver)

                            jobs.append({
                                "Job Title": title,
                                "Company": company,
                                "Recruiter": recruiter,
                                "Location": location,
                                "Employment Type": emp_types,
                                "Work Type": work_type,
                                "Corp to Corp": corp,
                                "Contract Duration": duration,
                                "Pay": pay,
                                "Posted Date": posted_date,
                                "Keyword": keyword,
                                "AI Reason": reason,
                                "Run Date": run_date_str,
                                "Run Time": run_time_str,
                                "Job URL": info["url"],
                            })
                            print(f"  ✅ Kept: {title[:60]} | Posted: {posted_date}")

                        except Exception as e:
                            print(f"  ⚠️ Error: {e}")
                            continue

                        smart_pause(1, 2)

                except Exception as e:
                    print(f"  ❌ Page error: {e}")
                    break

    finally:
        driver.quit()

    print(f"\n📊 AI Filter Stats: checked={ai_checked}, rejected={ai_rejected}, kept={len(jobs)}")
    return jobs, run_date_str, run_time_str


def build_basic_row(info, keyword, run_date_str, run_time_str):
    return {
        "Job Title": info["title"], "Company": info["company"],
        "Recruiter": "", "Location": info["location"],
        "Employment Type": "", "Work Type": "", "Corp to Corp": "",
        "Contract Duration": "", "Pay": "", "Posted Date": "Unknown",
        "Keyword": keyword, "AI Reason": "", "Run Date": run_date_str,
        "Run Time": run_time_str, "Job URL": info["url"],
    }


# ─── Google Sheets ────────────────────────────────────────────────────────────
HEADERS = [
    "Job Title", "Company", "Recruiter", "Location", "Employment Type",
    "Work Type", "Corp to Corp", "Contract Duration", "Pay",
    "Posted Date", "Keyword", "AI Reason", "Run Date", "Run Time", "Job URL"
]

def parse_posted_date(posted_str):
    """Try to parse a posted date string into a date object."""
    from datetime import date
    import re
    if not posted_str or posted_str == "Unknown":
        return None
    try:
        # ISO format
        return datetime.fromisoformat(posted_str).date()
    except:
        pass
    today = date.today()
    s = posted_str.lower().strip()
    # "X days ago"
    m = re.search(r'(\d+)\s+days?\s+ago', s)
    if m:
        return today - timedelta(days=int(m.group(1)))
    # "X hours ago"
    m = re.search(r'(\d+)\s+hours?\s+ago', s)
    if m:
        return today
    # "today"
    if 'today' in s:
        return today
    # "yesterday"
    if 'yesterday' in s:
        return today - timedelta(days=1)
    # Try dateutil
    try:
        from dateutil import parser as dateparser
        return dateparser.parse(posted_str).date()
    except:
        pass
    return None

def write_to_sheets(new_jobs, run_date_str):
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)

    # Get or create the single "Dice Leads" tab
    try:
        ws = sh.worksheet(SHEET_TAB)
    except:
        ws = sh.add_worksheet(title=SHEET_TAB, rows="2000", cols="20")

    # Read existing data
    existing_data = ws.get_all_values()

    if existing_data and existing_data[0] == HEADERS:
        existing_rows = existing_data[1:]
    else:
        existing_rows = []
        # Write headers
        ws.clear()
        ws.append_row(HEADERS)
        ws.format("A1:O1", {"textFormat": {"bold": True}})
        # Add filters to header row
        ws.set_basic_filter()

    # Get existing URLs for dedup
    url_col_idx = HEADERS.index("Job URL")
    run_date_col_idx = HEADERS.index("Run Date")
    posted_col_idx = HEADERS.index("Posted Date")
    existing_urls = set(row[url_col_idx] for row in existing_rows if len(row) > url_col_idx)

    # Filter out jobs older than 30 days based on RUN DATE (when we scraped it)
    # This is reliable — we control it. Posted Date from Dice is unreliable.
    cutoff = datetime.now().date() - timedelta(days=MAX_DAYS)
    kept_rows = []
    removed = 0
    for row in existing_rows:
        run_date_str_row = row[run_date_col_idx] if len(row) > run_date_col_idx else ""
        try:
            run_date = datetime.fromisoformat(run_date_str_row).date()
        except:
            # If we can't parse run date, keep the job to be safe
            kept_rows.append(row)
            continue
        if run_date < cutoff:
            removed += 1
            continue
        kept_rows.append(row)

    if removed > 0:
        print(f"🗑️ Removed {removed} jobs older than {MAX_DAYS} days")

    # Add new jobs (dedup against existing)
    added = 0
    new_rows = []
    for job in new_jobs:
        if job["Job URL"] in existing_urls:
            print(f"  ⏭️ Duplicate skipped: {job['Job Title'][:50]}")
            continue
        existing_urls.add(job["Job URL"])
        new_rows.append([job.get(h, "") for h in HEADERS])
        added += 1

    print(f"✅ Adding {added} new jobs, keeping {len(kept_rows)} existing")

    # Rebuild sheet: new jobs first, then existing
    all_rows = new_rows + kept_rows

    ws.clear()
    ws.append_row(HEADERS)
    if all_rows:
        ws.append_rows(all_rows, value_input_option='RAW')

    # Format header and add filters
    ws.format("A1:O1", {"textFormat": {"bold": True}})
    ws.set_basic_filter()

    print(f"✅ Sheet '{SHEET_TAB}' updated: {len(all_rows)} total jobs")
    return added, len(all_rows)


# ─── Save JSON to GitHub ──────────────────────────────────────────────────────
def save_json_to_github(all_jobs, run_date_str, run_time_str):
    import glob
    import subprocess
    from zoneinfo import ZoneInfo

    eastern = ZoneInfo("America/New_York")
    now = datetime.now(eastern)

    os.makedirs('public/data', exist_ok=True)

    payload = {
        "scraped_at": now.isoformat(),
        "scraped_at_eastern": now.strftime("%Y-%m-%d %I:%M %p ET"),
        "count": len(all_jobs),
        "jobs": all_jobs
    }

    with open('public/data/latest.json', 'w') as f:
        json.dump(payload, f, indent=2)
    print("✅ Wrote public/data/latest.json")

    subprocess.run(['git', 'config', 'user.email', 'scraper@fastdolphin.com'], check=True)
    subprocess.run(['git', 'config', 'user.name', 'Fast Dolphin Scraper'], check=True)
    # Pull latest changes first to avoid push rejection
    subprocess.run(['git', 'pull', '--rebase', 'origin', 'main'], check=True)
    subprocess.run(['git', 'add', 'public/data/'], check=True)
    result = subprocess.run(
        ['git', 'commit', '-m', f'Data: {run_date_str} {run_time_str} ({len(all_jobs)} jobs)'],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        subprocess.run(['git', 'push', 'origin', 'main'], check=True)
        # Trigger GitHub Pages redeploy so app picks up new data
        try:
            import urllib.request
            gh_token = os.environ.get("GITHUB_TOKEN", "")
            if not gh_token:
                # Use GITHUB_TOKEN from Actions environment
                gh_token = subprocess.run(
                    ['git', 'config', '--get', 'http.https://github.com/.extraheader'],
                    capture_output=True, text=True
                ).stdout.strip()
            req = urllib.request.Request(
                'https://api.github.com/repos/fastdolphin-cg/dice-leads/pages/builds',
                method='POST',
                headers={
                    'Authorization': f'Bearer {os.environ.get("GITHUB_TOKEN", "")}',
                    'Accept': 'application/vnd.github+json',
                }
            )
            urllib.request.urlopen(req)
            print("✅ GitHub Pages rebuild triggered")
        except Exception as e:
            print(f"ℹ️ Could not trigger Pages rebuild: {e}")
        print("✅ Data pushed to GitHub")
    else:
        print("ℹ️ Nothing to commit")


# ─── Email ────────────────────────────────────────────────────────────────────
def send_email(new_count, total_count, run_date_str, run_time_str):
    from zoneinfo import ZoneInfo
    eastern = ZoneInfo("America/New_York")
    today = datetime.now(eastern).strftime("%B %d, %Y")
    subject = f"Fast Dolphin LATAM Leads — {today} ({new_count} new leads)"

    body = f"""
<html>
<body style="font-family: Arial, sans-serif; background: #f4f6f9; padding: 20px;">
  <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
    <div style="background: #0A1628; padding: 28px 32px;">
      <h1 style="color: white; margin: 0; font-size: 22px;">Fast Dolphin · LATAM Lead Finder</h1>
      <p style="color: #7B93B8; margin: 6px 0 0;">Daily Dice.com scrape — {today} at {run_time_str}</p>
    </div>
    <div style="padding: 28px 32px;">
      <p style="font-size: 16px; color: #333;">Your LATAM contract leads have been updated — <strong>AI verified</strong> for quality.</p>
      <div style="display: flex; gap: 16px; margin: 20px 0;">
        <div style="flex: 1; background: #f0f4ff; border-radius: 8px; padding: 20px; text-align: center;">
          <div style="font-size: 36px; font-weight: bold; color: #1B6CF2;">{new_count}</div>
          <div style="color: #666; font-size: 13px;">new leads added today</div>
        </div>
        <div style="flex: 1; background: #f0fff4; border-radius: 8px; padding: 20px; text-align: center;">
          <div style="font-size: 36px; font-weight: bold; color: #30C88A;">{total_count}</div>
          <div style="color: #666; font-size: 13px;">total active leads</div>
        </div>
      </div>
      <p style="color: #555;">Each lead reviewed by AI to confirm genuine LATAM relevance.</p>
      <div style="text-align: center; margin: 24px 0; display: flex; gap: 12px; justify-content: center;">
        <a href="{SHEET_URL}" style="background: #1B6CF2; color: white; padding: 14px 24px; border-radius: 6px; text-decoration: none; font-weight: bold; font-size: 14px; display: inline-block;">
          📊 Open Google Sheet
        </a>
        <a href="{APP_URL}" style="background: #0A1628; color: white; padding: 14px 24px; border-radius: 6px; text-decoration: none; font-weight: bold; font-size: 14px; display: inline-block; border: 1px solid #1B6CF2;">
          🐬 Open Lead Finder App
        </a>
      </div>
      <p style="color: #999; font-size: 12px;">Filtered for: Mexico · Brazil · Colombia · Argentina · Chile · LATAM · Spanish · and more<br>Employment: Contract, Third Party & Contract Independent · Posted last {DEFAULT_DATE_RANGE} days · AI-verified</p>
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
    msg["To"] = ", ".join(NOTIFY_EMAILS)
    msg.attach(MIMEText(body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, NOTIFY_EMAILS, msg.as_string())

    print(f"📧 Email sent to: {', '.join(NOTIFY_EMAILS)}")


# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    cfg = get_config()
    label = f" [{cfg['run_label']}]" if cfg['run_label'] else ""
    print(f"Fast Dolphin LATAM Lead Scraper — AI Edition{label}")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    print("\nStarting scrape...")
    new_jobs, run_date_str, run_time_str = scrape_all()
    print(f"\nNew verified leads this run: {len(new_jobs)}")

    print("\nUpdating Google Sheets...")
    added_count, total_count = write_to_sheets(new_jobs, run_date_str)

    print("\nSaving JSON to GitHub...")
    # For the app, we need ALL jobs from the sheet
    # Re-read from sheet to get the full cumulative list
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(
        creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(SHEET_TAB)
    all_data = ws.get_all_values()
    headers = all_data[0] if all_data else HEADERS
    all_jobs_for_app = []
    for row in all_data[1:]:
        job = {}
        for i, h in enumerate(headers):
            job[h] = row[i] if i < len(row) else ""
        all_jobs_for_app.append(job)

    save_json_to_github(all_jobs_for_app, run_date_str, run_time_str)

    if cfg['send_email']:
        print("\nSending email notification...")
        send_email(added_count, total_count, run_date_str, run_time_str)
    else:
        print("\nSkipping email (send_email=false)")

    print("\nDone!")
