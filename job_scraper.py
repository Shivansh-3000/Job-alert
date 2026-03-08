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

EMAIL          = os.environ.get("EMAIL")
APP_PASSWORD   = os.environ.get("APP_PASSWORD")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID        = os.environ.get("CHAT_ID")

SEEN_FILE = "seen_jobs.json"

# ---------------------------------------------------------------
# TITLE_KEYWORDS  → matched against job TITLE only (precise)
# DESC_KEYWORDS   → matched against title + description (broader)
# ---------------------------------------------------------------
TITLE_KEYWORDS = [
    ".net", "c#", "asp.net", ".net core", "dot net",
    "edi", "electronic data interchange",
    "dotnet", "csharp",
]

DESC_KEYWORDS = [
    "asp.net", ".net core", "c# developer", "dotnet developer",
    "electronic data interchange", "edi developer",
    "dot net developer",
]

EXPERIENCE_PATTERNS = [
    r"0\s*[-–]\s*[123]\s*years?",
    r"1\s*[-–]\s*[23]\s*years?",
    r"1\s*to\s*[23]\s*years?",
    r"fresher", r"entry[\s-]level", r"junior",
    r"0\s*[-–]\s*1\s*years?",
    r"\b1\s*year\b", r"\b2\s*years?\b",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# ================================================================ #
#   TITLE match — precise, used for all sources                    #
# ================================================================ #
def title_match(title: str) -> bool:
    t = title.lower()
    return any(k in t for k in TITLE_KEYWORDS)

# ================================================================ #
#   DESC match — only for multi-word specific phrases              #
# ================================================================ #
def desc_match(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in DESC_KEYWORDS)

def experience_match(text: str) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in EXPERIENCE_PATTERNS)

