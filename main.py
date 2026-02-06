#!/usr/bin/env python3
"""
AI-Powered Lead Generation & Outreach Automation
Main application entry point with CLI interface.

Usage:
    python main.py --company-type "solar energy installers" --region "Winnipeg, Manitoba" --count 10
    python main.py --setup-board  # Create Monday.com board first
    python main.py --batch-file batch.json  # Process multiple searches
    python main.py --help
"""

import argparse
import logging
import sys
import json
from datetime import datetime

from config import get_config
from modules import (
    discover_companies,
    enrich_companies,
    create_board,
    create_leads,
    send_outreach_emails,
    preview_email,
    MondayCRMService,
    ProgressTracker
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'lead_generation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)


def setup_board(board_name: str = "AI Lead Generation") -> str:
    """Create a new Monday.com board with all required columns"""
    logger.info(f"Setting up Monday.com board: {board_name}")

    try:
        board_id = create_board(board_name)
        print(f"\n Board created successfully!")
        print(f"   Board ID: {board_id}")
        print(f"\n   Add this to your .env file:")
        print(f"   MONDAY_BOARD_ID={board_id}")
        return board_id
    except Exception as e:
        logger.error(f"Failed to create board: {e}")
        print(f"\n Error creating board: {e}")
        sys.exit(1)


def run_pipeline(
    company_type: str,
    region: str,
    count: int = 10,
    send_emails: bool = False,
    preview_only: bool = False,
    export_csv: bool = False,
    use_ai_emails: bool = False,
    enrichment_mode: str = "hunter"
):
    """
    Run the full lead generation pipeline.

    Steps:
    1. Discover companies using AI
    2. Enrich with contact information
    3. Create leads in Monday.com
    4. Send outreach emails (optional)
    """
    config = get_config()
    progress = ProgressTracker(total_steps=4)

    print("\n" + "=" * 60)
    print("  AI-Powered Lead Generation Pipeline")
    print("=" * 60)
    print(f"   Company Type: {company_type}")
    print(f"   Region: {region}")
    print(f"   Target Count: {count}")
    if use_ai_emails:
        print(f"   Email Mode: AI-Personalized")
    print(f"   Enrichment: {enrichment_mode}")
    print("=" * 60 + "\n")

    # Step 1: Discover Companies
    progress.start_step("Discovering Companies (Groq AI)", 1, count)
    try:
        companies = discover_companies(company_type, region, count)
        for i, company in enumerate(companies, 1):
            progress.update_item(i, len(companies), company.name, "found")
        progress.complete_step(1, f"Found {len(companies)} companies")
    except Exception as e:
        logger.error(f"Company discovery failed: {e}")
        print(f"   Error: {e}")
        sys.exit(1)

    # Step 2: Enrich Contacts
    progress.start_step("Enriching Contact Information", 2, len(companies))
    try:
        enriched = enrich_companies(companies, mode=enrichment_mode)
        contacts_found = sum(1 for c in enriched if c.contact and c.contact.email)
        for i, company in enumerate(enriched, 1):
            status = "contact found" if (company.contact and company.contact.email) else "no contact"
            progress.update_item(i, len(enriched), company.company_name, status)
        progress.complete_step(2, f"Contacts found for {contacts_found}/{len(enriched)} companies")
    except Exception as e:
        logger.error(f"Contact enrichment failed: {e}")
        print(f"   Error: {e}")
        # Continue with available data
        enriched = [
            type('EnrichedCompany', (), {
                'company_name': c.name,
                'website': c.website,
                'description': c.description,
                'industry': c.industry,
                'region': c.region,
                'contact': None
            })() for c in companies
        ]
        progress.complete_step(2, "Enrichment failed - continuing with basic data")

    # Step 3: Create Leads in Monday.com
    progress.start_step("Creating Leads in Monday.com", 3, len(enriched))

    if not config.monday.board_id:
        print("   No board ID configured. Creating new board...")
        board_id = setup_board()
        config.monday.board_id = board_id

    try:
        crm_service = MondayCRMService()
        crm_service.board_id = config.monday.board_id

        created_ids = []
        for i, company in enumerate(enriched, 1):
            try:
                item_id = crm_service.create_lead(company)
                if item_id:
                    created_ids.append((item_id, company))
                    progress.update_item(i, len(enriched), company.company_name, "created")
                else:
                    progress.update_item(i, len(enriched), company.company_name, "duplicate/skipped")
            except Exception as e:
                logger.warning(f"Could not create lead for {company.company_name}: {e}")
                progress.update_item(i, len(enriched), company.company_name, "failed")

        progress.complete_step(3, f"Created {len(created_ids)} leads in Monday.com")
    except Exception as e:
        logger.error(f"Monday.com integration failed: {e}")
        print(f"   Error: {e}")
        created_ids = [(None, c) for c in enriched]
        progress.complete_step(3, "CRM creation failed")

    # Step 4: Send Emails
    progress.start_step("Email Outreach", 4)

    # Filter companies with valid contacts
    emailable = [c for c in enriched if c.contact and c.contact.email]
    successful_emails = 0

    if not emailable:
        print("   No contacts with email addresses found. Skipping email step.")
        progress.complete_step(4, "No contacts available for email")
    elif preview_only:
        print("   Email Preview Mode (not sending):\n")
        for company in emailable[:3]:  # Preview first 3
            preview = preview_email(company, company_type)
            print(f"   To: {preview['to']}")
            print(f"   Subject: {preview['subject']}")
            print(f"   ---")
            print(f"   {preview['body'][:200]}...")
            print()
        progress.complete_step(4, f"Previewed {min(3, len(emailable))} emails")
    elif send_emails:
        print(f"   Sending emails to {len(emailable)} contacts...")
        try:
            results = send_outreach_emails(emailable, company_type, use_ai=use_ai_emails)
            successful_emails = sum(1 for r in results if r.success)
            for i, result in enumerate(results, 1):
                status = "sent" if result.success else f"failed: {result.error_message}"
                progress.update_item(i, len(results), result.company_name, status)

            # Update Monday.com with email status
            for (item_id, company), result in zip(created_ids, results):
                if item_id and result.success:
                    try:
                        crm_service.update_email_sent(item_id)
                    except Exception:
                        pass

            progress.complete_step(4, f"Sent {successful_emails}/{len(results)} emails")
        except Exception as e:
            logger.error(f"Email sending failed: {e}")
            print(f"   Error: {e}")
            progress.complete_step(4, "Email sending failed")
    else:
        print(f"   Skipping email (use --send-emails to enable)")
        progress.complete_step(4, "Skipped (not enabled)")

    # Export to CSV if requested
    if export_csv:
        export_to_csv(enriched, company_type, region)

    # Final Summary
    progress.print_summary({
        "Companies discovered": len(companies),
        "Contacts enriched": sum(1 for c in enriched if c.contact),
        "Leads created": len([i for i, _ in created_ids if i]),
        "Emails sent": successful_emails if send_emails else "N/A"
    })

    return enriched


def run_batch(batch_file: str, send_emails: bool = False, export_csv: bool = False, use_ai_emails: bool = False, enrichment_mode: str = "hunter"):
    """
    Run the pipeline for multiple company types/regions from a JSON batch file.

    Batch file format:
    [
        {"company_type": "solar installers", "region": "Winnipeg, Manitoba", "count": 10},
        {"company_type": "SaaS startups", "region": "Toronto, Ontario", "count": 5}
    ]
    """
    try:
        with open(batch_file, 'r', encoding='utf-8') as f:
            batch_jobs = json.load(f)
    except FileNotFoundError:
        print(f"\n Error: Batch file '{batch_file}' not found.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"\n Error: Invalid JSON in batch file: {e}")
        sys.exit(1)

    if not isinstance(batch_jobs, list) or len(batch_jobs) == 0:
        print("\n Error: Batch file must contain a non-empty JSON array of job objects.")
        sys.exit(1)

    total_jobs = len(batch_jobs)
    print("\n" + "=" * 60)
    print(f"  BATCH PROCESSING - {total_jobs} jobs")
    print("=" * 60)

    all_results = []

    for idx, job in enumerate(batch_jobs, 1):
        company_type = job.get("company_type", "")
        region = job.get("region", "")
        count = job.get("count", 10)

        if not company_type or not region:
            print(f"\n  [Job {idx}/{total_jobs}] Skipping - missing company_type or region")
            continue

        print(f"\n  {'#' * 60}")
        print(f"  Job {idx}/{total_jobs}: {company_type} in {region} (count: {count})")
        print(f"  {'#' * 60}")

        try:
            enriched = run_pipeline(
                company_type=company_type,
                region=region,
                count=count,
                send_emails=send_emails,
                export_csv=export_csv,
                use_ai_emails=use_ai_emails,
                enrichment_mode=enrichment_mode
            )
            all_results.extend(enriched)
        except Exception as e:
            logger.error(f"Batch job {idx} failed: {e}")
            print(f"  Job {idx} failed: {e}")

    print(f"\n{'=' * 60}")
    print(f"  BATCH COMPLETE")
    print(f"  Total leads processed across {total_jobs} jobs: {len(all_results)}")
    print(f"{'=' * 60}\n")

    return all_results


def export_to_csv(enriched_companies: list, company_type: str, region: str):
    """Export leads to CSV file"""
    import csv

    filename = f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([
            'Company Name', 'Website', 'Description', 'Industry', 'Region',
            'Contact Name', 'Contact Email', 'Contact Position', 'Contact Phone'
        ])

        # Data
        for company in enriched_companies:
            writer.writerow([
                company.company_name,
                company.website,
                company.description,
                company.industry,
                company.region,
                company.contact.name if company.contact else '',
                company.contact.email if company.contact else '',
                company.contact.position if company.contact else '',
                company.contact.phone if company.contact else ''
            ])

    print(f"   Exported to {filename}\n")


def main():
    """Main entry point with CLI argument parsing"""
    parser = argparse.ArgumentParser(
        description='AI-Powered Lead Generation & Outreach Automation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Setup Monday.com board first
  python main.py --setup-board

  # Run full pipeline
  python main.py --company-type "solar energy installers" --region "Winnipeg, Manitoba"

  # Run with email sending enabled
  python main.py --company-type "SaaS startups" --region "Toronto, Ontario" --send-emails

  # Run with AI-personalized emails
  python main.py -t "manufacturing" -r "Vancouver, BC" --send-emails --ai-emails

  # Preview emails without sending
  python main.py --company-type "tech companies" --region "Calgary, Alberta" --preview-emails

  # Export results to CSV
  python main.py --company-type "consulting firms" --region "Montreal, Quebec" --export-csv

  # Batch processing from file
  python main.py --batch-file batch.json --send-emails --export-csv
        """
    )

    parser.add_argument(
        '--setup-board',
        action='store_true',
        help='Create a new Monday.com board with required columns'
    )

    parser.add_argument(
        '--board-name',
        type=str,
        default='AI Lead Generation',
        help='Name for the Monday.com board (default: AI Lead Generation)'
    )

    parser.add_argument(
        '--company-type', '-t',
        type=str,
        help='Type of companies to find (e.g., "solar energy installers")'
    )

    parser.add_argument(
        '--region', '-r',
        type=str,
        help='Geographic region (e.g., "Winnipeg, Manitoba")'
    )

    parser.add_argument(
        '--count', '-c',
        type=int,
        default=10,
        help='Number of companies to find (default: 10, max: 50)'
    )

    parser.add_argument(
        '--send-emails',
        action='store_true',
        help='Send introduction emails to discovered contacts'
    )

    parser.add_argument(
        '--ai-emails',
        action='store_true',
        help='Use AI to generate personalized email content per lead'
    )

    parser.add_argument(
        '--preview-emails',
        action='store_true',
        help='Preview emails without sending'
    )

    parser.add_argument(
        '--export-csv',
        action='store_true',
        help='Export results to CSV file'
    )

    parser.add_argument(
        '--batch-file',
        type=str,
        help='Path to JSON file with multiple search jobs for batch processing'
    )

    parser.add_argument(
        '--enrichment-mode',
        type=str,
        choices=['hunter', 'manual'],
        default='hunter',
        help='Contact enrichment mode: "hunter" (Hunter.io API) or "manual" (web scraping + AI, free)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Setup board mode
    if args.setup_board:
        setup_board(args.board_name)
        return

    # Batch mode
    if args.batch_file:
        run_batch(
            batch_file=args.batch_file,
            send_emails=args.send_emails,
            export_csv=args.export_csv,
            use_ai_emails=args.ai_emails,
            enrichment_mode=args.enrichment_mode
        )
        return

    # Validate required arguments for pipeline
    if not args.company_type or not args.region:
        parser.error("--company-type and --region are required for lead generation (or use --batch-file)")

    # Run pipeline
    run_pipeline(
        company_type=args.company_type,
        region=args.region,
        count=args.count,
        send_emails=args.send_emails,
        preview_only=args.preview_emails,
        export_csv=args.export_csv,
        use_ai_emails=args.ai_emails,
        enrichment_mode=args.enrichment_mode
    )


if __name__ == "__main__":
    main()
