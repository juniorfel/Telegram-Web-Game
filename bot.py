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
        p.level = 50 # Sobe para testar guilda
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
            row.append(InlineKeyboardButton(label, callback_data=f'class_{c}'))
            if len(row) == 3:
                kb.append(row)
                row = []
        await update.message.reply_text(f"Bem-vindo ao Idle War! Escolha sua classe:", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await show_main_menu(update, player)
    db.close()

async def show_main_menu(update: Update, player: Player):
    keyboard = [
        [InlineKeyboardButton("Status 👤", callback_data='menu_status'),
         InlineKeyboardButton("Batalhar ⚔️", callback_data='menu_battle_mode'),
         InlineKeyboardButton("Diário 🎁", callback_data='menu_daily')],
        [InlineKeyboardButton("Fazenda 🌾", callback_data='menu_farm'), # NOVO BOTÃO
         InlineKeyboardButton("Ranking 🏆", callback_data='menu_ranking'),
         InlineKeyboardButton("LOJA VIP 💎", callback_data='menu_shop')],
        [InlineKeyboardButton("Guilda 🛡️", callback_data='menu_guild'),
         InlineKeyboardButton("Upgrade 💪", callback_data='menu_upgrade'),
         InlineKeyboardButton("Atualizar 🔄", callback_data='menu_refresh')]
    ]
    
    xp_needed = player.level * 100
    perc = (player.xp / xp_needed) * 100
    
    # Interface Limpa (Sem fase aqui)
    text = (f"**{player.name}** (Lvl {player.level} {player.class_name})\n"
            f"Exp: {format_number(player.xp)}/{format_number(xp_needed)} ({perc:.2f}%)\n"
            f"❤️ HP: {player.health}/{player.max_health}\n"
            f"⚡ Stamina: {player.stamina}/{player.max_stamina}\n"
            f"💰 {format_number(player.gold)} | 💎 {player.gems}")
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# --- CRIAÇÃO DE PERSONAGEM ---
async def handle_class_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    c = query.data.split('_')[1]
    if c == 'Aleatorio': c = random.choice(list(BASE_STATS.keys()))
    context.user_data['temp_class'] = c
    context.user_data['waiting_name'] = True
    
    desc = BASE_STATS[c].get('desc', '')
    await query.edit_message_text(f"Classe **{c}** selecionada!\n_{desc}_\n\nDigite o NOME do personagem (Máx 15 letras, sem espaços):", parse_mode='Markdown')

async def receive_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Handler genérico para Nome e Link de Guilda
    user_data = context.user_data
    
    # 1. Flow de Nome
    if user_data.get('waiting_name'):
        raw = update.message.text.strip()
        clean = raw.replace(" ", "")[:15]
        user_data['temp_name'] = clean
        kb = [[InlineKeyboardButton("✅ Confirmar", callback_data='confirm_name_yes'), InlineKeyboardButton("✏️ Alterar", callback_data='confirm_name_no')]]
        await update.message.reply_text(f"Nome: **{clean}**\nConfirma?", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        return

    # 2. Flow de Guilda (Nome)
    if user_data.get('waiting_guild_name'):
        raw = update.message.text.strip()
        clean = raw.replace(" ", "")[:15]
        user_data['temp_guild_name'] = clean
        user_data['waiting_guild_name'] = False
        user_data['waiting_guild_link'] = True # Próximo passo
        await update.message.reply_text(f"Nome da Guilda: **{clean}**\n\nAgora, envie o **Link do Grupo Telegram** (deve começar com https://t.me/ ou https://telegram.me/):")
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
            await update.message.reply_text(f"✅ Guilda **{g_name}** criada com sucesso!\nUse o menu para ver detalhes.")
        except Exception:
            await update.message.reply_text("Erro: Já existe uma guilda com esse nome.")
        db.close()

async def confirm_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == 'confirm_name_no':
        await query.edit_message_text("Digite o nome novamente:")
        return

    name = context.user_data['temp_name']
    c_class = context.user_data['temp_class']
    db = get_db()
    s = BASE_STATS[c_class]
    p = Player(id=update.effective_user.id, name=name, class_name=c_class,
               health=s['hp'], max_health=s['hp'], strength=s['str'], intelligence=s['int'], defense=s['def'],
               speed=s['spd'], crit_chance=s['crit'], gold=INITIAL_GOLD)
    db.add(p)
    db.commit()
    db.close()
    context.user_data['waiting_name'] = False
    await query.edit_message_text(f"Personagem **{name}** criado! Use /start.")

# --- MENUS ---
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    db = get_db()
    player = get_player(query.from_user.id, db)
    if not player: return

    # --- FAZENDA (FARM) ---
    if data == 'menu_farm':
        now = datetime.now()
        elapsed = (now - player.last_farm_harvest).total_seconds() / 3600 # Horas passadas
        
        # Produção: 10 * Nivel Trigo / hora
        production_rate = player.farm_level * 10 
        storage_cap = player.barn_level * 100
        
        generated = int(elapsed * production_rate)
        available = min(generated, storage_cap)
        
        kb = [
            [InlineKeyboardButton(f"💰 Vender Colheita (+{available}g)", callback_data='farm_harvest')],
            [InlineKeyboardButton(f"⬆️ Melhorar Campo (1000g)", callback_data='farm_up_field')],
            [InlineKeyboardButton(f"⬆️ Melhorar Celeiro (1000g)", callback_data='farm_up_barn')],
            [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]
        ]
        
        msg = (f"🌾 **Fazenda de {player.name}**\n\n"
               f"🚜 Produção: {production_rate} Trigos/hora\n"
               f"🏚️ Celeiro: {available}/{storage_cap} Armazenado\n"
               f"⏳ Tempo offline: {elapsed:.1f} horas")
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'farm_harvest':
        now = datetime.now()
        elapsed = (now - player.last_farm_harvest).total_seconds() / 3600
        production_rate = player.farm_level * 10
        storage_cap = player.barn_level * 100
        
        generated = int(elapsed * production_rate)
        available = min(generated, storage_cap)
        
        if available > 0:
            player.gold += available
            player.last_farm_harvest = now
            db.commit()
            await query.answer(f"Você vendeu {available} Trigos por {available} Ouro!")
            # Recarrega menu da fazenda
            await handle_menu(update, context) # Recursivo seguro aqui pois muda o data
        else:
            await query.answer("Nada para colher ainda!")

    elif data == 'farm_up_field':
        if player.gold >= 1000:
            player.gold -= 1000
            player.farm_level += 1
            db.commit()
            await query.answer("Campo melhorado! Produção aumentou.")
            await handle_menu(update, context) # Refresh
        else:
            await query.answer("Sem ouro suficiente (1000g)", show_alert=True)

    elif data == 'farm_up_barn':
        if player.gold >= 1000:
            player.gold -= 1000
            player.barn_level += 1
            db.commit()
            await query.answer("Celeiro melhorado! Capacidade aumentou.")
            await handle_menu(update, context) # Refresh
        else:
            await query.answer("Sem ouro suficiente (1000g)", show_alert=True)

    # --- GUILDA ---
    elif data == 'menu_guild':
        if player.guild_id:
            guild = db.query(Guild).filter(Guild.id == player.guild_id).first()
            kb = [
                [InlineKeyboardButton("💬 Entrar no Grupo Telegram", url=guild.telegram_link)],
                [InlineKeyboardButton("🚪 Sair da Guilda", callback_data='guild_leave')],
                [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]
            ]
            msg = f"🛡️ **{guild.name}**\n👑 Líder ID: {guild.leader_id}\n👥 Membros: {guild.member_count}/50"
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        else:
            kb = [[InlineKeyboardButton(f"Criar Guilda ({GUILD_CREATE_COST} Gemas)", callback_data='guild_create_start')],
                  [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
            await query.edit_message_text("Você não tem guilda.", reply_markup=InlineKeyboardMarkup(kb))

    elif data == 'guild_create_start':
        if player.level < GUILD_MIN_LEVEL:
            await query.answer(f"Precisa ser Nível {GUILD_MIN_LEVEL}!", show_alert=True); return
        if player.gems < GUILD_CREATE_COST:
            await query.answer(f"Precisa de {GUILD_CREATE_COST} Gemas!", show_alert=True); return
        
        context.user_data['waiting_guild_name'] = True
        await query.edit_message_text("🛡️ **Criando Guilda**\n\nDigite o **Nome da Guilda** (Máx 15 letras, sem espaços):", parse_mode='Markdown')

    elif data == 'guild_leave':
        if player.guild_id:
            g = db.query(Guild).filter(Guild.id == player.guild_id).first()
            g.member_count -= 1
            player.guild_id = None
            db.commit()
            await query.edit_message_text("Você saiu da guilda.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Voltar", callback_data='menu_refresh')]]))

    # --- LOJA / DIARIO / RANKING (Código anterior mantido simplificado) ---
    elif data == 'menu_shop':
        kb = [[InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
        await query.edit_message_text("💎 **LOJA VIP**\n\n🚧 Em breve: Gemas e Pacotes via XSolla.", reply_markup=InlineKeyboardMarkup(kb))

    elif data == 'menu_daily':
        now = datetime.now()
        if (now - player.last_daily_claim) > timedelta(hours=24):
            kb = [[InlineKeyboardButton("💰 Coletar (1000g + 1000xp)", callback_data='daily_claim_now')], [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
            await query.edit_message_text("🎁 Recompensa disponível!", reply_markup=InlineKeyboardMarkup(kb))
        else:
            kb = [[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
            await query.edit_message_text("🎁 Volte amanhã.", reply_markup=InlineKeyboardMarkup(kb))
    
    elif data == 'daily_claim_now':
        player.gold += 1000; player.xp += 1000; player.last_daily_claim = datetime.now(); player.stamina = player.max_stamina
        check_level_up(player)
        db.commit()
        await query.edit_message_text("✅ Coletado!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Voltar", callback_data='menu_refresh')]]))

    elif data == 'menu_ranking':
        top = db.query(Player).order_by(Player.pvp_rating.desc()).limit(10).all()
        msg = "🏆 **Top 10**\n" + "\n".join([f"{i+1}. {p.name} ({p.pvp_rating})" for i, p in enumerate(top)])
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]), parse_mode='Markdown')

    # --- BATALHA (Atualizado com Passivas e Fase Visual) ---
    elif data == 'menu_battle_mode':
        kb = [[InlineKeyboardButton("Campanha (PVE)", callback_data='battle_pve_start'), InlineKeyboardButton("Ranked (PVP)", callback_data='battle_pvp_start')], [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
        await query.edit_message_text("Escolha o modo:", reply_markup=InlineKeyboardMarkup(kb))

    elif data == 'battle_pve_start':
        m = generate_monster(player.current_phase_id)
        context.user_data['monster'] = m
        # FASE APARECE AQUI AGORA
        msg = (f"🗺️ **Fase {player.current_phase_id}**\n\n"
               f"🔥 **{m['name']}**\nHP: {m['hp']} | Spd: {m['spd']}\n"
               f"Atk: {m['atk']} | Def: {m['def']}\n"
               f"💰 {m['gold']}g | ✨ {m['xp']}xp")
        kb = [[InlineKeyboardButton("⚔️ LUTAR (1 Stamina)", callback_data='confirm_pve')], [InlineKeyboardButton("🔙", callback_data='menu_battle_mode')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'confirm_pve':
        if player.stamina < STAMINA_COST: await query.answer("Sem stamina!", show_alert=True); return
        player.stamina -= STAMINA_COST
        m = context.user_data['monster']
        
        # --- LÓGICA DE BATALHA COM PASSIVAS ---
        log = []
        
        # Passiva: Guerreiro (Bloqueio)
        dmg_taken_mult = 0.0 if (player.class_name == 'Guerreiro' and random.random() < 0.1) else 1.0
        if dmg_taken_mult == 0: log.append("🛡️ **BLOQUEIO!** Dano anulado!")

        # Passiva: Mago (Penetração)
        ignore_def = 0.2 if player.class_name == 'Mago' else 0.0
        
        # Passiva: Arqueiro (Crit Bonus)
        crit_bonus = 15 if player.class_name == 'Arqueiro' else 0
        is_crit = random.randint(1, 100) <= (player.crit_chance + crit_bonus)
        dmg_mult = 2.0 if is_crit else 1.0
        if is_crit: log.append("💥 **CRÍTICO!**")
        
        # Passiva: Assassino (Ataque Duplo)
        attacks = 2 if (player.class_name == 'Assassino' and random.random() < 0.15) else 1
        if attacks == 2: log.append("⚔️ **ATAQUE DUPLO!**")
        
        # Passiva: Feiticeiro (Miss Inimigo)
        enemy_hit_chance = 0.9 if player.class_name == 'Feiticeiro' else 1.0

        # Passiva: Paladino (Cura)
        lifesteal = 0.05 if player.class_name == 'Paladino' else 0.0

        # Passiva: Ogro (Redução Fixa)
        flat_red = 5 if player.class_name == 'Ogro' else 0

        # Passiva: Necromante (Reviver) - Checado na derrota

        # --- CÁLCULO FINAL ---
        total_dmg_dealt = 0
        m_def_eff = m['def'] * (1 - ignore_def)
        
        for _ in range(attacks):
            p_pwr = ((player.strength * 2) + player.intelligence) * dmg_mult
            # Fórmula simples de dano
            dmg = max(1, (p_pwr - m_def_eff))
            total_dmg_dealt += dmg

        # Chance de Vitória baseada no Dano vs HP Monstro
        turns_to_kill = m['hp'] / max(1, total_dmg_dealt)
        
        # Dano do Monstro
        m_dmg = max(1, m['atk'] - (player.defense * 0.5) - flat_red)
        if random.random() > enemy_hit_chance: m_dmg = 0; log.append("🐍 Inimigo errou!")
        
        turns_to_die = player.health / max(1, m_dmg * dmg_taken_mult)
        
        win = turns_to_kill <= turns_to_die
        
        # Necromante Save
        if not win and player.class_name == 'Necromante' and random.random() < 0.1:
            win = True; log.append("💀 **MORTO-VIVO!** Você se recusou a morrer!")

        if win:
            heal = int(total_dmg_dealt * lifesteal)
            if heal > 0: player.health = min(player.max_health, player.health + heal); log.append(f"✨ Curou {heal} HP")
            
            player.gold += m['gold']
            player.xp += m['xp']
            player.current_phase_id += 1
            if check_level_up(player): log.append("🎉 **LEVEL UP!**")
            msg = "\n".join(log) + f"\n\n🏆 **VITÓRIA!**\nInimigo: {m['name']}\n+ {m['gold']}g | + {m['xp']}xp"
        else:
            loss = int(m_dmg * dmg_taken_mult)
            player.health = max(0, player.health - loss)
            msg = "\n".join(log) + f"\n\n☠️ **DERROTA...**\nVocê levou {loss} de dano."

        db.commit()
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Continuar", callback_data='menu_refresh')]]), parse_mode='Markdown')

    elif data == 'menu_refresh':
        await show_main_menu(update, player)

    db.close()

def main_bot(token: str) -> Application:
    init_db()
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cheat", admin_cheat))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text_input))
    app.add_handler(CallbackQueryHandler(handle_class_selection, pattern='^class_'))
    app.add_handler(CallbackQueryHandler(confirm_name_handler, pattern='^confirm_name_'))
    app.add_handler(CallbackQueryHandler(handle_menu))
    return app
