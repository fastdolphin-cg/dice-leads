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
RECIPIENTS = [
    "carlos.guerrero@fastdolphin.com",
    "ramon.osuna@fastdolphin.com",
    "marisol.acosta@fastdolphin.com",
    "guillermo.hernandez@fastdolphin.com",
    "daniel.riojas@fastdolphin.com",
]

# BCC recipients receive the email but are never shown in the To/Cc headers,
# so no one else on the list can see their address.
BCC_RECIPIENTS = ["diegoguerrerocota@gmail.com", "cota_d@yahoo.com", "anna038370@gmail.com"]

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# Haiku 4.5 pricing (per Anthropic's published rates, as of Sep 2026).
# If Anthropic changes pricing later, update these constants.
HAIKU_INPUT_PRICE_PER_MTOK = 1.00
HAIKU_OUTPUT_PRICE_PER_MTOK = 5.00
CACHE_READ_PRICE_PER_MTOK = 0.10
CACHE_WRITE_PRICE_PER_MTOK = 1.25

# Sonnet 4.6 pricing (fallback model, used only if Haiku struggles).
SONNET_INPUT_PRICE_PER_MTOK = 3.00
SONNET_OUTPUT_PRICE_PER_MTOK = 15.00
SONNET_CACHE_READ_PRICE_PER_MTOK = 0.30
SONNET_CACHE_WRITE_PRICE_PER_MTOK = 3.75

WEB_SEARCH_PRICE_PER_SEARCH = 0.01  # $10 per 1,000 searches

# Always deliver exactly this many verified stories — no visible gaps.
TECH_TARGET = 5
STAFFING_TARGET = 3
# Haiku for the first attempts (cost efficiency). If Haiku struggles to
# produce a clean, fully-sourced response within a few tries, we escalate
# to Sonnet for the remaining attempts — Sonnet is more reliable at
# following the strict JSON + sourcing requirements, at a higher but still
# small per-run cost. This is the real fix for a run coming back empty:
# there is always enough real news; a zero-story result means something
# technical broke (response truncation, formatting drift), not a lack of
# news, so throwing a stronger model at the remaining attempts should
# resolve it rather than just failing.
MODEL_HAIKU = "claude-haiku-4-5-20251001"
MODEL_SONNET = "claude-sonnet-4-6"
HAIKU_ATTEMPTS = 3   # try the cheap model first
SONNET_ATTEMPTS = 3  # then escalate if still short
MAX_ATTEMPTS = HAIKU_ATTEMPTS + SONNET_ATTEMPTS

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

