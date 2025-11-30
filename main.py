import os
import uvicorn
from fastapi import FastAPI, Request, Response
from telegram import Update
from bot import main_bot

# --- Configuração ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
# A URL do seu site no Render/Heroku (sem a barra no final)
# Exemplo: https://meu-bot.onrender.com
WEBHOOK_URL_BASE = os.environ.get("RENDER_EXTERNAL_URL") 

if not BOT_TOKEN:
    raise ValueError("A variável de ambiente BOT_TOKEN não está definida.")

# Cria a aplicação do bot mas NÃO inicia ainda
application = main_bot(BOT_TOKEN)

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    """Inicializa o bot e define o webhook."""
    print("Inicializando aplicação do Bot...")
    # 1. Inicializa a aplicação (CRUCIAL para PTB v20+)
    await application.initialize()
    await application.start()
    
    # 2. Define o Webhook automaticamente se estivermos em produção
    if WEBHOOK_URL_BASE:
        webhook_path = f"/webhook/{BOT_TOKEN}"
        full_url = f"{WEBHOOK_URL_BASE}{webhook_path}"
        print(f"Definindo webhook para: {full_url}")
        
        await application.bot.set_webhook(url=full_url)
    else:
        print("AVISO: RENDER_EXTERNAL_URL não definida. O Webhook não foi configurado automaticamente.")

@app.on_event("shutdown")
async def shutdown_event():
    """Para o bot corretamente ao desligar o servidor."""
    await application.stop()
    await application.shutdown()

@app.post(f"/webhook/{BOT_TOKEN}")
async def telegram_webhook(request: Request):
    """Endpoint para receber as atualizações do Telegram."""
    try:
        update_json = await request.json()
        update = Update.de_json(update_json, application.bot)
        
        # Processa a atualização
        await application.process_update(update)
        
        return Response(status_code=200)
    except Exception as e:
        print(f"Erro no webhook: {e}")
        return Response(status_code=200)

@app.get("/")
async def root():
    return {"status": "ok", "bot": "Idle War Bot Online"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
