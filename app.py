"""
Lead Generation Dashboard
Simple Streamlit UI for the lead generation pipeline.
Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import csv
import io
import logging
import sys
from datetime import datetime
import os

# Setup logging to capture module logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])

from config import get_config
from modules.company_discovery import discover_companies, CompanyDiscoveryService
from modules.contact_enrichment import enrich_companies, ContactEnrichmentService, EnrichedCompany
from modules.monday_crm import MondayCRMService
from modules.email_outreach import EmailOutreachService, preview_email

# ── Page config ──
st.set_page_config(page_title="Lead Generation Tool", page_icon="briefcase", layout="wide")

# ── Simple login ──
USERNAME = st.secrets["app"]["username"]  
PASSWORD = st.secrets["app"]["password"]  

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("Login")
    user = st.text_input("Username")
    pwd = st.text_input("Password", type="password")
    if st.button("Login"):
        if user == USERNAME and pwd == PASSWORD:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Wrong username or password.")
    st.stop()

# ── Session state defaults ──
if "companies" not in st.session_state:
    st.session_state.companies = []
if "enriched" not in st.session_state:
    st.session_state.enriched = []
if "leads_created" not in st.session_state:
    st.session_state.leads_created = []
if "emails_sent" not in st.session_state:
    st.session_state.emails_sent = []


def main():
    st.title("Lead Generation Tool")
    st.caption("Find companies, get contacts, push to CRM, send emails.")

    # ── Sidebar: Settings ──
    with st.sidebar:
        st.header("Settings")

        try:
            config = get_config()
            st.success("Config loaded")
        except Exception as e:
            st.error(f"Config error: {e}")
            st.info("Check your .env file has all required keys.")
            return

        # Hunter.io credits display
        st.subheader("Hunter.io Account")
        try:
            svc = ContactEnrichmentService(mode="hunter")
            account = svc.check_account()
            if account:
                searches = account.get("requests", {}).get("searches", {})
                used = searches.get("used", 0)
                available = searches.get("available", 0)
                remaining = available - used
                st.metric("Credits Remaining", f"{remaining}/{available}")
            else:
                st.warning("Could not fetch account info")
        except Exception:
            st.warning("Hunter.io not configured")

        st.divider()

        # Monday.com board
        st.subheader("Monday.com")
        board_id = config.monday.board_id
        if board_id:
            st.text(f"Board ID: {board_id}")
        else:
            st.warning("No board ID set")
            if st.button("Create Board"):
                try:
                    crm = MondayCRMService()
                    new_id = crm.create_board("AI Lead Generation")
                    st.success(f"Board created: {new_id}")
                    st.info("Add this to your .env as MONDAY_BOARD_ID")
                except Exception as e:
                    st.error(f"Failed: {e}")

    # ── Main area: Tabs ──
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "1. Find Companies",
        "2. Get Contacts",
        "3. Push to CRM",
        "4. Send Emails",
        "5. Export"
    ])

    # ──────────────────────────────────────────
    # Tab 1: Company Discovery
    # ──────────────────────────────────────────
    with tab1:
        st.header("Find Companies")

        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            company_type = st.text_input("Company type", placeholder="e.g. solar energy installers")
        with col2:
            region = st.text_input("Region", placeholder="e.g. Winnipeg, Manitoba")
        with col3:
            count = st.number_input("Count", min_value=1, max_value=50, value=10)

        if st.button("Search", type="primary"):
            if not company_type or not region:
                st.warning("Enter both company type and region.")
            else:
                with st.spinner(f"Searching for {count} {company_type} in {region}..."):
                    try:
                        companies = discover_companies(company_type, region, count)
                        st.session_state.companies = companies
                        st.session_state.enriched = []  # reset downstream
                        st.session_state.leads_created = []
                        st.session_state.emails_sent = []
                        st.success(f"Found {len(companies)} companies")
                    except Exception as e:
                        st.error(f"Search failed: {e}")

        # Show results
        if st.session_state.companies:
            data = []
            for c in st.session_state.companies:
                data.append({
                    "Company": c.name,
                    "Website": c.website,
                    "Description": c.description,
                    "Industry": c.industry,
                    "Size": c.estimated_size
                })
            st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

    # ──────────────────────────────────────────
    # Tab 2: Contact Enrichment
    # ──────────────────────────────────────────
    with tab2:
        st.header("Get Contacts")

        if not st.session_state.companies:
            st.info("Run company search first (Tab 1).")
        else:
            st.write(f"{len(st.session_state.companies)} companies ready for enrichment.")

            mode = st.radio(
                "Enrichment mode",
                ["Hunter.io (uses API credits)", "Manual (web scraping, free)"],
                horizontal=True
            )
            mode_key = "hunter" if "Hunter" in mode else "manual"

            if st.button("Enrich Contacts", type="primary"):
                with st.spinner(f"Enriching contacts ({mode_key} mode)..."):
                    try:
                        enriched = enrich_companies(st.session_state.companies, mode=mode_key)
                        st.session_state.enriched = enriched
                        contacts_found = sum(1 for c in enriched if c.contact and c.contact.email)
                        st.success(f"Done. Contacts found for {contacts_found}/{len(enriched)} companies.")
                    except Exception as e:
                        st.error(f"Enrichment failed: {e}")

        # Show enriched results
        if st.session_state.enriched:
            data = []
            for c in st.session_state.enriched:
                row = {
                    "Company": c.company_name,
                    "Website": c.website,
                    "Contact": c.contact.name if c.contact else "-",
                    "Email": c.contact.email if c.contact else "-",
                    "Position": c.contact.position if c.contact else "-",
                    "Confidence": f"{c.contact.confidence_score}%" if c.contact and c.contact.confidence_score else "-",
                    "Phone": c.contact.phone if c.contact and c.contact.phone else "-",
                }
                data.append(row)
            st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

    # ──────────────────────────────────────────
    # Tab 3: Monday.com CRM
    # ──────────────────────────────────────────
    with tab3:
        st.header("Push to Monday.com")

        config = get_config()

        if not st.session_state.enriched:
            st.info("Enrich contacts first (Tab 2).")
        elif not config.monday.board_id:
            st.warning("No Monday.com board configured. Set MONDAY_BOARD_ID in .env or create one from the sidebar.")
        else:
            emailable = [c for c in st.session_state.enriched if c.contact and c.contact.email]
            no_contact = [c for c in st.session_state.enriched if not c.contact or not c.contact.email]

            st.write(f"Ready to push: **{len(emailable)}** with contacts, **{len(no_contact)}** without.")

            push_all = st.checkbox("Include companies without contacts", value=False)
            to_push = st.session_state.enriched if push_all else emailable

            if st.button("Push to Monday.com", type="primary"):
                with st.spinner(f"Creating {len(to_push)} leads..."):
                    try:
                        crm = MondayCRMService()
                        crm.board_id = config.monday.board_id
                        created = []
                        for company in to_push:
                            try:
                                item_id = crm.create_lead(company)
                                if item_id:
                                    created.append({"company": company.company_name, "item_id": item_id})
                            except Exception as e:
                                st.warning(f"Failed for {company.company_name}: {e}")
                        st.session_state.leads_created = created
                        st.success(f"Created {len(created)} leads in Monday.com")
                    except Exception as e:
                        st.error(f"CRM push failed: {e}")

        if st.session_state.leads_created:
            st.write("Created leads:")
            st.dataframe(
                pd.DataFrame(st.session_state.leads_created),
                use_container_width=True, hide_index=True
            )

    # ──────────────────────────────────────────
    # Tab 4: Email Outreach
    # ──────────────────────────────────────────
    with tab4:
        st.header("Send Emails")

        if not st.session_state.enriched:
            st.info("Enrich contacts first (Tab 2).")
        else:
            emailable = [c for c in st.session_state.enriched if c.contact and c.contact.email]

            if not emailable:
                st.warning("No contacts with email addresses found.")
            else:
                st.write(f"**{len(emailable)}** contacts with email addresses.")

                # Email template
                st.subheader("Email Template")
                subject_tpl = st.text_input(
                    "Subject",
                    value="Quick Introduction - {{sender_name}} + {{company_name}}"
                )
                body_tpl = st.text_area(
                    "Body",
                    height=200,
                    value="""Hi {{contact_name}},

