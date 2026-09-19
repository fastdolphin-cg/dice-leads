"""
Fast Dolphin Daily News Digest
Researches 7 general tech news stories + 3 IT/Engineering staffing news stories
via the Claude API (with built-in web search), formats them as an HTML email,
and sends via Gmail SMTP. Designed to run daily via GitHub Actions.

Avoids repeating yesterday's headlines by reading/writing a small state file
that gets committed back to the repo after each successful run.
"""

import os
import sys
import json
import re
import smtplib
from datetime import datetime
from zoneinfo import ZoneInfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

STATE_PATH = os.path.join(os.path.dirname(__file__), "state", "last_digest.json")

# For now, just Carlos. Add more addresses here later to expand to the team.
RECIPIENTS = ["carlos.guerrero@fastdolphin.com"]

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# Haiku for cost efficiency (matches existing app pattern). Swap to
# "claude-sonnet-4-6" if you want more nuanced writing later — the cost
# difference for one digest a day is trivial either way.
MODEL = "claude-haiku-4-5-20251001"

# ---------------------------------------------------------------------------
# State (avoids repeating yesterday's stories)
# ---------------------------------------------------------------------------

def load_previous_headlines():
    if not os.path.exists(STATE_PATH):
        return []
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("headlines", [])
    except Exception:
        return []


def save_state(headlines):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"headlines": headlines, "saved_at": datetime.utcnow().isoformat()},
            f,
            indent=2,
        )


# ---------------------------------------------------------------------------
# Claude API call
# ---------------------------------------------------------------------------

def build_prompt(prev_headlines, et_date_str):
    prev_block = "\n".join(f"- {h}" for h in prev_headlines) or "(none)"

    return f"""You are generating a daily news digest for Fast Dolphin, an IT/engineering staffing company.

TODAY'S DATE (US Eastern Time): {et_date_str}

Search the web for news published in the last 24 hours (yesterday, US Eastern Time).

TASK:
1. Select the 7 biggest, most significant general TECHNOLOGY news stories of the day.
   Range broadly across the tech industry — ERP/CRM, cloud services, mobile development,
   telecom/networks, software development, AI, big data/BI, engineering (mechanical,
   firmware/hardware, aerospace) — or any other major tech story. Prioritize genuine
   significance and impact over sticking to any fixed category list.

2. Select the 3 biggest news stories specifically about IT & Engineering STAFFING —
   hiring trends, layoffs, workforce shortages, staffing company news, market/salary
   trends, remote work policy shifts, visa/labor policy affecting IT/engineering hiring.

3. Do NOT repeat any of the following headlines already covered in the previous digest,
   unless there has been a genuinely new, significant development — in that case, focus
   the summary specifically on what's new:
{prev_block}

4. For each of the 10 items, write:
   - "title": a clear, specific headline (not generic)
   - "detail": a concise summary, no more than 300 words, covering what happened, why it
     matters, and the source
   - "source": the publication name

Respond with ONLY valid JSON, no markdown fences, no preamble, in exactly this shape:
{{
  "tech_news": [
    {{"title": "...", "detail": "...", "source": "..."}}
  ],
  "staffing_news": [
    {{"title": "...", "detail": "...", "source": "..."}}
  ]
}}

tech_news must have 7 items, staffing_news must have 3 items. If fewer than 7 or 3
qualifying stories exist, include as many strong ones as you can find and add a "note"
field at the top level briefly explaining the shortfall. Do not pad with filler or
low-relevance stories."""


def call_claude(prompt):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )
    text_parts = [
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ]
    return "\n".join(text_parts)


def parse_json_response(raw_text):
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    return json.loads(cleaned)


# ---------------------------------------------------------------------------
# Email formatting + sending
# ---------------------------------------------------------------------------

def render_items(items):
    html = ""
    for i, item in enumerate(items, 1):
        html += f"""
        <tr>
          <td style="padding:16px 0;border-bottom:1px solid #e5e5e5;">
            <div style="font-weight:600;font-size:16px;color:#1a1a1a;margin-bottom:6px;">
              {i}. {item.get('title', '')}
            </div>
            <div style="font-size:14px;color:#444;line-height:1.5;">
              {item.get('detail', '')}
            </div>
            <div style="font-size:12px;color:#888;margin-top:6px;">
              Source: {item.get('source', '')}
            </div>
          </td>
        </tr>"""
    return html


def render_html(data, et_date_str):
    note = data.get("note", "")
    note_html = (
        f'<p style="color:#b45309;font-size:13px;">{note}</p>' if note else ""
    )

    return f"""
    <html>
    <body style="font-family: -apple-system, Arial, sans-serif; background:#fafafa; padding:24px;">
      <div style="max-width:640px;margin:0 auto;background:#fff;border-radius:8px;padding:24px;">
        <h1 style="font-size:20px;color:#1a1a1a;margin-bottom:4px;">Fast Dolphin's Daily News Digest</h1>
        <p style="color:#666;font-size:13px;margin-top:0;">{et_date_str}</p>
        {note_html}
        <h2 style="font-size:16px;color:#1a1a1a;border-bottom:2px solid #1a1a1a;padding-bottom:6px;">Technology News</h2>
        <table style="width:100%;border-collapse:collapse;">{render_items(data.get('tech_news', []))}</table>
        <h2 style="font-size:16px;color:#1a1a1a;border-bottom:2px solid #1a1a1a;padding-bottom:6px;margin-top:24px;">IT &amp; Engineering Staffing News</h2>
        <table style="width:100%;border-collapse:collapse;">{render_items(data.get('staffing_news', []))}</table>
        <p style="color:#aaa;font-size:11px;margin-top:24px;">Generated automatically by Fast Dolphin's news digest bot.</p>
      </div>
    </body>
    </html>
    """


def send_email(subject, html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = ", ".join(RECIPIENTS)
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, RECIPIENTS, msg.as_string())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    et_now = datetime.now(ZoneInfo("America/New_York"))
    et_date_str = et_now.strftime("%B %d, %Y")

    prev_headlines = load_previous_headlines()
    prompt = build_prompt(prev_headlines, et_date_str)

    raw = call_claude(prompt)

    try:
        data = parse_json_response(raw)
    except Exception as e:
        print("Failed to parse Claude's response as JSON:", e)
        print("Raw response:\n", raw)
        sys.exit(1)

    html_body = render_html(data, et_date_str)
    subject = f"Fast Dolphin's Daily News Digest \u2013 {et_date_str}"

    send_email(subject, html_body)
    print(f"Sent digest to {', '.join(RECIPIENTS)}")

    all_titles = [
        item.get("title", "")
        for item in data.get("tech_news", []) + data.get("staffing_news", [])
    ]
    save_state(all_titles)


if __name__ == "__main__":
    main()
