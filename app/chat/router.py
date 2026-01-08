from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.chat.schemas import (
    AnalyzeReceiptImageRequest,
    ChatRequest,
    ChatResponse,
    CreateCustomerTicketRequest,
)
from app.chat.service import (
    TOOLS,
    analyze_receipt_image,
    create_customer_ticket,
    get_grok_client,
)

router = APIRouter(prefix="/chat", tags=["chat"])

EXECUTABLES = {
    "create_customer_ticket": create_customer_ticket,
    "analyze_receipt_image": analyze_receipt_image,
}

ARGUMENTS = {
    "create_customer_ticket": CreateCustomerTicketRequest,
    "analyze_receipt_image": AnalyzeReceiptImageRequest,
}


@router.post("", response_model=ChatResponse)
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


@router.post("/stream")
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


@router.post("/tools", response_model=ChatResponse)
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
