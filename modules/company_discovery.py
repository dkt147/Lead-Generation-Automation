"""
AI-Powered Company Discovery Module
Uses Groq (Llama 3.3) to discover companies matching specified criteria.
"""

import json
import logging
import re
from dataclasses import dataclass, asdict
from typing import List, Optional
import requests

from config import get_config
from modules.utils import retry_with_backoff

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredCompany:
    """Represents a discovered company"""
    name: str
    website: str
    description: str
    industry: str
    region: str
    estimated_size: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)


class CompanyDiscoveryService:
    """Service for AI-powered company discovery using Groq"""
    
    def __init__(self):
        self.config = get_config()
        self.api_url = f"{self.config.groq.api_url}/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.config.groq.api_key}",
            "Content-Type": "application/json"
        }
    
    def discover_companies(
        self,
        company_type: str,
        region: str,
        count: int = 10
    ) -> List[DiscoveredCompany]:
        """
        Discover companies matching the specified criteria using AI.
        
        Args:
            company_type: Industry or business type (e.g., "solar energy installers")
            region: Geographic area (e.g., "Winnipeg, Manitoba")
            count: Number of companies to find (default: 10, max: 50)
            
        Returns:
            List of DiscoveredCompany objects
        """
        count = min(count, 50)  # Cap at 50
        
        logger.info(f"Discovering {count} {company_type} companies in {region}")
        
        prompt = self._build_discovery_prompt(company_type, region, count)
        
        try:
            response = self._call_groq_api(prompt)
            companies = self._parse_response(response, company_type, region)
            
            logger.info(f"Successfully discovered {len(companies)} companies")
            return companies
            
        except Exception as e:
            logger.error(f"Error discovering companies: {str(e)}")
            raise
    
    def _build_discovery_prompt(self, company_type: str, region: str, count: int) -> str:
        """Build the prompt for company discovery"""
        return f"""You are a business research assistant. Find {count} REAL companies that are {company_type} located in or serving {region}.

IMPORTANT: Only provide REAL companies that actually exist. Do not make up fictional companies.

For each company, provide:
1. Company name (official registered name)
2. Website URL (must be real and accessible)
3. Brief description (1-2 sentences about what they do)
4. Specific industry/niche
5. Estimated company size (small/medium/large or employee count if known)

Return your response as a JSON array with this exact structure:
```json
[
    {{
        "name": "Company Name",
        "website": "https://www.example.com",
        "description": "Brief description of the company",
        "industry": "Specific industry",
        "estimated_size": "small/medium/large"
    }}
]
```

Focus on finding companies that:
- Are currently active and operating
- Have a web presence
- Are relevant to the {company_type} industry
- Operate in or serve {region}

If you cannot find {count} real companies, return as many as you can find with accurate information.

Return ONLY the JSON array, no additional text or explanation."""

    @retry_with_backoff(max_retries=3, base_delay=2.0, retryable_exceptions=(requests.RequestException, Exception))
    def _call_groq_api(self, prompt: str) -> str:
        """Make API call to Groq with automatic retry on failure"""
        payload = {
            "model": self.config.groq.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a business research assistant that finds real companies. Always respond with valid JSON only."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.3,
            "max_tokens": 4000
        }

        response = requests.post(
            self.api_url,
            headers=self.headers,
            json=payload,
            timeout=60
        )

        if response.status_code != 200:
            logger.error(f"Groq API error: {response.status_code} - {response.text}")
            raise Exception(f"Groq API error: {response.status_code}")

        result = response.json()
        return result["choices"][0]["message"]["content"]
    
    def _parse_response(
        self,
        response: str,
        company_type: str,
        region: str
    ) -> List[DiscoveredCompany]:
        """Parse the AI response into DiscoveredCompany objects"""
        
        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find JSON array directly
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                json_str = json_match.group(0)
            else:
                logger.error(f"Could not extract JSON from response: {response[:500]}")
                raise ValueError("Could not parse AI response as JSON")
        
        try:
            companies_data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            raise ValueError(f"Invalid JSON in AI response: {e}")
        
        companies = []
        for company in companies_data:
            try:
                # Clean and validate website URL
                website = company.get("website", "")
                if website and not website.startswith(("http://", "https://")):
                    website = f"https://{website}"
                
                discovered = DiscoveredCompany(
                    name=company.get("name", "Unknown"),
                    website=website,
                    description=company.get("description", ""),
                    industry=company.get("industry", company_type),
                    region=region,
                    estimated_size=company.get("estimated_size", "")
                )
                companies.append(discovered)
            except Exception as e:
                logger.warning(f"Error parsing company data: {e}")
                continue
        
        return companies


def discover_companies(
    company_type: str,
    region: str,
    count: int = 10
) -> List[DiscoveredCompany]:
    """
    Convenience function to discover companies.
    
    Args:
        company_type: Industry or business type
        region: Geographic area
        count: Number of companies to find
        
    Returns:
        List of DiscoveredCompany objects
    """
    service = CompanyDiscoveryService()
    return service.discover_companies(company_type, region, count)
