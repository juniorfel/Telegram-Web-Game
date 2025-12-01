import logging
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters, ErrorHandler
# Certifique-se de que Player, Guild, SessionLocal, init_db estejam no database.py
from database import Player, Guild, SessionLocal, init_db 
from sqlalchemy import func, or_
from typing import List 

# --- Configuração ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Constantes do Jogo ---
ADMIN_ID = 387214847
STAMINA_COST = 1
GUILD_CREATE_COST = 100
GUILD_MIN_LEVEL = 50
INITIAL_GOLD = 1000
RESPEC_COST = 100
REFERRAL_GEMS_NEW = 10
REFERRAL_GOLD_NEW = 2000
REFERRAL_GEMS_INVITER = 25
REFERRAL_GOLD_INVITER = 5000
OFFICIAL_CHANNEL_LINK = "https://t.me/idlewarchannel"
BOT_USERNAME = "IdleWarGamebot" 
HEAL_RATE_PER_HOUR = 0.05 # 5% de HP Máximo por hora por nível da Clínica

# Status Base
BASE_STATS = {
    "Guerreiro": {"str": 10, "int": 5, "def": 8, "hp": 50, "spd": 4, "crit": 5, "desc": "🛡️ Bloqueio Perfeito: Chance de anular dano."},
    "Mago": {"str": 5, "int": 10, "def": 7, "hp": 40, "spd": 6, "crit": 8, "desc": "🔮 Sabedoria: Ignora parte da defesa inimiga."},
    "Arqueiro": {"str": 8, "int": 6, "def": 9, "hp": 45, "spd": 8, "crit": 10, "desc": "🦅 Olhos de Águia: Alta chance de crítico."},
    "Paladino": {"str": 9, "int": 7, "def": 10, "hp": 60, "spd": 3, "crit": 3, "desc": "✨ Fé: Cura vida ao atacar."},
    "Ogro": {"str": 12, "int": 3, "def": 6, "hp": 70, "spd": 2, "crit": 5, "desc": "🪨 Pele de Pedra: Reduz dano fixo."},
    "Necromante": {"str": 4, "int": 11, "def": 5, "hp": 35, "spd": 5, "crit": 7, "desc": "💀 Segunda Chance: Chance de sobreviver à morte."},
    "Assassino": {"str": 7, "int": 5, "def": 11, "hp": 40, "spd": 10, "crit": 15, "desc": "⚔️ Ataque Duplo: Chance de atacar 2x."},
    "Feiticeiro": {"str": 6, "int": 9, "def": 8, "hp": 50, "spd": 5, "crit": 6, "desc": "🐍 Maldição: Inimigo pode errar o ataque."},
}
VALID_CLASSES = list(BASE_STATS.keys())

# --- Funções Auxiliares de BD e Jogo ---
def get_db(): return SessionLocal()
def get_player(user_id, db): return db.query(Player).filter(Player.id == user_id).first()
def format_number(num): return str(int(num)) if num else "0"

def apply_passive_healing(player: Player, db):
    """
    Função de cura passiva (Corrigida).
    Otimizada para usar clinic_level e HEAL_RATE_PER_HOUR.
    """
    now = datetime.now()
    # Proteção contra data vazia
    if not player.last_stamina_gain: 
        player.last_stamina_gain = now
        return 0 
        
    elapsed = (now - player.last_stamina_gain).total_seconds() / 3600
    clinic_level = player.clinic_level if hasattr(player, 'clinic_level') and player.clinic_level is not None else 0
    
    if clinic_level > 0 and player.health < player.max_health:
        total_heal = int(player.max_health * HEAL_RATE_PER_HOUR * clinic_level * elapsed)
        if total_heal > 0:
            player.health = min(player.max_health, player.health + total_heal)
            player.last_stamina_gain = now 
            return total_heal
            
    # Atualiza o timer mesmo se estiver cheio, para não acumular "horas infinitas"
    if player.health == player.max_health or clinic_level == 0: 
        player.last_stamina_gain = now 
        
    return 0


