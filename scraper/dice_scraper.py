import time
import random
import os
import json
import smtplib
import anthropic
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import gspread
from google.oauth2.service_account import Credentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ─── Configuration ────────────────────────────────────────────────────────────

SEARCH_URLS = [
    "https://www.dice.com/jobs?filters.postedDate=THREE&filters.employmentType=CONTRACTS%7CTHIRD_PARTY&q=mexico",
    "https://www.dice.com/jobs?filters.postedDate=THREE&filters.employmentType=CONTRACTS%7CTHIRD_PARTY&q=spanish",
    "https://www.dice.com/jobs?filters.postedDate=THREE&filters.employmentType=CONTRACTS%7CTHIRD_PARTY&q=brazil",
    "https://www.dice.com/jobs?filters.postedDate=THREE&filters.employmentType=CONTRACTS%7CTHIRD_PARTY&q=brasil",
    "https://www.dice.com/jobs?filters.postedDate=THREE&filters.employmentType=CONTRACTS%7CTHIRD_PARTY&q=argentina",
    "https://www.dice.com/jobs?filters.postedDate=THREE&filters.employmentType=CONTRACTS%7CTHIRD_PARTY&q=colombia",
    "https://www.dice.com/jobs?filters.postedDate=THREE&filters.employmentType=CONTRACTS%7CTHIRD_PARTY&q=ecuador",
    "https://www.dice.com/jobs?filters.postedDate=THREE&filters.employmentType=CONTRACTS%7CTHIRD_PARTY&q=costa+rica",
    "https://www.dice.com/jobs?filters.postedDate=THREE&filters.employmentType=CONTRACTS%7CTHIRD_PARTY&q=panama",
    "https://www.dice.com/jobs?filters.postedDate=THREE&filters.employmentType=CONTRACTS%7CTHIRD_PARTY&q=portuguese",
    "https://www.dice.com/jobs?filters.postedDate=THREE&filters.employmentType=CONTRACTS%7CTHIRD_PARTY&q=latam",
    "https://www.dice.com/jobs?filters.postedDate=THREE&filters.employmentType=CONTRACTS%7CTHIRD_PARTY&q=latin+america",
    "https://www.dice.com/jobs?filters.postedDate=THREE&filters.employmentType=CONTRACTS%7CTHIRD_PARTY&q=maquiladora",
    "https://www.dice.com/jobs?filters.postedDate=THREE&filters.employmentType=CONTRACTS%7CTHIRD_PARTY&q=chile",
    "https://www.dice.com/jobs?filters.postedDate=THREE&filters.employmentType=CONTRACTS%7CTHIRD_PARTY&q=bolivia",
    "https://www.dice.com/jobs?filters.postedDate=THREE&filters.employmentType=CONTRACTS%7CTHIRD_PARTY&q=peru",
]

MAX_PAGES = 5
SHEET_ID = "14Gjeh1TiJTIq0IhhAA0cKumraUy1Q0d99hmbhI1AtV8"
MAX_TABS = 7
GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
NOTIFY_EMAILS = ["carlos.guerrero@fastdolphin.com"]
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"

# ─── Claude AI Filter ─────────────────────────────────────────────────────────

AI_PROMPT = """You are a recruiting analyst for Fast Dolphin Consulting Group, a US-based IT staffing company that places consultants in Latin America or places Spanish/Portuguese-speaking consultants anywhere.

Analyze this job posting and answer: Is this a GENUINE opportunity for Fast Dolphin?

A job IS genuine if ANY of these are true:
- The role requires someone located in Latin America (Mexico, Brazil, Colombia, Argentina, Chile, Peru, Ecuador, Costa Rica, Panama, Bolivia, etc.)
- The role requires Spanish or Portuguese language skills
- The role explicitly mentions serving LATAM markets, clients, or regions
- The role is bilingual (English + Spanish or Portuguese)
- The job is based in a Latin American city (e.g. Mexico City, Guadalajara, Bogota, Sao Paulo, Buenos Aires, Santiago, Lima)
- The role mentions "nearshore" work involving Latin America

A job is NOT genuine if:
- Latin America is only mentioned as a company office location in a footer or boilerplate (e.g. "offices in USA, Mexico, India")
- The word "Mexico" refers to the US state of New Mexico with no other LATAM connection
- "Peru" appears only as part of the word "Perl" (programming language) or other unrelated words
- The company just lists countries where they have presence but the actual job has no LATAM requirement
- "Spanish" refers to something other than the Spanish language (e.g. a person's name, a place in Spain unrelated to LATAM)
- Latin America is mentioned only in an equal opportunity employment statement

Job Title: {title}
Company: {company}
Location: {location}
Keyword that matched: {keyword}

Job Description:
{description}

Respond with ONLY a JSON object in this exact format:
{{"decision": "YES" or "NO", "reason": "one sentence explanation"}}"""


def ai_filter_job(title, company, location, keyword, description):
    """Use Claude AI to intelligently determine if this is a genuine LATAM opportunity."""
    try:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

        # Truncate description to avoid excessive token usage
        desc_truncated = description[:3000] if len(description) > 3000 else description

        prompt = AI_PROMPT.format(
            title=title,
            company=company,
            location=location,
            keyword=keyword,
            description=desc_truncated
        )

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",  # Fast and cheap - perfect for filtering
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text.strip()

        # Parse JSON response
        result = json.loads(response_text)
        decision = result.get("decision", "NO").upper()
        reason = result.get("reason", "")

        print(f"  🤖 AI: {decision} — {reason}")
        return decision == "YES", reason

    except Exception as e:
        print(f"  ⚠️ AI filter error: {e} — keeping job by default")
        return True, "AI filter error - included by default"