I came across {{company_name}} while researching {{company_type}} companies in {{region}} and wanted to reach out.

I'd love to learn more about your work and explore if there might be any opportunities for collaboration.

Would you be open to a brief conversation?

Best regards,
{{sender_name}}"""
                )

                st.caption("Variables: {{contact_name}}, {{company_name}}, {{company_type}}, {{region}}, {{sender_name}}")

                company_type_email = st.text_input("Company type (for template)", placeholder="e.g. solar energy")

                col1, col2 = st.columns(2)

                # Preview
                with col1:
                    if st.button("Preview Email"):
                        sample = emailable[0]
                        prev = preview_email(sample, company_type_email, body_tpl, subject_tpl)
                        st.write(f"**To:** {prev.get('to', '')}")
                        st.write(f"**Subject:** {prev.get('subject', '')}")
                        st.divider()
                        st.text(prev.get("body", ""))

                # Send
                with col2:
                    if st.button("Send All Emails", type="primary"):
                        with st.spinner(f"Sending {len(emailable)} emails..."):
                            try:
                                svc = EmailOutreachService(template=body_tpl, subject_template=subject_tpl)
                                results = svc.send_emails_batch(emailable, company_type_email)
                                st.session_state.emails_sent = results
                                ok = sum(1 for r in results if r.success)
                                st.success(f"Sent {ok}/{len(results)} emails.")
                            except Exception as e:
                                st.error(f"Email sending failed: {e}")

        if st.session_state.emails_sent:
            data = []
            for r in st.session_state.emails_sent:
                data.append({
                    "Company": r.company_name,
                    "Recipient": r.recipient,
                    "Status": "Sent" if r.success else f"Failed: {r.error_message}"
                })
            st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)

    # ──────────────────────────────────────────
    # Tab 5: Export
    # ──────────────────────────────────────────
    with tab5:
        st.header("Export Data")

        if not st.session_state.enriched:
            st.info("No data to export. Run the pipeline first.")
        else:
            # Build CSV
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "Company Name", "Website", "Description", "Industry", "Region",
                "Contact Name", "Contact Email", "Contact Position", "Contact Phone"
            ])
            for c in st.session_state.enriched:
                writer.writerow([
                    c.company_name, c.website, c.description, c.industry, c.region,
                    c.contact.name if c.contact else "",
                    c.contact.email if c.contact else "",
                    c.contact.position if c.contact else "",
                    c.contact.phone if c.contact else "",
                ])

            csv_data = output.getvalue()

            st.download_button(
                label="Download CSV",
                data=csv_data,
                file_name=f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )

            # JSON export
            json_data = [c.to_dict() for c in st.session_state.enriched]
            st.download_button(
                label="Download JSON",
                data=pd.DataFrame(json_data).to_json(orient="records", indent=2),
                file_name=f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )

            st.subheader("Preview")
            preview_data = []
            for c in st.session_state.enriched:
                preview_data.append({
                    "Company": c.company_name,
                    "Website": c.website,
                    "Contact": c.contact.name if c.contact else "-",
                    "Email": c.contact.email if c.contact else "-",
                    "Position": c.contact.position if c.contact else "-",
                })
            st.dataframe(pd.DataFrame(preview_data), use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
