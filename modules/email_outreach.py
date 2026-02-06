"""
Email Outreach Module
Sends personalized introduction emails via Gmail SMTP.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict
from dataclasses import dataclass
import time
import requests

from config import get_config
from modules.utils import retry_with_backoff

logger = logging.getLogger(__name__)


# Default email template
DEFAULT_TEMPLATE = """Hi {{contact_name}},

I came across {{company_name}} while researching {{company_type}} companies in {{region}} and wanted to reach out.

I'd love to learn more about your work and explore if there might be any opportunities for collaboration.

Would you be open to a brief conversation?

Best regards,
{{sender_name}}
"""

DEFAULT_SUBJECT = "Quick Introduction - {{sender_name}} + {{company_name}}"


@dataclass
class EmailResult:
    """Result of an email send attempt"""
    success: bool
    recipient: str
    company_name: str
    error_message: str = ""


class EmailOutreachService:
    """Service for sending personalized outreach emails via Gmail SMTP"""

    def __init__(self, template: str = None, subject_template: str = None, use_ai: bool = False):
        self.config = get_config()
        self.template = template or DEFAULT_TEMPLATE
        self.subject_template = subject_template or DEFAULT_SUBJECT
        self.rate_limit_delay = 2.0  # Seconds between emails
        self.use_ai = use_ai

    @retry_with_backoff(max_retries=2, base_delay=2.0, retryable_exceptions=(requests.RequestException,))
    def generate_ai_email(self, enriched_company, company_type: str = "") -> Dict[str, str]:
        """
        Use Groq AI to generate a personalized email body for a specific lead.

        Returns:
            Dict with 'subject' and 'body' keys
        """
        contact = enriched_company.contact
        if not contact:
            return {}

        prompt = f"""Write a short, professional cold outreach email to {contact.name} ({contact.position}) at {enriched_company.company_name}.

Company info:
- Industry: {enriched_company.industry}
- Region: {enriched_company.region}
- Description: {enriched_company.description}
- Company type searched: {company_type}

Requirements:
- Address them by first name
- Reference something specific about their company or industry
- Keep it under 100 words (body only, exclude greeting and sign-off)
- Be professional but conversational
- End with a clear call to action (suggest a brief call)
- Do NOT include a subject line in the body

