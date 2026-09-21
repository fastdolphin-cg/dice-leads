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

# Recipients for the daily digest. Add more addresses here to expand to the team.
RECIPIENTS = ["carlos.guerrero@fastdolphin.com", "ramon.osuna@fastdolphin.com"]

# BCC recipients receive the email but are never shown in the To/Cc headers,
# so no one else on the list can see their address.
BCC_RECIPIENTS = ["diegoguerrerocota@gmail.com", "cota_d@yahoo.com", "anna038370@gmail.com"]

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# Haiku for cost efficiency (matches existing app pattern). Swap to
# "claude-sonnet-4-6" if you want more nuanced writing later — the cost
# difference for one digest a day is trivial either way.
MODEL = "claude-haiku-4-5-20251001"

# Haiku 4.5 pricing (per Anthropic's published rates, as of Sep 2026).
# If Anthropic changes pricing later, update these constants.
HAIKU_INPUT_PRICE_PER_MTOK = 1.00
HAIKU_OUTPUT_PRICE_PER_MTOK = 5.00
CACHE_READ_PRICE_PER_MTOK = 0.10
CACHE_WRITE_PRICE_PER_MTOK = 1.25
WEB_SEARCH_PRICE_PER_SEARCH = 0.01  # $10 per 1,000 searches

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
   - "sources": an array of the actual articles you used for this item, each as
     {{"name": "Publication Name", "url": "https://exact-article-url"}}. Use the real,
     exact URL of the specific article you read (from your search results) — not a
     guessed or homepage URL. Include more than one entry if you drew on multiple
     articles for the same story.

Do your searching and thinking silently. Your final message must contain
NOTHING but the JSON object itself — no preamble like "I'll search for...",
no explanation of your process, no markdown code fences, and no citation
tags or HTML of any kind inside the field values (plain text only).

