"""Destructive Composio tool catalog.

Lists the Composio tool slugs whose execution requires explicit user
confirmation in the UI (Allow/Deny card). Anything not in the destructive
set is treated as read-safe and executes without prompting.

We classify by exact slug rather than regex/prefix to avoid surprises:
a slug like GMAIL_LIST_DRAFTS is fine, but a slug we don't know yet (a
new Composio toolkit) must be either explicitly added here or left
auto-confirmed. The choice between those two defaults matters — see
DEFAULT_BEHAVIOR_FOR_UNKNOWN.

Inspecting COMPOSIO_MULTI_EXECUTE_TOOL:
The agent batches writes via the meta-tool. The wrapper must look INSIDE
the `tools` argument and check each sub-tool slug. A batch containing
ANY destructive sub-tool requires confirmation for the whole batch.
"""

from typing import Any

#: Tool slugs that perform writes / sends / deletes / modifications.
#: Curated against the toolkits enabled in agents/tools.DEPARTMENT_TOOLKITS.
DESTRUCTIVE_SLUGS: frozenset[str] = frozenset({
    # ---------- Gmail ----------
    # Sends an email externally — irreversible.
    "GMAIL_SEND_EMAIL",
    "GMAIL_SEND_DRAFT",
    "GMAIL_REPLY_TO_THREAD",
    # Modifies mailbox state in ways another reader will see.
    "GMAIL_DELETE_MESSAGE",
    "GMAIL_DELETE_DRAFT",
    "GMAIL_TRASH_MESSAGE",
    "GMAIL_MODIFY_LABELS",
    # NOTE: GMAIL_CREATE_DRAFT is INTENTIONALLY NOT here — drafts are
    # private and the user reviews them in Gmail before sending.

    # ---------- Outlook ----------
    "OUTLOOK_SEND_EMAIL",
    "OUTLOOK_SEND_DRAFT",
    "OUTLOOK_REPLY_TO_THREAD",
    "OUTLOOK_DELETE_MESSAGE",
    "OUTLOOK_DELETE_DRAFT",
    "OUTLOOK_TRASH_MESSAGE",
    "OUTLOOK_CALENDAR_CREATE_EVENT",
    "OUTLOOK_CALENDAR_UPDATE_EVENT",
    "OUTLOOK_CALENDAR_DELETE_EVENT",
    "OUTLOOK_CALENDAR_PATCH_EVENT",

    # ---------- Google Calendar ----------
    "GOOGLECALENDAR_CREATE_EVENT",
    "GOOGLECALENDAR_QUICK_ADD",
    "GOOGLECALENDAR_UPDATE_EVENT",
    "GOOGLECALENDAR_DELETE_EVENT",
    "GOOGLECALENDAR_PATCH_EVENT",

    # ---------- Google Meet ----------
    "GOOGLEMEET_CREATE_MEETING",
    "GOOGLEMEET_END_MEETING",

    # ---------- Google Drive ----------
    "GOOGLEDRIVE_CREATE_FILE",
    "GOOGLEDRIVE_UPLOAD_FILE",
    "GOOGLEDRIVE_UPDATE_FILE",
    "GOOGLEDRIVE_COPY_FILE",
    "GOOGLEDRIVE_DELETE_FILE",
    "GOOGLEDRIVE_TRASH_FILE",
    "GOOGLEDRIVE_MOVE_FILE",
    "GOOGLEDRIVE_SHARE_FILE",         # changes permissions — high risk
    "GOOGLEDRIVE_CREATE_PERMISSION",  # same
    "GOOGLEDRIVE_DELETE_PERMISSION",
    "GOOGLEDRIVE_CREATE_FOLDER",

    # ---------- Google Sheets ----------
    "GOOGLESHEETS_BATCH_UPDATE",
    "GOOGLESHEETS_BATCH_UPDATE_VALUES_BY_DATA_FILTER",
    "GOOGLESHEETS_UPDATE_VALUES",
    "GOOGLESHEETS_APPEND_VALUES",
    "GOOGLESHEETS_CLEAR_VALUES",
    "GOOGLESHEETS_BATCH_CLEAR_VALUES",
    "GOOGLESHEETS_DELETE_SHEET",
    "GOOGLESHEETS_CREATE_SPREADSHEET",
    "GOOGLESHEETS_DUPLICATE_SHEET",

    # ---------- Google Docs ----------
    "GOOGLEDOCS_CREATE_DOCUMENT",
    "GOOGLEDOCS_CREATE_DOCUMENT_FROM_TEMPLATE",
    "GOOGLEDOCS_UPDATE_DOCUMENT",
    "GOOGLEDOCS_BATCH_UPDATE",

    # ---------- Google Slides ----------
    "GOOGLESLIDES_CREATE_PRESENTATION",
    "GOOGLESLIDES_BATCH_UPDATE",

    # ---------- HubSpot ----------
    "HUBSPOT_CREATE_CONTACT",
    "HUBSPOT_UPDATE_CONTACT",
    "HUBSPOT_DELETE_CONTACT",
    "HUBSPOT_CREATE_COMPANY",
    "HUBSPOT_UPDATE_COMPANY",
    "HUBSPOT_DELETE_COMPANY",
    "HUBSPOT_CREATE_DEAL",
    "HUBSPOT_UPDATE_DEAL",
    "HUBSPOT_DELETE_DEAL",
    "HUBSPOT_CREATE_TICKET",
    "HUBSPOT_UPDATE_TICKET",
    "HUBSPOT_DELETE_TICKET",
    "HUBSPOT_CREATE_ENGAGEMENT",
    "HUBSPOT_SEND_EMAIL",

    # ---------- GoHighLevel (Highlevel) ----------
    "HIGHLEVEL_CREATE_CONTACT",
    "HIGHLEVEL_UPDATE_CONTACT",
    "HIGHLEVEL_DELETE_CONTACT",
    "HIGHLEVEL_CREATE_OPPORTUNITY",
    "HIGHLEVEL_UPDATE_OPPORTUNITY",
    "HIGHLEVEL_DELETE_OPPORTUNITY",
    "HIGHLEVEL_CREATE_APPOINTMENT",
    "HIGHLEVEL_UPDATE_APPOINTMENT",
    "HIGHLEVEL_DELETE_APPOINTMENT",
    "HIGHLEVEL_CREATE_TASK",
    "HIGHLEVEL_UPDATE_TASK",
    "HIGHLEVEL_DELETE_TASK",
    "HIGHLEVEL_SEND_SMS",
    "HIGHLEVEL_SEND_EMAIL",

    # ---------- Microsoft 365 (OneDrive, SharePoint, Teams, Excel, OneNote) ----------
    "ONE_DRIVE_CREATE_FILE",
    "ONE_DRIVE_UPLOAD_FILE",
    "ONE_DRIVE_UPDATE_FILE",
    "ONE_DRIVE_DELETE_FILE",
    "ONE_DRIVE_CREATE_FOLDER",
    "ONE_DRIVE_DELETE_FOLDER",
    "ONE_DRIVE_SHARE_FILE",
    "SHARE_POINT_CREATE_FILE",
    "SHARE_POINT_UPLOAD_FILE",
    "SHARE_POINT_DELETE_FILE",
    "SHARE_POINT_CREATE_FOLDER",
    "SHARE_POINT_DELETE_FOLDER",
    "MICROSOFT_TEAMS_SEND_MESSAGE",
    "MICROSOFT_TEAMS_CREATE_CHANNEL",
    "MICROSOFT_TEAMS_DELETE_CHANNEL",
    "EXCEL_CREATE_WORKBOOK",
    "EXCEL_UPDATE_WORKSHEET",
    "EXCEL_APPEND_ROWS",
    "EXCEL_DELETE_WORKSHEET",
    "ONENOTE_CREATE_NOTEBOOK",
    "ONENOTE_CREATE_SECTION",
    "ONENOTE_CREATE_PAGE",
    "ONENOTE_UPDATE_PAGE",
    "ONENOTE_DELETE_PAGE",

    # ---------- Jira ----------
    "JIRA_CREATE_ISSUE",
    "JIRA_UPDATE_ISSUE",
    "JIRA_DELETE_ISSUE",
    "JIRA_TRANSITION_ISSUE",
    "JIRA_ASSIGN_ISSUE",
    "JIRA_CREATE_COMMENT",
    "JIRA_UPDATE_COMMENT",
    "JIRA_DELETE_COMMENT",

    # ---------- Zoom ----------
    "ZOOM_CREATE_MEETING",
    "ZOOM_UPDATE_MEETING",
    "ZOOM_DELETE_MEETING",
    "ZOOM_END_MEETING",
})


