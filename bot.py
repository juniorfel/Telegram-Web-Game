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
ADMIN_ID = 387214847 # SEU ID DE ADMIN
STAMINA_COST = 1
GUILD_CREATE_COST = 100
INITIAL_GOLD = 1000

# Status Base das 8 Classes
BASE_STATS = {
    "Guerreiro": {"str": 10, "int": 5, "def": 8, "hp": 50, "spd": 4, "crit": 5},
    "Mago": {"str": 5, "int": 10, "def": 7, "hp": 40, "spd": 6, "crit": 8},
    "Arqueiro": {"str": 8, "int": 6, "def": 9, "hp": 45, "spd": 8, "crit": 10},
    "Paladino": {"str": 9, "int": 7, "def": 10, "hp": 60, "spd": 3, "crit": 3},
    "Ogro": {"str": 12, "int": 3, "def": 6, "hp": 70, "spd": 2, "crit": 5},
    "Necromante": {"str": 4, "int": 11, "def": 5, "hp": 35, "spd": 5, "crit": 7},
    "Assassino": {"str": 7, "int": 5, "def": 11, "hp": 40, "spd": 10, "crit": 15},
    "Feiticeiro": {"str": 6, "int": 9, "def": 8, "hp": 50, "spd": 5, "crit": 6},
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
    """Gera monstro da fase com stats escalonados"""
    multiplier = 1.1 ** (phase_id - 1)
    is_boss = (phase_id % 10 == 0)
    
    name = f"Boss Fase {phase_id}" if is_boss else f"Monstro Fase {phase_id}"
    
    # Stats do Monstro
    hp = int(30 * multiplier * (2 if is_boss else 1))
    atk = int(5 * multiplier)
    defense = int(2 * multiplier)
    speed = int(4 * multiplier) # Monstros ficam mais rápidos
    
    # Recompensas
    gold = 1000 * (2 ** ((phase_id-1)//10)) if is_boss else 100 * (2 ** ((phase_id-1)//10))
    xp = 50 * phase_id
    
    return {
        "name": name, "hp": hp, "atk": atk, "def": defense, "spd": speed,
        "gold": gold, "xp": xp, "is_boss": is_boss
    }

# --- COMANDO DE ADMIN (CHEAT) ---
async def admin_cheat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id != ADMIN_ID:
        return # Silencioso para não admins

    db = get_db()
    player = get_player(user.id, db)
    
    if player:
        player.gold += 10000
        player.gems += 500
        player.stamina = player.max_stamina
        player.xp += 5000 # Provavelmente vai subir vários níveis
        check_level_up(player)
        db.commit()
        await update.message.reply_text("🕵️ **ADMIN:** +10k Ouro, +500 Gemas, Stamina Full, +5k XP.")
    db.close()

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
         InlineKeyboardButton("LOJA VIP 💎", callback_data='menu_shop')], # Botão Alterado
        [InlineKeyboardButton("Criar Guilda 🛡️", callback_data='menu_guild'),
         InlineKeyboardButton("Atualizar 🔄", callback_data='menu_refresh')]
    ]
    
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

# --- Fluxo de Criação de Personagem ---

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
    clean_name = raw_name.replace(" ", "")[:15] # Remove espaços e corta

    context.user_data['temp_name'] = clean_name
    
    kb = [[InlineKeyboardButton("✅ Confirmar", callback_data='confirm_name_yes')],
          [InlineKeyboardButton("✏️ Alterar", callback_data='confirm_name_no')]]
    
    await update.message.reply_text(f"Seu nome será: **{clean_name}**\nVocê confirma?", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def confirm_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'confirm_name_no':
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
            health=stats['hp'], max_health=stats['hp'],
            strength=stats['str'], intelligence=stats['int'], defense=stats['def'],
            speed=stats['spd'], crit_chance=stats['crit'], # Novos stats salvos
            gold=INITIAL_GOLD
        )
        db.add(new_player)
        db.commit()
        db.close()
        
        context.user_data['waiting_name'] = False
        await query.edit_message_text(f"Personagem **{name}** criado! Use /start.")

# --- Sistemas de Gameplay ---

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    db = get_db()
    player = get_player(query.from_user.id, db)
    if not player: return

# --- LOJA VIP ---
    if data == 'menu_shop':
        kb = [[InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
        await query.edit_message_text(
            "💎 **LOJA VIP**\n\n"
            "🚧 Esta área está em desenvolvimento.\n"
            "Em breve você poderá adquirir Gemas e Pacotes Especiais para evoluir no jogo.", 
            reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'
        )

    # --- DIÁRIO ---
    elif data == 'menu_daily':
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
            player.stamina = player.max_stamina
            
            lvl_msg = ""
            if check_level_up(player): lvl_msg = f"\n🎉 **LEVEL UP!** Nível {player.level}!"
            db.commit()
            
            await query.edit_message_text(f"✅ **Coletado!**\n+1000 Ouro\n+1000 XP{lvl_msg}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Voltar", callback_data='menu_refresh')]]), parse_mode='Markdown')

    # --- RANKING ---
    elif data == 'menu_ranking':
        top_players = db.query(Player).order_by(Player.pvp_rating.desc()).limit(10).all()
        msg = "🏆 **Ranking Global (Top 10)**\n\n"
        for idx, p in enumerate(top_players, 1):
            medal = "🥇" if idx==1 else "🥈" if idx==2 else "🥉" if idx==3 else f"{idx}."
            msg += f"{medal} **{p.name}** - Rating: {p.pvp_rating} (Lvl {p.level})\n"
        kb = [[InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    # --- BATALHA (Lógica Melhorada com Crit/Speed) ---
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
        await query.edit_message_text(f"🔥 **{monster['name']}** (Lvl {player.current_phase_id})\nHP: {monster['hp']} | Spd: {monster['spd']}\nRecompensa: {monster['gold']} Ouro, {monster['xp']} XP", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'confirm_pve':
        if player.stamina < STAMINA_COST:
            await query.answer("Sem Stamina!", show_alert=True); return
        
        monster = context.user_data['monster']
        player.stamina -= STAMINA_COST
        
        # --- NOVA LÓGICA DE BATALHA ---
        
        # 1. Checagem de Crítico (Dano x2)
        is_crit = random.randint(1, 100) <= player.crit_chance
        crit_msg = "💥 **CRÍTICO!** " if is_crit else ""
        damage_mult = 2.0 if is_crit else 1.0
        
        # 2. Checagem de Velocidade (Iniciativa/Esquiva)
        # Se Player for mais rápido, tem bônus de ataque. Se Monstro for mais rápido, player toma mais dano se perder.
        speed_bonus = 0
        if player.speed > monster['spd']:
            speed_bonus = 5 # +5 de "poder" fictício
            speed_msg = "⚡ Você foi mais rápido!\n"
        else:
            speed_msg = ""
        
        # 3. Cálculo de Poder
        player_power = ((player.strength * 2) + player.intelligence + speed_bonus) * damage_mult
        monster_power = monster['atk'] + monster['def'] + monster['spd']
        
        # 4. Resultado (Baseado na diferença de poder + aleatoriedade)
        # Chance base aumenta se o player for muito mais forte
        base_chance = 0.5
        power_diff = (player_power - monster_power) / 100 # Cada 100 pontos de diferença muda 1%
        win_chance = base_chance + power_diff
        
        # Roll
        roll = random.random()
        
        if roll < win_chance:
            player.gold += monster['gold']
            player.xp += monster['xp']
            player.current_phase_id += 1
            lvl_msg = "\n🎉 **LEVEL UP!**" if check_level_up(player) else ""
            msg = f"{speed_msg}{crit_msg}⚔️ **VITÓRIA!**\nVocê derrotou {monster['name']}!\n+ {monster['gold']} Ouro\n+ {monster['xp']} XP{lvl_msg}"
        else:
            # Dano recebido (reduzido pela defesa)
            raw_dmg = monster['atk']
            mitigation = player.defense / 100 # % de defesa
            loss = int(max(5, raw_dmg * (1 - mitigation)))
            player.health = max(0, player.health - loss)
            msg = f"☠️ **DERROTA...**\nO monstro esquivou e contra-atacou!\nVocê perdeu {loss} HP."
        
        db.commit()
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Continuar", callback_data='menu_refresh')]]), parse_mode='Markdown')

    # --- UPGRADES ---
    elif data == 'menu_upgrade' or data.startswith('up_'):
        if data.startswith('up_'):
            stat = data.split('_')[1]
            # Custo escala com o atributo
            base_val = getattr(player, 'strength' if stat=='str' else 'defense' if stat=='def' else 'speed' if stat=='spd' else 'crit_chance')
            cost = int(50 + (base_val * 20))
            
            if player.gold >= cost:
                player.gold -= cost
                if stat == 'str': player.strength += 1
                if stat == 'def': player.defense += 1
                if stat == 'spd': player.speed += 1
                if stat == 'crit': player.crit_chance += 1
                db.commit()
                await query.answer(f"Upgrade {stat.upper()} realizado!")
            else:
                await query.answer("Ouro insuficiente!")
        
        # Exibe painel
        c_str = int(50 + (player.strength * 20))
        c_def = int(50 + (player.defense * 20))
        c_spd = int(50 + (player.speed * 20))
        c_crit = int(50 + (player.crit_chance * 20))
        
        kb = [
            [InlineKeyboardButton(f"Força +1 ({c_str}g)", callback_data='up_str'),
             InlineKeyboardButton(f"Defesa +1 ({c_def}g)", callback_data='up_def')],
            [InlineKeyboardButton(f"Speed +1 ({c_spd}g)", callback_data='up_spd'),
             InlineKeyboardButton(f"Crit% +1 ({c_crit}g)", callback_data='up_crit')],
            [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]
        ]
        await query.edit_message_text(
            f"💰 Ouro: {player.gold}\n"
            f"💪 STR: {player.strength} | 🛡️ DEF: {player.defense}\n"
            f"⚡ SPD: {player.speed} | 💥 CRIT: {player.crit_chance}%",
            reply_markup=InlineKeyboardMarkup(kb)
        )

    # Refresh
    elif data == 'menu_refresh' or data == 'menu_status':
        await show_main_menu(update, player)

    db.close()

# --- Configuração da Aplicação ---
def main_bot(token: str) -> Application:
    init_db()
    app = Application.builder().token(token).build()

    # Comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cheat", admin_cheat)) # SEU COMANDO SECRETO
    
    # Mensagens e Callbacks
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name))
    app.add_handler(CallbackQueryHandler(handle_class_selection, pattern='^class_'))
    app.add_handler(CallbackQueryHandler(confirm_name_handler, pattern='^confirm_name_'))
    app.add_handler(CallbackQueryHandler(handle_menu))

    return app