# --- Funções ADMIN (Corrigindo NameError de admin_promote) ---
def is_admin(user_id, db=None):
    if user_id == ADMIN_ID: return True
    if db:
        p = get_player(user_id, db)
        if p and p.is_admin: return True
    return False

async def admin_cheat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db()
    if not is_admin(update.effective_user.id, db): db.close(); return
    p = get_player(update.effective_user.id, db)
    if p:
        p.gold += 50000; p.gems += 500; p.level = 50; p.stamina = p.max_stamina
        db.commit()
        msg = ("🕵️ **Modo Deus Ativado!**\n\n"
               "👑 **Comandos GM:**\n"
               "`/banir [ID]` - Banir Jogador\n"
               "`/conta [ID]` - Deletar Conta\n"
               "`/ouro [ID] [QTD]` - Dar Ouro\n"
               "`/gemas [ID] [QTD]` - Dar Gemas\n"
               "`/xp [ID] [QTD]` - Dar XP\n"
               "`/promote [ID]` - Add Admin\n"
               "`/demote [ID]` - Remove Admin")
        await update.message.reply_text(msg, parse_mode='Markdown')
    db.close()

async def admin_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db()
    if not is_admin(update.effective_user.id, db): db.close(); return
    try:
        tid = int(context.args[0]); t = get_player(tid, db)
        if t: t.is_banned = True; db.commit(); await update.message.reply_text(f"🚫 {t.name} BANIDO.")
        else: await update.message.reply_text("Não encontrado.")
    except: await update.message.reply_text("Uso: /banir [ID]")
    db.close()

async def admin_promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # A FUNÇÃO FOI ADICIONADA AQUI!
    db = get_db()
    if not is_admin(update.effective_user.id, db): db.close(); return
    try:
        tid = int(context.args[0]); t = get_player(tid, db)
        if t: 
            t.is_admin = True; db.commit()
            await update.message.reply_text(f"👑 {t.name} PROMOVIDO a Admin.")
        else: await update.message.reply_text("Não encontrado.")
    except: await update.message.reply_text("Uso: /promote [ID]")
    db.close()

async def admin_demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # A FUNÇÃO FOI ADICIONADA AQUI!
    db = get_db()
    if not is_admin(update.effective_user.id, db): db.close(); return
    try:
        tid = int(context.args[0]); t = get_player(tid, db)
        if t: 
            t.is_admin = False; db.commit()
            await update.message.reply_text(f"📉 {t.name} REBAIXADO.")
        else: await update.message.reply_text("Não encontrado.")
    except: await update.message.reply_text("Uso: /demote [ID]")
    db.close()

# --- FUNÇÃO DO TECLADO ---
def get_main_keyboard() -> List[List[InlineKeyboardButton]]:
    """Gera o teclado principal do menu."""
    return [
        [InlineKeyboardButton("Info/Perfil ❓", callback_data='menu_info'),
         InlineKeyboardButton("Batalhar ⚔️", callback_data='menu_battle_mode'),
         InlineKeyboardButton("Diário 🎁", callback_data='menu_daily')],
        [InlineKeyboardButton("Correio ✉️", callback_data='menu_mailbox'),
         InlineKeyboardButton("Ranking 🏆", callback_data='menu_ranking'),
         InlineKeyboardButton("LOJA VIP 💎", callback_data='menu_shop')],
        [InlineKeyboardButton("Guilda 🛡️", callback_data='menu_guild'),
         InlineKeyboardButton("Upgrade 💪", callback_data='menu_upgrade'),
         InlineKeyboardButton("Construções 🏗️", callback_data='menu_constructions')]
    ]

