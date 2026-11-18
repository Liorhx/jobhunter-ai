import csv
import json
import os
import re
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from html import unescape

import requests

BASE = Path(__file__).resolve().parent
PROFILE = json.loads((BASE / "profile.json").read_text(encoding="utf-8"))
OUT = BASE / "data"
OUT.mkdir(exist_ok=True)
CSV_PATH = OUT / "jobs.csv"
TIMEOUT = 25
HEADERS = {"User-Agent": "JobHunterAI-PersonalJobSearch/1.0 (personal use)"}

def clean_html(value):
    value = re.sub(r"<script.*?</script>|<style.*?</style>", " ", str(value or ""), flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(value)).strip()

def get_json(url, params=None):
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        print(f"[WARN] Could not fetch {url}: {exc}")
        return {}

def normalize_job(source, raw):
    if source == "jobicy":
        return {
            "source": "Jobicy", "id": raw.get("id"),
            "title": raw.get("职位") or raw.get("jobTitle") or raw.get("title"),
            "company": raw.get("companyName") or raw.get("company"),
            "location": raw.get("jobGeo") or raw.get("location"),
            "type": raw.get("jobType"),
            "description": clean_html(raw.get("jobDescription")),
            "url": raw.get("url"),
            "published": raw.get("pubDate") or raw.get("date"),
            "salary": raw.get("annual薪") or raw.get("salary")
        }
    if source == "arbeitnow":
        return {
            "source": "Arbeitnow", "id": raw.get("slug"),
            "title": raw.get("title"), "company": raw.get("company_name"),
            "location": raw.get("location"),
            "type": ", ".join(raw.get("job_types") or []),
            "description": clean_html(raw.get("description")),
            "url": raw.get("url"),
            "published": raw.get("created_at"),
            "salary": ""
        }
    return {
        "source": "Remotive", "id": raw.get("id"),
        "title": raw.get("title"), "company": raw.get("company_name"),
        "location": raw.get("candidate_required_location") or "Remote (check eligibility)",
        "type": raw.get("job_type"),
        "description": clean_html(raw.get("description")),
        "url": raw.get("url"),
        "published": raw.get("publication_date"),
        "salary": raw.get("salary")
    }

def fetch_all():
    jobs = []
    # Jobicy public API: latest remote listings.
    data = get_json("https://jobicy.com/api/jobs", {"count": 50})
    for item in data.get("jobs", []) if isinstance(data, dict) else []:
        jobs.append(normalize_job("jobicy", item))

    # Arbeitnow public job board API.
    data = get_json("https://www.arbeitnow.com/api/job-board-api")
    for item in data.get("data", []) if isinstance(data, dict) else []:
        jobs.append(normalize_job("arbeitnow", item))

    # Remotive public API: observe attribution and redistribution terms.
    data = get_json("https://remotive.com/api/remote-jobs", {"limit": 50})
    for item in data.get("jobs", []) if isinstance(data, dict) else []:
        jobs.append(normalize_job("remotive", item))

    return [j for j in jobs if j.get("title") and j.get("url")]

def location_check(location):
    loc = (location or "").lower()
    positive = ["india", "worldwide", "anywhere", "global", "asia", "asia-pacific", "apac"]
    negative = ["united states only", "us only", "usa only", "canada only", "uk only",
                "europe only", "germany only", "australia only"]
    if any(x in loc for x in negative):
        return "Not India eligible"
    if any(x in loc for x in positive):
        return "Likely India eligible"
    if "remote" in loc or "any location" in loc:
        return "Check country eligibility"
    if not loc or loc.lower() in ["remote", "not specified"]:
        return "Check country eligibility"
    if any(x in loc for x in ["lucknow", "india", "bengaluru", "bangalore", "delhi",
                              "noida", "gurugram", "gurgaon", "mumbai", "hyderabad",
                              "pune", "chennai"]):
        return "India location"
    return "Location mismatch / verify"

def score_job(job):
    p = PROFILE["candidate"]
    title = (job.get("title") or "").lower()
    desc = (job.get("description") or "").lower()
    company = (job.get("company") or "").lower()
    location = job.get("location") or ""
    total = 0
    reasons = []

    role_hits = [r for r in p["target_roles"] if r.lower() in title]
    if role_hits:
        total += 30
        reasons.append("Target role match")
    elif any(x in title for x in ["developer", "engineer", "software", "frontend", "backend"]):
        total += 16
        reasons.append("Adjacent software role")
    else:
        reasons.append("Title not closely matched")

    skill_hits = [s for s in p["skills"] if s.lower() in desc or s.lower() in title]
    skill_points = min(35, len(skill_hits) * 5)
    total += skill_points
    if skill_hits:
        reasons.append("Skills: " + ", ".join(skill_hits[:7]))

    if any(x in title + " " + desc[:2500] for x in ["junior", "entry level", "entry-level", "0-2 years", "1-2 years", "0-3 years", "associate"]):
        total += 12
        reasons.append("Junior/entry-level signal")
    elif any(x in title + " " + desc[:2500] for x in ["senior", "staff engineer", "lead engineer", "principal"]):
        total -= 25
        reasons.append("Likely senior role")

    loc_status = location_check(location)
    if loc_status == "India location":
        total += 15
        reasons.append("India-based role")
    elif loc_status == "Likely India eligible":
        total += 15
        reasons.append("Worldwide/India eligibility indicated")
    elif loc_status == "Check country eligibility":
        total += 5
        reasons.append("Remote; country eligibility needs checking")
    else:
        total -= 30
        reasons.append(loc_status)

    if any(x in company for x in ["stealth", "labs", "technologies", "tech", "ai", "software"]):
        total += 2

    total = max(0, min(100, total))
    return total, loc_status, "; ".join(reasons), skill_hits