#: When the agent calls a slug we don't recognize (e.g. a new Composio
#: toolkit), do we treat it as safe-to-execute or as requiring
#: confirmation? "safe" is permissive; "confirm" is paranoid.
#: Default to "safe" because false-positive confirmation prompts annoy
#: users and most read-only tools are well-named (GET_*, LIST_*, etc.).
DEFAULT_BEHAVIOR_FOR_UNKNOWN: str = "safe"


#: Composio meta-tool slug that batches multiple tool calls into one
#: invocation. We must look inside its arguments to find sub-tools.
META_EXECUTE_SLUG = "COMPOSIO_MULTI_EXECUTE_TOOL"


def is_destructive(tool_slug: str) -> bool:
    """Single-tool check. Does NOT introspect COMPOSIO_MULTI_EXECUTE_TOOL.

    For the meta-tool, callers should also use extract_destructive_subtools
    to inspect its arguments before deciding.
    """
    return tool_slug.upper() in DESTRUCTIVE_SLUGS


def extract_destructive_subtools(meta_args: dict[str, Any]) -> list[dict[str, Any]]:
    """Inspect a COMPOSIO_MULTI_EXECUTE_TOOL argument payload and return
    the list of sub-tool entries that are destructive.

    Composio's meta-tool payload looks like:
        {"tools": [{"tool_slug": "GMAIL_SEND_EMAIL", "arguments": {...}}, ...]}

    Returns a list of {"tool_slug": str, "arguments": dict} for sub-tools
    that require confirmation. Empty list means the batch is read-safe
    and can execute without a prompt.
    """
    items = meta_args.get("tools")
    if not isinstance(items, list):
        return []

    destructive = []
    for item in items:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("tool_slug", "")).upper()
        if slug in DESTRUCTIVE_SLUGS:
            destructive.append({
                "tool_slug": slug,
                "arguments": item.get("arguments", {}) or {},
            })
    return destructive


