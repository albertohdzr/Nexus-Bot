from datetime import datetime
from typing import Any, Dict

from app.core.supabase import get_supabase_client, get_supabase_error


def handle_status_updates(value: Dict[str, Any]) -> None:
    statuses = value.get("statuses") or []
    if not statuses:
        return

    supabase = get_supabase_client()

    for status in statuses:
        message_id = status.get("id")
        if not message_id:
            continue

        next_status = status.get("status")
        status_timestamp = status.get("timestamp")
        if status_timestamp:
            status_timestamp = datetime.fromtimestamp(
                int(status_timestamp)
            ).isoformat()
        else:
            status_timestamp = datetime.utcnow().isoformat()

        updates: Dict[str, Any] = {
            "status": next_status,
            "payload": {"status_detail": status},
        }

        if next_status == "sent":
            updates["sent_at"] = status_timestamp
        if next_status == "delivered":
            updates["delivered_at"] = status_timestamp
        if next_status == "read":
            updates["read_at"] = status_timestamp

        result = supabase.from_("messages").update(updates).eq(
            "wa_message_id", message_id
        ).execute()

        error = get_supabase_error(result)
        if error:
            print(
                "Error updating message status:",
                error,
                {"messageId": message_id, "nextStatus": next_status},
            )
        else:
            print(
                "Updated message status",
                {
                    "messageId": message_id,
                    "nextStatus": next_status,
                    "statusTimestamp": status_timestamp,
                },
            )