Respond in this exact format:
SUBJECT: <email subject line>
BODY: <full email body including greeting and sign-off from {self.config.email.sender_name}>"""

        groq_url = f"{self.config.groq.api_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.groq.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.config.groq.model,
            "messages": [
                {"role": "system", "content": "You write concise, personalized business outreach emails. No fluff."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 400
        }

        response = requests.post(groq_url, headers=headers, json=payload, timeout=30)

        if response.status_code != 200:
            logger.warning(f"AI email generation failed: {response.status_code}")
            return {}

        content = response.json()["choices"][0]["message"]["content"]

        subject = ""
        body = ""
        if "SUBJECT:" in content and "BODY:" in content:
            parts = content.split("BODY:", 1)
            subject = parts[0].replace("SUBJECT:", "").strip()
            body = parts[1].strip()
        else:
            body = content.strip()
            subject = f"Quick Introduction - {self.config.email.sender_name} + {enriched_company.company_name}"

        return {"subject": subject, "body": body}

    def _replace_placeholders(self, text: str, variables: Dict[str, str]) -> str:
        """Replace template placeholders with actual values"""
        result = text
        for key, value in variables.items():
            placeholder = "{{" + key + "}}"
            result = result.replace(placeholder, value or "")
        return result
    
    def _create_email(
        self,
        to_email: str,
        subject: str,
        body: str
    ) -> MIMEMultipart:
        """Create email message object"""
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{self.config.email.sender_name} <{self.config.email.address}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        
        # Plain text version
        part = MIMEText(body, "plain")
        msg.attach(part)
        
        return msg
    
    def send_email(
        self,
        enriched_company,
        company_type: str = "",
        custom_variables: Dict[str, str] = None
    ) -> EmailResult:
        """
        Send a personalized introduction email to a contact.
        
        Args:
            enriched_company: EnrichedCompany object
            company_type: Type of company (for template)
            custom_variables: Additional template variables
            
        Returns:
            EmailResult object
        """
        if not enriched_company.contact or not enriched_company.contact.email:
            return EmailResult(
                success=False,
                recipient="",
                company_name=enriched_company.company_name,
                error_message="No contact email available"
            )
        
        contact = enriched_company.contact
        recipient = contact.email
        
        # Build template variables
        variables = {
            "contact_name": contact.name.split()[0] if contact.name else "there",  # First name only
            "company_name": enriched_company.company_name,
            "company_type": company_type,
            "region": enriched_company.region,
            "sender_name": self.config.email.sender_name,
            "contact_position": contact.position,
            "company_description": enriched_company.description
        }
        
        # Add custom variables
        if custom_variables:
            variables.update(custom_variables)
        
        # Generate subject and body (AI-powered or template-based)
        if self.use_ai:
            ai_content = self.generate_ai_email(enriched_company, company_type)
            if ai_content:
                subject = ai_content.get("subject", "")
                body = ai_content.get("body", "")
                logger.info(f"Using AI-generated email for {enriched_company.company_name}")
            else:
                subject = self._replace_placeholders(self.subject_template, variables)
                body = self._replace_placeholders(self.template, variables)
                logger.info(f"AI generation failed, falling back to template for {enriched_company.company_name}")
        else:
            subject = self._replace_placeholders(self.subject_template, variables)
            body = self._replace_placeholders(self.template, variables)

        logger.info(f"Sending email to {recipient} ({enriched_company.company_name})")
        
        try:
            # Create message
            msg = self._create_email(recipient, subject, body)
            
            # Connect to Gmail SMTP
            with smtplib.SMTP(self.config.email.smtp_server, self.config.email.smtp_port) as server:
                server.starttls()
                server.login(self.config.email.address, self.config.email.app_password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {recipient}")
            
            return EmailResult(
                success=True,
                recipient=recipient,
                company_name=enriched_company.company_name
            )
            
        except smtplib.SMTPAuthenticationError as e:
            error_msg = "Gmail authentication failed. Check your app password."
            logger.error(f"{error_msg}: {e}")
            return EmailResult(
                success=False,
                recipient=recipient,
                company_name=enriched_company.company_name,
                error_message=error_msg
            )
            
        except smtplib.SMTPException as e:
            error_msg = f"SMTP error: {str(e)}"
            logger.error(error_msg)
            return EmailResult(
                success=False,
                recipient=recipient,
                company_name=enriched_company.company_name,
                error_message=error_msg
            )
            
        except Exception as e:
            error_msg = f"Error sending email: {str(e)}"
            logger.error(error_msg)
            return EmailResult(
                success=False,
                recipient=recipient,
                company_name=enriched_company.company_name,
                error_message=error_msg
            )
    
    def send_emails_batch(
        self,
        enriched_companies: list,
        company_type: str = "",
        custom_variables: Dict[str, str] = None
    ) -> list:
        """
        Send emails to multiple contacts.
        
        Args:
            enriched_companies: List of EnrichedCompany objects
            company_type: Type of company (for template)
            custom_variables: Additional template variables
            
        Returns:
            List of EmailResult objects
        """
        results = []
        total = len(enriched_companies)
        
        for i, company in enumerate(enriched_companies, 1):
            logger.info(f"Processing email {i}/{total}: {company.company_name}")
            
            result = self.send_email(company, company_type, custom_variables)
            results.append(result)
            
            # Rate limiting between emails
            if result.success and i < total:
                time.sleep(self.rate_limit_delay)
        
        # Summary
        successful = sum(1 for r in results if r.success)
        logger.info(f"Email campaign complete: {successful}/{total} emails sent successfully")
        
        return results


def send_outreach_emails(
    enriched_companies: list,
    company_type: str = "",
    template: str = None,
    subject_template: str = None,
    use_ai: bool = False
) -> list:
    """
    Convenience function to send outreach emails.

    Args:
        enriched_companies: List of EnrichedCompany objects
        company_type: Type of company (for template)
        template: Custom email body template
        subject_template: Custom subject template
        use_ai: Use AI to generate personalized email content per lead

    Returns:
        List of EmailResult objects
    """
    service = EmailOutreachService(template, subject_template, use_ai=use_ai)
    return service.send_emails_batch(enriched_companies, company_type)


def preview_email(
    enriched_company,
    company_type: str = "",
    template: str = None,
    subject_template: str = None
) -> Dict[str, str]:
    """
    Preview an email without sending it.
    
    Returns:
        Dict with 'subject' and 'body' keys
    """
    service = EmailOutreachService(template, subject_template)
    
    if not enriched_company.contact:
        return {"subject": "", "body": "", "error": "No contact available"}
    
    contact = enriched_company.contact
    variables = {
        "contact_name": contact.name.split()[0] if contact.name else "there",
        "company_name": enriched_company.company_name,
        "company_type": company_type,
        "region": enriched_company.region,
        "sender_name": service.config.email.sender_name,
        "contact_position": contact.position,
        "company_description": enriched_company.description
    }
    
    return {
        "subject": service._replace_placeholders(service.subject_template, variables),
        "body": service._replace_placeholders(service.template, variables),
        "to": contact.email
    }