def summarize_for_human(tool_slug: str, arguments: dict[str, Any]) -> str:
    """Produce a single-line human-readable summary of an action.

    Used as the body of the confirmation card. Keep it short — the agent
    can elaborate in the chat above. Falls back to the raw slug if we
    don't have a specific template.
    """
    slug = tool_slug.upper()
    args = arguments or {}

    if slug in ("GMAIL_SEND_EMAIL", "GMAIL_SEND_DRAFT", "OUTLOOK_SEND_EMAIL", "OUTLOOK_SEND_DRAFT"):
        to = _first(args, ("recipient_email", "to", "toRecipients", "to_email"))
        subject = _first(args, ("subject",), default="(no subject)")
        return f"Send email to {to or '?'} — subject: {subject}"

    if slug in ("GMAIL_REPLY_TO_THREAD", "OUTLOOK_REPLY_TO_THREAD"):
        thread = _first(args, ("thread_id", "threadId"), default="thread")
        return f"Reply in Outlook thread {thread}" if "OUTLOOK" in slug else f"Reply in Gmail thread {thread}"

    if slug.startswith("GMAIL_DELETE") or slug.startswith("GMAIL_TRASH") or slug.startswith("OUTLOOK_DELETE") or slug.startswith("OUTLOOK_TRASH"):
        msg = _first(args, ("message_id", "id", "messageId"), default="message")
        return f"{slug.replace('_', ' ').title()} ({msg})"

    if slug in ("GOOGLECALENDAR_CREATE_EVENT", "GOOGLECALENDAR_QUICK_ADD", "OUTLOOK_CALENDAR_CREATE_EVENT"):
        summary = _first(args, ("summary", "title", "text", "subject"), default="(untitled)")
        start = _first(args, ("start_datetime", "start", "start_time", "startDateTime"), default="")
        attendees = args.get("attendees") or args.get("attendee_emails") or args.get("attendees_emails") or []
        n = len(attendees) if isinstance(attendees, list) else 0
        return f"Create calendar event '{summary}' {start} ({n} attendees)" if n else f"Create calendar event '{summary}' {start}"

    if slug in ("GOOGLECALENDAR_UPDATE_EVENT", "OUTLOOK_CALENDAR_UPDATE_EVENT"):
        eid = _first(args, ("event_id", "id", "eventId"), default="event")
        return f"Update calendar event {eid}"

    if slug in ("GOOGLECALENDAR_DELETE_EVENT", "OUTLOOK_CALENDAR_DELETE_EVENT"):
        eid = _first(args, ("event_id", "id", "eventId"), default="event")
        return f"Delete calendar event {eid} (attendees will be notified)"

    if slug in ("GOOGLEDRIVE_DELETE_FILE", "ONE_DRIVE_DELETE_FILE", "SHARE_POINT_DELETE_FILE"):
        fid = _first(args, ("file_id", "id", "fileId"), default="file")
        return f"Delete file {fid} (permanent)"

    if slug in ("GOOGLEDRIVE_SHARE_FILE", "ONE_DRIVE_SHARE_FILE"):
        fid = _first(args, ("file_id", "id", "fileId"), default="file")
        emails = args.get("emails") or args.get("email_address") or "(see args)"
        return f"Share file {fid} with {emails}"

    if slug.startswith("GOOGLESHEETS_"):
        sid = _first(args, ("spreadsheet_id", "spreadsheetId", "id"), default="spreadsheet")
        return f"{slug.replace('_', ' ').title()} on {sid}"

    if slug.startswith("HUBSPOT_") or slug.startswith("HIGHLEVEL_"):
        return f"{slug.replace('_', ' ').title()} (CRM)"

    if slug.startswith("JIRA_"):
        key = _first(args, ("issue_key", "issueIdOrKey", "key"), default="")
        return f"{slug.replace('_', ' ').title()} {key}".strip()

    if slug.startswith("ZOOM_"):
        topic = _first(args, ("topic", "subject"), default="")
        return f"{slug.replace('_', ' ').title()} {topic}".strip()

    return slug.replace("_", " ").title()


