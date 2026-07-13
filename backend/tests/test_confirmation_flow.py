"""Tests for the destructive-action confirmation flow.

Covers:
- Destructive tool detection (single tool + nested in COMPOSIO_MULTI_EXECUTE_TOOL)
- The ConfirmationRequired exception carries the right payload
- summarize_for_human gives readable strings for common tool slugs
- DEFAULT_BEHAVIOR_FOR_UNKNOWN keeps unknown slugs out of the destructive set

Does NOT exercise the live confirm endpoint (would need a Composio
integration fixture); the endpoint's own tests will follow once we have
a Composio mock harness.
"""



def test_destructive_slugs_includes_canonical_writes():
    """Sanity: the catalog has to include the obvious dangerous ones.
    If any of these slip out of the set, the gate goes away silently."""
    from agents.destructive_tools import DESTRUCTIVE_SLUGS

    for slug in (
        "GMAIL_SEND_EMAIL",
        "GMAIL_REPLY_TO_THREAD",
        "GOOGLECALENDAR_CREATE_EVENT",
        "GOOGLECALENDAR_DELETE_EVENT",
        "GOOGLEDRIVE_DELETE_FILE",
        "GOOGLEDRIVE_SHARE_FILE",
        "GOOGLESHEETS_BATCH_UPDATE",
        "HUBSPOT_CREATE_DEAL",
        "JIRA_CREATE_ISSUE",
        "ZOOM_CREATE_MEETING",
    ):
        assert slug in DESTRUCTIVE_SLUGS, f"{slug} must require confirmation"


def test_destructive_slugs_excludes_drafts_and_reads():
    """Drafts are private; reads are inherently safe. They must NOT be
    in the destructive set or every chat will be interrupted by useless
    permission prompts."""
    from agents.destructive_tools import DESTRUCTIVE_SLUGS

    for slug in (
        "GMAIL_CREATE_DRAFT",   # draft only — not sent
        "GMAIL_LIST_MESSAGES",
        "GMAIL_FETCH_EMAILS",
        "GOOGLEDRIVE_SEARCH",
        "GOOGLESHEETS_BATCH_GET",
        "GOOGLECALENDAR_LIST_EVENTS",
        "HUBSPOT_GET_DEAL",
    ):
        assert slug not in DESTRUCTIVE_SLUGS, f"{slug} must NOT require confirmation"


def test_is_destructive_is_case_insensitive():
    from agents.destructive_tools import is_destructive

    assert is_destructive("GMAIL_SEND_EMAIL")
    assert is_destructive("gmail_send_email")
    assert is_destructive("Gmail_Send_Email")
    assert not is_destructive("GMAIL_FETCH_EMAILS")
    assert not is_destructive("totally_unknown_tool")


def test_extract_destructive_subtools_finds_writes_in_batch():
    """The agent batches calls via COMPOSIO_MULTI_EXECUTE_TOOL. If even one
    sub-tool is destructive, the wrapper must return it so we can gate
    the whole batch."""
    from agents.destructive_tools import extract_destructive_subtools

    meta_args = {
        "tools": [
            {"tool_slug": "GMAIL_FETCH_EMAILS", "arguments": {"max_results": 5}},
            {"tool_slug": "GMAIL_SEND_EMAIL", "arguments": {"to": "x@y.com", "subject": "Hi"}},
            {"tool_slug": "GOOGLEDRIVE_SEARCH", "arguments": {"query": "report"}},
            {"tool_slug": "GOOGLECALENDAR_CREATE_EVENT", "arguments": {"summary": "Sync"}},
        ]
    }
    found = extract_destructive_subtools(meta_args)

    slugs = {item["tool_slug"] for item in found}
    assert slugs == {"GMAIL_SEND_EMAIL", "GOOGLECALENDAR_CREATE_EVENT"}
    # Arguments must be carried through so the eventual execute call has
    # the data it needs.
    by_slug = {item["tool_slug"]: item["arguments"] for item in found}
    assert by_slug["GMAIL_SEND_EMAIL"]["to"] == "x@y.com"


def test_extract_destructive_subtools_returns_empty_for_all_reads():
    """All-read batch → no confirmation, agent proceeds normally."""
    from agents.destructive_tools import extract_destructive_subtools

    meta_args = {
        "tools": [
            {"tool_slug": "GMAIL_FETCH_EMAILS", "arguments": {}},
            {"tool_slug": "GOOGLEDRIVE_SEARCH", "arguments": {}},
        ]
    }
    assert extract_destructive_subtools(meta_args) == []


def test_extract_destructive_subtools_tolerates_malformed_payload():
    """The agent could pass a malformed meta-tool arg. We must not crash."""
    from agents.destructive_tools import extract_destructive_subtools

    assert extract_destructive_subtools({}) == []
    assert extract_destructive_subtools({"tools": "not a list"}) == []
    assert extract_destructive_subtools({"tools": [None, "string", 42]}) == []
    # Missing tool_slug
    assert extract_destructive_subtools({"tools": [{"arguments": {}}]}) == []


def test_summarize_for_human_gmail_send_email():
    from agents.destructive_tools import summarize_for_human

    s = summarize_for_human("GMAIL_SEND_EMAIL", {"recipient_email": "acme@x.com", "subject": "Hi"})
    assert "acme@x.com" in s
    assert "Hi" in s


def test_summarize_for_human_fallback_is_human_readable():
    """Unknown slug should at least produce a Title Case label, not raw uppercase."""
    from agents.destructive_tools import summarize_for_human

    s = summarize_for_human("SOMETHING_NEW_TOOL", {})
    assert "Something New Tool" in s


def test_confirmation_required_exception_carries_payload():
    """The exception is the contract between the tool wrapper and the
    chat router. Must round-trip slug, args, session id, description."""
    from agents.tools import ConfirmationRequired

    cr = ConfirmationRequired(
        tool_slug="GMAIL_SEND_EMAIL",
        tool_args={"to": "a@b.com", "subject": "x"},
        composio_session_id="trs_xyz",
        human_description="Send email to a@b.com — subject: x",
    )
    assert cr.tool_slug == "GMAIL_SEND_EMAIL"
    assert cr.tool_args == {"to": "a@b.com", "subject": "x"}
    assert cr.composio_session_id == "trs_xyz"
    assert cr.human_description.startswith("Send email")
    assert cr.destructive_subtools == []


def test_confirmation_required_carries_batch_subtools():
    from agents.tools import ConfirmationRequired

    subs = [
        {"tool_slug": "GMAIL_SEND_EMAIL", "arguments": {"to": "a@b.com"}},
        {"tool_slug": "GOOGLECALENDAR_CREATE_EVENT", "arguments": {"summary": "Sync"}},
    ]
    cr = ConfirmationRequired(
        tool_slug="COMPOSIO_MULTI_EXECUTE_TOOL",
        tool_args={"tools": subs},
        composio_session_id="trs_xyz",
        human_description="2 actions: ...",
        destructive_subtools=subs,
    )
    assert len(cr.destructive_subtools) == 2
    assert cr.destructive_subtools[0]["tool_slug"] == "GMAIL_SEND_EMAIL"


def test_pending_action_model_columns():
    """If a future schema change drops a column the router relies on,
    fail loudly here rather than in production at 3am."""
    from db.models import PendingAction

    cols = {c.name for c in PendingAction.__table__.columns}
    required = {
        "id", "user_id", "session_id", "tool_slug", "tool_args",
        "human_description", "composio_session_id", "status",
        "result", "created_at", "expires_at",
    }
    missing = required - cols
    assert not missing, f"PendingAction missing columns: {missing}"
