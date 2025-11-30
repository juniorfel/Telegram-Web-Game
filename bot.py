import logging
import random
import math
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from database import Player, Guild, SessionLocal, init_db

# --- Configuração ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

ADMIN_ID = 387214847
STAMINA_COST = 1
GUILD_CREATE_COST = 100
GUILD_MIN_LEVEL = 50
INITIAL_GOLD = 1000

# Stats e Descrições das Passivas
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

# --- Funções Auxiliares ---
def get_db(): return SessionLocal()
def get_player(user_id, db): return db.query(Player).filter(Player.id == user_id).first()

def format_number(num):
    if num >= 1_000_000_000: return f"{num / 1_000_000_000:.2f} B"
    elif num >= 1_000_000: return f"{num / 1_000_000:.2f} M"
    elif num >= 1_000: return f"{num / 1_000:.2f} K"
    return str(int(num))

def check_level_up(player):
    leveled = False
    while True:
        needed = player.level * 100
        if player.xp >= needed:
            player.xp -= needed
            player.level += 1
            player.max_health += 5
            player.health = player.max_health
            player.strength += 1
            player.defense += 1
            leveled = True
        else: break
    return leveled

def generate_monster(phase_id):
    mult = 1.1 ** (phase_id - 1)
    is_boss = (phase_id % 10 == 0)
    name = f"Boss Fase {phase_id}" if is_boss else f"Monstro Fase {phase_id}"
    hp = int(30 * mult * (2 if is_boss else 1))
    gold = 1000 * (2 ** ((phase_id-1)//10)) if is_boss else 100 * (2 ** ((phase_id-1)//10))
    return {"name": name, "hp": hp, "atk": int(5*mult), "def": int(2*mult), "spd": int(4*mult), "gold": gold, "xp": 50*phase_id, "is_boss": is_boss}

# --- COMANDO CHEAT ---
async def admin_cheat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID: return
    db = get_db()
    p = get_player(update.effective_user.id, db)
    if p:
        p.gold += 50000
        p.gems += 500
        p.level = 50
        p.stamina = 100
        db.commit()
        await update.message.reply_text("🕵️ ADMIN MODE: Recursos e Nível 50 adicionados.")
    db.close()

# --- START & MENU ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db = get_db()
    player = get_player(user.id, db)
    if not player:
        # Menu Classes 3x3
        kb = []
        classes = list(BASE_STATS.keys()) + ['Aleatorio']
        row = []
        for c in classes:
            label = f"{c} 🎲" if c == 'Aleatorio' else c
            # ATENÇÃO: O callback_data deve bater EXATAMENTE com o regex do handler
            row.append(InlineKeyboardButton(label, callback_data=f'class_{c}'))
            if len(row) == 3:
                kb.append(row)
                row = []
        
        # Garante que envie a última linha se não completou 3
        if row: kb.append(row)

        await update.message.reply_text(f"Bem-vindo ao Idle War! Escolha sua classe:", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await show_main_menu(update, player)
    db.close()

async def show_main_menu(update: Update, player: Player):
    keyboard = [
        [InlineKeyboardButton("Status 👤", callback_data='menu_status'),
         InlineKeyboardButton("Batalhar ⚔️", callback_data='menu_battle_mode'),
         InlineKeyboardButton("Diário 🎁", callback_data='menu_daily')],
        [InlineKeyboardButton("Fazenda 🌾", callback_data='menu_farm'),
         InlineKeyboardButton("Ranking 🏆", callback_data='menu_ranking'),
         InlineKeyboardButton("LOJA VIP 💎", callback_data='menu_shop')],
        [InlineKeyboardButton("Guilda 🛡️", callback_data='menu_guild'),
         InlineKeyboardButton("Upgrade 💪", callback_data='menu_upgrade'),
         InlineKeyboardButton("Atualizar 🔄", callback_data='menu_refresh')]
    ]
    
    xp_needed = player.level * 100
    perc = (player.xp / xp_needed) * 100
    
    text = (f"**{player.name}** (Lvl {player.level} {player.class_name})\n"
            f"Exp: {format_number(player.xp)}/{format_number(xp_needed)} ({perc:.2f}%)\n"
            f"❤️ HP: {player.health}/{player.max_health}\n"
            f"⚡ Stamina: {player.stamina}/{player.max_stamina}\n"
            f"💰 {format_number(player.gold)} | 💎 {player.gems}")
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except Exception as e:
        print(f"Erro ao mostrar menu: {e}")

# --- CRIAÇÃO DE PERSONAGEM (CORRIGIDO) ---
async def handle_class_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    try:
        # DIAGNÓSTICO: Verifique nos logs do Render se isso aparece
        print(f"DEBUG: Botão clicado: {query.data}") 

        # Remove o prefixo 'class_' para pegar o nome puro
        raw_choice = query.data.replace('class_', '')
        
        # Lógica do Aleatório CORRIGIDA e BLINDADA
        if raw_choice == 'Aleatorio':
            final_class = random.choice(list(BASE_STATS.keys()))
            print(f"DEBUG: Aleatório sorteou: {final_class}")
        else:
            final_class = raw_choice
            print(f"DEBUG: Classe escolhida: {final_class}")

        # Salva no contexto TEMPORÁRIO
        context.user_data['temp_class'] = final_class
        context.user_data['waiting_name'] = True
        
        desc = BASE_STATS[final_class].get('desc', 'Classe balanceada.')
        
        await query.edit_message_text(
            f"Classe **{final_class}** selecionada! ✅\n_{desc}_\n\n"
            "Digite o **NOME** do personagem (Máx 15 letras, sem espaços):", 
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"ERRO CRÍTICO no handle_class_selection: {e}")
        await query.edit_message_text("❌ Ocorreu um erro ao selecionar a classe. Tente digitar /start novamente.")

async def receive_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = context.user_data
    
    # 1. Flow de Nome
    if user_data.get('waiting_name'):
        raw = update.message.text.strip()
        clean = raw.replace(" ", "")[:15]
        
        if len(clean) < 3:
            await update.message.reply_text("Nome muito curto! Mínimo 3 letras.")
            return

        user_data['temp_name'] = clean
        
        # Recupera a classe para mostrar na confirmação
        chosen_class = user_data.get('temp_class', 'Desconhecida')
        
        kb = [[InlineKeyboardButton("✅ Confirmar", callback_data='confirm_name_yes'), InlineKeyboardButton("✏️ Alterar", callback_data='confirm_name_no')]]
        await update.message.reply_text(f"Nome: **{clean}**\nClasse: **{chosen_class}**\n\nConfirma?", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        return

    # 2. Flow de Guilda (Nome)
    if user_data.get('waiting_guild_name'):
        raw = update.message.text.strip()
        clean = raw.replace(" ", "")[:15]
        user_data['temp_guild_name'] = clean
        user_data['waiting_guild_name'] = False
        user_data['waiting_guild_link'] = True 
        await update.message.reply_text(f"Nome da Guilda: **{clean}**\n\nAgora, envie o **Link do Grupo Telegram** (deve começar com https://t.me/ ou https://telegram.me/):")
        return

    # 3. Flow de Guilda (Link)
    if user_data.get('waiting_guild_link'):
        link = update.message.text.strip()
        if not (link.startswith("https://t.me/") or link.startswith("https://telegram.me/")):
            await update.message.reply_text("🚫 Link inválido! Deve começar com https://t.me/ ...")
            return
        
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
            await update.message.reply_text(f"✅ Guilda **{g_name}** criada!")
        except Exception:
            await update.message.reply_text("Erro: Nome de guilda já existe.")
        db.close()

async def confirm_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    if query.data == 'confirm_name_no':
        await query.edit_message_text("Digite o nome novamente:")
        return

    # RECUPERAÇÃO SEGURA DOS DADOS
    name = context.user_data.get('temp_name')
    c_class = context.user_data.get('temp_class')
    
    # Se por algum motivo a memória falhou (reinício do servidor), aborta com segurança
    if not name or not c_class:
        await query.edit_message_text("⚠️ Erro de sessão (demorou muito?). Digite /start para tentar de novo.")
        return

    db = get_db()
    s = BASE_STATS.get(c_class, BASE_STATS['Guerreiro']) # Fallback para Guerreiro se der erro
    
    p = Player(id=update.effective_user.id, name=name, class_name=c_class,
               health=s['hp'], max_health=s['hp'], strength=s['str'], intelligence=s['int'], defense=s['def'],
               speed=s['spd'], crit_chance=s['crit'], gold=INITIAL_GOLD)
    db.add(p)
    db.commit()
    db.close()
    
    context.user_data['waiting_name'] = False
    await query.edit_message_text(f"🎉 Personagem **{name}** ({c_class}) criado! Use /start.")

# --- MENUS DE GAMEPLAY ---
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    db = get_db()
    player = get_player(query.from_user.id, db)
    if not player: return

    # --- FAZENDA ---
    if data == 'menu_farm':
        now = datetime.now()
        elapsed = (now - player.last_farm_harvest).total_seconds() / 3600
        prod_rate = player.farm_level * 10 
        cap = player.barn_level * 100
        avail = min(int(elapsed * prod_rate), cap)
        
        kb = [[InlineKeyboardButton(f"💰 Vender (+{avail}g)", callback_data='farm_harvest')],
              [InlineKeyboardButton("⬆️ Campo (1k)", callback_data='farm_up_field'), InlineKeyboardButton("⬆️ Celeiro (1k)", callback_data='farm_up_barn')],
              [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
        
        msg = f"🌾 **Fazenda**\n🚜 {prod_rate}/h | 🏚️ {avail}/{cap}\n⏳ Offline: {elapsed:.1f}h"
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'farm_harvest':
        now = datetime.now()
        elapsed = (now - player.last_farm_harvest).total_seconds() / 3600
        avail = min(int(elapsed * player.farm_level * 10), player.barn_level * 100)
        
        if avail > 0:
            player.gold += avail
            player.last_farm_harvest = now
            db.commit()
            await query.answer(f"Vendeu por {avail}g!")
            await handle_menu(update, context)
        else:
            await query.answer("Nada para colher.")

    elif data in ['farm_up_field', 'farm_up_barn']:
        if player.gold >= 1000:
            player.gold -= 1000
            if data == 'farm_up_field': player.farm_level += 1
            else: player.barn_level += 1
            db.commit()
            await query.answer("Melhoria realizada!")
            await handle_menu(update, context)
        else:
            await query.answer("Sem ouro (1000g)!", show_alert=True)

    # --- GUILDA ---
    elif data == 'menu_guild':
        if player.guild_id:
            guild = db.query(Guild).filter(Guild.id == player.guild_id).first()
            kb = [[InlineKeyboardButton("💬 Grupo Telegram", url=guild.telegram_link)],
                  [InlineKeyboardButton("🚪 Sair", callback_data='guild_leave')],
                  [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
            await query.edit_message_text(f"🛡️ **{guild.name}**\n👥 Membros: {guild.member_count}/50", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        else:
            kb = [[InlineKeyboardButton(f"Criar ({GUILD_CREATE_COST} Gemas)", callback_data='guild_create_start')],
                  [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
            await query.edit_message_text("Sem guilda.", reply_markup=InlineKeyboardMarkup(kb))

    elif data == 'guild_create_start':
        if player.level < GUILD_MIN_LEVEL: await query.answer(f"Nível {GUILD_MIN_LEVEL} necessário!", show_alert=True); return
        if player.gems < GUILD_CREATE_COST: await query.answer(f"Faltam Gemas ({GUILD_CREATE_COST})!", show_alert=True); return
        context.user_data['waiting_guild_name'] = True
        await query.edit_message_text("🛡️ Digite o **Nome da Guilda**:", parse_mode='Markdown')

    elif data == 'guild_leave':
        if player.guild_id:
            g = db.query(Guild).filter(Guild.id == player.guild_id).first()
            g.member_count -= 1
            player.guild_id = None
            db.commit()
            await query.edit_message_text("Saiu da guilda.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))

    # --- OUTROS ---
    elif data == 'menu_shop':
        await query.edit_message_text("💎 **LOJA VIP**\n🚧 Em breve via XSolla.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))

    elif data == 'menu_daily':
        now = datetime.now()
        if (now - player.last_daily_claim) > timedelta(hours=24):
            kb = [[InlineKeyboardButton("💰 Coletar", callback_data='daily_claim_now')], [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
            await query.edit_message_text("🎁 Recompensa pronta!", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await query.edit_message_text("🎁 Volte amanhã.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))
    
    elif data == 'daily_claim_now':
        player.gold += 1000; player.xp += 1000; player.last_daily_claim = datetime.now(); player.stamina = player.max_stamina
        check_level_up(player)
        db.commit()
        await query.edit_message_text("✅ Coletado!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))

    elif data == 'menu_ranking':
        top = db.query(Player).order_by(Player.pvp_rating.desc()).limit(10).all()
        msg = "🏆 **Top 10**\n" + "\n".join([f"{i+1}. {p.name} ({p.pvp_rating})" for i, p in enumerate(top)])
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]), parse_mode='Markdown')

    elif data == 'menu_upgrade':
        # Menu de Upgrade Simplificado (Stats)
        c_str = int(50 + (player.strength * 20))
        kb = [[InlineKeyboardButton(f"Força +1 ({c_str}g)", callback_data='up_str')],
              [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
        await query.edit_message_text(f"💪 Força: {player.strength}\n💰 Ouro: {player.gold}", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith('up_'):
        # Lógica de upgrade rápida
        cost = int(50 + (player.strength * 20))
        if player.gold >= cost:
            player.gold -= cost
            player.strength += 1
            db.commit()
            await query.answer("Sucesso!")
            await handle_menu(update, context)
        else:
            await query.answer("Sem ouro!", show_alert=True)

    # --- BATALHA ---
    elif data == 'menu_battle_mode':
        kb = [[InlineKeyboardButton("Campanha (PVE)", callback_data='battle_pve_start'), InlineKeyboardButton("Ranked (PVP)", callback_data='battle_pvp_start')], [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
        await query.edit_message_text("Modo:", reply_markup=InlineKeyboardMarkup(kb))

    elif data == 'battle_pve_start':
        m = generate_monster(player.current_phase_id)
        context.user_data['monster'] = m
        msg = f"🗺️ **Fase {player.current_phase_id}**\n🔥 **{m['name']}**\nHP: {m['hp']}\n💰 {m['gold']}g"
        kb = [[InlineKeyboardButton("⚔️ LUTAR", callback_data='confirm_pve')], [InlineKeyboardButton("🔙", callback_data='menu_battle_mode')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'confirm_pve':
        if player.stamina < STAMINA_COST: await query.answer("Sem stamina!", show_alert=True); return
        player.stamina -= STAMINA_COST
        m = context.user_data.get('monster')
        
        # Batalha Simples e Robusta
        p_pwr = (player.strength * 2) + player.intelligence
        win = random.random() < 0.6 # 60% chance base
        
        if win:
            player.gold += m['gold']; player.xp += m['xp']; player.current_phase_id += 1
            check_level_up(player)
            msg = f"🏆 **VITÓRIA!**\n+ {m['gold']}g | + {m['xp']}xp"
        else:
            loss = 10
            player.health = max(0, player.health - loss)
            msg = f"☠️ **DERROTA...**\nPerdeu {loss} HP"

        db.commit()
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Continuar", callback_data='menu_refresh')]]), parse_mode='Markdown')
    
    # Refresh Genérico
    elif data == 'menu_refresh' or data == 'menu_status':
        await show_main_menu(update, player)

    db.close()

def main_bot(token: str) -> Application:
    init_db()
    app = Application.builder().token(token).build()
    
    # HANDLERS - A ORDEM IMPORTA
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cheat", admin_cheat))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text_input))
    
    # Callback Handlers
    # 1. Classes e Confirmação de Nome (Prioridade)
    app.add_handler(CallbackQueryHandler(handle_class_selection, pattern='^class_'))
    app.add_handler(CallbackQueryHandler(confirm_name_handler, pattern='^confirm_name_'))
    
    # 2. Upgrades Específicos
    app.add_handler(CallbackQueryHandler(handle_menu, pattern='^up_'))
    
    # 3. Menu Geral (Pega o resto)
    app.add_handler(CallbackQueryHandler(handle_menu))
    
    return app
