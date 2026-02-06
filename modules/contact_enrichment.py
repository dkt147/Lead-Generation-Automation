"""
Contact Enrichment Module
Supports two modes:
  - "hunter": Uses Hunter.io API (costs credits per domain search)
  - "manual": Uses web scraping + Groq AI (free, no API credits needed)
"""

import logging
import time
import re
from dataclasses import dataclass, asdict
from typing import List, Optional
from urllib.parse import urlparse, urljoin
import requests

from config import get_config
from modules.utils import retry_with_backoff

logger = logging.getLogger(__name__)

# Decision-maker titles ranked by priority
DECISION_MAKER_TITLES = [
    "ceo", "chief executive", "founder", "co-founder", "owner",
    "president", "director", "vp", "vice president",
    "managing", "manager", "head", "lead", "partner"
]


@dataclass
class Contact:
    """Represents an enriched contact"""
    name: str
    email: str
    position: str
    confidence_score: float = 0.0
    linkedin_url: str = ""
    phone: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EnrichedCompany:
    """Company with enriched contact information"""
    company_name: str
    website: str
    description: str
    industry: str
    region: str
    contact: Optional[Contact] = None

    def to_dict(self) -> dict:
        result = {
            "company_name": self.company_name,
            "website": self.website,
            "description": self.description,
            "industry": self.industry,
            "region": self.region,
            "contact_name": "",
            "contact_email": "",
            "contact_position": "",
            "contact_linkedin": "",
            "contact_phone": ""
        }
        if self.contact:
            result["contact_name"] = self.contact.name
            result["contact_email"] = self.contact.email
            result["contact_position"] = self.contact.position
            result["contact_linkedin"] = self.contact.linkedin_url
            result["contact_phone"] = self.contact.phone
        return result


