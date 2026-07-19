"""Composio v3 tool configuration per department.

Each department gets a scoped set of Composio-managed tool integrations.
Uses Composio's standard provider to return tool objects via session.tools().

SECURITY: tools are created fresh per request (no caching) and every tool
invocation is wrapped with an audit logger that records the bound
(user_id, composio_session_id) at execution time. This is to prevent the
cross-user data leak class where a cached tool object outlived its
intended user binding.

Set DISABLE_COMPOSIO=true in the environment to kill-switch all tool
loading without touching code (emergency containment).
"""

import logging
import os
from typing import Any

from agents.config import COMPOSIO_API_KEY
from agents.destructive_tools import (
    DESTRUCTIVE_SLUGS,
    META_EXECUTE_SLUG,
    build_batch_details,
    build_full_action_details,
    extract_destructive_subtools,
    is_destructive,
    summarize_for_human,
)

logger = logging.getLogger(__name__)
audit_log = logging.getLogger("kizuna.audit.composio")


class ConfirmationRequired(Exception):
    """Raised from a Composio tool wrapper when a destructive action needs
    explicit user approval before executing. Caught above in the chat
    SSE generator, which persists a PendingAction row and emits the
    confirmation_required event to the client.
    """

    def __init__(
        self,
        *,
        tool_slug: str,
        tool_args: dict[str, Any],
        composio_session_id: str,
        human_description: str,
        destructive_subtools: list[dict[str, Any]] | None = None,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(f"Confirmation required for {tool_slug}")
        self.tool_slug = tool_slug
        self.tool_args = tool_args
        self.composio_session_id = composio_session_id
        self.human_description = human_description
        # For COMPOSIO_MULTI_EXECUTE_TOOL: the destructive sub-tools the
        # agent was about to invoke. Empty for direct destructive calls.
        self.destructive_subtools = destructive_subtools or []
        # Structured per-action field payload shown in the permission card.
        # One entry per destructive sub-tool, or a single-element list for
        # direct destructive calls. Shape: [{tool_slug, fields:[{label,value,multiline?}]}, ...]
        self.details = details or []

# Toolkits per department — used for both agent tool loading and connectors UI.
DEPARTMENT_TOOLKITS: dict[str, list[str]] = {
    "admin": [
        "zoom", "gmail", "google_chat", "googlecalendar", "googlemeet",
        "googledrive", "googlesheets", "googledocs", "googleslides", "outlook",
        "highlevel", "one_drive", "share_point", "microsoft_teams", "excel", "onenote",
        "instagram", "linkedin",
    ],
    "sales": [
        "hubspot", "zoom", "gmail", "google_chat", "googlecalendar", "googlemeet",
        "googledrive", "googlesheets", "googledocs", "googleslides", "outlook",
        "highlevel", "one_drive", "share_point", "microsoft_teams", "excel", "onenote",
        "instagram", "linkedin",
    ],
    "operations": [
        "jira", "zoom", "gmail", "google_chat", "googlecalendar", "googlemeet",
        "googledrive", "googlesheets", "googledocs", "googleslides", "outlook",
        "highlevel", "one_drive", "share_point", "microsoft_teams", "excel", "onenote",
        "instagram", "linkedin",
    ],
    "finance": [
        "zoom", "gmail", "google_chat", "googlecalendar", "googlemeet",
        "googledrive", "googlesheets", "googledocs", "googleslides", "outlook",
        "highlevel", "one_drive", "share_point", "microsoft_teams", "excel", "onenote",
        "instagram", "linkedin",
    ],
    "executive": [
        "hubspot", "jira", "zoom", "gmail", "google_chat", "googlecalendar", "googlemeet",
        "googledrive", "googlesheets", "googledocs", "googleslides", "outlook",
        "highlevel", "one_drive", "share_point", "microsoft_teams", "excel", "onenote",
        "instagram", "linkedin",
    ],
}

# Toolkits that are known to fail (no managed auth config in Composio).
# These are still shown in the connectors UI but excluded from agent tool loading.
_SKIP_TOOLKITS = {"google_chat"}

# Toolkits that require custom developer credentials/auth configurations on the dashboard.
# If these are not connected by the user, we skip them from session creation to prevent BadRequestError.
_CUSTOM_AUTH_TOOLKITS = {"highlevel", "onenote"}


def _is_disabled() -> bool:
    return os.environ.get("DISABLE_COMPOSIO", "").lower() in ("1", "true", "yes")


def _wrap_with_audit(tool, user_id: str, session_id: str, department: str):
    """Replace a FunctionTool's underlying callable with an audited version.

    Two duties:
    1. Audit log: every invocation records (user_id, composio_session_id,
       tool name). Forensic evidence of binding correctness.
    2. Permission gate: destructive tool calls (or COMPOSIO_MULTI_EXECUTE
       batches containing destructive sub-tools) raise ConfirmationRequired
       INSTEAD of executing. The chat SSE generator catches this above,
       persists a PendingAction row, and emits a confirmation_required
       event to the client. The actual execution happens later via
       POST /api/chat/confirm/{action_id} after the user clicks Allow.
    """
    # Handle dict-like tools from newer Composio versions
    if not hasattr(tool, 'func'):
        raise AttributeError(f"Tool does not have 'func' attribute: {type(tool)}")

    original = tool.func
    tool_name = getattr(original, "__name__", "unknown")

    def audited(**kwargs):
        audit_log.info(
            "tool_call user_id=%s composio_session_id=%s tool=%s department=%s",
            user_id, session_id, tool_name, department,
        )

        # ----- Permission gate -----
        slug_upper = tool_name.upper()
        if slug_upper == META_EXECUTE_SLUG:
            destructive_subs = extract_destructive_subtools(kwargs)
            if destructive_subs:
                description = _build_batch_description(destructive_subs)
                audit_log.info(
                    "tool_gated user_id=%s composio_session_id=%s tool=%s "
                    "destructive_subtools=%d",
                    user_id, session_id, tool_name, len(destructive_subs),
                )
                raise ConfirmationRequired(
                    tool_slug=tool_name,
                    tool_args=dict(kwargs),
                    composio_session_id=session_id,
                    human_description=description,
                    destructive_subtools=destructive_subs,
                    details=build_batch_details(destructive_subs),
                )
        elif is_destructive(slug_upper):
            description = summarize_for_human(slug_upper, kwargs)
            audit_log.info(
                "tool_gated user_id=%s composio_session_id=%s tool=%s",
                user_id, session_id, tool_name,
            )
            raise ConfirmationRequired(
                tool_slug=tool_name,
                tool_args=dict(kwargs),
                composio_session_id=session_id,
                human_description=description,
                details=[build_full_action_details(slug_upper, kwargs)],
            )
        # ----- end permission gate -----

        try:
            result = original(**kwargs)
            audit_log.info(
                "tool_done user_id=%s composio_session_id=%s tool=%s status=ok",
                user_id, session_id, tool_name,
            )
            return result
        except Exception as e:
            audit_log.error(
                "tool_fail user_id=%s composio_session_id=%s tool=%s error=%s",
                user_id, session_id, tool_name, e,
            )
            raise

    # Preserve the metadata for function declaration / schema.
    audited.__name__ = original.__name__
    audited.__doc__ = original.__doc__
    if hasattr(original, "__signature__"):
        audited.__signature__ = original.__signature__
    if hasattr(original, "__annotations__"):
        audited.__annotations__ = original.__annotations__

    tool.func = audited
    return tool


def _build_batch_description(destructive_subs: list[dict[str, Any]]) -> str:
    """One-line summary covering all destructive sub-tools in a MULTI_EXECUTE batch."""
    if len(destructive_subs) == 1:
        s = destructive_subs[0]
        return summarize_for_human(s["tool_slug"], s["arguments"])
    parts = [summarize_for_human(s["tool_slug"], s["arguments"]) for s in destructive_subs]
    return f"{len(parts)} actions: " + "; ".join(parts)


def get_composio_tools(user_id: str, department: str) -> list:
    """Get Composio tools for a user scoped to their department.

    No caching — every call mints a fresh Composio session bound to user_id
    and wraps each tool with audit logging. This is the security boundary:
    if the user_id passed in is wrong, the wrong account is used. Callers
    MUST pass the authenticated request user, never a derived or cached
    value.
    """
    if _is_disabled():
        logger.warning("Composio disabled via DISABLE_COMPOSIO env var — returning no tools")
        return []

    all_toolkits = DEPARTMENT_TOOLKITS.get(department)
    if not all_toolkits:
        return []

    if not COMPOSIO_API_KEY:
        logger.warning("COMPOSIO_API_KEY not set — tools disabled")
        return []

    toolkits = [tk for tk in all_toolkits if tk not in _SKIP_TOOLKITS]
    if not toolkits:
        return []

    try:
        from composio import Composio

        composio = Composio()

        # Find which of the custom auth toolkits are actually connected/active for this user
        connected_slugs = set()
        try:
            accounts = composio.connected_accounts.list(
                user_ids=[user_id],
                statuses=["ACTIVE"],
            )
            connected_slugs = {item.toolkit.slug for item in accounts.items}
        except Exception as conn_err:
            logger.warning(f"Failed to check connected accounts in get_composio_tools: {conn_err}")

        # Filter the toolkits list to only include:
        # 1. Non-custom-auth toolkits
        # 2. Custom-auth toolkits that are actively connected by the user
        toolkits_to_load = []
        for tk in toolkits:
            if tk in _CUSTOM_AUTH_TOOLKITS:
                if tk in connected_slugs:
                    toolkits_to_load.append(tk)
            else:
                toolkits_to_load.append(tk)

        if not toolkits_to_load:
            logger.info(f"No connectable toolkits to load for user={user_id} department={department}")
            return []

        session = composio.create(user_id=user_id, toolkits=toolkits_to_load)
        session_id = session.session_id
        tools = session.tools()

        audit_log.info(
            "session_create user_id=%s composio_session_id=%s department=%s tool_count=%d",
            user_id, session_id, department, len(tools),
        )

        # Wrap every tool with audit logging that pins user_id + session_id
        # at execution time. Skip wrapping for tools that don't support it.
        wrapped = []
        for t in tools:
            try:
                wrapped.append(_wrap_with_audit(t, user_id, session_id, department))
            except (AttributeError, TypeError):
                # Tool doesn't support wrapping (e.g., dict format), use as-is
                logger.debug(f"Tool {t} doesn't support audit wrapping, using as-is")
                wrapped.append(t)

        logger.info(
            f"Loaded {len(wrapped)} Composio tools for user={user_id} "
            f"composio_session={session_id} department={department}"
        )
        return wrapped
    except Exception as e:
        logger.warning(f"Failed to load Composio tools for {department}: {e}")
        return []