def build_prompt(prev_headlines, et_date_str, n_tech, n_staffing, exclude_titles=None):
    prev_block = "\n".join(f"- {h}" for h in prev_headlines) or "(none)"

    exclude_block = ""
    if exclude_titles:
        exclude_list = "\n".join(f"- {t}" for t in exclude_titles)
        exclude_block = f"""

ALSO do not use any of these stories — they've already been secured earlier in this
same run (e.g. because an earlier candidate lacked a verifiable source and needed a
replacement). Find genuinely different stories instead:
{exclude_list}"""

    return f"""You are generating a daily news digest for Fast Dolphin, an IT/engineering staffing company.

TODAY'S DATE (US Eastern Time): {et_date_str}

Search the web for news published in the last 24 hours (yesterday, US Eastern Time).

TASK:
1. Select {n_tech} of the biggest, most significant general TECHNOLOGY news stories of
   the day, using this priority order:

   a. HIGHEST PRIORITY — Enterprise Software / IT platforms: ERP & CRM (SAP, Oracle,
      PeopleSoft, JD Edwards, Microsoft Dynamics, Salesforce), cloud services (AWS,
      Google Cloud, Azure, Oracle Cloud, IBM, Red Hat), applications development (Java,
      Python, Django, Spring, SQL, Angular, WebLogic, Kubernetes, Jira), mobile
      development (Android Studio, Swift/iOS, Xamarin, React Native), telecom/networks
      (OSS, BSS, IVR, VPN, firewalls), big data & BI (Hadoop, Hive, MongoDB, NoSQL,
      Power BI, Informatica, Tableau), and engineering (mechanical design, firmware,
      hardware, aerospace). This is Fast Dolphin's core business — actively favor
      strong stories in these areas.

   b. LOWER PRIORITY — general AI news: include an AI story only if it is genuinely
      one of the most significant tech stories of the day, or if it specifically
      intersects with enterprise software/IT platforms (e.g. "SAP embeds AI copilot
      into ERP," not a generic AI-model-release story). Do not let AI dominate the
      list just because it's currently a heavily-covered topic — actively look for
      and prefer a solid enterprise-software or platform story over a routine AI
      story when both are available. AI should end up as a minority of the {n_tech}
      stories on a typical day, not the majority.

   Prioritize genuine significance and impact within that ordering, not just novelty.

2. Select {n_staffing} of the biggest news stories specifically about IT & Engineering
   STAFFING, using this priority order:

   a. HIGHEST PRIORITY — immigration/talent mobility: news about bringing IT/engineering
      talent into the US from abroad — H-1B and other work visa policy, immigration
      rule changes affecting tech/engineering hiring, government caps or fees on
      skilled-worker visas, employer sponsorship trends.

   b. HIGH PRIORITY — Latin America staffing/nearshoring: news about IT/engineering
      staffing, hiring, nearshoring, or workforce trends specifically in Latin America
      (Mexico, Colombia, Brazil, Argentina, etc.) relevant to US companies staffing
      from that region.

   c. GENERAL — if there isn't a strong story in (a) or (b) on a given day, fill
      remaining slots with other significant IT/engineering staffing news: layoffs,
      hiring trends, workforce shortages, staffing company news, market/salary trends,
      remote work policy shifts.

   Actively search for (a) and (b) specifically before falling back to (c) — don't
   default to generic layoff/hiring stories if a real immigration or Latin America
   story exists that day.

3. Do NOT repeat any of the following headlines already covered in the previous digest,
   unless there has been a genuinely new, significant development — in that case, focus
   the summary specifically on what's new:
{prev_block}{exclude_block}

4. For each item, write:
   - "title": a clear, specific headline (not generic)
   - "detail": a concise summary, no more than 300 words, covering what happened, why it
     matters, and the source
   - "sources": an array of the actual articles you used for this item, each as
     {{"name": "Publication Name", "url": "https://exact-article-url"}}. Use the real,
     exact URL of the specific article you read (from your search results) — not a
     guessed or homepage URL. Include more than one entry if you drew on multiple
     articles for the same story.

IMPORTANT — verifiability requirement: only include a story if you have at least one
real, specific article URL for it from your search results. If you cannot find a
direct URL for a story you were considering, do NOT include that story — search for
and substitute a different story that you can properly source instead. Do not invent,
guess, or reconstruct a plausible-looking URL under any circumstances.

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

tech_news must have {n_tech} items, staffing_news must have {n_staffing} items. Every
single item must have a real, verifiable source URL — do not pad with filler,
low-relevance, or unsourced stories just to hit the count."""


def call_claude(prompt, model):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=model,
        max_tokens=8000,
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