class ContactEnrichmentService:
    """Service for enriching company data with contact information.
    Supports 'hunter' mode (Hunter.io API) and 'manual' mode (web scraping + AI).
    """

    CONTACT_PATHS = [
        "/contact", "/contact-us", "/about", "/about-us",
        "/team", "/our-team", "/leadership", "/management"
    ]

    def __init__(self, mode: str = "hunter"):
        """
        Args:
            mode: 'hunter' for Hunter.io API, 'manual' for web scraping + Groq AI
        """
        self.config = get_config()
        self.mode = mode.lower()

        # Hunter.io config
        if self.mode == "hunter":
            self.api_key = self.config.hunter.api_key
            self.base_url = self.config.hunter.api_url

        # Manual mode config (Groq AI + scraping)
        if self.mode == "manual":
            self.groq_url = f"{self.config.groq.api_url}/chat/completions"
            self.groq_headers = {
                "Authorization": f"Bearer {self.config.groq.api_key}",
                "Content-Type": "application/json"
            }
            self.request_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }

        self.rate_limit_delay = 0.5

    # ──────────────────────────────────────────────
    # Shared helpers
    # ──────────────────────────────────────────────

    def _extract_domain(self, website: str) -> str:
        if not website:
            return ""
        try:
            if not website.startswith(("http://", "https://")):
                website = f"https://{website}"
            parsed = urlparse(website)
            domain = parsed.netloc or parsed.path
            if domain.startswith("www."):
                domain = domain[4:]
            return domain.lower().strip("/")
        except Exception:
            return website.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]

    # ──────────────────────────────────────────────
    # Hunter.io mode
    # ──────────────────────────────────────────────

    def check_account(self) -> dict:
        """Check Hunter.io account info and remaining credits (FREE)"""
        try:
            response = requests.get(
                f"{self.base_url}/account",
                params={"api_key": self.api_key},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json().get("data", {})
                searches = data.get("requests", {}).get("searches", {})
                logger.info(f"Hunter.io: {searches.get('used', '?')}/{searches.get('available', '?')} searches used")
                return data
            else:
                logger.error(f"Hunter.io account check failed: {response.status_code}")
                return {}
        except Exception as e:
            logger.error(f"Hunter.io account check error: {e}")
            return {}

    @retry_with_backoff(max_retries=2, base_delay=1.0, retryable_exceptions=(requests.ConnectionError, requests.Timeout))
    def _email_count(self, domain: str) -> int:
        """Check how many emails exist for a domain (FREE)"""
        try:
            response = requests.get(
                f"{self.base_url}/email-count",
                params={"domain": domain, "api_key": self.api_key},
                timeout=10
            )
            if response.status_code == 200:
                return response.json().get("data", {}).get("total", 0)
            return 0
        except (requests.ConnectionError, requests.Timeout):
            raise
        except Exception:
            return 0

    @retry_with_backoff(max_retries=2, base_delay=1.0, retryable_exceptions=(requests.ConnectionError, requests.Timeout))
    def _domain_search(self, domain: str) -> dict:
        """Search for emails at a domain (1 credit if results found)"""
        try:
            response = requests.get(
                f"{self.base_url}/domain-search",
                params={"domain": domain, "api_key": self.api_key, "limit": 10},
                timeout=15
            )
            if response.status_code == 200:
                return response.json().get("data", {})
            elif response.status_code == 429:
                logger.warning(f"Rate limit hit for {domain}, waiting...")
                time.sleep(5)
                return {}
            elif response.status_code == 401:
                logger.error("Hunter.io API key is invalid")
                return {}
            elif response.status_code == 403:
                logger.error("Hunter.io: no credits remaining")
                return {}
            else:
                logger.warning(f"Domain search failed for {domain}: {response.status_code}")
                return {}
        except (requests.ConnectionError, requests.Timeout):
            raise
        except Exception as e:
            logger.error(f"Domain search error for {domain}: {e}")
            return {}

    def _pick_best_contact(self, emails: list) -> Optional[Contact]:
        """Pick the best decision-maker from Hunter.io results"""
        if not emails:
            return None

        scored = []
        for email_data in emails:
            position = (email_data.get("position") or "").lower()
            confidence = email_data.get("confidence", 0)
            title_score = len(DECISION_MAKER_TITLES)
            for i, title in enumerate(DECISION_MAKER_TITLES):
                if title in position:
                    title_score = i
                    break
            scored.append((title_score, -confidence, email_data))

        scored.sort(key=lambda x: (x[0], x[1]))
        best = scored[0][2]

        first_name = best.get("first_name", "")
        last_name = best.get("last_name", "")
        name = f"{first_name} {last_name}".strip() or "Contact"

        return Contact(
            name=name,
            email=best.get("value", ""),
            position=best.get("position") or "Decision Maker",
            confidence_score=best.get("confidence", 0),
            linkedin_url=best.get("linkedin", "") or "",
            phone=best.get("phone_number") or ""
        )

    def _enrich_hunter(self, company) -> EnrichedCompany:
        """Enrich using Hunter.io API"""
        domain = self._extract_domain(company.website)
        logger.info(f"[Hunter] Enriching {company.name} (domain: {domain})")

        if not domain:
            logger.warning(f"No valid domain for {company.name}")
            return self._empty_enriched(company)

        try:
            email_count = self._email_count(domain)
            time.sleep(self.rate_limit_delay)

            contact = None
            if email_count > 0:
                logger.info(f"{domain}: {email_count} emails, running domain search...")
                search_data = self._domain_search(domain)
                emails = search_data.get("emails", [])
                if emails:
                    contact = self._pick_best_contact(emails)
                    if contact:
                        logger.info(f"Found: {contact.name} ({contact.position}) - {contact.email}")
                time.sleep(self.rate_limit_delay)
            else:
                logger.info(f"{domain}: no emails in Hunter.io, skipping (0 credits used)")

            return EnrichedCompany(
                company_name=company.name, website=company.website,
                description=company.description, industry=company.industry,
                region=company.region, contact=contact
            )
        except Exception as e:
            logger.error(f"Hunter enrichment error for {company.name}: {e}")
            return self._empty_enriched(company)

    # ──────────────────────────────────────────────
    # Manual mode (web scraping + Groq AI)
    # ──────────────────────────────────────────────

    @retry_with_backoff(max_retries=2, base_delay=1.0, retryable_exceptions=(requests.ConnectionError, requests.Timeout))
    def _fetch_page(self, url: str) -> Optional[str]:
        try:
            response = requests.get(url, headers=self.request_headers, timeout=10, allow_redirects=True)
            if response.status_code == 200:
                return response.text
            return None
        except (requests.ConnectionError, requests.Timeout):
            raise
        except Exception:
            return None

    def _extract_emails_from_text(self, text: str) -> List[str]:
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = re.findall(email_pattern, text)
        exclude = ['example.com', 'domain.com', 'email.com', 'test.com',
                    'noreply', 'no-reply', 'donotreply',
                    'careers@', 'jobs@', 'newsletter@', 'unsubscribe@',
                    '.png', '.jpg', '.gif', 'sentry.io', 'wixpress.com']
        filtered = [e for e in emails if not any(p in e.lower() for p in exclude)]
        return list(set(filtered))

    def _extract_phones_from_text(self, text: str) -> List[str]:
        patterns = [
            r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
            r'\+1[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
        ]
        phones = []
        for pattern in patterns:
            phones.extend(re.findall(pattern, text))
        return list(set(phones))[:3]

    def _scrape_website(self, base_url: str) -> dict:
        if not base_url.startswith(('http://', 'https://')):
            base_url = f"https://{base_url}"

        all_text = ""
        emails_found = []
        phones_found = []

        homepage_content = self._fetch_page(base_url)
        if homepage_content:
            all_text += homepage_content
            emails_found.extend(self._extract_emails_from_text(homepage_content))
            phones_found.extend(self._extract_phones_from_text(homepage_content))

        for path in self.CONTACT_PATHS:
            url = urljoin(base_url, path)
            content = self._fetch_page(url)
            if content:
                all_text += content
                emails_found.extend(self._extract_emails_from_text(content))
                phones_found.extend(self._extract_phones_from_text(content))

        return {
            "text": all_text[:15000],
            "emails": list(set(emails_found)),
            "phones": list(set(phones_found))
        }

    def _email_to_name(self, email_prefix: str) -> str:
        name = re.sub(r'\d+', '', email_prefix)
        parts = re.split(r'[._-]', name)
        name_parts = [p.capitalize() for p in parts if len(p) > 1]
        if len(name_parts) >= 2:
            return ' '.join(name_parts[:2])
        elif name_parts:
            return name_parts[0]
        return "Contact"

    def _use_ai_to_find_contact(self, company_name: str, scraped_data: dict) -> Optional[Contact]:
        emails = scraped_data.get("emails", [])
        phones = scraped_data.get("phones", [])

        if not emails:
            return None

        if len(emails) == 1:
            email = emails[0]
            name = self._email_to_name(email.split('@')[0])
            return Contact(name=name, email=email, position="Contact", phone=phones[0] if phones else "")

        prompt = f"""Analyze these emails found on {company_name}'s website and pick the best one for business inquiries.

Emails: {', '.join(emails[:10])}
Phones: {', '.join(phones[:5])}

Rules:
- Prefer personal emails over generic ones (info@, contact@)
- Look for decision-makers: CEO, founder, owner, director, manager

Respond in this exact format:
EMAIL: [best email]
NAME: [guessed name or "Contact"]
POSITION: [guessed position or "Decision Maker"]
PHONE: [best phone or "none"]"""

        try:
            payload = {
                "model": self.config.groq.model,
                "messages": [
                    {"role": "system", "content": "You extract contact information. Respond only in the exact format requested."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 200
            }
            response = requests.post(self.groq_url, headers=self.groq_headers, json=payload, timeout=30)

            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                email = name = ""
                position = "Decision Maker"
                phone = ""
                for line in content.split('\n'):
                    if line.startswith('EMAIL:'):
                        email = line.replace('EMAIL:', '').strip()
                    elif line.startswith('NAME:'):
                        name = line.replace('NAME:', '').strip()
                    elif line.startswith('POSITION:'):
                        position = line.replace('POSITION:', '').strip()
                    elif line.startswith('PHONE:'):
                        phone = line.replace('PHONE:', '').strip()
                        if phone.lower() == 'none':
                            phone = ""
                if email and '@' in email:
                    return Contact(
                        name=name if name != "Contact" else self._email_to_name(email.split('@')[0]),
                        email=email, position=position,
                        phone=phone or (phones[0] if phones else "")
                    )
        except Exception as e:
            logger.debug(f"AI contact extraction failed: {e}")

        # Fallback
        if emails:
            email = emails[0]
            return Contact(name=self._email_to_name(email.split('@')[0]), email=email,
                           position="Contact", phone=phones[0] if phones else "")
        return None

    def _enrich_manual(self, company) -> EnrichedCompany:
        """Enrich using web scraping + Groq AI"""
        logger.info(f"[Manual] Enriching {company.name} ({company.website})")
        try:
            scraped_data = self._scrape_website(company.website)
            contact = self._use_ai_to_find_contact(company.name, scraped_data)
            if contact:
                logger.info(f"Found: {contact.name} - {contact.email}")
            else:
                logger.info(f"No contacts found for {company.name}")
            time.sleep(self.rate_limit_delay)
            return EnrichedCompany(
                company_name=company.name, website=company.website,
                description=company.description, industry=company.industry,
                region=company.region, contact=contact
            )
        except Exception as e:
            logger.error(f"Manual enrichment error for {company.name}: {e}")
            return self._empty_enriched(company)

    # ──────────────────────────────────────────────
    # Main interface
    # ──────────────────────────────────────────────

    def _empty_enriched(self, company) -> EnrichedCompany:
        return EnrichedCompany(
            company_name=company.name, website=company.website,
            description=company.description, industry=company.industry,
            region=company.region
        )

    def enrich_company(self, company) -> EnrichedCompany:
        if self.mode == "hunter":
            return self._enrich_hunter(company)
        else:
            return self._enrich_manual(company)

    def enrich_companies(self, companies: List) -> List[EnrichedCompany]:
        # Check Hunter.io credits before starting
        if self.mode == "hunter":
            account = self.check_account()
            if account:
                searches = account.get("requests", {}).get("searches", {})
                available = searches.get("available", 0)
                used = searches.get("used", 0)
                remaining = available - used
                logger.info(f"Hunter.io credits remaining: {remaining}/{available}")
                if remaining <= 0:
                    logger.error("No Hunter.io credits remaining!")
                    return [self._empty_enriched(c) for c in companies]

        enriched = []
        total = len(companies)
        for i, company in enumerate(companies, 1):
            logger.info(f"Processing {i}/{total}: {company.name}")
            enriched.append(self.enrich_company(company))

        with_contacts = sum(1 for c in enriched if c.contact and c.contact.email)
        logger.info(f"Enrichment complete: {with_contacts}/{total} companies have contacts")
        return enriched


def enrich_companies(companies: List, mode: str = "hunter") -> List[EnrichedCompany]:
    """Convenience function to enrich companies with contact information.
    Args:
        companies: List of DiscoveredCompany objects
        mode: 'hunter' for Hunter.io API, 'manual' for web scraping + Groq AI
    """
    service = ContactEnrichmentService(mode=mode)
    return service.enrich_companies(companies)
