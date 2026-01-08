from fastapi import HTTPException
from openai import OpenAI

from app.core.config import settings
from app.chat.schemas import (
    AnalyzeReceiptImageRequest,
    AnalyzeReceiptImageResponse,
    CreateCustomerTicketRequest,
)


def get_grok_client() -> OpenAI:
    if not settings.xai_api_key:
        raise HTTPException(status_code=500, detail="XAI_API_KEY is not set")
    return OpenAI(base_url=settings.xai_base_url, api_key=settings.xai_api_key)


def create_customer_ticket(request: CreateCustomerTicketRequest) -> str:
    return (
        f"Created customer ticket for {request.name} "
        f"with issue {request.issue}"
    )


def analyze_receipt_image(request: AnalyzeReceiptImageRequest) -> str:
    grok_client = get_grok_client()
    response = grok_client.beta.chat.completions.parse(
        model="grok-2-vision-latest",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": request.image_url,
                            "detail": "high",
                        },
                    },
                    {
                        "type": "text",
                        "text": "Please extract the date and items and subtotal from the receipt",
                    },
                ],
            }
        ],
        response_format=AnalyzeReceiptImageResponse,
    )
    receipt_data = response.choices[0].message.parsed
    if not receipt_data:
        raise HTTPException(
            status_code=500, detail="Failed to extract details from image"
        )
    return receipt_data.model_dump_json(indent=2)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_customer_ticket",
            "description": "Create a customer ticket",
            "parameters": CreateCustomerTicketRequest.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_receipt_image",
            "description": "Analyze a receipt image and return the date, items, and subtotal",
            "parameters": AnalyzeReceiptImageRequest.model_json_schema(),
        },
    },
]
