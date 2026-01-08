from fastapi import FastAPI

from app.chat.router import router as chat_router
from app.core.supabase import get_supabase_client
from app.whatsapp.outbound_router import router as whatsapp_outbound_router
from app.whatsapp.process_router import router as whatsapp_process_router
from app.whatsapp.webhook import router as whatsapp_router

app = FastAPI()

app.include_router(chat_router)
app.include_router(whatsapp_router)
app.include_router(whatsapp_outbound_router)
app.include_router(whatsapp_process_router)


@app.get("/")
def read_root():
    return {"mensaje": "Backend funcionando correctamente"}


@app.get("/usuarios")
def get_users():
    supabase = get_supabase_client()
    response = supabase.table("usuarios").select("*").execute()
    data = response.get("data") if isinstance(response, dict) else response.data
    return data


@app.post("/usuarios")
def create_user(nombre: str, email: str):
    supabase = get_supabase_client()
    data = {"nombre": nombre, "email": email}
    response = supabase.table("usuarios").insert(data).execute()
    return response.get("data") if isinstance(response, dict) else response.data
