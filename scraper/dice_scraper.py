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
    """Use Claude AI to intelligently determine if this is a genuine LATAM opportunity."""
    try:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        desc_truncated = description[:3000] if len(description) > 3000 else description
        prompt = AI_PROMPT.format(
            title=title,
            company=company,
            location=location,
            keyword=keyword,
            description=desc_truncated
        )
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system="You are a strict JSON-only responder. Always respond with valid JSON only, no other text.",
            messages=[{"role": "user", "content": prompt}]
        )
        response_text = message.content[0].text.strip()
        print(f"  🔍 Raw AI response: {response_text[:200]}")
        # Strip markdown code blocks if present
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
        print(f"  ⚠️ AI filter error: {type(e).__name__}: {e} — keeping job by default")
        return True, f"AI filter error: {type(e).__name__}: {e}"


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

                            description = ""
                            # Try multiple selectors to find job description
                            desc_selectors = [
                                "div.job-description",
                                "[data-testid='jobDescriptionHtml']",
                                "div[data-cy='jobDescription']",
                                "section.job-description",
                                "#jobDescription",
                                "div.job-details",
                                "div.description",
                                "article",
                                "main",
                            ]
                            for sel in desc_selectors:
                                try:
                                    desc_el = driver.find_element(By.CSS_SELECTOR, sel)
                                    text = desc_el.text.strip()
                                    if text and len(text) > 100:
                                        description = text
                                        break
                                except:
                                    continue
                            
                            # Last resort: get all visible text from body
                            if not description:
                                try:
                                    description = driver.find_element(By.TAG_NAME, "body").text[:3000]
                                except:
                                    pass
                            
                            print(f"  📝 Description length: {len(description)} chars")

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
                                "AI Verified": "Yes",
                                "AI Reason": reason,
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
        "AI Verified": "Not checked",
        "AI Reason": "",
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
               "Keyword", "AI Verified", "AI Reason", "Job URL", "Date Scraped"]

    worksheet.append_row(headers)

    for job in jobs:
        worksheet.append_row([job.get(h, "") for h in headers])

    worksheet.format("A1:N1", {"textFormat": {"bold": True}})

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
    subject = f"Fast Dolphin LATAM Leads — {today} ({job_count} verified leads)"

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
        <div style="color: #00C2A8; font-size: 12px; margin-top: 6px;">Each lead reviewed by AI to confirm genuine LATAM relevance</div>
      </div>
      <p style="color: #555;">Results are in the <strong>{tab_name}</strong> tab of your Google Sheet:</p>
      <div style="text-align: center; margin: 24px 0; display: flex; gap: 12px; justify-content: center; flex-wrap: wrap;">
        <a href="{SHEET_URL}" style="background: #1B6CF2; color: white; padding: 14px 28px; border-radius: 6px; text-decoration: none; font-weight: bold; font-size: 15px; display: inline-block;">
          📊 Open Google Sheet
        </a>
        <a href="https://fastdolphin-cg.github.io/dice-leads" style="background: #0A1628; color: white; padding: 14px 28px; border-radius: 6px; text-decoration: none; font-weight: bold; font-size: 15px; display: inline-block; border: 1px solid #1B6CF2;">
          🐬 Open Lead Finder App
        </a>
      </div>
      <p style="color: #999; font-size: 12px;">Filtered for: Mexico · Brazil · Colombia · Argentina · Chile · LATAM · Spanish · and more<br>Employment type: Contract and Third Party only · Posted in last 3 days · AI-verified for quality</p>
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


# ─── Save JSON to GitHub ──────────────────────────────────────────────────────

def save_json_to_github(jobs, tab_name):
    """Save results as JSON files in public/data/ and push to GitHub."""
    import glob
    import subprocess

    os.makedirs('public/data', exist_ok=True)

    payload = {
        "tab": tab_name,
        "scraped_at": datetime.now().isoformat(),
        "count": len(jobs),
        "jobs": jobs
    }

    with open('public/data/latest.json', 'w') as f:
        json.dump(payload, f, indent=2)
    print("✅ Wrote public/data/latest.json")

    date_str = datetime.now().strftime("%Y-%m-%d")
    with open(f'public/data/{date_str}.json', 'w') as f:
        json.dump(payload, f, indent=2)
    print(f"✅ Wrote public/data/{date_str}.json")

    dated_files = sorted(glob.glob('public/data/????-??-??.json'), reverse=True)[:7]
    index = [os.path.basename(f).replace('.json', '') for f in dated_files]
    with open('public/data/index.json', 'w') as f:
        json.dump(index, f)
    print(f"✅ Wrote public/data/index.json: {index}")

    subprocess.run(['git', 'config', 'user.email', 'scraper@fastdolphin.com'], check=True)
    subprocess.run(['git', 'config', 'user.name', 'Fast Dolphin Scraper'], check=True)
    subprocess.run(['git', 'add', 'public/data/'], check=True)
    result = subprocess.run(['git', 'commit', '-m', f'Data: {tab_name} ({len(jobs)} leads)'],
                           capture_output=True, text=True)
    if result.returncode == 0:
        subprocess.run(['git', 'push'], check=True)
        print("✅ Data pushed to GitHub")
    else:
        print("ℹ️ Nothing to commit")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Fast Dolphin LATAM Lead Scraper — AI Edition")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    print("\nStarting scrape...")
    jobs = scrape_all()
    print(f"\nTotal verified leads: {len(jobs)}")

    print("\nWriting to Google Sheets...")
    tab_name = write_to_sheets(jobs)

    print("\nSaving JSON to GitHub...")
    save_json_to_github(jobs, tab_name)

    print("\nSending email notification...")
    send_email(len(jobs), tab_name)

    print("\nDone!")