def _first(d: dict[str, Any], keys: tuple, default: str = "") -> str:
    """Return first non-empty value among keys; coerce to string."""
    for k in keys:
        v = d.get(k)
        if v:
            return str(v)
    return default


def _first_key(d: dict[str, Any], keys: tuple) -> str:
    """Return the first key from `keys` that exists in d with a non-empty
    value, otherwise the first key in the tuple (so overrides have
    somewhere to write to even when the agent omitted it)."""
    for k in keys:
        if d.get(k):
            return k
    return keys[0]


def _field(
    label: str,
    value: str,
    arg_key: str,
    *,
    multiline: bool = False,
    editable: bool = True,
) -> dict[str, Any]:
    return {
        "label": label,
        "value": value,
        "arg_key": arg_key,
        "multiline": multiline,
        "editable": editable,
    }


# ---------------------------------------------------------------------------
# Full-detail payload — shown in the permission card so the user sees
# exactly what's being sent / changed before clicking Allow.
# ---------------------------------------------------------------------------

#: A single field in the rendered permission card.
#:   {"label": "Body", "value": "...", "arg_key": "body",
#:    "multiline": True, "editable": True}
#:
#:   arg_key  — the tool-argument key this field maps to. Used when the
#:              user edits the value: the frontend sends {arg_key:
#:              new_value} and the backend merges that into the stored
#:              tool_args before executing.
#:   editable — whether the frontend shows an input box. Identifier
#:              fields (file IDs, event IDs, spreadsheet IDs) are
#:              non-editable because changing them changes which object
#:              we touch, not what we send.
#:   multiline — render as <textarea> instead of <input>.
Field = dict[str, Any]


