"""Session summary service — auto-generates rolling summaries every 10 messages.

The summary provides long-term context when a user returns to a session,
so the agent knows what was previously discussed without loading all messages.
"""

import logging

from openai import OpenAI
from sqlalchemy.orm import Session as DBSession

from agents.config import OPENROUTER_API_KEY, LLM_MODEL
from db.models import ChatSession, ChatMessage

logger = logging.getLogger(__name__)

SUMMARY_THRESHOLD = 10  # Generate/update summary every N new messages


def should_update_summary(current_count: int, last_summary_count: int) -> bool:
    """Check if we should generate/update the session summary."""
    return (current_count - last_summary_count) >= SUMMARY_THRESHOLD


async def update_session_summary(db: DBSession, session_id: str) -> None:
    """Generate or update the rolling session summary if threshold is met.

    Called after each assistant response. Checks if enough new messages
    have accumulated since the last summary, and if so, asks Gemini to
    generate a concise summary of the full conversation.
    """
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        return

    # Count messages in session
    msg_count = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).count()

    if not should_update_summary(msg_count, session.summary_msg_count or 0):
        return

    # Fetch all messages for summarization
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
        .all()
    )

    # Format conversation for summarization
    conversation_text = "\n".join(
        f"{m.role}: {m.content[:500]}" for m in messages
    )

    try:
        client = OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Summarize this conversation in 3-5 sentences. "
                        "Focus on: what the user is working on, key decisions made, "
                        "and pending action items.\n\n"
                        f"{conversation_text[:8000]}"
                    ),
                }
            ],
            temperature=0.7,
        )
        summary_text = response.choices[0].message.content

        session.session_summary = summary_text
        session.summary_msg_count = msg_count
        db.commit()
        logger.info(f"Updated session summary for {session_id} (msgs={msg_count})")

    except Exception as e:
        logger.warning(f"Failed to generate session summary: {e}")