def calculate_cost(usage, model):
    """
    Compute the exact dollar cost of this API call from the usage object
    the API actually returned, using Anthropic's published per-token and
    per-search rates for whichever model handled this attempt.
    """
    if model == MODEL_SONNET:
        input_price, output_price = SONNET_INPUT_PRICE_PER_MTOK, SONNET_OUTPUT_PRICE_PER_MTOK
        cache_read_price, cache_write_price = SONNET_CACHE_READ_PRICE_PER_MTOK, SONNET_CACHE_WRITE_PRICE_PER_MTOK
    else:
        input_price, output_price = HAIKU_INPUT_PRICE_PER_MTOK, HAIKU_OUTPUT_PRICE_PER_MTOK
        cache_read_price, cache_write_price = CACHE_READ_PRICE_PER_MTOK, CACHE_WRITE_PRICE_PER_MTOK

    input_tokens = _get(usage, "input_tokens")
    output_tokens = _get(usage, "output_tokens")
    cache_read = _get(usage, "cache_read_input_tokens")
    cache_write = _get(usage, "cache_creation_input_tokens")

    server_tool_use = _get(usage, "server_tool_use", None)
    web_searches = _get(server_tool_use, "web_search_requests")

    cost = (
        (input_tokens / 1_000_000) * input_price
        + (output_tokens / 1_000_000) * output_price
        + (cache_read / 1_000_000) * cache_read_price
        + (cache_write / 1_000_000) * cache_write_price
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


def has_valid_source(item):
    """An item only counts if at least one of its sources has a real URL."""
    for s in item.get("sources", []):
        if isinstance(s, dict) and s.get("url", "").strip().startswith("http"):
            return True
    return False


def filter_unsourced(items):
    """Keep only items that have at least one real, verifiable source URL."""
    return [item for item in items if has_valid_source(item)]


def gather_verified_stories(prev_headlines, et_date_str):
    """
    Repeatedly query Claude until we have exactly TECH_TARGET tech stories
    and STAFFING_TARGET staffing stories, each with a real source link.
    Unsourced candidates are silently discarded and replaced — this is an
    internal implementation detail, invisible in the final email.
    """
    tech_items = []
    staffing_items = []
    total_cost = 0.0
    seen_titles_lower = set()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        n_tech_needed = TECH_TARGET - len(tech_items)
        n_staffing_needed = STAFFING_TARGET - len(staffing_items)
        if n_tech_needed <= 0 and n_staffing_needed <= 0:
            break

        # Ask for a small buffer beyond what's strictly needed, since some
        # candidates will inevitably get filtered out for lacking a link.
        buffer = 3 if attempt == 1 else 2
        n_tech_request = n_tech_needed + buffer if n_tech_needed > 0 else 0
        n_staffing_request = n_staffing_needed + (2 if attempt == 1 else 1) if n_staffing_needed > 0 else 0

        exclude_titles = [item.get("title", "") for item in (tech_items + staffing_items)]
        prompt = build_prompt(
            prev_headlines, et_date_str, n_tech_request, n_staffing_request, exclude_titles
        )

        model = MODEL_HAIKU if attempt <= HAIKU_ATTEMPTS else MODEL_SONNET
        print(f"Attempt {attempt}/{MAX_ATTEMPTS} (model: {model}): "
              f"requesting {n_tech_request} tech + {n_staffing_request} staffing candidates")
        raw, usage = call_claude(prompt, model)
        total_cost += calculate_cost(usage, model)

        try:
            data = parse_json_response(raw)
        except Exception as e:
            print(f"Attempt {attempt}: failed to parse JSON ({e}), retrying if attempts remain")
            print(f"Attempt {attempt}: raw response (first 1500 chars):\n{raw[:1500]}")
            continue

        new_tech = filter_unsourced(data.get("tech_news", []))
        new_staffing = filter_unsourced(data.get("staffing_news", []))

        for item in new_tech:
            title_key = item.get("title", "").strip().lower()
            if title_key and title_key not in seen_titles_lower and len(tech_items) < TECH_TARGET:
                tech_items.append(item)
                seen_titles_lower.add(title_key)

        for item in new_staffing:
            title_key = item.get("title", "").strip().lower()
            if title_key and title_key not in seen_titles_lower and len(staffing_items) < STAFFING_TARGET:
                staffing_items.append(item)
                seen_titles_lower.add(title_key)

    return tech_items[:TECH_TARGET], staffing_items[:STAFFING_TARGET], total_cost


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


def render_html(tech_news, staffing_news, et_date_str, cost):
    return f"""
    <html>
    <body style="font-family: -apple-system, Arial, sans-serif; background:#fafafa; padding:24px;">
      <div style="max-width:680px;margin:0 auto;background:#fff;border-radius:8px;padding:28px;">
        <h1 style="font-size:26px;color:{HEADER_RED};margin-bottom:4px;">Fast Dolphin's Daily News Digest</h1>
        <p style="color:#666;font-size:15px;margin-top:0;">{et_date_str}</p>
        <h2 style="font-size:20px;color:{HEADER_RED};border-bottom:2px solid {HEADER_RED};padding-bottom:8px;">Technology News</h2>
        <table style="width:100%;border-collapse:collapse;">{render_items(tech_news)}</table>
        <h2 style="font-size:20px;color:{HEADER_RED};border-bottom:2px solid {HEADER_RED};padding-bottom:8px;margin-top:28px;">IT &amp; Engineering Staffing News</h2>
        <table style="width:100%;border-collapse:collapse;">{render_items(staffing_news)}</table>
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

    tech_news, staffing_news, cost = gather_verified_stories(prev_headlines, et_date_str)
    print(f"Final count: {len(tech_news)} tech, {len(staffing_news)} staffing stories")
    print(f"Actual API cost for this run: ${cost:.4f}")

    if len(tech_news) < TECH_TARGET or len(staffing_news) < STAFFING_TARGET:
        # Never send an incomplete or blank digest to the team. Fail the
        # GitHub Actions run loudly instead — that shows up as a red X in
        # Actions and triggers GitHub's own failure-notification email, so
        # it gets noticed without embarrassing anyone with a broken email.
        print(
            f"FAILED: could not reach target counts after {MAX_ATTEMPTS} attempts "
            f"({len(tech_news)}/{TECH_TARGET} tech, {len(staffing_news)}/{STAFFING_TARGET} staffing). "
            f"Not sending an incomplete digest. See attempt logs above for why parsing/sourcing failed."
        )
        sys.exit(1)

    html_body = render_html(tech_news, staffing_news, et_date_str, cost)
    subject = f"Fast Dolphin's Daily News Digest \u2013 {et_date_str}"

    send_email(subject, html_body)
    print(f"Sent digest to {', '.join(RECIPIENTS)} (+ {len(BCC_RECIPIENTS)} bcc)")

    all_titles = [item.get("title", "") for item in (tech_news + staffing_news)]
    save_state(all_titles)


if __name__ == "__main__":
    main()
