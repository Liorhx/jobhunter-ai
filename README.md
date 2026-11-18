# JobHunter AI — ₹0 personal job search automation

A private, scheduled job-discovery and matching assistant. It fetches public job listings, scores them against `profile.json`, saves new matches in `data/jobs.csv`, and optionally uses Gemini and Telegram.

## What it does
- Runs in GitHub Actions at 08:30 and 17:30 India time (schedule may be delayed by GitHub).
- Fetches Jobicy, Arbeitnow and Remotive public listings.
- Scores role, skills, early-career signals and location eligibility.
- Deduplicates by application URL.
- Stores a persistent CSV tracker in this repository.
- Optional Gemini fit summary and Telegram notification.
- Does **not** auto-submit job applications.

## Setup

1. Create a **private** GitHub repository named `jobhunter-ai`.
2. Upload all files from this folder, preserving `.github/workflows/job-search.yml`.
3. Open the repository's **Settings → Actions → General** and allow workflows to run.
4. Open **Actions → JobHunter AI Search → Run workflow** for the first manual run.
5. After it completes, open `data/jobs.csv` to review matches.

## Optional Gemini (keep it ₹0)

1. Create an API key in Google AI Studio: https://aistudio.google.com/app/apikey
2. In GitHub: **Settings → Secrets and variables → Actions → New repository secret**.
3. Name it `GEMINI_API_KEY`; paste the key as the value.
4. Do not attach a billing account or enable paid billing if your budget must remain zero. Free-tier availability and quotas vary by model, region and account. If the free quota is unavailable, leave the secret unset; rule-based scoring still works.

Gemini requests are capped at 15 new matches per run. You can reduce `max_ai_jobs_per_run` in `profile.json`.

## Optional Telegram alerts

1. Create a bot using Telegram's `@BotFather` and copy its token.
2. Send a message to your bot, then obtain your chat ID using Telegram's bot API `getUpdates` method.
3. Add repository Actions secrets named `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
4. If you do not configure these, the tracker still works.

## Customize your profile

Edit `profile.json`:
- `target_roles`: roles you want
- `skills`: skills you can genuinely discuss in an interview
- `minimum_score`: lower to discover more jobs, raise to be stricter
- `minimum_salary_lpa`: informational starting preference; salary is often absent from public feeds, so the first version does not reject listings solely because salary is missing.

Do not add skills or experience you cannot substantiate.

## Important source limitations

- Job feeds have different geographic coverage and may not include all Indian startups.
- Remote does not automatically mean work-from-India is permitted. Check each employer's country eligibility.
- Remotive requires source attribution/linking and restricts redistribution to certain third-party job sites. This tool is a personal tracker; preserve the source and original job link.
- Public APIs can change, rate-limit, or return stale/duplicate listings.
- Jobicy and Arbeitnow coverage is not exhaustive.

## Application workflow

For every promising row:
1. Open the original job link.
2. Confirm the listing is still active and accepts applicants in India.
3. Confirm salary, experience, employment type and work authorization.
4. Tailor your resume honestly.
5. Submit through the employer's official application page.
6. Change `application_status` in the CSV to `Applied`, `Interview`, `Rejected`, `Offer`, or `Follow-up`.

## Troubleshooting

- No jobs: lower `minimum_score` to 25, then run manually.
- Workflow not running: check Actions permissions and workflow file path.
- API error: open the Actions run log; one unavailable source does not stop the other sources.
- No Gemini summaries: remove the Gemini secret and continue with rule-based scoring, or check your AI Studio quota.
- CSV not updating: check the workflow's final commit step and repository write permissions.

## Cost controls
- Use a private repository.
- Do not add a billing account to Gemini or other cloud services.
- GitHub Free private repositories have included Actions minutes; check current usage in GitHub Settings → Billing.
- No paid hosting, database or third-party automation is required.
