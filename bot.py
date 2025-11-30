import logging
import random
import math
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
MAX_STAMINA_DAILY_ADD = 5

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

# --- Funções Auxiliares de Banco de Dados ---
def get_db():
    return SessionLocal()

def get_player(user_id, db):
    return db.query(Player).filter(Player.id == user_id).first()

# --- Lógica Matemática do Jogo ---

def calculate_upgrade_cost(current_value, stat_type):
    """Calcula custo de upgrade: Custo Base * (Valor Atual / 2)"""
    base_costs = {"str": 50, "def": 50, "hp": 30, "speed": 100, "crit": 150}
    base = base_costs.get(stat_type, 50)
    return int(base + (current_value * 10))

def generate_monster(phase_id):
    """Gera um monstro dinamicamente baseado na fase."""
    phase_level = (phase_id - 1) // 10 + 1
    is_boss = (phase_id % 10 == 0)
    
    # Multiplicador de força baseado na fase
    multiplier = 1.1 ** (phase_id - 1)
    
    name = f"Boss Fase {phase_id}" if is_boss else f"Monstro Fase {phase_id}"
    hp = int(30 * multiplier * (2 if is_boss else 1))
    attack = int(5 * multiplier * (1.5 if is_boss else 1))
    defense = int(2 * multiplier)
    
    # Recompensa
    reward_mult = 2 ** (phase_level - 1)
    gold = 1000 * reward_mult if is_boss else 100 * reward_mult
    gems = 5 * reward_mult if is_boss else 0
    
    return {
        "name": name, "hp": hp, "atk": attack, "def": defense,
        "gold": gold, "gems": gems, "is_boss": is_boss, "xp": 10 * phase_id
    }

