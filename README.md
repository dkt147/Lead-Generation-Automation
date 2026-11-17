# AI Lead Generation & Outreach Automation

Find companies with AI, enrich them with decision-maker contacts, drop them into Monday.com and send personalised intro emails — from a CLI or a Streamlit dashboard.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-Llama%203.3%2070B-F55036)
![Monday.com](https://img.shields.io/badge/Monday.com-GraphQL-FF3D57)

## How it works

```
company type + region
        │
        ▼
 1. Discover   ── Groq (Llama 3.3 70B) returns real companies as structured JSON
        │
        ▼
 2. Enrich     ── Hunter.io (CEO / Founder / Director first)  or  free scraping + AI mode
        │
        ▼
 3. CRM        ── creates Monday.com items, skips duplicates by company + email
        │
        ▼
 4. Outreach   ── template or AI-written email via Gmail SMTP, status logged back to Monday.com
```

## Features

- **AI company discovery** with JSON-repair and retry/backoff for flaky model output
- **Credit-saving enrichment** — checks Hunter's free Email Count endpoint before spending a Domain Search credit
- **Free enrichment mode** (`--enrichment-mode manual`) using web scraping + AI
- **Duplicate protection** in Monday.com
- **Preview mode** to see emails before anything is sent
- **Batch jobs** from a JSON file, CSV export
- **Password-protected Streamlit dashboard**

## Quick start

```bash
git clone https://github.com/dkt147/Lead-Generation-Automation.git
cd Lead-Generation-Automation
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your keys
```

### Run from the command line

```bash
# One-time: create a Monday.com board with the right columns
python main.py --setup-board --board-name "AI Lead Generation"

# Find 10 solar installers in Winnipeg, preview the emails
python main.py -t "solar energy installers" -r "Winnipeg, Manitoba" -c 10 --preview-emails

# Same, but send AI-personalised emails and export a CSV
python main.py -t "solar energy installers" -r "Winnipeg, Manitoba" --send-emails --ai-emails --export-csv

# Run several searches from a file
python main.py --batch-file batch_example.json
```

| Flag | What it does |
|---|---|
| `-t, --company-type` | Industry to search, e.g. `"SaaS startups"` |
| `-r, --region` | Area, e.g. `"Greater Toronto Area"` |
| `-c, --count` | Companies to find (default 10, max 50) |
| `--enrichment-mode` | `hunter` (default) or `manual` (free) |
| `--send-emails` / `--ai-emails` / `--preview-emails` | Outreach options |
| `--export-csv` | Save results to CSV |
| `--batch-file` | JSON file of multiple search jobs |
| `--setup-board`, `--board-name` | Create the Monday.com board |
| `-v, --verbose` | Detailed logs |

### Run the dashboard

```bash
streamlit run app.py
```

On Streamlit Cloud, put keys in `.streamlit/secrets.toml` (sections: `monday`, `groq`, `hunter`, `gmail`, `defaults`, `app`) instead of `.env`.

## Configuration

| Variable | Where to get it |
|---|---|
| `GROQ_API_KEY` | console.groq.com |
| `HUNTER_API_KEY` | hunter.io → API |
| `MONDAY_API_KEY`, `MONDAY_BOARD_ID` | Monday.com → Developers |
| `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` | Google account → App passwords (2FA required) |
| `SENDER_NAME` | Name shown on outgoing emails |
| `DEFAULT_COMPANY_COUNT`, `DEFAULT_REGION` | Optional defaults |

## Project structure

```
├── main.py              # CLI entry point
├── app.py               # Streamlit dashboard
├── config/settings.py   # env / Streamlit secrets loader
└── modules/
    ├── company_discovery.py   # Groq AI search
    ├── contact_enrichment.py  # Hunter.io + manual scraping
    ├── monday_crm.py          # Monday.com GraphQL
    ├── email_outreach.py      # Gmail SMTP + templates
    └── utils.py
```

## Roadmap

- PostgreSQL lead history
- Async enrichment for speed
- Scheduled weekly runs
- Open / click tracking

See [WRITEUP.md](WRITEUP.md) for design decisions and trade-offs.

## Need this for your business?

I build custom lead-gen and AI automation pipelines. **[Hire me on Upwork](https://www.upwork.com/freelancers/~01fc7f8e0654357bd1)**.
