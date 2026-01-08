import os
from datetime import datetime
from typing import Callable, Literal, Optional, Type

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel
from supabase import create_client, Client
from dotenv import load_dotenv

# Cargar variables de entorno (para seguridad)
load_dotenv()

app = FastAPI()

# Configuración de Supabase
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

# Configuración de xAI
XAI_API_KEY = os.environ.get("XAI_API_KEY")
XAI_BASE_URL = os.environ.get("XAI_BASE_URL", "https://api.x.ai/v1")


def get_grok_client() -> OpenAI:
    if not XAI_API_KEY:
        raise HTTPException(status_code=500, detail="XAI_API_KEY is not set")
    return OpenAI(base_url=XAI_BASE_URL, api_key=XAI_API_KEY)


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


def create_customer_ticket(request: CreateCustomerTicketRequest) -> str:
    # In practice, you'd save this to your DB or CRM
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

EXECUTABLES: dict[str, Callable] = {
    "create_customer_ticket": create_customer_ticket,
    "analyze_receipt_image": analyze_receipt_image,
}

ARGUMENTS: dict[str, Type[BaseModel]] = {
    "create_customer_ticket": CreateCustomerTicketRequest,
    "analyze_receipt_image": AnalyzeReceiptImageRequest,
}

@app.get("/")
def read_root():
    return {"mensaje": "Backend funcionando correctamente"}

# Ejemplo: Obtener datos de una tabla llamada 'usuarios'
@app.get("/usuarios")
def get_users():
    # Equivalente a SELECT * FROM usuarios
    response = supabase.table("usuarios").select("*").execute()
    return response.data

# Ejemplo: Insertar datos
@app.post("/usuarios")
def create_user(nombre: str, email: str):
    data = {"nombre": nombre, "email": email}
    response = supabase.table("usuarios").insert(data).execute()
    return response.data


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    grok_client = get_grok_client()
    messages = [message.model_dump(exclude_none=True) for message in request.messages]
    if request.system_prompt:
        messages = [{"role": "system", "content": request.system_prompt}] + messages

    completion = grok_client.chat.completions.create(
        model=request.model,
        messages=messages,
    )
    assistant = completion.choices[0].message.content or ""
    messages.append({"role": "assistant", "content": assistant})
    return ChatResponse(assistant=assistant, messages=messages)


@app.post("/chat/stream")
def chat_stream(request: ChatRequest):
    grok_client = get_grok_client()
    messages = [message.model_dump(exclude_none=True) for message in request.messages]
    if request.system_prompt:
        messages = [{"role": "system", "content": request.system_prompt}] + messages

    stream = grok_client.chat.completions.create(
        model=request.model,
        messages=messages,
        stream=True,
    )

    def generate():
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    return StreamingResponse(generate(), media_type="text/plain")


@app.post("/chat/tools", response_model=ChatResponse)
def chat_with_tools(request: ChatRequest):
    grok_client = get_grok_client()
    messages = [message.model_dump(exclude_none=True) for message in request.messages]
    if request.system_prompt:
        messages = [{"role": "system", "content": request.system_prompt}] + messages

    completion = grok_client.chat.completions.create(
        model=request.model,
        messages=messages,
        tools=TOOLS,
    )

    assistant_message = completion.choices[0].message
    assistant_content = assistant_message.content or ""
    tool_calls = assistant_message.tool_calls or []
    messages.append(
        {
            "role": "assistant",
            "content": assistant_content,
            "tool_calls": [tool_call.model_dump() for tool_call in tool_calls]
            if tool_calls
            else None,
        }
    )

    for tool_call in tool_calls:
        tool_name = tool_call.function.name
        tool_args_json = tool_call.function.arguments
        tool_schema = ARGUMENTS[tool_name]
        tool_args = tool_schema.model_validate_json(tool_args_json)
        tool_result = EXECUTABLES[tool_name](tool_args)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            }
        )

    if tool_calls:
        followup = grok_client.chat.completions.create(
            model=request.model,
            messages=messages,
            tools=TOOLS,
        )
        followup_content = followup.choices[0].message.content or ""
        messages.append({"role": "assistant", "content": followup_content})
        return ChatResponse(assistant=followup_content, messages=messages)

    return ChatResponse(assistant=assistant_content, messages=messages)
