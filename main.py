import os
import uvicorn
from fastapi import FastAPI, Request, Response
from telegram import Update
from bot import main_bot

# --- Variáveis de Ambiente ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL_BASE = os.environ.get("RENDER_EXTERNAL_URL")
PORT = int(os.environ.get("PORT", 10000))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN não definido!")

app = FastAPI()
application = main_bot(BOT_TOKEN)

@app.on_event("startup")
async def startup_event():
    print("Iniciando Bot...")
    await application.initialize()
    await application.start()
    
    if WEBHOOK_URL_BASE:
        url = WEBHOOK_URL_BASE.rstrip('/') + f"/webhook/{BOT_TOKEN}"
        print(f"Setando Webhook para: {url}")
        await application.bot.set_webhook(url=url)

@app.on_event("shutdown")
async def shutdown_event():
    await application.stop()
    await application.shutdown()

@app.post(f"/webhook/{BOT_TOKEN}")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    except Exception as e:
        print(f"Erro: {e}")
    return Response(status_code=200)

@app.get("/")
async def health():
    return {"status": "Idle War Bot Online!"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