def build_full_action_details(tool_slug: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Return a structured payload of fields to render in the permission card.

    Output shape:
        {
            "tool_slug": "GMAIL_SEND_EMAIL",
            "fields": [
                {"label": "To",      "value": "..."},
                {"label": "Subject", "value": "..."},
                {"label": "Body",    "value": "...", "multiline": True},
            ],
        }

    Falls back to a generic raw-JSON dump for tools we don't have a
    specific template for — better than hiding the content entirely.
    """
    slug = tool_slug.upper()
    args = arguments or {}
    fields: list[Field] = []

    if slug in ("GMAIL_SEND_EMAIL", "GMAIL_SEND_DRAFT", "OUTLOOK_SEND_EMAIL", "OUTLOOK_SEND_DRAFT"):
        fields.append(_field("To", _first(args, ("recipient_email", "to", "to_email", "toRecipients")), _first_key(args, ("recipient_email", "to", "to_email", "toRecipients"))))
        cc_key = _first_key(args, ("cc", "cc_emails", "ccRecipients"))
        cc = _first(args, ("cc", "cc_emails", "ccRecipients"))
        if cc:
            fields.append(_field("Cc", cc, cc_key))
        bcc_key = _first_key(args, ("bcc", "bcc_emails", "bccRecipients"))
        bcc = _first(args, ("bcc", "bcc_emails", "bccRecipients"))
        if bcc:
            fields.append(_field("Bcc", bcc, bcc_key))
        fields.append(_field("Subject", _first(args, ("subject",), default="(no subject)"), "subject"))
        body_key = _first_key(args, ("body", "message_body", "html_body", "text_body", "content"))
        fields.append(_field("Body", _first(args, ("body", "message_body", "html_body", "text_body", "content"), default="(empty)"), body_key, multiline=True))

    elif slug in ("GMAIL_REPLY_TO_THREAD", "OUTLOOK_REPLY_TO_THREAD"):
        fields.append(_field("Thread", _first(args, ("thread_id", "threadId")), _first_key(args, ("thread_id", "threadId")), editable=False))
        body_key = _first_key(args, ("body", "message_body", "content"))
        fields.append(_field("Reply body", _first(args, ("body", "message_body", "content"), default="(empty)"), body_key, multiline=True))

    elif slug.startswith("GMAIL_DELETE") or slug.startswith("GMAIL_TRASH") or slug.startswith("OUTLOOK_DELETE") or slug.startswith("OUTLOOK_TRASH"):
        fields.append(_field("Message ID", _first(args, ("message_id", "id", "messageId")), _first_key(args, ("message_id", "id", "messageId")), editable=False))

    elif slug in ("GOOGLECALENDAR_CREATE_EVENT", "GOOGLECALENDAR_QUICK_ADD", "OUTLOOK_CALENDAR_CREATE_EVENT"):
        title_key = _first_key(args, ("summary", "title", "text", "subject"))
        fields.append(_field("Title", _first(args, ("summary", "title", "text", "subject"), default="(untitled)"), title_key))
        start = _first(args, ("start_datetime", "start", "start_time", "startDateTime"))
        if start:
            fields.append(_field("Starts", start, _first_key(args, ("start_datetime", "start", "start_time", "startDateTime"))))
        end = _first(args, ("end_datetime", "end", "end_time", "endDateTime"))
        if end:
            fields.append(_field("Ends", end, _first_key(args, ("end_datetime", "end", "end_time", "endDateTime"))))
        location = _first(args, ("location",))
        if location:
            fields.append(_field("Location", location, "location"))
        attendees = args.get("attendees") or args.get("attendee_emails") or args.get("attendees_emails") or []
        if isinstance(attendees, list) and attendees:
            emails = []
            for a in attendees:
                if isinstance(a, str):
                    emails.append(a)
                elif isinstance(a, dict):
                    emails.append(a.get("email", str(a)))
            attendees_key = "attendees" if args.get("attendees") else ("attendee_emails" if args.get("attendee_emails") else "attendees_emails")
            fields.append(_field("Attendees", ", ".join(emails), attendees_key))
        description = _first(args, ("description",))
        if description:
            fields.append(_field("Description", description, "description", multiline=True))

    elif slug in ("GOOGLECALENDAR_UPDATE_EVENT", "OUTLOOK_CALENDAR_UPDATE_EVENT"):
        fields.append(_field("Event ID", _first(args, ("event_id", "id", "eventId")), _first_key(args, ("event_id", "id", "eventId")), editable=False))
        for key, value in args.items():
            if key in ("event_id", "id", "eventId", "calendar_id", "calendarId"):
                continue
            fields.append(_field(
                key.replace("_", " ").title(),
                str(value),
                key,
                multiline=isinstance(value, str) and "\n" in value,
            ))

    elif slug == "GOOGLECALENDAR_DELETE_EVENT":
        fields.append(_field("Event ID", _first(args, ("event_id", "id")), _first_key(args, ("event_id", "id")), editable=False))
        fields.append(_field("Note", "Attendees will be notified of cancellation.", "_note", editable=False))

    elif slug in ("GOOGLEDRIVE_DELETE_FILE", "ONE_DRIVE_DELETE_FILE", "SHARE_POINT_DELETE_FILE"):
        fields.append(_field("File ID", _first(args, ("file_id", "id", "fileId")), _first_key(args, ("file_id", "id", "fileId")), editable=False))
        fields.append(_field("Warning", "This is permanent — file goes to trash and may be unrecoverable.", "_warning", editable=False))

    elif slug in ("GOOGLEDRIVE_SHARE_FILE", "ONE_DRIVE_SHARE_FILE"):
        fields.append(_field("File ID", _first(args, ("file_id", "id", "fileId")), _first_key(args, ("file_id", "id", "fileId")), editable=False))
        emails_key = _first_key(args, ("emails", "email_address", "email_addresses"))
        emails = args.get("emails") or args.get("email_address") or args.get("email_addresses")
        fields.append(_field("Share with", str(emails) if emails else "(see args)", emails_key))
        role = _first(args, ("role", "permission_role"))
        if role:
            fields.append(_field("Role", role, _first_key(args, ("role", "permission_role"))))

    elif slug.startswith("GOOGLEDRIVE_") or slug.startswith("ONE_DRIVE_") or slug.startswith("SHARE_POINT_"):
        for key, value in args.items():
            id_like = key in ("file_id", "id", "fileId", "folder_id", "folderId", "parent_id", "parentId")
            fields.append(_field(
                key.replace("_", " ").title(),
                str(value),
                key,
                multiline=isinstance(value, str) and len(str(value)) > 80,
                editable=not id_like,
            ))

    elif slug.startswith("GOOGLESHEETS_"):
        sid_key = _first_key(args, ("spreadsheet_id", "spreadsheetId", "id"))
        fields.append(_field("Spreadsheet", _first(args, ("spreadsheet_id", "spreadsheetId", "id")), sid_key, editable=False))
        rng = _first(args, ("range", "ranges"))
        if rng:
            fields.append(_field("Range", rng, _first_key(args, ("range", "ranges"))))
        values = args.get("values") or args.get("data")
        if values is not None:
            import json as _json
            values_key = "values" if args.get("values") is not None else "data"
            fields.append(_field("Values", _json.dumps(values, indent=2, default=str), values_key, multiline=True))

    elif slug.startswith("GOOGLEDOCS_"):
        for key, value in args.items():
            id_like = key in ("document_id", "id")
            fields.append(_field(
                key.replace("_", " ").title(),
                str(value),
                key,
                multiline=isinstance(value, str) and len(str(value)) > 80,
                editable=not id_like,
            ))

    elif slug.startswith("HUBSPOT_") or slug.startswith("HIGHLEVEL_"):
        for key, value in args.items():
            id_like = key in ("contact_id", "company_id", "deal_id", "ticket_id", "id", "contactId", "opportunityId", "appointmentId", "taskId")
            fields.append(_field(
                key.replace("_", " ").title(),
                str(value),
                key,
                multiline=isinstance(value, str) and len(str(value)) > 80,
                editable=not id_like,
            ))

    elif slug.startswith("JIRA_"):
        fields.append(_field("Project", _first(args, ("project_key", "project")), _first_key(args, ("project_key", "project"))))
        fields.append(_field("Summary", _first(args, ("summary", "title")), _first_key(args, ("summary", "title"))))
        description = _first(args, ("description",))
        if description:
            fields.append(_field("Description", description, "description", multiline=True))
        issuetype = _first(args, ("issue_type", "issuetype"))
        if issuetype:
            fields.append(_field("Type", issuetype, _first_key(args, ("issue_type", "issuetype"))))
        for key, value in args.items():
            if key in ("project_key", "project", "summary", "title", "description", "issue_type", "issuetype"):
                continue
            id_like = key in ("issue_key", "id", "issueIdOrKey")
            fields.append(_field(key.replace("_", " ").title(), str(value), key, editable=not id_like))

    elif slug.startswith("ZOOM_"):
        fields.append(_field("Topic", _first(args, ("topic", "subject")), _first_key(args, ("topic", "subject"))))
        when = _first(args, ("start_time", "when"))
        if when:
            fields.append(_field("Start", when, _first_key(args, ("start_time", "when"))))
        duration = _first(args, ("duration", "duration_minutes"))
        if duration:
            fields.append(_field("Duration", f"{duration} min", _first_key(args, ("duration", "duration_minutes"))))
        invitees = args.get("invitees") or args.get("attendees")
        if invitees:
            fields.append(_field("Invitees", str(invitees), "invitees" if args.get("invitees") else "attendees"))

    if not fields:
        import json as _json
        fields.append(_field("Arguments", _json.dumps(args, indent=2, default=str), "_raw", multiline=True, editable=False))

    fields = [f for f in fields if f.get("value")]
    return {"tool_slug": slug, "fields": fields}


def apply_overrides(arguments: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Merge user-edited field values back into the tool argument dict.

    Special-cases:
    - Comma-separated string for list-of-strings args (Attendees, Cc, Bcc):
      coerced back to list[str].
    - JSON-formatted "Values" field for Sheets: parsed back to native shape.
    - Underscore-prefixed pseudo keys ("_note", "_warning", "_raw") are
      skipped because they aren't real tool args.
    """
    import json as _json

    merged = dict(arguments)
    list_keys = {"attendees", "attendee_emails", "cc", "bcc", "cc_emails", "bcc_emails",
                 "emails", "email_addresses", "invitees"}
    json_keys = {"values", "data"}

    for key, raw in overrides.items():
        if not key or key.startswith("_"):
            continue
        if key in list_keys and isinstance(raw, str):
            # Split on commas / newlines; trim whitespace; drop empties
            parts = [p.strip() for p in raw.replace("\n", ",").split(",") if p.strip()]
            merged[key] = parts
        elif key in json_keys and isinstance(raw, str):
            try:
                merged[key] = _json.loads(raw)
            except _json.JSONDecodeError:
                # If user broke the JSON, fall back to raw string so the
                # tool gives a clear error instead of silently swallowing.
                merged[key] = raw
        else:
            merged[key] = raw

    return merged


def build_batch_details(destructive_subs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """For COMPOSIO_MULTI_EXECUTE_TOOL: one details payload per destructive
    sub-tool, in the order the agent intended to execute them."""
    return [
        build_full_action_details(s["tool_slug"], s.get("arguments", {}))
        for s in destructive_subs
    ]
