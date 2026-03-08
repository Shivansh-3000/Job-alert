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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# ================================================================ #
#  MATCHING LOGIC                                                   #
# ================================================================ #

# These patterns use word boundaries (\b) so ".net" won't match
# inside words like "internet", "planet", "magnet" etc.
SKILL_PATTERNS = [
    r"\b\.net\b",
    r"\bc#\b",
    r"\basp\.net\b",
    r"\b\.net\s*core\b",
    r"\bdot\s*net\b",
    r"\bdotnet\b",
    r"\bcsharp\b",
    r"\bedi\b",
    r"\belectronic\s+data\s+interchange\b",
]

# Job must contain at least one of these role words in the TITLE
# This prevents "Credit Analyst" or "Social Media Manager" from passing
ROLE_KEYWORDS = [
    "developer", "engineer", "sde", "swe",
    "software", "backend", "fullstack", "full stack",
    "full-stack", "frontend", "architect", "programmer",
    "technical", "tech lead", "development",
]

# Experience patterns — matches 0-2.5 year range descriptions
EXPERIENCE_PATTERNS = [
    r"\b0\s*[-–to]+\s*[123]\s*years?\b",
    r"\b1\s*[-–to]+\s*[23]\s*years?\b",
    r"\b1\s*[-–to]+\s*2\.5\s*years?\b",
    r"\b0\s*[-–to]+\s*2\.5\s*years?\b",
    r"\bfresher\b",
    r"\bentry[\s-]level\b",
    r"\bjunior\b",
    r"\b0[\s-]+1\s*years?\b",
    r"\b1\s*year\b",
    r"\b2\s*years?\b",
]

# Seniority words that indicate too much experience — skip these
SENIOR_BLOCKLIST = [
    r"\bstaff\b", r"\bprincipal\b", r"\bdirector\b",
    r"\bvp\b", r"\bvice\s+president\b", r"\bhead\s+of\b",
    r"\blead\b", r"\bsenior\b", r"\bsr\.\b", r"\bsr\b",
    r"\b[5-9]\+?\s*years?\b", r"\b1[0-9]\+?\s*years?\b",
]


def skill_match(text: str) -> bool:
    """Returns True if any .NET/C#/EDI skill keyword is found."""
    t = text.lower()
    return any(re.search(p, t) for p in SKILL_PATTERNS)


def role_match(title: str) -> bool:
    """Returns True only if the job title is a developer/engineer role."""
    t = title.lower()
    return any(k in t for k in ROLE_KEYWORDS)


def experience_match(text: str) -> bool:
    """Returns True if the description mentions 0-2.5 years experience."""
    t = text.lower()
    return any(re.search(p, t) for p in EXPERIENCE_PATTERNS)


def not_too_senior(title: str) -> bool:
    """Returns True if the title does NOT contain senior/lead/staff etc."""
    t = title.lower()
    return not any(re.search(p, t) for p in SENIOR_BLOCKLIST)


def is_relevant(title: str, description: str = "") -> bool:
    """
    A job passes only if ALL of these are true:
    1. Title contains a developer/engineer role word
    2. Title or description contains a .NET/C#/EDI skill keyword
    3. Title does NOT indicate senior/lead/staff level
    4. Description mentions 0-2.5 years experience
       (if no description available, skip this check)
    """
    if not role_match(title):
        return False

    if not skill_match(title + " " + description):
        return False

    if not not_too_senior(title):
        return False

    # Only apply experience filter if we have a description to check
    if description.strip():
        if not experience_match(description):
            return False

    return True


# ================================================================ #
#  COMPANY LISTS                                                    #
# ================================================================ #

GREENHOUSE_COMPANIES = [
    # Indian product companies
    ("Freshworks",   "freshworks"),
    ("Postman",      "postman"),
    ("Sprinklr",     "sprinklr"),
    ("Innovaccer",   "innovaccer"),
    ("Druva",        "druva"),
    ("Icertis",      "icertis"),
    ("PhonePe",      "phonepe"),
    # Global product companies
    ("Atlassian",    "atlassian"),
    ("Stripe",       "stripe"),
    ("Figma",        "figma"),
    ("Notion",       "notion"),
    ("Coinbase",     "coinbase"),
    ("Discord",      "discord"),
    ("Dropbox",      "dropbox"),
    ("Zscaler",      "zscaler"),
    ("CrowdStrike",  "crowdstrike"),
    ("MongoDB",      "mongodb"),
    ("Twilio",       "twilio"),
    ("Datadog",      "datadoghq"),
    ("Grammarly",    "grammarly"),
    ("HashiCorp",    "hashicorp"),
    ("Robinhood",    "robinhood"),
    ("Canva",        "canva"),
    ("Snap",         "snap"),
    ("Lyft",         "lyft"),
]

LEVER_COMPANIES = [
    # Indian product companies
    ("Meesho",       "meesho"),
    ("Mindtickle",   "mindtickle"),
    ("CRED",         "cred"),
    ("BrowserStack", "browserstack"),
    ("Razorpay",     "razorpay"),
    ("Chargebee",    "chargebee"),
    ("CleverTap",    "clevertap"),
    ("MoEngage",     "moengage"),
    ("Whatfix",      "whatfix"),
    ("Groww",        "groww"),
    # Global product companies
    ("Netflix",      "netflix"),
    ("Reddit",       "reddit"),
    ("Scale AI",     "scaleai"),
    ("Airtable",     "airtable"),
    ("Anduril",      "anduril"),
]

WORKDAY_COMPANIES = [
    ("Visa",        "visa",        "Visa_Careers",            "1"),
    ("Mastercard",  "mastercard",  "MCW_Careers",             "1"),
    ("Walmart",     "walmart",     "WalmartExternalCareers",  "5"),
    ("SAP",         "sap",         "SAP",                     "1"),
    ("Adobe",       "adobe",       "ADBE_University_Hiring",  "1"),
    ("PayPal",      "paypal",      "jobs",                    "1"),
    ("Intuit",      "intuit",      "Intuit_Careers",          "1"),
    ("ServiceNow",  "servicenow",  "External",                "1"),
]

# ================================================================ #
#  UTILS                                                            #
# ================================================================ #

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
#  ALERTS                                                           #
# ================================================================ #

def send_email(subject: str, body: str):
    if not EMAIL or not APP_PASSWORD:
        print("  ⚠️  Email credentials missing.")
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
        print("  ⚠️  Telegram credentials missing.")
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
#  STORAGE                                                          #
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
        print(f"⚠️  Could not save: {e}")

# ================================================================ #
#  SCRAPERS                                                         #
# ================================================================ #

def scrape_greenhouse(company: str, board: str) -> list:
    jobs = []
    res  = safe_get(
        f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    )
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

        if is_relevant(title, desc):
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
    res  = safe_get(
        f"https://api.lever.co/v0/postings/{board}?mode=json"
    )
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

        if is_relevant(title, desc):
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
                # No description available from Workday search — title only
                if role_match(title) and skill_match(title) and not_too_senior(title):
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
            desc     = job.get("description", "")

            if is_relevant(title, desc):
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

        if is_relevant(title, desc):
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

            if is_relevant(title, desc):
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
#  MAIN SCRAPER                                                     #
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
#  MESSAGE & MAIN                                                   #
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
