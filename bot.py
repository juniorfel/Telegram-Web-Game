import logging
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from database import Player, Guild, SessionLocal, init_db

# --- Configuração de Log ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configurações do Jogo ---
STAMINA_COST = 1
GUILD_CREATE_COST = 100
INITIAL_GOLD = 1000 # Ouro inicial alterado

# Status Base das 8 Classes
BASE_STATS = {
    "Guerreiro": {"str": 10, "int": 5, "def": 8, "hp": 50},
    "Mago": {"str": 5, "int": 10, "def": 7, "hp": 40},
    "Arqueiro": {"str": 8, "int": 6, "def": 9, "hp": 45},
    "Paladino": {"str": 9, "int": 7, "def": 10, "hp": 60},
    "Ogro": {"str": 12, "int": 3, "def": 6, "hp": 70},
    "Necromante": {"str": 4, "int": 11, "def": 5, "hp": 35},
    "Assassino": {"str": 7, "int": 5, "def": 11, "hp": 40},
    "Feiticeiro": {"str": 6, "int": 9, "def": 8, "hp": 50},
}

# --- Funções Auxiliares ---
def get_db(): return SessionLocal()
def get_player(user_id, db): return db.query(Player).filter(Player.id == user_id).first()

def check_level_up(player):
    """Sistema de Níveis: XP Necessário = Level * 100"""
    leveled_up = False
    while True:
        xp_needed = player.level * 100
        if player.xp >= xp_needed:
            player.xp -= xp_needed
            player.level += 1
            # Bônus por nível
            player.max_health += 5
            player.health = player.max_health
            player.strength += 1
            player.defense += 1
            leveled_up = True
        else:
            break
    return leveled_up

