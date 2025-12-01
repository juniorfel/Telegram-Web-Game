from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from database import init_db
# Agora importamos o router e as funcoes principais de gameplay
from gameplay import (
    start, receive_text_input, handle_class_selection, confirm_name_handler, handle_menu,
    get_my_id, join_guild_command
)
# (Admin mantido)
from admin import (
    admin_cheat, admin_ban, admin_delete, admin_give, admin_promote, admin_demote
)

def main_bot(token: str) -> Application:
    init_db()
    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", get_my_id))
    app.add_handler(CommandHandler("guild", join_guild_command))
    
    app.add_handler(CommandHandler("cheat", admin_cheat))
    app.add_handler(CommandHandler("banir", admin_ban))
    app.add_handler(CommandHandler("conta", admin_delete))
    app.add_handler(CommandHandler("ouro", admin_give))
    app.add_handler(CommandHandler("gemas", admin_give))
    app.add_handler(CommandHandler("xp", admin_give))
    app.add_handler(CommandHandler("promote", admin_promote))
    app.add_handler(CommandHandler("demote", admin_demote))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text_input))
    app.add_handler(CallbackQueryHandler(handle_class_selection, pattern='^class_'))
    app.add_handler(CallbackQueryHandler(confirm_name_handler, pattern='^confirm_name_'))
    app.add_handler(CallbackQueryHandler(handle_menu))
    
    return app