def ai_enrich(job, score, skill_hits):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "", ""
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    prompt = f"""You are evaluating a job for a real candidate. Do not invent qualifications.
Candidate: Full-stack developer in India. Skills: {', '.join(PROFILE['candidate']['skills'])}.
Experience should be treated as early-career / 0-3 years; do not claim a specific number of years.
Job title: {job.get('title')}
Company: {job.get('company')}
Location eligibility: {job.get('location')}
Description (truncated): {(job.get('description') or '')[:7000]}
Rule-based score: {score}/100. Matching skills: {', '.join(skill_hits)}
Return ONLY JSON: {{"fit_summary":"max 35 words","concerns":"max 25 words","suggested_action":"APPLY or REVIEW or SKIP"}}
"""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        response = requests.post(url, params={"key": api_key},
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0.2, "maxOutputTokens": 180}},
            timeout=40)
        response.raise_for_status()
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.I).strip()
        result = json.loads(text)
        return result.get("fit_summary", ""), result.get("concerns", "")
    except Exception as exc:
        print(f"[WARN] Gemini skipped for this job: {exc}")
        return "", ""

def read_existing():
    if not CSV_PATH.exists():
        return {}
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        return {row["url"]: row for row in csv.DictReader(f) if row.get("url")}

FIELDS = ["first_seen_utc", "source", "company", "title", "location", "location_check",
          "salary", "match_score", "matching_skills", "match_reasons", "ai_fit_summary",
          "ai_concerns", "url", "application_status", "notes"]

def main():
    existing = read_existing()
    jobs = fetch_all()
    print(f"Fetched {len(jobs)} raw listings.")
    new_count = 0
    ai_count = 0
    for job in jobs:
        url = job["url"]
        if url in existing:
            continue
        score, loc_status, reasons, skills = score_job(job)
        filters = PROFILE["filters"]
        if score < filters["minimum_score"]:
            continue
        if filters["only_india_eligible_or_location_unclear"] and loc_status in ["Not India eligible", "Location mismatch / verify"]:
            continue

        fit, concerns = "", ""
        max_ai = int(filters.get("max_ai_jobs_per_run", 0))
        if os.getenv("GEMINI_API_KEY") and ai_count < max_ai:
            fit, concerns = ai_enrich(job, score, skills)
            ai_count += 1
            time.sleep(1.5)

        existing[url] = {
            "first_seen_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": job.get("source", ""),
            "company": job.get("company", ""),
            "title": job.get("title", ""),
            "location": job.get("location", ""),
            "location_check": loc_status,
            "salary": job.get("salary", ""),
            "match_score": score,
            "matching_skills": ", ".join(skills),
            "match_reasons": reasons,
            "ai_fit_summary": fit,
            "ai_concerns": concerns,
            "url": url,
            "application_status": "Review",
            "notes": ""
        }
        new_count += 1

    rows = sorted(existing.values(), key=lambda r: int(r.get("match_score") or 0), reverse=True)
    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Added {new_count} new relevant jobs. Total tracked: {len(rows)}")
    print(f"Saved: {CSV_PATH}")
    for row in rows[:15]:
        print(f"{row['match_score']:>3} | {row['company'][:24]:24} | {row['title'][:48]} | {row['url']}")

    # Optional Telegram notification: only sends a compact summary, never personal data.
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id and new_count:
        top = [r for r in rows if r.get("first_seen_utc", "").startswith(datetime.now(timezone.utc).date().isoformat())][:8]
        msg = f"JobHunter AI: {new_count} new matches found.\n"
        msg += "\n".join(f"{r['match_score']}/100 · {r['title']} — {r['company']}\n{r['url']}" for r in top)
        try:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat_id, "text": msg[:3900], "disable_web_page_preview": True},
                          timeout=20).raise_for_status()
        except Exception as exc:
            print(f"[WARN] Telegram notification failed: {exc}")

if __name__ == "__main__":
    main()
