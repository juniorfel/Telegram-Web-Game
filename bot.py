import logging
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from database import Player, Guild, SessionLocal, init_db
from sqlalchemy import func

# --- Configuração ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

ADMIN_ID = 387214847
STAMINA_COST = 1
GUILD_CREATE_COST = 100
GUILD_MIN_LEVEL = 50
INITIAL_GOLD = 1000

# Constantes de Afiliados
REFERRAL_GEMS_NEW = 10
REFERRAL_GOLD_NEW = 2000
REFERRAL_GEMS_INVITER = 25
REFERRAL_GOLD_INVITER = 5000

# Constantes de Comunidade
OFFICIAL_CHANNEL_LINK = "https://t.me/idlewarchannel"
BOT_USERNAME = "IdleWarGamebot" 
HEAL_RATE_PER_HOUR = 0.05 

# Status Base das 8 Classes
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

# --- Funções Auxiliares (Mantidas) ---
def get_db(): return SessionLocal()
def get_player(user_id, db): return db.query(Player).filter(Player.id == user_id).first()
def format_number(num): return str(int(num))

def check_level_up(player):
    leveled_up = False
    while player.xp >= player.level * 100:
        player.xp -= player.level * 100
        player.level += 1
        player.max_health += 5
        player.health = player.max_health
        player.strength += 1
        player.defense += 1
        leveled_up = True
    return leveled_up