def generate_monster(phase_id):
    """Gera monstro da fase"""
    multiplier = 1.1 ** (phase_id - 1)
    is_boss = (phase_id % 10 == 0)
    name = f"Boss Fase {phase_id}" if is_boss else f"Monstro Fase {phase_id}"
    hp = int(30 * multiplier * (2 if is_boss else 1))
    gold = 1000 * (2 ** ((phase_id-1)//10)) if is_boss else 100 * (2 ** ((phase_id-1)//10))
    xp = 50 * phase_id
    return {"name": name, "hp": hp, "atk": int(5*multiplier), "def": int(2*multiplier), "gold": gold, "xp": xp, "is_boss": is_boss}

# --- Handlers de Início ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db = get_db()
    player = get_player(user.id, db)

    if not player:
        # Menu de Classes
        keyboard = [
            [InlineKeyboardButton("Guerreiro ⚔️", callback_data='class_Guerreiro'),
             InlineKeyboardButton("Mago 🔮", callback_data='class_Mago'),
             InlineKeyboardButton("Arqueiro 🏹", callback_data='class_Arqueiro')],
            [InlineKeyboardButton("Paladino 🛡️", callback_data='class_Paladino'),
             InlineKeyboardButton("Ogro 🧌", callback_data='class_Ogro'),
             InlineKeyboardButton("Necromante 💀", callback_data='class_Necromante')],
            [InlineKeyboardButton("Assassino 🔪", callback_data='class_Assassino'),
             InlineKeyboardButton("Feiticeiro 🐍", callback_data='class_Feiticeiro'),
             InlineKeyboardButton("Aleatório 🎲", callback_data='class_Aleatorio')]
        ]
        await update.message.reply_text(f"Bem-vindo, {user.first_name}! Escolha sua classe:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await show_main_menu(update, player)
    db.close()

async def show_main_menu(update: Update, player: Player):
    keyboard = [
        [InlineKeyboardButton("Status 👤", callback_data='menu_status'),
         InlineKeyboardButton("Batalhar ⚔️", callback_data='menu_battle_mode'),
         InlineKeyboardButton("Diário 🎁", callback_data='menu_daily')],
        [InlineKeyboardButton("Upgrade 💪", callback_data='menu_upgrade'),
         InlineKeyboardButton("Ranking 🏆", callback_data='menu_ranking'),
         InlineKeyboardButton("Loja 💎", callback_data='menu_shop')],
        [InlineKeyboardButton("Criar Guilda 🛡️", callback_data='menu_guild'),
         InlineKeyboardButton("Atualizar 🔄", callback_data='menu_refresh')]
    ]
    # Barra de XP visual
    xp_needed = player.level * 100
    xp_percent = int((player.xp / xp_needed) * 10)
    xp_bar = "🟦" * xp_percent + "⬜" * (10 - xp_percent)

    text = (f"**{player.name}** (Lvl {player.level} {player.class_name})\n"
            f"XP: {xp_bar} ({player.xp}/{xp_needed})\n"
            f"❤️ HP: {player.health}/{player.max_health}\n"
            f"⚡ Stamina: {player.stamina}/{player.max_stamina}\n"
            f"💰 {player.gold} | 💎 {player.gems}\n"
            f"🗺️ Fase: {player.current_phase_id}")
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# --- Fluxo de Criação de Personagem (Com Confirmação) ---

async def handle_class_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    class_choice = query.data.split('_')[1]
    if class_choice == 'Aleatorio': class_choice = random.choice(list(BASE_STATS.keys()))
    
    context.user_data['temp_class'] = class_choice
    context.user_data['waiting_name'] = True
    
    await query.edit_message_text(f"Classe **{class_choice}** selecionada!\nDigite o NOME do seu personagem (Máx 15 letras, sem espaços):", parse_mode='Markdown')

async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get('waiting_name'): return

    raw_name = update.message.text.strip()
    # Remove espaços e limita caracteres
    clean_name = raw_name.replace(" ", "")[:15]

    context.user_data['temp_name'] = clean_name
    
    # Botão de Confirmar ou Alterar
    kb = [
        [InlineKeyboardButton("✅ Confirmar", callback_data='confirm_name_yes')],
        [InlineKeyboardButton("✏️ Alterar", callback_data='confirm_name_no')]
    ]
    
    await update.message.reply_text(
        f"Seu nome será: **{clean_name}**\nVocê confirma?",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode='Markdown'
    )

async def confirm_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'confirm_name_no':
        await query.edit_message_text("Ok! Digite o nome novamente:")
        return # Continua esperando nome (waiting_name ainda é True)

    # Se confirmou
    if data == 'confirm_name_yes':
        name = context.user_data['temp_name']
        char_class = context.user_data['temp_class']
        user = update.effective_user
        
        db = get_db()
        stats = BASE_STATS[char_class]
        
        new_player = Player(
            id=user.id, username=user.username, name=name, class_name=char_class,
            health=stats['hp'], max_health=stats['hp'],
            strength=stats['str'], intelligence=stats['int'], defense=stats['def'],
            gold=INITIAL_GOLD # Começa com 1000 de Ouro
        )
        db.add(new_player)
        db.commit()
        db.close()
        
        context.user_data['waiting_name'] = False
        await query.edit_message_text(f"Personagem **{name}** criado com sucesso! Use /start.")

# --- Sistemas de Gameplay ---

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    db = get_db()
    player = get_player(query.from_user.id, db)
    if not player: return

    # --- Lógica do Diário ---
    if data == 'menu_daily':
        now = datetime.now()
        can_claim = (now - player.last_daily_claim) > timedelta(hours=24)
        
        msg = "🎁 **Recompensa Diária**\n\n"
        kb = []
        
        if can_claim:
            msg += "Você tem uma recompensa disponível!"
            kb.append([InlineKeyboardButton("💰 Coletar (1000 Gold + 1000 XP)", callback_data='daily_claim_now')])
        else:
            wait_time = timedelta(hours=24) - (now - player.last_daily_claim)
            hours, remainder = divmod(int(wait_time.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            msg += f"Espere {hours}h {minutes}m para coletar novamente."
        
        kb.append([InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')])
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'daily_claim_now':
        now = datetime.now()
        if (now - player.last_daily_claim) > timedelta(hours=24):
            player.gold += 1000
            player.xp += 1000
            player.last_daily_claim = now
            player.stamina = player.max_stamina # Restaura stamina tbm
            
            # Checa Nível
            lvl_msg = ""
            if check_level_up(player):
                lvl_msg = f"\n🎉 **LEVEL UP!** Você subiu para o nível {player.level}!"
            
            db.commit()
            
            await query.edit_message_text(
                f"✅ **Coletado com Sucesso!**\n+1000 Ouro\n+1000 XP\nStamina Restaurada!{lvl_msg}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]),
                parse_mode='Markdown'
            )
        else:
             await query.edit_message_text("Já coletado!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Voltar", callback_data='menu_refresh')]]))

    # --- Lógica de Ranking ---
    elif data == 'menu_ranking':
        # Pega Top 10 por PvP Rating
        top_players = db.query(Player).order_by(Player.pvp_rating.desc()).limit(10).all()
        
        msg = "🏆 **Ranking Global (Top 10)**\n\n"
        for idx, p in enumerate(top_players, 1):
            medal = "🥇" if idx==1 else "🥈" if idx==2 else "🥉" if idx==3 else f"{idx}."
            msg += f"{medal} **{p.name}** - Rating: {p.pvp_rating} (Lvl {p.level})\n"
        
        kb = [[InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    # --- Modos de Batalha (Manter lógica existente, adicionar XP) ---
    elif data == 'menu_battle_mode':
        kb = [[InlineKeyboardButton("Campanha (PVE) 🗺️", callback_data='battle_pve_start'),
               InlineKeyboardButton("Ranked (PVP) 🆚", callback_data='battle_pvp_start')],
              [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
        await query.edit_message_text("Escolha o modo:", reply_markup=InlineKeyboardMarkup(kb))

    elif data == 'battle_pve_start':
        monster = generate_monster(player.current_phase_id)
        context.user_data['monster'] = monster
        kb = [[InlineKeyboardButton("⚔️ LUTAR (1 Stamina)", callback_data='confirm_pve')],
              [InlineKeyboardButton("🔙 Fugir", callback_data='menu_battle_mode')]]
        await query.edit_message_text(f"🔥 **{monster['name']}** (Lvl {player.current_phase_id})\nHP: {monster['hp']}\nRecompensa: {monster['gold']} Ouro, {monster['xp']} XP", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'confirm_pve':
        if player.stamina < STAMINA_COST:
            await query.answer("Sem Stamina!", show_alert=True); return
        
        monster = context.user_data['monster']
        player.stamina -= STAMINA_COST
        
        # Batalha Simples
        win = random.random() > 0.4 # 60% chance base
        if win:
            player.gold += monster['gold']
            player.xp += monster['xp']
            player.current_phase_id += 1
            lvl_msg = "\n🎉 LEVEL UP!" if check_level_up(player) else ""
            msg = f"⚔️ **Vitória!**\n+ {monster['gold']} Ouro\n+ {monster['xp']} XP{lvl_msg}"
        else:
            loss = int(monster['atk']/2)
            player.health = max(0, player.health - loss)
            msg = f"☠️ **Derrota...**\nVocê perdeu {loss} HP."
        
        db.commit()
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Continuar", callback_data='menu_refresh')]]), parse_mode='Markdown')

    elif data == 'menu_upgrade' or data.startswith('up_'):
        # Lógica de upgrade simplificada para economizar espaço
        if data.startswith('up_'):
            stat = data.split('_')[1]
            cost = int(50 + (getattr(player, 'strength' if stat=='str' else 'defense') * 10))
            if player.gold >= cost:
                player.gold -= cost
                if stat == 'str': player.strength += 1
                if stat == 'def': player.defense += 1
                db.commit()
                await query.answer("Upgrade Realizado!")
            else:
                await query.answer("Ouro insuficiente!")
        
        c_str = int(50 + (player.strength * 10))
        kb = [[InlineKeyboardButton(f"+1 Força ({c_str}g)", callback_data='up_str')],
              [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
        await query.edit_message_text(f"Ouro: {player.gold}\nForça: {player.strength}", reply_markup=InlineKeyboardMarkup(kb))

    # Handlers genéricos de atualização
    elif data == 'menu_refresh' or data == 'menu_status':
        await show_main_menu(update, player)

    db.close()

# --- Configuração da Aplicação ---
def main_bot(token: str) -> Application:
    init_db() # Cria tabelas e SEEDS BOTS
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name))
    
    app.add_handler(CallbackQueryHandler(handle_class_selection, pattern='^class_'))
    app.add_handler(CallbackQueryHandler(confirm_name_handler, pattern='^confirm_name_'))
    app.add_handler(CallbackQueryHandler(handle_menu))

    return app
