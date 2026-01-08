from datetime import datetime
from typing import Callable, Literal, Optional, Type

from pydantic import BaseModel


class ChatMessageInput(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: Optional[str] = None


class ChatRequest(BaseModel):
    messages: list[ChatMessageInput]
    model: str = "grok-4"
    system_prompt: Optional[str] = None


class ChatResponse(BaseModel):
    assistant: str
    messages: list[dict]


class CreateCustomerTicketRequest(BaseModel):
    name: str
    issue: str


class AnalyzeReceiptImageRequest(BaseModel):
    image_url: str


class Item(BaseModel):
    name: str
    quantity: int
    price_in_cents: int


class AnalyzeReceiptImageResponse(BaseModel):
    date: datetime
    items: list[Item]
    currency: str
    total_in_cents: int


ToolExecutables = dict[str, Callable]
ToolArguments = dict[str, Type[BaseModel]]