# ─── Selenium Setup ───────────────────────────────────────────────────────────

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
                                "url": job_url,
                                "title": title,
                                "company": company,
                                "location": location,
                                "keyword": keyword,
                            })

                    if not page_jobs:
                        break

                    print(f"  🔗 Found {len(page_jobs)} cards")

                    # Visit each job detail page
                    for info in page_jobs:
                        if info["url"] in seen_urls:
                            continue
                        seen_urls.add(info["url"])

                        if "job-detail" not in info["url"]:
                            jobs.append(build_basic_row(info, keyword))
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

                            # Get job description (main content only)
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
                                "Keyword": keyword,
                                "AI Verified": "✅ Yes",
                                "Job URL": info["url"],
                                "Date Scraped": datetime.now().strftime("%Y-%m-%d"),
                            })
                            print(f"  ✅ Kept: {title[:60]}")

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
    return jobs


def build_basic_row(info, keyword):
    return {
        "Job Title": info["title"],
        "Company": info["company"],
        "Recruiter": "",
        "Location": info["location"],
        "Employment Type": "",
        "Work Type": "",
        "Corp to Corp": "",
        "Contract Duration": "",
        "Pay": "",
        "Keyword": keyword,
        "AI Verified": "⚠️ Not checked",
        "Job URL": info["url"],
        "Date Scraped": datetime.now().strftime("%Y-%m-%d"),
    }


# ─── Google Sheets ────────────────────────────────────────────────────────────

def write_to_sheets(jobs):
    creds_json = os.environ["GOOGLE_CREDENTIALS"]
    creds_dict = json.loads(creds_json)

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)

    tab_name = datetime.now().strftime("%b %d, %Y")

    try:
        existing = sh.worksheet(tab_name)
        sh.del_worksheet(existing)
    except:
        pass

    worksheet = sh.add_worksheet(title=tab_name, rows=str(len(jobs) + 2), cols="15")

    headers = ["Job Title", "Company", "Recruiter", "Location", "Employment Type",
               "Work Type", "Corp to Corp", "Contract Duration", "Pay",
               "Keyword", "AI Verified", "Job URL", "Date Scraped"]

    worksheet.append_row(headers)

    for job in jobs:
        worksheet.append_row([job.get(h, "") for h in headers])

    worksheet.format("A1:M1", {"textFormat": {"bold": True}})

    # Keep only MAX_TABS most recent tabs
    all_sheets = sh.worksheets()
    dated_sheets = [s for s in all_sheets if s.title != "Sheet1"]
    if len(dated_sheets) > MAX_TABS:
        dated_sheets.sort(key=lambda s: s.title)
        for old_sheet in dated_sheets[:len(dated_sheets) - MAX_TABS]:
            sh.del_worksheet(old_sheet)
            print(f"🗑️ Deleted old tab: {old_sheet.title}")

    print(f"✅ Written {len(jobs)} jobs to tab '{tab_name}'")
    return tab_name


# ─── Email ────────────────────────────────────────────────────────────────────

def send_email(job_count, tab_name):
    today = datetime.now().strftime("%B %d, %Y")
    subject = f"🐬 Fast Dolphin LATAM Leads — {today} ({job_count} verified leads)"

    body = f"""
<html>
<body style="font-family: Arial, sans-serif; background: #f4f6f9; padding: 20px;">
  <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
    <div style="background: #0A1628; padding: 28px 32px;">
      <h1 style="color: white; margin: 0; font-size: 22px;">Fast Dolphin · LATAM Lead Finder</h1>
      <p style="color: #7B93B8; margin: 6px 0 0;">Daily Dice.com scrape — {today}</p>
    </div>
    <div style="padding: 28px 32px;">
      <p style="font-size: 16px; color: #333;">Your daily LATAM contract leads are ready — <strong>AI verified</strong> for quality.</p>
      <div style="background: #f0f4ff; border-radius: 8px; padding: 20px; margin: 20px 0; text-align: center;">
        <div style="font-size: 42px; font-weight: bold; color: #1B6CF2;">{job_count}</div>
        <div style="color: #666; font-size: 14px;">verified LATAM contract leads found today</div>
        <div style="color: #00C2A8; font-size: 12px; margin-top: 6px;">✅ Each lead reviewed by AI to confirm genuine LATAM relevance</div>
      </div>
      <p style="color: #555;">Results are in the <strong>{tab_name}</strong> tab of your Google Sheet:</p>
      <div style="text-align: center; margin: 24px 0;">
        <a href="{SHEET_URL}" style="background: #1B6CF2; color: white; padding: 14px 28px; border-radius: 6px; text-decoration: none; font-weight: bold; font-size: 15px;">
          📊 Open Google Sheet
        </a>
      </div>
      <p style="color: #999; font-size: 12px;">Filtered for: Mexico · Brazil · Colombia · Argentina · Chile · LATAM · Spanish · and more<br>Employment type: Contract & Third Party only · Posted in last 3 days · AI-verified for quality</p>
    </div>
    <div style="background: #f9f9f9; padding: 16px 32px; text-align: center; border-top: 1px solid #eee;">
      <p style="color: #aaa; font-size: 12px; margin: 0;">Fast Dolphin Consulting Group · Internal use only</p>
    </div>
  </div>
</body>
</html>
"""

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
    print(f"🐬 Fast Dolphin LATAM Lead Scraper — AI Edition")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    print("\n🔎 Starting scrape...")
    jobs = scrape_all()
    print(f"\n✅ Total verified leads: {len(jobs)}")

    print("\n📊 Writing to Google Sheets...")
    tab_name = write_to_sheets(jobs)

    print("\n📧 Sending email notification...")
    send_email(len(jobs), tab_name)

    print("\n🎉 Done!")
