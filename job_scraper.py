import requests
import smtplib
import os
import json
import re
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup

# ================= CONFIG (FROM GITHUB SECRETS) ================= #

EMAIL        = os.environ.get("gairolashivansh@gmail.com")
APP_PASSWORD = os.environ.get("jyxigfjolfroxzpn")
TELEGRAM_TOKEN = os.environ.get("8702304485:AAEu9VgrWtKvlq86v-x4RNZWUqG18wABU28")
CHAT_ID      = os.environ.get("8702304485")

SEEN_FILE = "seen_jobs.json"

KEYWORDS = [
    ".net", "c#", "asp.net",
    ".net core", "dot net",
    "edi", "electronic data interchange"
]

EXPERIENCE_PATTERNS = [
    r"0\s*[-–]\s*[123]\s*years?",
    r"1\s*[-–]\s*[23]\s*years?",
    r"1\s*to\s*[23]\s*years?",
    r"fresher",
    r"entry[\s-]level",
    r"junior",
    r"0\s*[-–]\s*1\s*years?",
    r"\b1\s*year\b",
    r"\b2\s*years?\b",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ================= GREENHOUSE COMPANIES ================= #

GREENHOUSE_COMPANIES = [
    ("Atlassian",    "atlassian"),
    ("Freshworks",   "freshworks"),
    ("Postman",      "postman"),
    ("Razorpay",     "razorpay"),
    ("Browserstack", "browserstack"),
    ("Chargebee",    "chargebee"),
    ("Hasura",       "hasura"),
    ("Moengage",     "moengage"),
    ("Whatfix",      "whatfix"),
    ("Clevertap",    "clevertap"),
    ("Visa", "visa"),
    ("Mastercard",  "mastercard")
]

# ================= LEVER COMPANIES ================= #

LEVER_COMPANIES = [
    ("Meesho",        "meesho"),
    ("Darwinbox",     "darwinbox"),
    ("Unacademy",     "unacademy"),
    ("slice",         "sliceit"),
    ("Groww",         "groww"),
    ("Sigmoid",       "sigmoid"),
    ("Mindtickle",    "mindtickle"),
]

# ================= UTIL ================= #

def keyword_match(text: str) -> bool:
    text = text.lower()
    return any(k in text for k in KEYWORDS)

def experience_match(text: str) -> bool:
    text = text.lower()
    return any(re.search(p, text) for p in EXPERIENCE_PATTERNS)

def safe_get(url: str, headers=None, retries=2, delay=3) -> requests.Response | None:
    """GET with retry logic and timeout."""
    for attempt in range(retries):
        try:
            res = requests.get(url, headers=headers or {}, timeout=15)
            res.raise_for_status()
            return res
        except requests.RequestException as e:
            print(f"  [Attempt {attempt+1}] GET failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(delay)
    return None

# ================= ALERTS ================= #

def send_email(subject: str, body: str):
    if not EMAIL or not APP_PASSWORD:
        print("⚠️  Email credentials missing — skipping email.")
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = EMAIL
        msg["To"]      = EMAIL
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(EMAIL, APP_PASSWORD)
            server.send_message(msg)

        print("  ✅ Email sent.")
    except Exception as e:
        print(f"  ❌ Email failed: {e}")


def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("⚠️  Telegram credentials missing — skipping Telegram.")
        return
    try:
        url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        resp = requests.post(url, data={
            "chat_id":    CHAT_ID,
            "text":       message,
            "parse_mode": "HTML",
        }, timeout=10)
        if resp.ok:
            print("  ✅ Telegram sent.")
        else:
            print(f"  ❌ Telegram error: {resp.text}")
    except Exception as e:
        print(f"  ❌ Telegram exception: {e}")

# ================= STORAGE ================= #

def load_seen() -> list:
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []

def save_seen(seen: list):
    try:
        with open(SEEN_FILE, "w") as f:
            json.dump(seen, f, indent=2)
    except IOError as e:
        print(f"⚠️  Could not save seen file: {e}")

# ================= GREENHOUSE API ================= #

def scrape_greenhouse(company: str, board: str) -> list:
    jobs = []
    url  = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"

    res = safe_get(url)
    if not res:
        print(f"  ⚠️  {company} (Greenhouse): no response")
        return jobs

    try:
        data = res.json()
    except ValueError:
        print(f"  ⚠️  {company} (Greenhouse): bad JSON")
        return jobs

    for job in data.get("jobs", []):
        title   = job.get("title", "")
        link    = job.get("absolute_url", "")
        content = job.get("content", "")          # full description (HTML)
        location = ""
        if job.get("location"):
            location = job["location"].get("name", "")

        # Flatten HTML description to plain text for keyword/exp matching
        desc_text = BeautifulSoup(content, "html.parser").get_text(" ")

        if keyword_match(title + " " + desc_text):
            jobs.append({
                "company":  company,
                "title":    title,
                "link":     link,
                "location": location,
                "source":   "Greenhouse",
            })

    print(f"  [{company}] Greenhouse → {len(jobs)} matched")
    return jobs

# ================= LEVER API ================= #

def scrape_lever(company: str, board: str) -> list:
    jobs = []
    url  = f"https://api.lever.co/v0/postings/{board}?mode=json"

    res = safe_get(url)
    if not res:
        print(f"  ⚠️  {company} (Lever): no response")
        return jobs

    try:
        data = res.json()
    except ValueError:
        print(f"  ⚠️  {company} (Lever): bad JSON")
        return jobs

    for job in data:
        title    = job.get("text", "")
        link     = job.get("hostedUrl", "")
        location = job.get("categories", {}).get("location", "")

        # Combine all text for matching
        lists    = job.get("lists", [])
        desc_text = " ".join(
            BeautifulSoup(item.get("content", ""), "html.parser").get_text(" ")
            for item in lists
        )
        additional = BeautifulSoup(
            job.get("additional", ""), "html.parser"
        ).get_text(" ")
        full_text = title + " " + desc_text + " " + additional

        if keyword_match(full_text):
            jobs.append({
                "company":  company,
                "title":    title,
                "link":     link,
                "location": location,
                "source":   "Lever",
            })

    print(f"  [{company}] Lever → {len(jobs)} matched")
    return jobs

# ================= REMOTIVE (REMOTE .NET JOBS) ================= #

def scrape_remotive() -> list:
    """Remotive has a free public JSON API — no scraping needed."""
    jobs = []
    url  = "https://remotive.com/api/remote-jobs?category=software-dev&limit=100"

    res = safe_get(url)
    if not res:
        print("  ⚠️  Remotive: no response")
        return jobs

    try:
        data = res.json()
    except ValueError:
        print("  ⚠️  Remotive: bad JSON")
        return jobs

    for job in data.get("jobs", []):
        title       = job.get("title", "")
        link        = job.get("url", "")
        description = job.get("description", "")
        company     = job.get("company_name", "Remote")
        location    = job.get("candidate_required_location", "Remote")

        desc_text = BeautifulSoup(description, "html.parser").get_text(" ")

        if keyword_match(title + " " + desc_text):
            jobs.append({
                "company":  company,
                "title":    title,
                "link":     link,
                "location": location,
                "source":   "Remotive",
            })

    print(f"  [Remotive] → {len(jobs)} matched")
    return jobs

# ================= ARBEITNOW (FREE JOB API) ================= #

def scrape_arbeitnow() -> list:
    """Arbeitnow offers a free job listing API usable without auth."""
    jobs = []
    base = "https://www.arbeitnow.com/api/job-board-api"

    for page in range(1, 4):            # check first 3 pages
        res = safe_get(f"{base}?page={page}")
        if not res:
            break
        try:
            data = res.json()
        except ValueError:
            break

        items = data.get("data", [])
        if not items:
            break

        for job in items:
            title       = job.get("title", "")
            link        = job.get("url", "")
            description = job.get("description", "")
            company     = job.get("company_name", "")
            location    = job.get("location", "")

            desc_text = BeautifulSoup(description, "html.parser").get_text(" ")

            if keyword_match(title + " " + desc_text):
                jobs.append({
                    "company":  company,
                    "title":    title,
                    "link":     link,
                    "location": location,
                    "source":   "Arbeitnow",
                })

        time.sleep(1)                   # be polite between pages

    print(f"  [Arbeitnow] → {len(jobs)} matched")
    return jobs

# ================= MAIN SCRAPER ================= #

def scrape_all() -> list:
    all_jobs = []

    print("\n🔍 Scraping Greenhouse boards...")
    for company, board in GREENHOUSE_COMPANIES:
        all_jobs += scrape_greenhouse(company, board)
        time.sleep(0.5)

    print("\n🔍 Scraping Lever boards...")
    for company, board in LEVER_COMPANIES:
        all_jobs += scrape_lever(company, board)
        time.sleep(0.5)

    print("\n🔍 Scraping Remotive API...")
    all_jobs += scrape_remotive()

    print("\n🔍 Scraping Arbeitnow API...")
    all_jobs += scrape_arbeitnow()

    # Deduplicate by link
    seen_links = set()
    unique = []
    for job in all_jobs:
        if job["link"] not in seen_links:
            seen_links.add(job["link"])
            unique.append(job)

    print(f"\n📊 Total unique matched jobs: {len(unique)}")
    return unique

# ================= MESSAGE BUILDER ================= #

def build_message(job: dict) -> str:
    return (
        f"🚀 New Job Opening!\n\n"
        f"🏢 Company  : {job['company']}\n"
        f"💼 Role     : {job['title']}\n"
        f"📍 Location : {job.get('location') or 'Not specified'}\n"
        f"🔗 Link     : {job['link']}\n"
        f"📡 Source   : {job['source']}"
    )

# ================= MAIN ================= #

def main():
    print("=" * 55)
    print("  Job Scraper Starting")
    print("=" * 55)

    # Debug: confirm secrets are loaded
    print(f"\n🔑 EMAIL        : {'✅ set' if EMAIL else '❌ missing'}")
    print(f"🔑 APP_PASSWORD : {'✅ set' if APP_PASSWORD else '❌ missing'}")
    print(f"🔑 TELEGRAM     : {'✅ set' if TELEGRAM_TOKEN else '❌ missing'}")
    print(f"🔑 CHAT_ID      : {'✅ set' if CHAT_ID else '❌ missing'}\n")

    seen     = load_seen()
    jobs     = scrape_all()
    new_jobs = [j for j in jobs if j["link"] not in seen]

    print(f"\n🆕 New jobs (not seen before): {len(new_jobs)}")

    if not new_jobs:
        print("✅ No new jobs this run.")
    else:
        for job in new_jobs:
            print(f"\n  → Sending alert for: {job['title']} @ {job['company']}")
            message = build_message(job)
            send_email(f"New Job: {job['title']} @ {job['company']} 🚀", message)
            send_telegram(message)
            seen.append(job["link"])
            time.sleep(1)               # avoid rate-limits between notifications

    save_seen(seen)
    print("\n✅ Done. seen_jobs.json updated.")

if __name__ == "__main__":
    main()
