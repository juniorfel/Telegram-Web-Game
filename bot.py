import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from sqlalchemy.orm import Session
from database import Player, SessionLocal, init_db

# Configuração de Log
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Funções de Utilitário do Banco de Dados ---

def get_db() -> Session:
    """Retorna uma sessão do banco de dados."""
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

def get_player(user_id: int, db: Session) -> Player | None:
    """Busca um jogador pelo ID do Telegram."""
    return db.query(Player).filter(Player.id == user_id).first()

# --- Comandos do Bot ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inicia o bot e registra um novo jogador."""
    user = update.effective_user
    db = get_db()
    player = get_player(user.id, db)

    if player:
        await update.message.reply_text(f"Bem-vindo de volta, {player.name}! Seu nível atual é {player.level}.")
        return

    # Novo Jogador: Oferecer escolha de classe
    keyboard = [
        [InlineKeyboardButton("Guerreiro (Força)", callback_data='class_Guerreiro')],
        [InlineKeyboardButton("Mago (Inteligência)", callback_data='class_Mago')],
        [InlineKeyboardButton("Ladrão (Defesa)", callback_data='class_Ladrao')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Saudações, {user.first_name}! Bem-vindo ao Idle War.\n"
        "Para começar sua jornada, escolha sua classe:",
        reply_markup=reply_markup
    )

async def handle_class_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processa a escolha de classe do novo jogador."""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    class_choice = query.data.split('_')[1]
    
    db = get_db()
    player = get_player(user.id, db)

    if player:
        await query.edit_message_text("Você já escolheu sua classe.")
        return

    # Atributos baseados na classe
    base_stats = {
        "Guerreiro": {"str": 10, "int": 5, "def": 8},
        "Mago": {"str": 5, "int": 10, "def": 7},
        "Ladrao": {"str": 7, "int": 7, "def": 9},
    }
    stats = base_stats.get(class_choice, base_stats["Guerreiro"])
    
    # Cria o novo jogador
    new_player = Player(
        user_id=user.id,
        username=user.username,
        name=user.first_name,
        class_name=class_choice,
        health=50,
        max_health=50,
        strength=stats["str"],
        intelligence=stats["int"],
        defense=stats["def"]
    )
    
    db.add(new_player)
    db.commit()

    await query.edit_message_text(
        f"Parabéns! Você é agora um(a) **{class_choice}**.\n\n"
        f"Seus atributos iniciais:\n"
        f"💪 Força: {new_player.strength}\n"
        f"🧠 Inteligência: {new_player.intelligence}\n"
        f"🛡️ Defesa: {new_player.defense}\n\n"
        "Use o comando /status para ver seu perfil completo."
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra o status atual do jogador."""
    db = get_db()
    player = get_player(update.effective_user.id, db)

    if not player:
        await update.message.reply_text("Você precisa iniciar o jogo com /start primeiro.")
        return

    await update.message.reply_text(
        f"**Perfil de {player.name} ({player.class_name})**\n\n"
        f"⭐ Nível: {player.level}\n"
        f"❤️ HP: {player.health}/{player.max_health}\n"
        f"💰 Ouro: {player.gold}\n\n"
        f"**Atributos:**\n"
        f"💪 Força: {player.strength}\n"
        f"🧠 Inteligência: {player.intelligence}\n"
        f"🛡️ Defesa: {player.defense}\n\n"
        f"Rating PvP: {player.pvp_rating}"
    )

async def daily_claim(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Permite ao jogador reivindicar o ganho de atributo diário."""
    db = get_db()
    player = get_player(update.effective_user.id, db)

    if not player:
        await update.message.reply_text("Você precisa iniciar o jogo com /start primeiro.")
        return

    time_since_last_claim = datetime.now() - player.last_daily_claim
    
    # Verifica se 24 horas se passaram
    if time_since_last_claim < timedelta(hours=24):
        time_remaining = timedelta(hours=24) - time_since_last_claim
        hours, remainder = divmod(time_remaining.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        await update.message.reply_text(
            f"Você já reivindicou seu ganho diário. Tente novamente em {hours}h {minutes}m."
        )
        return

    # Lógica de ganho de atributo (exemplo simples)
    # O atributo principal da classe ganha +2, os outros +1
    gain_str, gain_int, gain_def = 1, 1, 1
    if player.class_name == "Guerreiro":
        gain_str = 2
    elif player.class_name == "Mago":
        gain_int = 2
    elif player.class_name == "Ladrao":
        gain_def = 2

    player.strength += gain_str
    player.intelligence += gain_int
    player.defense += gain_def
    player.last_daily_claim = datetime.now()
    
    db.commit()

    await update.message.reply_text(
        f"🎉 **Reivindicação Diária Concluída!** 🎉\n\n"
        f"Você ganhou:\n"
        f"💪 Força: +{gain_str}\n"
        f"🧠 Inteligência: +{gain_int}\n"
        f"🛡️ Defesa: +{gain_def}\n\n"
        f"Seu poder aumentou! Use /status para ver seus novos atributos."
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a message to the user."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    
    # Opcional: Enviar uma mensagem de erro amigável ao usuário
    # Verificamos se update existe, pois em alguns erros ele pode ser None
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "Desculpe, ocorreu um erro interno ao processar seu comando. Tente novamente mais tarde."
        )

# --- Função Principal do Bot ---

def main_bot(token: str) -> Application:
    """Configura e retorna a aplicação do bot."""
    # Inicializa o banco de dados (cria as tabelas se não existirem)
    init_db()
    
    application = Application.builder().token(token).build()

    # Handlers de Comandos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("daily", daily_claim))
    
    # Handler de Callback (para seleção de classe)
    application.add_handler(CallbackQueryHandler(handle_class_selection, pattern='^class_'))

    # Handler de Erro
    application.add_error_handler(error_handler)

    return application
