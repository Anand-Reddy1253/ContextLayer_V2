"""One-off: add real labels to real, live Confluence pages.

Deliberately NOT a SourceConnector method and NOT called from sync —
ADR-001 ("no connector method ever writes to a vendor source") is a hard,
permanent rule for connectors/confluence/live.py specifically. This script
lives outside that class entirely and is a manual editorial action run
once, by hand, against the live Confluence site — not a Context Fabric
read/sync capability.

Uses the real Confluence v2 REST API's own label endpoint
(`POST /wiki/api/v2/pages/{id}/labels`), Basic auth with the same
email + API token already stored (encrypted) for the "conf_talentflow"
connector connection.

Run from the repo root: `python scripts/label_confluence_pages.py`
"""

import asyncio

import httpx

from context_fabric.connectors.credentials import decrypt_credential
from context_fabric.persistence.repositories.connector_connection import (
    ConnectorConnectionRepository,
)
from context_fabric.persistence.session import session_scope
from context_fabric.settings import Settings

# Real page native_id -> label, per the plan agreed with the user. Titles
# are the real, live-synced page titles this was built against — see
# them again with:
#   SELECT native_id, name FROM node WHERE source_system='confluence' AND kind='PAGE';
PAGE_LABELS: dict[str, str] = {
    # ADRs
    "1114305": "type-adr",  # ADR-0015: Real-Time Notification Delivery Contract
    "1146881": "type-adr",  # ADR-0004: Layered Service Architecture and Dependency Direction
    "1146902": "type-adr",  # ADR-0018: Schema Evolution for the Talentflow Datastore
    "1179649": "type-adr",  # ADR-0011: NgRx Effects as the Sole Async Boundary
    "327898": "type-adr",  # ADR-0007: Status Lifecycle Handling for Applications and Candidates
    "327919": "type-adr",  # ADR-0021: Bearer Token Exchange and Principal Propagation
    # Runbooks
    "1015830": "type-runbook",  # Runbook: Web Deploy and Rollback on Container Apps
    "1212417": "type-runbook",  # Runbook: Transient Fault Handling for Directory Calls
    "98310": "type-runbook",  # Runbook: Environment Configuration and Startup Flags
    # Integration guides
    "1245185": "type-integration-guide",  # Integration Guide: Consuming the Talentflow REST Surface
    "1277953": "type-integration-guide",  # Integration Guide: Local Development Modes and Request Interception
    # Onboarding
    "1146923": "type-onboarding",  # Backend Onboarding
    "65718": "type-onboarding",  # Frontend Ways of Working
    # Meeting notes
    "360467": "type-meeting-notes",  # Talentflow Sync — 2026-08-12
    "688342": "type-meeting-notes",  # Frontend / Platform Sync Notes — 2026-07-29
    # Templates
    "327852": "type-template",  # Template - Project plan
    "327865": "type-template",  # Template - Meeting notes
    "327878": "type-template",  # Template - Weekly status report
    # Lifecycle
    "491714": "status-draft",  # Draft: Candidate Grid Filter Rework
    # Deliberately not labeled: Confluence's own default boilerplate
    # (Overview, Getting started in Confluence, Explore Confluence
    # Features, My first space) and real content that doesn't cleanly
    # fit any type/status bucket (Talentflow Web Home, How We Deploy the
    # Talentflow API, Directory Lookup Retry Settings, Talentflow API
    # Home, Container Apps Scaling Evaluation, Everything You Need to
    # Know About the Candidate Feature, Deployment Standards for
    # Talentflow Container Apps, Talentflow Platform Home, Team Directory
    # and Component Ownership).
}


async def main() -> None:
    secret_key = Settings().CF_SECRET_KEY
    if not secret_key:
        raise SystemExit("CF_SECRET_KEY is not set (check .env)")

    async with session_scope() as session:
        repo = ConnectorConnectionRepository(session)
        rows = await repo.list_all()
        conf = next((r for r in rows if r.source_system == "confluence"), None)
        if conf is None:
            raise SystemExit("no confluence connector connection found")

        ciphertext = await repo.get_credential_ciphertext(conf.id)
        if ciphertext is None:
            raise SystemExit("confluence connection has no stored credential")
        api_token = decrypt_credential(ciphertext, secret_key)

    email = conf.config["email"]
    site_url = conf.config["site_url"].rstrip("/")

    # Confluence's v2 REST API only supports *listing* page labels
    # (`GET /wiki/api/v2/pages/{id}/labels`, used by the connector) — a
    # real, empirically-confirmed 405 on POST there. Creating a label is
    # still v1-API-only: `POST /wiki/rest/api/content/{id}/label` with a
    # JSON array body.
    async with httpx.AsyncClient(
        base_url=f"{site_url}/wiki/rest/api",
        auth=(email, api_token),
        headers={"Accept": "application/json"},
        timeout=30.0,
    ) as client:
        succeeded, failed = 0, 0
        for page_id, label in PAGE_LABELS.items():
            resp = await client.post(
                f"/content/{page_id}/label", json=[{"prefix": "global", "name": label}]
            )
            if resp.status_code in (200, 201):
                print(f"  {page_id}: added '{label}'")
                succeeded += 1
            else:
                print(f"  {page_id}: FAILED ({resp.status_code}) {resp.text[:200]}")
                failed += 1

    print(f"\n{succeeded} succeeded, {failed} failed, out of {len(PAGE_LABELS)}.")
    print("Now re-sync the confluence connector to pull the new labels in.")


asyncio.run(main())
