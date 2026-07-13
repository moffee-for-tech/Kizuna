"""Connectors router — Composio-backed toolkit connection management."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address

from middleware.rbac import get_current_user
from agents.tools import DEPARTMENT_TOOLKITS
from agents.config import COMPOSIO_API_KEY

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/connectors", tags=["connectors"])

limiter = Limiter(key_func=get_remote_address)

# Human-readable names for toolkit slugs
TOOLKIT_NAMES = {
    "gmail": "Gmail",
    "google_chat": "Google Chat",
    "googlecalendar": "Google Calendar",
    "googlemeet": "Google Meet",
    "googledrive": "Google Drive",
    "googlesheets": "Google Sheets",
    "googledocs": "Google Docs",
    "googleslides": "Google Slides",
    "hubspot": "HubSpot",
    "jira": "Jira",
    "zoom": "Zoom",
    "outlook": "Outlook",
    "highlevel": "GoHighLevel",
    "one_drive": "OneDrive",
    "share_point": "SharePoint",
    "microsoft_teams": "Microsoft Teams",
    "excel": "Excel",
    "onenote": "OneNote",
}

TOOLKIT_DESCRIPTIONS = {
    "gmail": "Read, draft, and send emails",
    "google_chat": "Send messages and manage spaces",
    "googlecalendar": "Manage your schedule and meetings",
    "googlemeet": "Schedule and manage video meetings",
    "googledrive": "Search and organize files",
    "googlesheets": "Read and update spreadsheets",
    "googledocs": "Create and edit documents",
    "googleslides": "Create and edit presentations",
    "hubspot": "Access CRM data and pipeline",
    "jira": "Manage tickets and workflows",
    "zoom": "Schedule meetings and access recordings",
    "outlook": "Access and manage Outlook emails and calendar",
    "highlevel": "Access CRM, pipelines, and contacts in GoHighLevel",
    "one_drive": "Access, upload, and organize cloud files in OneDrive",
    "share_point": "Search and manage document libraries and sites in SharePoint",
    "microsoft_teams": "Send chat messages and manage channels in Microsoft Teams",
    "excel": "Read and update spreadsheets in Excel",
    "onenote": "Read and write digital notes in OneNote",
}


def _get_composio():
    """Lazy-init Composio client."""
    if not COMPOSIO_API_KEY:
        raise HTTPException(status_code=503, detail="Composio not configured")
    from composio import Composio
    return Composio()


@router.get("")
async def get_connectors(current_user: dict = Depends(get_current_user)):
    """List available toolkits for user's department with connection status."""
    department = current_user["department"]
    user_id = current_user["id"]
    toolkits = DEPARTMENT_TOOLKITS.get(department, [])

    if not toolkits or not COMPOSIO_API_KEY:
        return {"connectors": [], "department": department}

    # Check which toolkits the user has connected
    connected_slugs = set()
    try:
        composio = _get_composio()
        accounts = composio.connected_accounts.list(
            user_ids=[user_id],
            statuses=["ACTIVE"],
        )
        for item in accounts.items:
            connected_slugs.add(item.toolkit.slug)
    except Exception as e:
        logger.warning(f"Failed to fetch connected accounts: {e}")

    connectors = []
    for slug in toolkits:
        connectors.append({
            "id": slug,
            "name": TOOLKIT_NAMES.get(slug, slug.title()),
            "description": TOOLKIT_DESCRIPTIONS.get(slug, ""),
            "connected": slug in connected_slugs,
        })

    return {"connectors": connectors, "department": department}


@router.post("/{toolkit_id}/auth")
async def initiate_auth(
    toolkit_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Start Composio OAuth flow — returns the auth URL for the frontend popup."""
    department = current_user["department"]
    user_id = current_user["id"]
    toolkits = DEPARTMENT_TOOLKITS.get(department, [])

    if toolkit_id not in toolkits:
        raise HTTPException(status_code=403, detail="Toolkit not available for your department")

    try:
        composio = _get_composio()
        session = composio.create(user_id=user_id, toolkits=[toolkit_id])
        result = session.authorize(toolkit_id)
        return {"auth_url": result.redirect_url, "connection_id": result.id}
    except Exception as e:
        logger.error(f"Failed to initiate auth for {toolkit_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to start authentication for {toolkit_id}")


@router.get("/{toolkit_id}/status")
async def check_status(
    toolkit_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Check if a toolkit connection is active for the current user."""
    user_id = current_user["id"]

    try:
        composio = _get_composio()
        accounts = composio.connected_accounts.list(
            user_ids=[user_id],
            toolkit_slugs=[toolkit_id],
        )
        for item in accounts.items:
            if item.status == "ACTIVE":
                return {"status": "ACTIVE", "toolkit_id": toolkit_id}
        if accounts.items:
            return {"status": accounts.items[0].status, "toolkit_id": toolkit_id}
        return {"status": "NOT_CONNECTED", "toolkit_id": toolkit_id}
    except Exception as e:
        logger.error(f"Failed to check status for {toolkit_id}: {e}")
        return {"status": "UNKNOWN", "toolkit_id": toolkit_id}


@router.post("/{toolkit_id}/disconnect")
async def disconnect_toolkit(
    toolkit_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Disconnect a toolkit for the current user."""
    user_id = current_user["id"]

    try:
        composio = _get_composio()
        accounts = composio.connected_accounts.list(
            user_ids=[user_id],
            toolkit_slugs=[toolkit_id],
        )
        for item in accounts.items:
            composio.connected_accounts.delete(item.id)
        return {"detail": "Disconnected", "toolkit_id": toolkit_id}
    except Exception as e:
        logger.error(f"Failed to disconnect {toolkit_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to disconnect {toolkit_id}")