def strip_html(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text(" ")

def safe_get(url, headers=None, params=None, retries=2, delay=3):
    for attempt in range(retries):
        try:
            res = requests.get(
                url, headers=headers or {}, params=params, timeout=15
            )
            res.raise_for_status()
            return res
        except requests.RequestException as e:
            print(f"  [Attempt {attempt+1}] GET failed → {url}: {e}")
            if attempt < retries - 1:
                time.sleep(delay)
    return None

# ================================================================ #
#   COMPANY LISTS — verified board IDs                             #
# ================================================================ #

# ── Greenhouse ───────────────────────────────────────────────────
# Format: (Display Name, greenhouse_board_id)
GREENHOUSE_COMPANIES = [
    # Indian product companies
    ("Freshworks",      "freshworks"),
    ("Postman",         "postman"),
    ("Sprinklr",        "sprinklr"),
    ("Innovaccer",      "innovaccer"),
    ("Druva",           "druva"),
    ("Icertis",         "icertis"),
    ("PhonePe",         "phonepe"),
    # Global product companies
    ("Atlassian",       "atlassian"),
    ("Stripe",          "stripe"),
    ("Figma",           "figma"),
    ("Notion",          "notion"),
    ("Coinbase",        "coinbase"),
    ("Discord",         "discord"),
    ("Dropbox",         "dropbox"),
    ("Zscaler",         "zscaler"),
    ("CrowdStrike",     "crowdstrike"),
    ("MongoDB",         "mongodb"),
    ("Twilio",          "twilio"),
    ("Datadog",         "datadoghq"),
    ("Grammarly",       "grammarly"),
    ("HashiCorp",       "hashicorp"),
    ("Robinhood",       "robinhood"),
    ("Canva",           "canva"),
    ("Snap",            "snap"),
    ("Lyft",            "lyft"),
]

# ── Lever ────────────────────────────────────────────────────────
# Format: (Display Name, lever_board_id)
LEVER_COMPANIES = [
    # Indian product companies
    ("Meesho",          "meesho"),
    ("Mindtickle",      "mindtickle"),
    ("CRED",            "cred"),
    ("BrowserStack",    "browserstack"),
    ("Razorpay",        "razorpay"),
    ("Chargebee",       "chargebee"),
    ("CleverTap",       "clevertap"),
    ("MoEngage",        "moengage"),
    ("Whatfix",         "whatfix"),
    ("Groww",           "groww"),
    # Global product companies
    ("Netflix",         "netflix"),
    ("Reddit",          "reddit"),
    ("Scale AI",        "scaleai"),
    ("Airtable",        "airtable"),
    ("Anduril",         "anduril"),
]

# ── Workday ──────────────────────────────────────────────────────
# Format: (Display Name, tenant, board_id, wd_version)
WORKDAY_COMPANIES = [
    ("Visa",            "visa",         "Visa_Careers",             "1"),
    ("Mastercard",      "mastercard",   "MCW_Careers",              "1"),
    ("Walmart",         "walmart",      "WalmartExternalCareers",   "5"),
    ("SAP",             "sap",          "SAP",                      "1"),
    ("Adobe",           "adobe",        "ADBE_University_Hiring",   "1"),
    ("PayPal",          "paypal",       "jobs",                     "1"),
    ("Intuit",          "intuit",       "Intuit_Careers",           "1"),
    ("Salesforce",      "salesforce",   "External_Career_Site",     "2"),
    ("ServiceNow",      "servicenow",   "External",                 "1"),
]

# ================================================================ #
#   ALERTS                                                         #
# ================================================================ #

def send_email(subject: str, body: str):
    if not EMAIL or not APP_PASSWORD:
        print("  ⚠️  Email credentials missing — skipping.")
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
        print("  ⚠️  Telegram credentials missing — skipping.")
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

# ================================================================ #
#   STORAGE                                                        #
# ================================================================ #

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

# ================================================================ #
#   SCRAPERS                                                       #
# ================================================================ #

def scrape_greenhouse(company: str, board: str) -> list:
    jobs = []
    url  = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    res  = safe_get(url)
    if not res:
        return jobs

    try:
        data = res.json()
    except ValueError:
        return jobs

    for job in data.get("jobs", []):
        title    = job.get("title", "")
        link     = job.get("absolute_url", "")
        location = job.get("location", {}).get("name", "")
        desc     = strip_html(job.get("content", ""))

        # ✅ Title must match — prevents false positives like Postman
        if title_match(title) or desc_match(desc):
            jobs.append({
                "company":  company,
                "title":    title,
                "link":     link,
                "location": location,
                "source":   "Greenhouse",
            })

    print(f"  [{company}] → {len(jobs)} matched")
    return jobs


def scrape_lever(company: str, board: str) -> list:
    jobs = []
    url  = f"https://api.lever.co/v0/postings/{board}?mode=json"
    res  = safe_get(url)
    if not res:
        return jobs

    try:
        data = res.json()
    except ValueError:
        return jobs

    for job in data:
        title    = job.get("text", "")
        link     = job.get("hostedUrl", "")
        location = job.get("categories", {}).get("location", "")
        desc     = " ".join(
            strip_html(i.get("content", "")) for i in job.get("lists", [])
        ) + " " + strip_html(job.get("additional", ""))

        if title_match(title) or desc_match(desc):
            jobs.append({
                "company":  company,
                "title":    title,
                "link":     link,
                "location": location,
                "source":   "Lever",
            })

    print(f"  [{company}] → {len(jobs)} matched")
    return jobs


def scrape_workday(company: str, tenant: str, board: str, version: str) -> list:
    jobs       = []
    search_url = (
        f"https://{tenant}.wd{version}.myworkdayjobs.com"
        f"/wday/cxs/{tenant}/{board}/jobs"
    )
    for keyword in [".net developer", "c# developer", "edi developer"]:
        try:
            res = requests.post(
                search_url,
                json={"appliedFacets": {}, "limit": 20, "offset": 0,
                      "searchText": keyword},
                headers={**HEADERS, "Content-Type": "application/json"},
                timeout=15,
            )
            data = res.json()
            for job in data.get("jobPostings", []):
                title    = job.get("title", "")
                path     = job.get("externalPath", "")
                link     = (
                    f"https://{tenant}.wd{version}.myworkdayjobs.com"
                    f"/en-US/{board}{path}"
                )
                location = job.get("locationsText", "")
                if title_match(title):
                    jobs.append({
                        "company":  company,
                        "title":    title,
                        "link":     link,
                        "location": location,
                        "source":   "Workday",
                    })
            time.sleep(0.5)
        except Exception as e:
            print(f"  ⚠️  {company} Workday error: {e}")

    print(f"  [{company}] → {len(jobs)} matched")
    return jobs


def scrape_amazon() -> list:
    jobs = []
    for query in [".net developer", "c# developer", "edi developer"]:
        res = safe_get(
            "https://www.amazon.jobs/en/search.json",
            headers=HEADERS,
            params={"base_query": query, "loc_query": "India",
                    "job_type": "Full-Time", "result_limit": 50},
        )
        if not res:
            continue
        try:
            data = res.json()
        except ValueError:
            continue

        for job in data.get("jobs", []):
            title    = job.get("title", "")
            job_id   = job.get("id_icims", "")
            link     = f"https://www.amazon.jobs/en/jobs/{job_id}"
            location = job.get("location", "")
            if title_match(title):
                jobs.append({
                    "company":  "Amazon",
                    "title":    title,
                    "link":     link,
                    "location": location,
                    "source":   "Amazon Jobs",
                })
        time.sleep(1)

    seen_links, unique = set(), []
    for j in jobs:
        if j["link"] not in seen_links:
            seen_links.add(j["link"])
            unique.append(j)

    print(f"  [Amazon] → {len(unique)} matched")
    return unique


def scrape_remotive() -> list:
    jobs = []
    res  = safe_get(
        "https://remotive.com/api/remote-jobs?category=software-dev&limit=100"
    )
    if not res:
        return jobs
    try:
        data = res.json()
    except ValueError:
        return jobs

    for job in data.get("jobs", []):
        title   = job.get("title", "")
        link    = job.get("url", "")
        company = job.get("company_name", "Remote")
        loc     = job.get("candidate_required_location", "Remote")
        desc    = strip_html(job.get("description", ""))

        if title_match(title) or desc_match(desc):
            jobs.append({
                "company":  company,
                "title":    title,
                "link":     link,
                "location": loc,
                "source":   "Remotive",
            })

    print(f"  [Remotive] → {len(jobs)} matched")
    return jobs


def scrape_arbeitnow() -> list:
    jobs = []
    for page in range(1, 4):
        res = safe_get(
            f"https://www.arbeitnow.com/api/job-board-api?page={page}"
        )
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
            title   = job.get("title", "")
            link    = job.get("url", "")
            company = job.get("company_name", "")
            loc     = job.get("location", "")
            desc    = strip_html(job.get("description", ""))

            if title_match(title) or desc_match(desc):
                jobs.append({
                    "company":  company,
                    "title":    title,
                    "link":     link,
                    "location": loc,
                    "source":   "Arbeitnow",
                })
        time.sleep(1)

    print(f"  [Arbeitnow] → {len(jobs)} matched")
    return jobs

# ================================================================ #
#   MAIN SCRAPER                                                   #
# ================================================================ #

def scrape_all() -> list:
    all_jobs = []

    print("\n🔍 Greenhouse boards...")
    for company, board in GREENHOUSE_COMPANIES:
        all_jobs += scrape_greenhouse(company, board)
        time.sleep(0.5)

    print("\n🔍 Lever boards...")
    for company, board in LEVER_COMPANIES:
        all_jobs += scrape_lever(company, board)
        time.sleep(0.5)

    print("\n🔍 Workday boards...")
    for company, tenant, board, version in WORKDAY_COMPANIES:
        all_jobs += scrape_workday(company, tenant, board, version)
        time.sleep(1)

    print("\n🔍 Amazon Jobs...")
    all_jobs += scrape_amazon()

    print("\n🔍 Remotive API...")
    all_jobs += scrape_remotive()

    print("\n🔍 Arbeitnow API...")
    all_jobs += scrape_arbeitnow()

    # Global dedup
    seen_links, unique = set(), []
    for job in all_jobs:
        if job["link"] and job["link"] not in seen_links:
            seen_links.add(job["link"])
            unique.append(job)

    print(f"\n📊 Total unique matched jobs: {len(unique)}")
    return unique

# ================================================================ #
#   MESSAGE & MAIN                                                 #
# ================================================================ #

def build_message(job: dict) -> str:
    return (
        f"🚀 New Job Alert!\n\n"
        f"🏢 Company  : {job['company']}\n"
        f"💼 Role     : {job['title']}\n"
        f"📍 Location : {job.get('location') or 'Not specified'}\n"
        f"🔗 Link     : {job['link']}\n"
        f"📡 Source   : {job['source']}"
    )


def main():
    print("=" * 55)
    print("  Job Scraper — Starting")
    print("=" * 55)

    print(f"\n🔑 EMAIL        : {'✅ set' if EMAIL else '❌ missing'}")
    print(f"🔑 APP_PASSWORD : {'✅ set' if APP_PASSWORD else '❌ missing'}")
    print(f"🔑 TELEGRAM     : {'✅ set' if TELEGRAM_TOKEN else '❌ missing'}")
    print(f"🔑 CHAT_ID      : {'✅ set' if CHAT_ID else '❌ missing'}\n")

    seen     = load_seen()
    jobs     = scrape_all()
    new_jobs = [j for j in jobs if j["link"] not in seen]

    print(f"\n🆕 New jobs not seen before: {len(new_jobs)}")

    if not new_jobs:
        print("✅ No new jobs this run — nothing to send.")
    else:
        for job in new_jobs:
            print(f"\n  → Alerting: {job['title']} @ {job['company']}")
            message = build_message(job)
            send_email(f"🚀 New Job: {job['title']} @ {job['company']}", message)
            send_telegram(message)
            seen.append(job["link"])
            time.sleep(1)

    save_seen(seen)
    print("\n✅ Done. seen_jobs.json saved.")


if __name__ == "__main__":
    main()
