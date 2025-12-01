from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from database import init_db

# Importando as funções dos módulos que criamos
from gameplay import (
    start, 
    receive_text_input, 
    handle_class_selection, 
    confirm_name_handler, 
    handle_menu
)
from admin import (
    admin_cheat, 
    admin_ban, 
    admin_delete, 
    admin_give, 
    admin_promote, 
    admin_demote
)

def main_bot(token: str) -> Application:
    """
    Função principal que configura e retorna a aplicação do bot.
    """
    # 1. Inicializa o Banco de Dados (Cria tabelas e roda migrações)
    init_db()
    
    # 2. Constrói a Aplicação
    app = Application.builder().token(token).build()
    
    # --- REGISTRO DE COMANDOS (ADMIN & GERAL) ---
    app.add_handler(CommandHandler("start", start))
    
    # Comandos de GM (Importados de admin.py)
    app.add_handler(CommandHandler("cheat", admin_cheat))
    app.add_handler(CommandHandler("banir", admin_ban))
    app.add_handler(CommandHandler("conta", admin_delete))
    app.add_handler(CommandHandler("ouro", admin_give))
    app.add_handler(CommandHandler("gemas", admin_give))
    app.add_handler(CommandHandler("xp", admin_give))
    app.add_handler(CommandHandler("promote", admin_promote))
    app.add_handler(CommandHandler("demote", admin_demote))
    
    # --- REGISTRO DE MENSAGENS E BOTÕES (GAMEPLAY) ---
    
    # Captura texto (Nome de char, nome de guilda, doação, busca)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text_input))
    
    # Captura cliques nos botões (Importados de gameplay.py)
    app.add_handler(CallbackQueryHandler(handle_class_selection, pattern='^class_'))
    app.add_handler(CallbackQueryHandler(confirm_name_handler, pattern='^confirm_name_'))
    
    # Handler Geral (Trata todos os outros menus: Batalha, Guilda, Farm, Upgrade)
    app.add_handler(CallbackQueryHandler(handle_menu))
    
    return app