def generate_monster(phase_id):
    mult = 1.1 ** (phase_id - 1)
    is_boss = (phase_id % 10 == 0)
    name = f"Boss Fase {phase_id}" if is_boss else f"Monstro Fase {phase_id}"
    gold = 1000 * (2 ** ((phase_id-1)//10)) if is_boss else 100 * (2 ** ((phase_id-1)//10))
    xp = 50 * phase_id
    return {"name": name, "hp": int(30*mult), "atk": int(5*mult), "def": int(2*mult), "spd": int(4*mult), "gold": gold, "xp": xp, "is_boss": is_boss}

def get_construction_cost(level, initial_cost=1000):
    return int(initial_cost * (1.5 ** level))

def apply_passive_healing(player: Player, db):
    now = datetime.now()
    time_elapsed = now - player.last_stamina_gain
    hours_elapsed = time_elapsed.total_seconds() / 3600
    clinic_level = player.clinic_level
    if clinic_level > 0 and player.health < player.max_health:
        heal_amount_per_hour = player.max_health * HEAL_RATE_PER_HOUR * clinic_level
        total_heal = int(heal_amount_per_hour * hours_elapsed)
        player.health = min(player.max_health, player.health + total_heal)
        player.last_stamina_gain = now 
        return total_heal
    if player.health == player.max_health:
        player.last_stamina_gain = now 
    return 0

# --- COMANDO DE ADMIN (CHEAT) ---
async def admin_cheat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id != ADMIN_ID: return
    db = get_db()
    player = get_player(user.id, db)
    if player:
        player.gold += 50000; player.gems += 500; player.level = 50; player.stamina = 100
        db.commit()
        await update.message.reply_text("🕵️ ADMIN: Recursos e Nível 50 adicionados.")
    db.close()

# --- START & MENU ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db = get_db()
    player = get_player(user.id, db)

    if context.args and not player:
        try:
            referrer_id = int(context.args[0])
            referrer = get_player(referrer_id, db)
            if referrer and referrer_id != user.id: context.user_data['referrer_id'] = referrer_id
        except ValueError: pass 

    if not player:
        # --- CORREÇÃO: Inicializa kb e row ANTES do loop ---
        kb = []
        row = []
        classes = list(BASE_STATS.keys()) + ['Aleatorio']
        
        for c in classes:
            label = f"{c} 🎲" if c == 'Aleatorio' else c
            row.append(InlineKeyboardButton(label, callback_data=f'class_{c}'))
            if len(row) == 3: kb.append(row); row = []
        
        msg = f"Bem-vindo ao Idle War! Escolha sua classe:"
        if context.user_data.get('referrer_id'):
            referrer_player = get_player(context.user_data['referrer_id'], db)
            if referrer_player: msg += f"\n\nIndicação de **{referrer_player.name}** detectada! Ambos receberão bônus!"

        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    else:
        heal_amount = apply_passive_healing(player, db)
        db.commit()
        
        await show_main_menu(update, player)
        
        if heal_amount > 0:
             await context.bot.send_message(chat_id=user.id, text=f"✨ Você se regenerou **+{heal_amount} HP** enquanto estava offline!", parse_mode='Markdown')
             
    db.close()

async def show_main_menu(update: Update, player: Player):
    # --- NOVO LAYOUT DE 9 BOTÕES ---
    keyboard = [
        [InlineKeyboardButton("Info/Perfil ❓", callback_data='menu_info'),
         InlineKeyboardButton("Batalhar ⚔️", callback_data='menu_battle_mode'),
         InlineKeyboardButton("Diário 🎁", callback_data='menu_daily')],
        [InlineKeyboardButton("Correio/Eventos ✉️", callback_data='menu_mailbox'),
         InlineKeyboardButton("Ranking 🏆", callback_data='menu_ranking'),
         InlineKeyboardButton("LOJA VIP 💎", callback_data='menu_shop')],
        [InlineKeyboardButton("Guilda 🛡️", callback_data='menu_guild'),
         InlineKeyboardButton("Upgrade 💪", callback_data='menu_upgrade'),
         InlineKeyboardButton("Construções 🏗️", callback_data='menu_constructions')]
    ]
    
    xp_needed = player.level * 100
    perc = (player.xp / xp_needed) * 100
    
    text = (f"**{player.name}** (Lvl {player.level} {player.class_name})\n"
            f"Exp: {format_number(player.xp)}/{format_number(xp_needed)} ({perc:.2f}%)\n"
            f"❤️ HP: {player.health}/{player.max_health}\n"
            f"⚡ Stamina: {player.stamina}/{player.max_stamina}\n"
            f"💰 {format_number(player.gold)} | 💎 {player.gems}")
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


# --- RECEBIMENTO DE TEXTO ---
async def receive_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = context.user_data
    
    # 1. Flow de Nome
    if user_data.get('waiting_name'):
        raw = update.message.text.strip(); clean = raw.replace(" ", "")[:15]
        user_data['temp_name'] = clean
        user_data['waiting_name'] = False
        kb = [[InlineKeyboardButton("✅ Confirmar", callback_data='confirm_name_yes')], [InlineKeyboardButton("✏️ Alterar", callback_data='confirm_name_no')]]
        await update.message.reply_text(f"Seu nome será: **{clean}**\nConfirma?", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        return

    # 2. Flow de Guilda (Nome)
    if user_data.get('waiting_guild_name'):
        raw = update.message.text.strip(); clean = raw.replace(" ", "")[:15]
        user_data['temp_guild_name'] = clean
        user_data['waiting_guild_name'] = False
        user_data['waiting_guild_link'] = True 
        await update.message.reply_text(f"Nome da Guilda: **{clean}**\n\nAgora, envie o **Link do Grupo Telegram** (deve começar com https://t.me/):")
        return

    # 3. Flow de Guilda (Link)
    if user_data.get('waiting_guild_link'):
        link = update.message.text.strip()
        if not (link.startswith("https://t.me/") or link.startswith("https://telegram.me/")):
            await update.message.reply_text("🚫 Link inválido! O link deve começar com https://t.me/ ... Tente novamente:")
            return
        
        # Cria a Guilda
        db = get_db()
        player = get_player(update.effective_user.id, db)
        g_name = user_data['temp_guild_name']
        
        try:
            new_guild = Guild(name=g_name, leader_id=player.id, telegram_link=link, member_count=1)
            db.add(new_guild)
            db.commit()
            
            player.gems -= GUILD_CREATE_COST
            player.guild_id = new_guild.id
            db.commit()
            
            user_data['waiting_guild_link'] = False
            await update.message.reply_text(f"✅ Guilda **{g_name}** criada com sucesso! Use o menu para ver detalhes.")
        except Exception:
            await update.message.reply_text("Erro: Já existe uma guilda com esse nome.")
        db.close()


# --- CONFIRMAÇÃO DE NOME ---
async def confirm_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'confirm_name_no':
        context.user_data['waiting_name'] = True
        await query.edit_message_text("Ok! Digite o nome novamente:")
        return

    if data == 'confirm_name_yes':
        name = context.user_data['temp_name']
        char_class = context.user_data['temp_class']
        user = update.effective_user
        
        db = get_db()
        stats = BASE_STATS[char_class]
        
        new_player = Player(
            id=user.id, username=user.username, name=name, class_name=char_class,
            health=stats['hp'], max_health=stats['hp'], strength=stats['str'], intelligence=stats['int'], defense=stats['def'],
            speed=stats['spd'], crit_chance=stats['crit'], gold=INITIAL_GOLD
        )
        db.add(new_player)
        db.commit()
        
        referral_msg = ""
        referrer_id = context.user_data.get('referrer_id')
        if referrer_id:
            referrer = get_player(referrer_id, db)
            if referrer:
                referrer.gems += REFERRAL_GEMS_INVITER
                referrer.gold += REFERRAL_GOLD_INVITER
                new_player.gems += REFERRAL_GEMS_NEW
                new_player.gold += REFERRAL_GOLD_NEW
                db.commit()
                referral_msg = f"\n\n🎁 **BÔNUS AFILIADO!**\nVocê ganhou {REFERRAL_GEMS_NEW}💎 e {REFERRAL_GOLD_NEW}💰."
                logger.info(f"Afiliado: {user.id} registrado. {referrer_id} recebeu recompensas.")

        db.close()
        
        context.user_data['waiting_name'] = False
        await query.edit_message_text(
            f"Personagem **{name}** criado!{referral_msg}\nUse /start.",
            parse_mode='Markdown'
        )


# --- HANDLER GERAL DE MENUS ---
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    db = get_db()
    player = get_player(query.from_user.id, db)
    if not player: return

    # --- NOVO: CORREIO/EVENTOS ---
    if data == 'menu_mailbox':
        kb = [
            [InlineKeyboardButton("Canal Oficial 📢", url=OFFICIAL_CHANNEL_LINK)],
            [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]
        ]
        await query.edit_message_text(
            "✉️ **Correio & Eventos**\n\n"
            "Acompanhe as novidades e eventos no nosso canal oficial.",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'
        )
    
    # --- Menu Info/Perfil ---
    elif data == 'menu_info':
        referral_link = f"https://t.me/{BOT_USERNAME}?start={player.id}"

        status_text = (f"**Status Detalhado de {player.name}**\n"
                       f"💪 Força: {player.strength} | 🧠 Inteligência: {player.intelligence}\n"
                       f"🛡️ Defesa: {player.defense} | ⚡ Velocidade: {player.speed}\n"
                       f"💥 Crítico: {player.crit_chance}%\n"
                       f"----------------------------------\n"
                       f"🔗 **SEU LINK DE AFILIADO:**\n"
                       f"```\n{referral_link}\n```")
        
        kb = [[InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
        await query.edit_message_text(status_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    # --- Outras Lógicas (Batalha, Guilda, Upgrade, etc) mantidas ---

    # Refresh
    elif data == 'menu_refresh':
        await show_main_menu(update, player)

    db.close()

# --- Configuração da Aplicação ---
def main_bot(token: str) -> Application:
    init_db()
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cheat", admin_cheat))
    
    # Mensagens e Callbacks
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text_input))
    app.add_handler(CallbackQueryHandler(confirm_name_handler, pattern='^confirm_name_'))
    app.add_handler(CallbackQueryHandler(handle_menu))

    return app
