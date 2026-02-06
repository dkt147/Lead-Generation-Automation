# Project Write-Up

## Technical Decisions

I chose **Groq (Llama 3.3 70B)** for company discovery because it's fast, free, and returns solid results for business research tasks. For contact enrichment, the app supports two modes: **Hunter.io** for accurate professional contacts, and a **manual scraping mode** that uses web scraping + AI as a free fallback when you want to save API credits.

For email, I went with **Gmail SMTP** since it's the simplest to set up and doesn't need another paid service. Monday.com integration uses their GraphQL API to create leads with all the required fields.

The dashboard is built with **Streamlit** because it lets you build a clean web UI in pure Python without needing frontend code. It's password-protected since we're using paid API services.

## Challenges and Solutions

The biggest challenge was working within Hunter.io's free tier limits. I solved this by adding a credit-saving strategy: the app first checks if a domain has any emails using Hunter's free Email Count endpoint, and only spends a credit on Domain Search if there's data to find. This avoids wasting credits on domains with no results.

Another challenge was getting reliable company data from AI. Sometimes the model returns incomplete or badly formatted JSON. I added JSON extraction with regex fallback and retry logic with exponential backoff to handle flaky API responses.

Duplicate detection in Monday.com was tricky since their API doesn't have a built-in unique check. The app fetches existing board items and compares company names and emails before creating new ones.

## How I Would Improve This

With more time and a production budget, I would:

- Add a database (PostgreSQL) to store leads locally and track history
- Use async requests to speed up enrichment (process multiple companies at once)
- Add a scheduler so searches can run automatically on a weekly basis
- Build a proper authentication system instead of a static password
- Add email open/click tracking to measure outreach effectiveness
- Use Hunter.io's paid plan for higher volume and add bulk verification

## Time Breakdown

| Task | Hours |
|------|-------|
| Project setup, config, architecture | 2 |
| Company discovery module (Groq AI) | 2 |
| Hunter.io contact enrichment | 2.5 |
| Manual enrichment mode (scraping + AI) | 1.5 |
| Monday.com CRM integration | 2.5 |
| Email outreach module | 2 |
| Streamlit dashboard | 2 |
| Testing and bug fixes | 1.5 |
| **Total** | **16** |