# --- START & MENU ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db = get_db()
    player = get_player(user.id, db)

    if player and player.is_banned:
        await update.message.reply_text("🚫 Conta Banida."); db.close(); return

    if context.args and not player:
        try:
            rid = int(context.args[0])
            if rid != user.id: context.user_data['referrer_id'] = rid
        except ValueError: pass 

    if not player:
        # Lógica de Menu de Criação
        summary = ""
        for name, data in BASE_STATS.items():
            summary += f"\n**{name}**: {data['desc']}\n   ❤️ {data['hp']} | 💪 {data['str']} | 🧠 {data['int']} | 🛡️ {data['def']}"

        msg = (f"✨ **A Névoa se Dissipa!** ✨\n\n"
               f"Viajante, o destino dos Reinos de Aerthos aguarda sua escolha.\n\n"
               f"💰 **Recursos Iniciais:**\n{INITIAL_GOLD} Ouro\n0 Gemas\n\n"
               f"Qual poder ancestral você irá empunhar?\n{summary}")

        kb = []; row = []
        classes = list(BASE_STATS.keys()) + ['Aleatorio']
        for c in classes:
            row.append(InlineKeyboardButton(f"{c} 🎲" if c=='Aleatorio' else c, callback_data=f'class_{c}'))
            if len(row) == 3: kb.append(row); row = []
        if row: kb.append(row)

        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    else:
        # Lógica de Player Existente
        heal = apply_passive_healing(player, db)
        db.commit()
        await show_main_menu(update, player)
        if heal > 0: await context.bot.send_message(chat_id=user.id, text=f"✨ Clínica: **+{heal} HP** recuperados.", parse_mode='Markdown')
    db.close()

async def show_main_menu(update: Update, player: Player):
    # FIX PRINCIPAL: 'keyboard' está definida aqui, GARANTINDO o escopo.
    keyboard = get_main_keyboard() 
    
    # Tratamento de segurança para XP/Nivel
    lvl = player.level if player.level and player.level > 0 else 1
    xp = player.xp if player.xp else 0
    needed = lvl * 100
    perc = (xp / needed) * 100 if needed > 0 else 0
    
    # NOME SEGURO
    safe_name = str(player.name).replace("_", " ").replace("*", "").replace("`", "") if player.name else "Herói"
    
    text = (f"**{safe_name}** (Lvl {lvl} {player.class_name})\n"
            f"Exp: {format_number(xp)}/{format_number(needed)} ({perc:.1f}%)\n"
            f"❤️ HP: {player.health}/{player.max_health}\n"
            f"⚡ Stamina: {player.stamina}/{player.max_stamina}\n"
            f"💰 {format_number(player.gold)} | 💎 {player.gems}")
    
    # ENVIO
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        except Exception: 
            # Fallback para nova mensagem se edição falhar
            await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        # Esta linha NÃO VAI MAIS FALHAR.
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# --- HANDLERS DE CALLBACK (PLACEHOLDERS) ---

async def handle_class_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Sua lógica de seleção de classe
    pass 

async def confirm_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Sua lógica de confirmação de nome
    pass 

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Sua lógica de navegação do menu
    pass 

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lida com erros na aplicação."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    if update.effective_message:
        await update.effective_message.reply_text(
            "Desculpe, ocorreu um erro interno ao processar seu comando. Tente novamente mais tarde."
        )

# --- Configuração da Aplicação ---
def main_bot(token: str) -> Application:
    init_db() 
    app = Application.builder().token(token).build()
    
    # REGISTRO DOS COMANDOS
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cheat", admin_cheat))
    app.add_handler(CommandHandler("banir", admin_ban))
    app.add_handler(CommandHandler("promote", admin_promote)) # Adicionado o handler
    app.add_handler(CommandHandler("demote", admin_demote)) # Adicionado o handler

    # REGISTRO DOS HANDLERS DE CALLBACK
    app.add_handler(CallbackQueryHandler(handle_class_selection, pattern='^class_'))
    app.add_handler(CallbackQueryHandler(confirm_name_handler, pattern='^confirm_name_'))
    app.add_handler(CallbackQueryHandler(handle_menu))
    
    # REGISTRO DE ERROS
    app.add_handler(ErrorHandler(error_handler))
    
    return app
