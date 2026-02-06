"""
Lead Generation Modules
"""

from .utils import retry_with_backoff, ProgressTracker
from .company_discovery import discover_companies, DiscoveredCompany, CompanyDiscoveryService
from .contact_enrichment import enrich_companies, EnrichedCompany, Contact, ContactEnrichmentService
from .monday_crm import create_board, create_leads, MondayCRMService
from .email_outreach import send_outreach_emails, preview_email, EmailOutreachService, EmailResult

__all__ = [
    # Utilities
    "retry_with_backoff",
    "ProgressTracker",

    # Company Discovery
    "discover_companies",
    "DiscoveredCompany",
    "CompanyDiscoveryService",

    # Contact Enrichment
    "enrich_companies",
    "EnrichedCompany",
    "Contact",
    "ContactEnrichmentService",

    # Monday.com CRM
    "create_board",
    "create_leads",
    "MondayCRMService",

    # Email Outreach
    "send_outreach_emails",
    "preview_email",
    "EmailOutreachService",
    "EmailResult"
]
