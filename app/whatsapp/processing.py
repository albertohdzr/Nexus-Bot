from datetime import datetime
import time
from typing import Any, Dict, Optional, Set

from app.core.config import settings
from app.core.supabase import (
    get_supabase_client,
    get_supabase_data,
    get_supabase_error,
)
from app.whatsapp.media import MediaDownloadError, download_whatsapp_media
from app.whatsapp.storage import upload_to_storage


def _get_public_media_url(path: str) -> Optional[str]:
    supabase = get_supabase_client()
    bucket = settings.supabase_storage_bucket
    response = supabase.storage.from_(bucket).get_public_url(path)
    if isinstance(response, dict):
        return response.get("publicURL") or response.get("publicUrl")
    if hasattr(response, "get"):
        try:
            return response.get("publicURL") or response.get("publicUrl")
        except Exception:
            return None
    return None


def handle_incoming_messages(value: Dict[str, Any]) -> None:
    print("[whatsapp] webhook payload received")
    messages = list(value.get("messages") or [])
    if not messages:
        print("[whatsapp] no messages in payload")
        return

    contact = value.get("contacts", [None])[0]
    metadata = value.get("metadata") or {}
    phone_number = metadata.get("display_phone_number")
    phone_number_id = metadata.get("phone_number_id")
    print(
        "[whatsapp] metadata",
        {"phone_number": phone_number, "phone_number_id": phone_number_id},
    )

    supabase = get_supabase_client()
    org_response = (
        supabase.from_("organizations")
        .select("id, name")
        .eq("phone_number_id", phone_number_id)
        .limit(1)
        .execute()
    )
    org_error = get_supabase_error(org_response)
    org_rows = get_supabase_data(org_response) or []
    org_data = org_rows[0] if org_rows else None

    if org_error or not org_data:
        print("Organization not found for phone_number_id:", phone_number_id)
        return
    print("[whatsapp] org resolved", {"org_id": org_data.get("id")})

    ordered_messages = sorted(
        messages,
        key=lambda item: int(item.get("timestamp") or 0),
    )

    chats_to_process: Set[str] = set()

    for message in ordered_messages:
        wa_id = None
        if contact and isinstance(contact, dict):
            wa_id = contact.get("wa_id")
        wa_id = wa_id or message.get("from") or ""
        name = None
        if contact and isinstance(contact, dict):
            profile = contact.get("profile") or {}
            name = profile.get("name")
        name = name or wa_id

        if not wa_id:
            print("Missing waId in incoming message")
            continue
        print("[whatsapp] incoming message", {"wa_id": wa_id, "type": message.get("type")})

        upsert_response = (
            supabase.from_("chats")
            .upsert(
                {
                    "wa_id": wa_id,
                    "name": name,
                    "phone_number": phone_number,
                    "organization_id": org_data["id"],
                    "updated_at": datetime.utcnow().isoformat(),
                },
                on_conflict="wa_id,organization_id",
            )
            .execute()
        )
        upsert_error = get_supabase_error(upsert_response)
        if upsert_error:
            print("Error upserting chat:", upsert_error)
            continue

        chat_response = (
            supabase.from_("chats")
            .select("*")
            .eq("wa_id", wa_id)
            .eq("organization_id", org_data["id"])
            .limit(1)
            .execute()
        )
        chat_error = get_supabase_error(chat_response)
        chat_rows = get_supabase_data(chat_response) or []
        chat_data = chat_rows[0] if chat_rows else None

        if chat_error or not chat_data:
            print("Error fetching chat after upsert:", chat_error)
            continue

        chat_id = chat_data.get("id")
        if not chat_id:
            print("Missing chat id after upsert")
            continue
        print("[whatsapp] chat resolved", {"chat_id": chat_id})

        media_url: Optional[str] = None
        media_path: Optional[str] = None

        is_image = message.get("type") == "image" and message.get("image", {}).get(
            "id"
        )
        is_document = message.get("type") == "document" and message.get(
            "document", {}
        ).get("id")
        is_audio = message.get("type") == "audio" and message.get("audio", {}).get(
            "id"
        )

        media_id = None
        media_mime = None
        media_file_name = None
        media_caption = None

        if is_image:
            media_id = message.get("image", {}).get("id")
            media_mime = message.get("image", {}).get("mime_type")
            media_caption = message.get("image", {}).get("caption")
        elif is_document:
            media_id = message.get("document", {}).get("id")
            media_mime = message.get("document", {}).get("mime_type")
            media_file_name = message.get("document", {}).get("filename")
        elif is_audio:
            media_id = message.get("audio", {}).get("id")
            media_mime = message.get("audio", {}).get("mime_type")

        if media_id:
            try:
                file_bytes, mime_type = download_whatsapp_media(media_id)
                if file_bytes:
                    storage_path = f"chats/{chat_id}/{media_id}-{media_file_name or 'file'}"
                    stored_path, storage_error = upload_to_storage(
                        file_bytes=file_bytes,
                        path=storage_path,
                        content_type=mime_type or media_mime,
                    )
                    if storage_error:
                        print(
                            "Storage upload error (inbound media):",
                            storage_error,
                        )
                    else:
                        media_path = stored_path or storage_path
                        media_url = _get_public_media_url(media_path) or media_path
            except MediaDownloadError as exc:
                print("Error downloading/uploading inbound media:", exc)

        message_body = (
            (message.get("text") or {}).get("body")
            or media_caption
            or media_file_name
            or ("Mensaje de voz" if message.get("audio") else None)
            or "[Media/Other]"
        )

        message_id = message.get("id")
        if message_id:
            existing_response = (
                supabase.from_("messages")
                .select("id")
                .eq("wa_message_id", message_id)
                .maybe_single()
                .execute()
            )
            existing_error = get_supabase_error(existing_response)
            existing_data = get_supabase_data(existing_response)

            if existing_error:
                print(
                    "Error checking duplicate message:",
                    {"messageId": message_id, "error": existing_error},
                )

            if existing_data:
                print("Skipping duplicate message", {"messageId": message_id})
                continue

        message_timestamp_ms = (
            int(message.get("timestamp")) * 1000
            if message.get("timestamp")
            else int(datetime.utcnow().timestamp() * 1000)
        )
        message_timestamp_iso = datetime.fromtimestamp(
            message_timestamp_ms / 1000
        ).isoformat()

        message_insert = (
            supabase.from_("messages")
            .insert(
                {
                    "chat_id": chat_id,
                    "chat_session_id": None,
                    "wa_message_id": message_id,
                    "body": message_body,
                    "type": message.get("type"),
                    "status": "received",
                    "direction": "inbound",
                    "role": "user",
                    "payload": {
                        **message,
                        "media_id": media_id,
                        "media_mime_type": media_mime,
                        "media_file_name": media_file_name,
                        "media_caption": media_caption,
                        "voice": (message.get("audio") or {}).get("voice"),
                        "conversation_id": None,
                    },
                    "wa_timestamp": message_timestamp_iso,
                    "sender_name": name,
                    "media_id": media_id,
                    "media_path": media_path,
                    "media_url": media_url,
                    "media_mime_type": media_mime,
                    "created_at": message_timestamp_iso,
                }
            )
            .execute()
        )

        message_error = get_supabase_error(message_insert)
        if message_error:
            print("Error inserting message:", message_error)
            continue
        print("[whatsapp] message stored", {"wa_message_id": message_id})

        queue_response = supabase.rpc(
            "accumulate_whatsapp_message",
            {
                "p_chat_id": chat_id,
                "p_new_text": message_body or "",
            },
        ).execute()
        queue_error = get_supabase_error(queue_response)

        if queue_error:
            print("Error accumulating message queue:", queue_error)
        else:
            print("[whatsapp] message queued", {"chat_id": chat_id})
            chats_to_process.add(chat_id)

    for chat_id in chats_to_process:
        try:
            start = time.time()
            print("[whatsapp] invoking process-whatsapp-queue", {"chat_id": chat_id})
            invoke_response = supabase.functions.invoke(
                "process-whatsapp-queue",
                {"body": {"chat_id": chat_id}},
            )
            elapsed = round((time.time() - start) * 1000)
            invoke_error = get_supabase_error(invoke_response)
            if invoke_error:
                print(
                    "[whatsapp] process-whatsapp-queue error",
                    {"chat_id": chat_id, "error": invoke_error},
                )
            else:
                print(
                    "[whatsapp] process-whatsapp-queue ok",
                    {"chat_id": chat_id, "elapsed_ms": elapsed},
                )
        except Exception as exc:
            print(
                "[whatsapp] process-whatsapp-queue exception",
                {"chat_id": chat_id, "error": str(exc)},
            )
