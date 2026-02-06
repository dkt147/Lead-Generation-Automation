"""
Monday.com CRM Integration Module
Creates boards, columns, and lead items in Monday.com.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import requests
import json

from config import get_config
from modules.utils import retry_with_backoff

logger = logging.getLogger(__name__)


class MondayCRMService:
    """Service for Monday.com CRM operations"""

    # Column definitions for the lead board
    LEAD_COLUMNS = [
        {"id": "website", "title": "Website", "type": "link"},
        {"id": "contact_name", "title": "Contact Name", "type": "text"},
        {"id": "contact_email", "title": "Contact Email", "type": "email"},
        {"id": "contact_position", "title": "Contact Position", "type": "text"},
        {"id": "company_description", "title": "Company Description", "type": "long_text"},
        {"id": "region", "title": "Region", "type": "text"},
        {"id": "lead_source", "title": "Lead Source", "type": "text"},
        {"id": "status", "title": "Status", "type": "status"},
        {"id": "date_added", "title": "Date Added", "type": "date"},
        {"id": "email_sent", "title": "Email Sent", "type": "checkbox"}
    ]

    def __init__(self):
        self.config = get_config()
        self.api_url = self.config.monday.api_url
        self.headers = {
            "Authorization": self.config.monday.api_key,
            "Content-Type": "application/json",
            "API-Version": "2024-01"
        }
        self.board_id = self.config.monday.board_id

    @retry_with_backoff(max_retries=3, base_delay=2.0, retryable_exceptions=(requests.RequestException, ConnectionError))
    def _execute_query(self, query: str, variables: dict = None) -> dict:
        """Execute a GraphQL query against Monday.com API with automatic retry"""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        response = requests.post(
            self.api_url,
            json=payload,
            headers=self.headers,
            timeout=30
        )

        if response.status_code != 200:
            logger.error(f"Monday.com API error: {response.status_code} - {response.text}")
            raise Exception(f"Monday.com API error: {response.status_code}")

        result = response.json()

        if "errors" in result:
            error_msg = result["errors"][0].get("message", "Unknown error")
            logger.error(f"Monday.com GraphQL error: {error_msg}")
            raise Exception(f"Monday.com error: {error_msg}")

        return result.get("data", {})

    def get_workspaces(self) -> List[dict]:
        """Get all available workspaces"""
        query = """
        query {
            workspaces {
                id
                name
            }
        }
        """
        result = self._execute_query(query)
        return result.get("workspaces", [])

    def create_board(self, name: str = "AI Lead Generation", workspace_id: str = None) -> str:
        """
        Create a new board for lead management.

        Args:
            name: Board name
            workspace_id: Optional workspace ID (uses main workspace if not provided)

        Returns:
            Board ID
        """
        logger.info(f"Creating board: {name}")

        # Create board
        if workspace_id:
            query = """
            mutation ($name: String!, $workspace_id: ID!) {
                create_board(board_name: $name, board_kind: public, workspace_id: $workspace_id) {
                    id
                }
            }
            """
            variables = {"name": name, "workspace_id": workspace_id}
        else:
            query = """
            mutation ($name: String!) {
                create_board(board_name: $name, board_kind: public) {
                    id
                }
            }
            """
            variables = {"name": name}

        result = self._execute_query(query, variables)
        board_id = result["create_board"]["id"]

        logger.info(f"Board created with ID: {board_id}")

        # Create columns
        self._create_columns(board_id)

        self.board_id = board_id
        return board_id

    def _create_columns(self, board_id: str):
        """Create all required columns on the board"""
        logger.info("Creating board columns...")

        for column in self.LEAD_COLUMNS:
            try:
                query = """
                mutation ($board_id: ID!, $title: String!, $column_type: ColumnType!) {
                    create_column(board_id: $board_id, title: $title, column_type: $column_type) {
                        id
                    }
                }
                """
                variables = {
                    "board_id": board_id,
                    "title": column["title"],
                    "column_type": column["type"]
                }

                self._execute_query(query, variables)
                logger.debug(f"Created column: {column['title']}")

            except Exception as e:
                # Column might already exist
                logger.warning(f"Could not create column {column['title']}: {e}")

    def get_board_columns(self, board_id: str = None) -> Dict[str, str]:
        """Get column mappings for a board (title -> id)"""
        board_id = board_id or self.board_id

        query = """
        query ($board_id: ID!) {
            boards(ids: [$board_id]) {
                columns {
                    id
                    title
                    type
                }
            }
        }
        """

        result = self._execute_query(query, {"board_id": board_id})

        columns = {}
        if result.get("boards"):
            for col in result["boards"][0].get("columns", []):
                columns[col["title"].lower()] = col["id"]

        return columns

    def check_duplicate(self, board_id: str, company_name: str, email: str = None) -> bool:
        """Check if a lead already exists on the board"""
        board_id = board_id or self.board_id

        if not company_name:
            return False

        query = """
        query ($board_id: ID!) {
            boards(ids: [$board_id]) {
                items_page(limit: 500) {
                    items {
                        name
                        column_values {
                            id
                            text
                        }
                    }
                }
            }
        }
        """

        result = self._execute_query(query, {"board_id": board_id})

        if not result.get("boards"):
            return False

        items = result["boards"][0].get("items_page", {}).get("items", [])

        for item in items:
            # Check company name (with null safety)
            item_name = item.get("name") or ""
            if item_name.lower() == company_name.lower():
                return True

            # Check email if provided
            if email:
                for col_val in item.get("column_values", []):
                    col_text = col_val.get("text") or ""
                    if col_text.lower() == email.lower():
                        return True

        return False

    def create_lead(self, enriched_company, board_id: str = None) -> Optional[str]:
        """
        Create a lead item in Monday.com.

        Args:
            enriched_company: EnrichedCompany object
            board_id: Board ID (uses configured board if not provided)

        Returns:
            Item ID if created, None if duplicate or error
        """
        board_id = board_id or self.board_id

        if not board_id:
            raise ValueError("No board ID configured. Create a board first.")

        company_name = enriched_company.company_name or "Unknown Company"
        contact_email = ""
        if enriched_company.contact and enriched_company.contact.email:
            contact_email = enriched_company.contact.email

        # Check for duplicates
        if self.check_duplicate(board_id, company_name, contact_email):
            logger.info(f"Skipping duplicate: {company_name}")
            return None

        logger.info(f"Creating lead: {company_name}")

        # Get column mappings
        columns = self.get_board_columns(board_id)

        # Build column values
        column_values = {}

        # Website (link type)
        if "website" in columns and enriched_company.website:
            column_values[columns["website"]] = {
                "url": enriched_company.website,
                "text": enriched_company.website
            }

        # Contact Name
        if "contact name" in columns and enriched_company.contact and enriched_company.contact.name:
            column_values[columns["contact name"]] = enriched_company.contact.name

        # Contact Email
        if "contact email" in columns and enriched_company.contact and enriched_company.contact.email:
            column_values[columns["contact email"]] = {
                "email": enriched_company.contact.email,
                "text": enriched_company.contact.email
            }

        # Contact Position
        if "contact position" in columns and enriched_company.contact and enriched_company.contact.position:
            column_values[columns["contact position"]] = enriched_company.contact.position

        # Company Description
        if "company description" in columns and enriched_company.description:
            column_values[columns["company description"]] = {
                "text": enriched_company.description
            }

        # Region
        if "region" in columns and enriched_company.region:
            column_values[columns["region"]] = enriched_company.region

        # Lead Source
        if "lead source" in columns:
            column_values[columns["lead source"]] = "AI Discovery"

        # Status - Use Monday.com's default status labels
        # Available: "Working on it", "Done", "Stuck"
        if "status" in columns:
            column_values[columns["status"]] = {"label": "Working on it"}

        # Date Added
        if "date added" in columns:
            column_values[columns["date added"]] = {"date": datetime.now().strftime("%Y-%m-%d")}

        # Email Sent
        if "email sent" in columns:
            column_values[columns["email sent"]] = {"checked": "false"}

        # Create item
        query = """
        mutation ($board_id: ID!, $item_name: String!, $column_values: JSON!) {
            create_item(board_id: $board_id, item_name: $item_name, column_values: $column_values) {
                id
            }
        }
        """

        variables = {
            "board_id": board_id,
            "item_name": company_name,
            "column_values": json.dumps(column_values)
        }

        result = self._execute_query(query, variables)
        item_id = result["create_item"]["id"]

        logger.info(f"Lead created with ID: {item_id}")
        return item_id

    def update_email_sent(self, item_id: str, board_id: str = None):
        """Mark an item as having email sent"""
        board_id = board_id or self.board_id
        columns = self.get_board_columns(board_id)

        if "email sent" not in columns:
            return

        query = """
        mutation ($board_id: ID!, $item_id: ID!, $column_values: JSON!) {
            change_multiple_column_values(board_id: $board_id, item_id: $item_id, column_values: $column_values) {
                id
            }
        }
        """

        variables = {
            "board_id": board_id,
            "item_id": item_id,
            "column_values": json.dumps({columns["email sent"]: {"checked": "true"}})
        }

        self._execute_query(query, variables)
        logger.info(f"Updated email sent status for item {item_id}")

    def create_leads_batch(self, enriched_companies: List, board_id: str = None) -> List[str]:
        """
        Create multiple leads in Monday.com.

        Args:
            enriched_companies: List of EnrichedCompany objects
            board_id: Board ID

        Returns:
            List of created item IDs
        """
        board_id = board_id or self.board_id
        created_ids = []

        for company in enriched_companies:
            try:
                item_id = self.create_lead(company, board_id)
                if item_id:
                    created_ids.append(item_id)
            except Exception as e:
                logger.error(f"Error creating lead for {company.company_name}: {e}")

        logger.info(f"Created {len(created_ids)} leads in Monday.com")
        return created_ids


def create_board(name: str = "AI Lead Generation") -> str:
    """Convenience function to create a board"""
    service = MondayCRMService()
    return service.create_board(name)


def create_leads(enriched_companies: List, board_id: str = None) -> List[str]:
    """Convenience function to create leads"""
    service = MondayCRMService()
    if board_id:
        service.board_id = board_id
    return service.create_leads_batch(enriched_companies, board_id)