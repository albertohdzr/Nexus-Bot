from datetime import datetime
from typing import Any, Dict, Optional

from app.core.supabase import (
    get_supabase_client,
    get_supabase_data,
    get_supabase_error,
)


def normalize_language(value: Optional[str]) -> str:
    if not value:
        return ""
    cleaned = value.replace("-", "_")
    parts = cleaned.split("_")
    if len(parts) == 2:
        return f"{parts[0].lower()}_{parts[1].upper()}"
    return cleaned


def is_template_change_field(field: Optional[str]) -> bool:
    return field in {
        "message_template_status_update",
        "message_template_quality_update",
        "message_template_components_update",
    }


def build_components_from_template_update(value: Dict[str, Any]) -> list[Dict[str, Any]]:
    components: list[Dict[str, Any]] = []
    header_text = value.get("message_template_title")
    body_text = value.get("message_template_element")
    footer_text = value.get("message_template_footer")

    if isinstance(header_text, str) and header_text.strip():
        components.append({
            "type": "HEADER",
            "format": "TEXT",
            "text": header_text,
        })

    if isinstance(body_text, str) and body_text.strip():
        components.append({
            "type": "BODY",
            "text": body_text,
        })

    if isinstance(footer_text, str) and footer_text.strip():
        components.append({
            "type": "FOOTER",
            "text": footer_text,
        })

    buttons_value = value.get("message_template_buttons")
    if isinstance(buttons_value, list) and buttons_value:
        buttons = []
        for button in buttons_value:
            if not isinstance(button, dict):
                continue
            button_type = str(
                button.get("message_template_button_type", "")
            ).upper()
            button_text = str(button.get("message_template_button_text", ""))
            if button_type == "URL":
                buttons.append({
                    "type": "URL",
                    "text": button_text,
                    "url": button.get("message_template_button_url"),
                })
            elif button_type == "PHONE_NUMBER":
                buttons.append({
                    "type": "PHONE_NUMBER",
                    "text": button_text,
                    "phone_number": button.get(
                        "message_template_button_phone_number"
                    ),
                })
            else:
                buttons.append({
                    "type": "QUICK_REPLY",
                    "text": button_text,
                })
        components.append({
            "type": "BUTTONS",
            "buttons": buttons,
        })

    return components


def handle_template_updates(
    entry_id: Optional[str],
    entry_time: Optional[int],
    change: Dict[str, Any],
) -> None:
    if not is_template_change_field(change.get("field")):
        return

    value = change.get("value")
    if not isinstance(value, dict):
        return

    waba_id = str(entry_id or "")
    if not waba_id:
        print("Missing WABA id for template update")
        return

    supabase = get_supabase_client()
    org_response = (
        supabase.from_("organizations")
        .select("id")
        .eq("whatsapp_business_account_id", waba_id)
        .single()
        .execute()
    )
    org_error = get_supabase_error(org_response)
    org_data = get_supabase_data(org_response)

    if org_error or not org_data:
        print("Organization not found for WABA id:", waba_id)
        return

    external_id = (
        str(value.get("message_template_id"))
        if value.get("message_template_id") is not None
        else None
    )
    template_name = (
        value.get("message_template_name")
        if isinstance(value.get("message_template_name"), str)
        else None
    )
    template_language = normalize_language(
        value.get("message_template_language")
        if isinstance(value.get("message_template_language"), str)
        else None
    )

    template_id: Optional[str] = None

    if external_id:
        template_response = (
            supabase.from_("whatsapp_templates")
            .select("id")
            .eq("organization_id", org_data["id"])
            .eq("external_id", external_id)
            .maybe_single()
            .execute()
        )
        template_data = get_supabase_data(template_response)
        template_id = template_data.get("id") if template_data else None

    if not template_id and template_name:
        template_matches_response = (
            supabase.from_("whatsapp_templates")
            .select("id, language")
            .eq("organization_id", org_data["id"])
            .eq("name", template_name)
            .execute()
        )
        template_matches = get_supabase_data(template_matches_response) or []
        matched = None
        for row in template_matches:
            row_language = normalize_language(row.get("language"))
            if template_language and row_language == template_language:
                matched = row
                break
        template_id = matched.get("id") if matched else None

    if not template_id:
        print(
            "Template not found for webhook update",
            {
                "externalId": external_id,
                "templateName": template_name,
                "templateLanguage": template_language,
            },
        )
        return

    event_timestamp = (
        datetime.fromtimestamp(entry_time).isoformat()
        if entry_time
        else datetime.utcnow().isoformat()
    )

    update_data: Dict[str, Any] = {
        "updated_at": datetime.utcnow().isoformat(),
        "last_meta_event": change,
        "meta_updated_at": event_timestamp,
    }

    if external_id:
        update_data["external_id"] = external_id
    if template_name:
        update_data["name"] = template_name
    if template_language:
        update_data["language"] = template_language

    field = change.get("field")
    if field == "message_template_status_update":
        status_value = str(value.get("event") or "PENDING")
        update_data["status"] = status_value.lower()
        if value.get("message_template_category"):
            update_data["category"] = str(
                value.get("message_template_category")
            ).upper()

    if field == "message_template_quality_update":
        if value.get("new_quality_score"):
            update_data["quality_score"] = str(
                value.get("new_quality_score")
            ).upper()

    if field == "message_template_components_update":
        components = build_components_from_template_update(value)
        if components:
            update_data["components"] = components

    update_response = (
        supabase.from_("whatsapp_templates")
        .update(update_data)
        .eq("id", template_id)
        .eq("organization_id", org_data["id"])
        .execute()
    )

    update_error = get_supabase_error(update_response)
    if update_error:
        print("Error updating template from webhook:", update_error)
