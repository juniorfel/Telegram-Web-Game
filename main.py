import os
import uvicorn
from fastapi import FastAPI, Request, Response
from telegram import Update
from bot import main_bot

# --- Configuração ---
# O token do bot deve ser lido de uma variável de ambiente por segurança
BOT_TOKEN = os.environ.get("BOT_TOKEN") 

# Se o token não estiver definido, o bot não pode rodar
if not BOT_TOKEN:
    # Em um ambiente de produção como o Render, isso irá falhar o deploy, o que é o desejado.
    raise ValueError("A variável de ambiente BOT_TOKEN não está definida.")

# O caminho do webhook deve incluir o token para segurança
WEBHOOK_URL_PATH = f"/webhook/{BOT_TOKEN}"

# Inicializa a aplicação do bot
application = main_bot(BOT_TOKEN)

# Inicializa a aplicação FastAPI
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    """Configura o webhook ao iniciar o servidor."""
    # O URL base será fornecido pelo Render (ou outro serviço de hospedagem)
    print("Aplicação FastAPI iniciada. Webhook configurado para o caminho:", WEBHOOK_URL_PATH)

@app.post(WEBHOOK_URL_PATH)
async def telegram_webhook(request: Request):
    """Endpoint para receber as atualizações do Telegram."""
    try:
        # Recebe o corpo da requisição como JSON
        update_json = await request.json()
        
        # Cria um objeto Update do telegram-bot-python
        update = Update.de_json(update_json, application.bot)
        
        # Processa a atualização de forma síncrona no contexto assíncrono
        # Isso garante que a resposta seja enviada antes do 200 OK
        await application.process_update(update)
        
        return Response(status_code=200)
    except Exception as e:
        print(f"Erro ao processar atualização: {e}")
        # Retorna 200 OK para evitar que o Telegram reenvie a mensagem
        return Response(status_code=200) 

@app.get("/")
async def root():
    """Endpoint de saúde para verificar se o servidor está ativo."""
    return {"status": "ok", "message": "Idle War Bot está online e aguardando webhooks."}

if __name__ == "__main__":
    # Comando para rodar localmente (para testes)
    uvicorn.run(app, host="0.0.0.0", port=8000)