# --- Handlers Principais ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ponto de entrada: Criação de char ou Menu Principal."""
    user = update.effective_user
    db = get_db()
    player = get_player(user.id, db)

    if not player:
        # Menu de Criação (8 Classes + Aleatório)
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
        await update.message.reply_text(
            f"Bem-vindo ao Idle War, {user.first_name}!\nEscolha sua classe:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        # Menu Principal
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
    text = (f"**{player.name}** (Lvl {player.level} {player.class_name})\n"
            f"❤️ HP: {player.health}/{player.max_health}\n"
            f"⚡ Stamina: {player.stamina}/{player.max_stamina}\n"
            f"💰 {player.gold} | 💎 {player.gems}\n"
            f"🗺️ Fase Atual: {player.current_phase_id}")
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# --- Fluxo de Criação ---

async def handle_class_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    class_choice = query.data.split('_')[1]
    
    if class_choice == 'Aleatorio':
        class_choice = random.choice(list(BASE_STATS.keys()))
        
    context.user_data['temp_class'] = class_choice
    context.user_data['waiting_name'] = True
    
    await query.edit_message_text(f"Classe **{class_choice}** selecionada!\nDigite o NOME do seu personagem:")

async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get('waiting_name'):
        return

    name = update.message.text.strip()
    char_class = context.user_data['temp_class']
    user = update.effective_user
    
    db = get_db()
    stats = BASE_STATS[char_class]
    
    # Cria Player
    new_player = Player(
        id=user.id, username=user.username, name=name, class_name=char_class,
        health=stats['hp'], max_health=stats['hp'],
        strength=stats['str'], intelligence=stats['int'], defense=stats['def']
    )
    db.add(new_player)
    db.commit()
    db.close()
    
    context.user_data['waiting_name'] = False
    await update.message.reply_text(f"Personagem **{name}** criado! Use /start para jogar.")

# --- Sistemas de Jogo ---

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    db = get_db()
    player = get_player(query.from_user.id, db)
    
    if not player: return

    # 1. Menu de Modos de Batalha
    if data == 'menu_battle_mode':
        kb = [[InlineKeyboardButton("Campanha (PVE) 🗺️", callback_data='battle_pve_start'),
               InlineKeyboardButton("Ranked (PVP) 🆚", callback_data='battle_pvp_start')],
              [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
        await query.edit_message_text("Escolha o modo de batalha:", reply_markup=InlineKeyboardMarkup(kb))

    # 2. Confirmação PVE
    elif data == 'battle_pve_start':
        monster = generate_monster(player.current_phase_id)
        context.user_data['monster'] = monster # Salva monstro na sessão
        kb = [[InlineKeyboardButton("⚔️ LUTAR (1 Stamina)", callback_data='confirm_pve')],
              [InlineKeyboardButton("🔙 Fugir", callback_data='menu_battle_mode')]]
        
        await query.edit_message_text(
            f"🔥 **{monster['name']}** apareceu!\n"
            f"❤️ HP: {monster['hp']} | ⚔️ Atk: {monster['atk']}\n"
            f"💰 Recompensa: {monster['gold']} Ouro" + (f" + {monster['gems']} 💎" if monster['gems'] else ""),
            reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'
        )

    # 3. Execução PVE
    elif data == 'confirm_pve':
        if player.stamina < STAMINA_COST:
            await query.edit_message_text("⚠️ Sem Stamina! Espere o reset diário.", reply_markup=None)
            return
            
        monster = context.user_data.get('monster')
        player.stamina -= STAMINA_COST
        
        # Lógica Simples de Batalha
        player_power = player.strength + player.intelligence + player.defense
        monster_power = monster['atk'] + monster['def']
        
        # Chance baseada em poder + fator aleatório
        win_chance = player_power / (player_power + monster_power)
        roll = random.random()
        
        if roll < win_chance or roll < 0.1: # 10% chance mínima de vitória
            player.gold += monster['gold']
            player.gems += monster['gems']
            player.xp += monster['xp']
            player.current_phase_id += 1 # Avança fase
            msg = f"🎉 **VITÓRIA!**\nVocê derrotou {monster['name']}!\n+ {monster['gold']} Ouro\n+ {monster['gems']} Gemas\nVocê avançou para a fase {player.current_phase_id}!"
        else:
            dmg = int(monster['atk'] / 2)
            player.health = max(0, player.health - dmg)
            msg = f"☠️ **DERROTA...**\nO monstro era muito forte.\nVocê perdeu {dmg} de HP."
            
        db.commit()
        kb = [[InlineKeyboardButton("Continuar", callback_data='menu_refresh')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    # 4. Confirmação PVP
    elif data == 'battle_pvp_start':
        # Busca oponente aleatório próximo do rating
        opponent = db.query(Player).filter(Player.id != player.id).order_by(Player.pvp_rating.desc()).first()
        
        if not opponent:
            await query.edit_message_text("Nenhum oponente encontrado na arena.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Voltar", callback_data='menu_refresh')]]))
            return

        context.user_data['opponent_id'] = opponent.id
        kb = [[InlineKeyboardButton(f"⚔️ DESAFIAR {opponent.name}", callback_data='confirm_pvp')],
              [InlineKeyboardButton("🔙 Voltar", callback_data='menu_battle_mode')]]
        await query.edit_message_text(f"Oponente encontrado: **{opponent.name}**\nRating: {opponent.pvp_rating}", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    # 5. Execução PVP
    elif data == 'confirm_pvp':
        if player.stamina < STAMINA_COST:
            await query.edit_message_text("⚠️ Sem Stamina!", reply_markup=None); return

        opp_id = context.user_data['opponent_id']
        opponent = db.query(Player).filter(Player.id == opp_id).first()
        player.stamina -= STAMINA_COST
        
        # Simples: Maior força vence
        if player.strength > opponent.strength:
            player.pvp_rating += 25
            player.gold += 50
            msg = f"🏆 **Vitória na Arena!**\nVocê venceu {opponent.name}!\n+25 Rating | +50 Ouro"
        else:
            player.pvp_rating = max(0, player.pvp_rating - 15)
            msg = f"🏳️ **Derrota na Arena...**\n{opponent.name} foi mais forte.\n-15 Rating"
            
        db.commit()
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Voltar", callback_data='menu_refresh')]]), parse_mode='Markdown')

    # 6. Menu Upgrade
    elif data == 'menu_upgrade':
        # Lista atributos e custos
        c_str = calculate_upgrade_cost(player.strength, 'str')
        c_def = calculate_upgrade_cost(player.defense, 'def')
        c_hp = calculate_upgrade_cost(player.max_health, 'hp')
        
        kb = [
            [InlineKeyboardButton(f"+1 Força ({c_str}g)", callback_data='up_str')],
            [InlineKeyboardButton(f"+1 Defesa ({c_def}g)", callback_data='up_def')],
            [InlineKeyboardButton(f"+10 Max HP ({c_hp}g)", callback_data='up_hp')],
            [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]
        ]
        await query.edit_message_text(f"💰 **Seu Ouro:** {player.gold}\nMelhore seus atributos:", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    # 7. Executar Upgrade (Genérico)
    elif data.startswith('up_'):
        stat = data.split('_')[1]
        cost = 0
        
        if stat == 'str':
            cost = calculate_upgrade_cost(player.strength, 'str')
            if player.gold >= cost:
                player.gold -= cost
                player.strength += 1
                msg = "Força aumentada!"
            else: msg = "Ouro insuficiente!"
        
        elif stat == 'def':
            cost = calculate_upgrade_cost(player.defense, 'def')
            if player.gold >= cost:
                player.gold -= cost
                player.defense += 1
                msg = "Defesa aumentada!"
            else: msg = "Ouro insuficiente!"

        elif stat == 'hp':
            cost = calculate_upgrade_cost(player.max_health, 'hp')
            if player.gold >= cost:
                player.gold -= cost
                player.max_health += 10
                player.health += 10 # Cura também
                msg = "Vida Máxima aumentada!"
            else: msg = "Ouro insuficiente!"
            
        db.commit()
        await query.answer(msg) # Mostra pop-up
        await show_main_menu(update, player) # Recarrega menu

    # 8. Menu Guilda
    elif data == 'menu_guild':
        if player.guild_id:
            guild = db.query(Guild).filter(Guild.id == player.guild_id).first()
            await query.edit_message_text(f"Você pertence à guilda: **{guild.name}**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Voltar", callback_data='menu_refresh')]]))
        else:
            kb = [[InlineKeyboardButton(f"Criar Guilda ({GUILD_CREATE_COST} Gemas)", callback_data='create_guild')],
                  [InlineKeyboardButton("Voltar", callback_data='menu_refresh')]]
            await query.edit_message_text("Você não tem guilda.", reply_markup=InlineKeyboardMarkup(kb))

    elif data == 'create_guild':
        if player.gems >= GUILD_CREATE_COST:
            # Lógica simplificada: Cria guilda com nome do usuário
            player.gems -= GUILD_CREATE_COST
            new_guild = Guild(name=f"Guilda de {player.name}", leader_id=player.id)
            db.add(new_guild)
            db.commit() # Commita para gerar ID
            player.guild_id = new_guild.id
            db.commit()
            await query.edit_message_text(f"Guilda **{new_guild.name}** criada com sucesso!")
        else:
            await query.answer("Gemas insuficientes!", show_alert=True)

    # 9. Diário
    elif data == 'menu_daily':
        now = datetime.now()
        if now - player.last_stamina_gain > timedelta(hours=24):
            player.stamina = player.max_stamina
            player.last_stamina_gain = now
            msg = "Stamina restaurada e bônus diário coletado!"
        else:
            msg = "Você já coletou seu bônus hoje. Volte amanhã."
        
        db.commit()
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Voltar", callback_data='menu_refresh')]]))
        
    # 10. Atualizar / Status
    elif data == 'menu_refresh' or data == 'menu_status':
        await show_main_menu(update, player)
        
    db.close()

# --- Configuração da Aplicação ---
def main_bot(token: str) -> Application:
    init_db() # Cria tabelas se não existirem
    app = Application.builder().token(token).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name))
    
    # Callback Router (Gerencia todos os botões)
    app.add_handler(CallbackQueryHandler(handle_class_selection, pattern='^class_'))
    app.add_handler(CallbackQueryHandler(handle_menu))

    return app