Respond with ONLY valid JSON, in exactly this shape:
{{
  "tech_news": [
    {{"title": "...", "detail": "...", "sources": [{{"name": "...", "url": "..."}}]}}
  ],
  "staffing_news": [
    {{"title": "...", "detail": "...", "sources": [{{"name": "...", "url": "..."}}]}}
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
    raw_text = "\n".join(text_parts)
    return raw_text, response.usage


def _get(obj, key, default=0):
    """Safely read an attribute or dict key, whichever form the SDK returns."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default) or default
    return getattr(obj, key, default) or default


def calculate_cost(usage):
    """
    Compute the exact dollar cost of this API call from the usage object
    the API actually returned, using Anthropic's published per-token and
    per-search rates. This is a real measurement, not an estimate.
    """
    input_tokens = _get(usage, "input_tokens")
    output_tokens = _get(usage, "output_tokens")
    cache_read = _get(usage, "cache_read_input_tokens")
    cache_write = _get(usage, "cache_creation_input_tokens")

    server_tool_use = _get(usage, "server_tool_use", None)
    web_searches = _get(server_tool_use, "web_search_requests")

    cost = (
        (input_tokens / 1_000_000) * HAIKU_INPUT_PRICE_PER_MTOK
        + (output_tokens / 1_000_000) * HAIKU_OUTPUT_PRICE_PER_MTOK
        + (cache_read / 1_000_000) * CACHE_READ_PRICE_PER_MTOK
        + (cache_write / 1_000_000) * CACHE_WRITE_PRICE_PER_MTOK
        + (web_searches * WEB_SEARCH_PRICE_PER_SEARCH)
    )
    return cost


def parse_json_response(raw_text):
    """
    Claude sometimes narrates its search process before producing the JSON
    ("I'll search for...", "Let me look at...") and may wrap the JSON in
    markdown code fences. Rather than assuming the JSON is the whole string,
    isolate the outermost {...} block directly.
    """
    text = raw_text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in Claude's response")
    return json.loads(text[start : end + 1])


def strip_markup(text):
    """
    Claude's web search sometimes embeds citation tags like
    <cite index="37-1">...</cite> directly in the text. Strip any such
    tags (and any other stray HTML) so the email body is clean plain text.
    """
    if not isinstance(text, str):
        return text
    text = re.sub(r"</?cite[^>]*>", "", text)
    text = re.sub(r"<[^>]+>", "", text)  # strip any other stray HTML tags
    return text.strip()


# ---------------------------------------------------------------------------
# Email formatting + sending
# ---------------------------------------------------------------------------

HEADER_RED = "#D32F2F"  # Fast Dolphin brand red (best-guess; adjust if you have the exact hex)


def render_sources(sources):
    """Render one or more source links as comma-separated <a> tags, falling
    back to plain text if no URL was provided for a given source."""
    if not sources:
        return ""
    parts = []
    for s in sources:
        name = strip_markup(s.get("name", "")) if isinstance(s, dict) else strip_markup(str(s))
        url = s.get("url", "") if isinstance(s, dict) else ""
        if url:
            safe_url = url.replace('"', "%22")
            parts.append(f'<a href="{safe_url}" style="color:{HEADER_RED};text-decoration:none;">{name}</a>')
        elif name:
            parts.append(name)
    return ", ".join(parts)


def render_items(items):
    html = ""
    for i, item in enumerate(items, 1):
        title = strip_markup(item.get("title", ""))
        detail = strip_markup(item.get("detail", ""))
        sources_html = render_sources(item.get("sources", []))
        html += f"""
        <tr>
          <td style="padding:20px 0;border-bottom:1px solid #e5e5e5;">
            <div style="font-weight:600;font-size:20px;color:{HEADER_RED};margin-bottom:8px;">
              {i}. {title}
            </div>
            <div style="font-size:17px;color:#444;line-height:1.6;">
              {detail}
            </div>
            <div style="font-size:15px;color:#888;margin-top:8px;">
              Source: {sources_html}
            </div>
          </td>
        </tr>"""
    return html


def render_html(data, et_date_str, cost):
    note = data.get("note", "")
    note_html = (
        f'<p style="color:#b45309;font-size:16px;">{note}</p>' if note else ""
    )

    return f"""
    <html>
    <body style="font-family: -apple-system, Arial, sans-serif; background:#fafafa; padding:24px;">
      <div style="max-width:680px;margin:0 auto;background:#fff;border-radius:8px;padding:28px;">
        <h1 style="font-size:26px;color:{HEADER_RED};margin-bottom:4px;">Fast Dolphin's Daily News Digest</h1>
        <p style="color:#666;font-size:15px;margin-top:0;">{et_date_str}</p>
        {note_html}
        <h2 style="font-size:20px;color:{HEADER_RED};border-bottom:2px solid {HEADER_RED};padding-bottom:8px;">Technology News</h2>
        <table style="width:100%;border-collapse:collapse;">{render_items(data.get('tech_news', []))}</table>
        <h2 style="font-size:20px;color:{HEADER_RED};border-bottom:2px solid {HEADER_RED};padding-bottom:8px;margin-top:28px;">IT &amp; Engineering Staffing News</h2>
        <table style="width:100%;border-collapse:collapse;">{render_items(data.get('staffing_news', []))}</table>
        <p style="color:#aaa;font-size:13px;margin-top:28px;">
          Generated automatically by Fast Dolphin's Continuous Improvement Initiative.
          Total cost of this run: ${cost:.4f}
        </p>
      </div>
    </body>
    </html>
    """


def send_email(subject, html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = ", ".join(RECIPIENTS)
    # Deliberately no "Bcc" header set — BCC addresses are passed only to the
    # SMTP envelope below, not written into any header, so they stay hidden
    # from everyone else on the list.
    msg.attach(MIMEText(html_body, "html"))

    all_envelope_recipients = RECIPIENTS + BCC_RECIPIENTS

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, all_envelope_recipients, msg.as_string())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    et_now = datetime.now(ZoneInfo("America/New_York"))
    et_date_str = et_now.strftime("%B %d, %Y")

    prev_headlines = load_previous_headlines()
    prompt = build_prompt(prev_headlines, et_date_str)

    raw, usage = call_claude(prompt)
    cost = calculate_cost(usage)
    print(f"Actual API cost for this run: ${cost:.4f}")

    try:
        data = parse_json_response(raw)
    except Exception as e:
        print("Failed to parse Claude's response as JSON:", e)
        print("Raw response:\n", raw)
        sys.exit(1)

    html_body = render_html(data, et_date_str, cost)
    subject = f"Fast Dolphin's Daily News Digest \u2013 {et_date_str}"

    send_email(subject, html_body)
    print(f"Sent digest to {', '.join(RECIPIENTS)} (+ {len(BCC_RECIPIENTS)} bcc)")

    all_titles = [
        item.get("title", "")
        for item in data.get("tech_news", []) + data.get("staffing_news", [])
    ]
    save_state(all_titles)


if __name__ == "__main__":
    main()
