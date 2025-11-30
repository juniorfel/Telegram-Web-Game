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
RESPEC_COST = 100 # Custo em Gemas para mudar classe

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
VALID_CLASSES = list(BASE_STATS.keys())

# --- Funções Auxiliares ---
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
        # GERA O RESUMO DE ATRIBUTOS
        class_summary = "📊 **ATRIBUTOS INICIAIS**\n"
        for name, data in BASE_STATS.items():
            desc = data.get('desc', 'Nenhuma descrição disponível.')
            summary = (
                f"\n**{name}**: {desc}\n"
                f"   ❤️ {data['hp']} | 💪 {data['str']} STR | 🧠 {data['int']} INT | 🛡️ {data['def']} DEF"
            )
            class_summary += summary

        msg = (
            "✨ **A Névoa se Dissipa!** ✨\n\n"
            "Viajante, o destino final dos Reinos de Aerthos repousa em sua escolha. "
            "Os campos de **Idle War** aguardam o clamor de uma nova lenda.\n"
            f"\n{class_summary}\n"
            "\nQual poder ancestral você irá empunhar?"
        )

        kb = []
        row = []
        classes = list(BASE_STATS.keys()) + ['Aleatorio']
        for c in classes:
            label = f"{c} 🎲" if c == 'Aleatorio' else c
            row.append(InlineKeyboardButton(label, callback_data=f'class_{c}'))
            if len(row) == 3: kb.append(row); row = []
        
        if row: kb.append(row) # Garante linha final

        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    else:
        heal_amount = apply_passive_healing(player, db)
        db.commit()
        await show_main_menu(update, player)
        if heal_amount > 0:
             await context.bot.send_message(chat_id=user.id, text=f"✨ Você se regenerou **+{heal_amount} HP** enquanto estava offline!", parse_mode='Markdown')
    db.close()

async def show_main_menu(update: Update, player: Player):
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

# --- SELEÇÃO DE CLASSE ---
async def handle_class_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    class_choice = query.data.split('_')[1]
    
    if class_choice == 'Aleatorio':
        class_choice = random.choice(VALID_CLASSES) 
        
    context.user_data['temp_class'] = class_choice
    context.user_data['waiting_name'] = True
    
    desc = BASE_STATS[class_choice].get('desc', 'Nenhuma descrição disponível.')
    await query.edit_message_text(
        f"Classe **{class_choice}** selecionada!\n_{desc}_\n\nDigite o NOME do personagem (Máx 15 letras, sem espaços):",
        parse_mode='Markdown'
    )

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
        await update.message.reply_text(f"Nome da Guilda: **{clean}**\n\nAgora, envie o **Link do Grupo Telegram**:", parse_mode='Markdown')
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
            player.gems -= GUILD_CREATE_COST; player.guild_id = new_guild.id; db.commit()
            user_data['waiting_guild_link'] = False
            await update.message.reply_text(f"✅ Guilda **{g_name}** criada!")
        except Exception:
            await update.message.reply_text("Erro: Nome de guilda já existe.")
        db.close()
        return

    # 4. Flow de Doação
    donation_type = user_data.get('waiting_donation_type')
    if donation_type in ['gold', 'gems']:
        db = get_db()
        player = get_player(update.effective_user.id, db)
        if player and player.guild_id:
            guild = db.query(Guild).filter(Guild.id == player.guild_id).first()
            try:
                amount = int(update.message.text.strip())
                if amount <= 0: raise ValueError
            except ValueError:
                await update.message.reply_text(f"Valor inválido. Digite um número positivo.")
                return
            
            success = False
            if donation_type == 'gold' and player.gold >= amount:
                player.gold -= amount; guild.treasury_gold += amount; success = True
            elif donation_type == 'gems' and player.gems >= amount:
                player.gems -= amount; guild.treasury_gems += amount; success = True
            
            db.commit()
            if success: await update.message.reply_text(f"✅ Doou {amount} {donation_type}!")
            else: await update.message.reply_text(f"🚫 Saldo insuficiente.")
            
        user_data['waiting_donation_type'] = None
        db.close()

async def confirm_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    if query.data == 'confirm_name_no':
        context.user_data['waiting_name'] = True
        await query.edit_message_text("Ok! Digite o nome novamente:")
        return

    name = context.user_data.get('temp_name')
    c_class = context.user_data.get('temp_class')
    user = update.effective_user
    db = get_db()
    stats = BASE_STATS[c_class]
        
    new_player = Player(
        id=user.id, username=user.username, name=name, class_name=c_class,
        health=stats['hp'], max_health=stats['hp'], strength=stats['str'], intelligence=stats['int'], defense=stats['def'],
        speed=stats['spd'], crit_chance=stats['crit'], gold=INITIAL_GOLD
    )
    db.add(new_player)
    db.commit()
    
    ref_msg = ""
    rid = context.user_data.get('referrer_id')
    if rid:
        referrer = get_player(rid, db)
        if referrer:
            referrer.gems += REFERRAL_GEMS_INVITER; referrer.gold += REFERRAL_GOLD_INVITER
            new_player.gems += REFERRAL_GEMS_NEW; new_player.gold += REFERRAL_GOLD_NEW
            db.commit()
            ref_msg = f"\n\n🎁 **BÔNUS AFILIADO!**\nVocê ganhou {REFERRAL_GEMS_NEW}💎 e {REFERRAL_GOLD_NEW}💰."

    db.close()
    context.user_data['waiting_name'] = False
    await query.edit_message_text(f"Personagem **{name}** criado!{ref_msg}\nUse /start.", parse_mode='Markdown')

# --- HANDLER GERAL DE MENUS ---
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    db = get_db()
    player = get_player(query.from_user.id, db)
    if not player: return

    # --- CORREIO ---
    if data == 'menu_mailbox':
        kb = [[InlineKeyboardButton("Canal Oficial 📢", url=OFFICIAL_CHANNEL_LINK)], [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
        await query.edit_message_text("✉️ **Correio & Eventos**\n\nNovidades no canal oficial.", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    
    # --- INFO ---
    elif data == 'menu_info':
        link = f"https://t.me/{BOT_USERNAME}?start={player.id}"
        msg = (f"**Status de {player.name}**\n💪 {player.strength} STR | 🧠 {player.intelligence} INT\n🛡️ {player.defense} DEF | ⚡ {player.speed} SPD\n💥 {player.crit_chance}% CRIT\n\n🔗 **AFILIADO:**\n`{link}`")
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]), parse_mode='Markdown')

    # --- DIÁRIO ---
    elif data == 'menu_daily':
        now = datetime.now()
        if (now - player.last_daily_claim) > timedelta(hours=24):
            kb = [[InlineKeyboardButton("💰 Coletar", callback_data='daily_claim_now')], [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
            await query.edit_message_text("🎁 Recompensa Pronta!", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await query.edit_message_text("🎁 Volte amanhã.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))
    
    elif data == 'daily_claim_now':
        player.gold += 1000; player.xp += 1000; player.last_daily_claim = datetime.now(); player.stamina = player.max_stamina
        check_level_up(player); db.commit()
        await query.edit_message_text("✅ Coletado!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))

    # --- RANKING ---
    elif data == 'menu_ranking':
        top = db.query(Player).order_by(Player.pvp_rating.desc()).limit(10).all()
        msg = "🏆 **Top 10**\n" + "\n".join([f"{i+1}. {p.name} ({p.pvp_rating})" for i, p in enumerate(top)])
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]), parse_mode='Markdown')

    # --- LOJA ---
    elif data == 'menu_shop':
        await query.edit_message_text("💎 **LOJA VIP**\n🚧 Em breve via XSolla.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))

    # --- BATALHA ---
    elif data == 'menu_battle_mode':
        kb = [[InlineKeyboardButton("Campanha (PVE)", callback_data='battle_pve_start'), InlineKeyboardButton("Ranked (PVP)", callback_data='battle_pvp_start')], [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
        await query.edit_message_text("Escolha:", reply_markup=InlineKeyboardMarkup(kb))

    elif data == 'battle_pve_start':
        m = generate_monster(player.current_phase_id)
        context.user_data['monster'] = m
        kb = [[InlineKeyboardButton("⚔️ LUTAR", callback_data='confirm_pve')], [InlineKeyboardButton("🔙", callback_data='menu_battle_mode')]]
        await query.edit_message_text(f"🔥 **{m['name']}**\nHP: {m['hp']} | 💰 {m['gold']}g", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'confirm_pve':
        if player.stamina < STAMINA_COST: await query.answer("Sem stamina!", show_alert=True); return
        player.stamina -= STAMINA_COST
        m = context.user_data.get('monster')
        win = random.random() < 0.6
        if win:
            player.gold += m['gold']; player.xp += m['xp']; player.current_phase_id += 1; check_level_up(player)
            msg = f"🏆 **VITÓRIA!**\n+ {m['gold']}g"
        else:
            player.health = max(0, player.health - 10)
            msg = "☠️ **DERROTA...**"
        db.commit()
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Continuar", callback_data='menu_battle_mode')]]), parse_mode='Markdown')

    elif data == 'battle_pvp_start':
        opp = db.query(Player).filter(Player.id != player.id).order_by(Player.pvp_rating.desc()).first()
        if not opp: await query.edit_message_text("Sem oponentes.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_battle_mode')]])); return
        context.user_data['opponent_id'] = opp.id
        kb = [[InlineKeyboardButton(f"⚔️ DESAFIAR {opp.name}", callback_data='confirm_pvp')], [InlineKeyboardButton("🔙", callback_data='menu_battle_mode')]]
        await query.edit_message_text(f"🆚 **{opp.name}**\nRating: {opp.pvp_rating}", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'confirm_pvp':
        if player.stamina < STAMINA_COST: await query.answer("Sem stamina!", show_alert=True); return
        opp = db.query(Player).filter(Player.id == context.user_data.get('opponent_id')).first()
        player.stamina -= STAMINA_COST
        if not opp: return
        if (player.strength + player.defense) > (opp.strength + opp.defense):
            player.pvp_rating += 25; msg = "🏆 **Vitória Ranqueada!**"
        else:
            player.pvp_rating = max(0, player.pvp_rating - 15); msg = "🏳️ **Derrota...**"
        db.commit()
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Continuar", callback_data='menu_battle_mode')]]), parse_mode='Markdown')

    # --- UPGRADE & RESPEC ---
    elif data == 'menu_upgrade':
        c_str = int(50 + (player.strength * 20))
        kb = [[InlineKeyboardButton(f"Força +1 ({c_str}g)", callback_data='up_str')],
              [InlineKeyboardButton(f"🔄 Mudar Classe ({RESPEC_COST} Gemas)", callback_data='respec_start')],
              [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
        await query.edit_message_text("Upgrade:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith('up_'):
        cost = int(50 + (player.strength * 20))
        if player.gold >= cost:
            player.gold -= cost; player.strength += 1; db.commit()
            await query.answer("Sucesso!")
            await handle_menu(update, context)
        else: await query.answer("Sem ouro!", show_alert=True)

    elif data == 'respec_start':
        if player.gems < RESPEC_COST: await query.answer(f"Precisa de {RESPEC_COST} Gemas!", show_alert=True); return
        kb = []; row = []
        for c in list(BASE_STATS.keys()) + ['Aleatorio']:
            row.append(InlineKeyboardButton(c, callback_data=f'respec_{c}'))
            if len(row) == 3: kb.append(row); row = []
        if row: kb.append(row)
        await query.edit_message_text(f"Mudar classe: {RESPEC_COST} Gemas.", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith('respec_'):
        new_c = data.split('_')[1]
        if new_c == 'Aleatorio': new_c = random.choice(list(BASE_STATS.keys()))
        if player.gems >= RESPEC_COST:
            player.gems -= RESPEC_COST
            s = BASE_STATS[new_c]
            player.class_name = new_c; player.strength = s['str']; player.intelligence = s['int']; player.defense = s['def']; player.health = player.max_health
            db.commit()
            await query.edit_message_text(f"✅ Nova classe: **{new_c}**!", parse_mode='Markdown')

    # --- GUILDA ---
    elif data == 'menu_guild':
        if player.guild_id:
            g = db.query(Guild).filter(Guild.id == player.guild_id).first()
            kb = [[InlineKeyboardButton("💬 Grupo", url=g.telegram_link)],
                  [InlineKeyboardButton("💰 Doar Ouro", callback_data='donate_start_gold'), InlineKeyboardButton("💎 Doar Gemas", callback_data='donate_start_gems')],
                  [InlineKeyboardButton("🚪 Sair", callback_data='guild_leave')],
                  [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
            await query.edit_message_text(f"🛡️ **{g.name}**\n💰 {g.treasury_gold} | 💎 {g.treasury_gems}\n👥 {g.member_count}/50", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        else:
            kb = [[InlineKeyboardButton(f"Criar ({GUILD_CREATE_COST} Gemas)", callback_data='guild_create_start')],
                  [InlineKeyboardButton("🔍 Entrar", callback_data='guild_join_start')],
                  [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
            await query.edit_message_text("Sem guilda.", reply_markup=InlineKeyboardMarkup(kb))

    elif data == 'guild_create_start':
        if player.level < GUILD_MIN_LEVEL: await query.answer(f"Nível {GUILD_MIN_LEVEL} necessário!", show_alert=True); return
        if player.gems < GUILD_CREATE_COST: await query.answer(f"Faltam Gemas!", show_alert=True); return
        context.user_data['waiting_guild_name'] = True
        await query.edit_message_text("Nome da Guilda:", parse_mode='Markdown')

    elif data == 'guild_join_start':
        await query.edit_message_text("Peça o link de convite ao Líder da Guilda.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_guild')]]))

    elif data == 'guild_leave':
        g = db.query(Guild).filter(Guild.id == player.guild_id).first()
        if g: g.member_count -= 1; player.guild_id = None; db.commit()
        await query.edit_message_text("Saiu.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))

    elif data.startswith('donate_start_'):
        context.user_data['waiting_donation_type'] = data.split('_')[-1]
        await query.edit_message_text(f"Digite o valor para doar ({data.split('_')[-1]}):")

    # --- CONSTRUÇÕES (Fazenda inclusa) ---
    elif data == 'menu_constructions':
        kb = [[InlineKeyboardButton("Fazenda 🌾", callback_data='constr_fazenda'), InlineKeyboardButton("Quartel ⚔️", callback_data='constr_quartel')],
              [InlineKeyboardButton("Academia 🔮", callback_data='constr_academia'), InlineKeyboardButton("Pista 🏃‍♂️", callback_data='constr_pista')],
              [InlineKeyboardButton("Clínica ❤️", callback_data='constr_clinica'), InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
        await query.edit_message_text("🏗️ **Construções**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data.startswith('constr_') or data.startswith('upgrade_'):
        BUILDINGS = {
            'fazenda': {'attr': 'farm_level', 'cost': 500, 'desc': 'Produz Trigo/Ouro'},
            'quartel': {'attr': 'barracks_level', 'cost': 2000, 'desc': '+Força/Defesa'},
            'academia': {'attr': 'academy_level', 'cost': 1500, 'desc': '+Inteligência/XP'},
            'pista': {'attr': 'track_level', 'cost': 2500, 'desc': '+Velocidade/Crítico'},
            'clinica': {'attr': 'clinic_level', 'cost': 3000, 'desc': '+HP/Stamina Regen'}
        }
        b_key = data.split('_')[1]
        conf = BUILDINGS[b_key]
        lvl = getattr(player, conf['attr'])
        cost = int(conf['cost'] * (1.5 ** lvl))
        
        if data.startswith('upgrade_'):
            if player.gold >= cost:
                player.gold -= cost
                setattr(player, conf['attr'], lvl + 1)
                db.commit()
                await query.answer("Melhorado!")
                lvl += 1 # Update visual
                cost = int(conf['cost'] * (1.5 ** lvl)) # Next cost
            else: await query.answer("Sem ouro!", show_alert=True)

        # Menu Específico da Construção
        kb = [[InlineKeyboardButton(f"⬆️ Melhorar ({cost}g)", callback_data=f'upgrade_{b_key}')]]
        
        # Se for Fazenda, adiciona botão de colher
        if b_key == 'fazenda' and lvl > 0:
            kb.insert(0, [InlineKeyboardButton("💰 Vender Colheita", callback_data='farm_harvest')])
            
        kb.append([InlineKeyboardButton("🔙", callback_data='menu_constructions')])
        await query.edit_message_text(f"🏗️ **{b_key.upper()}** (Lvl {lvl})\n{conf['desc']}", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    # Handler da colheita (dentro do menu construções agora)
    elif data == 'farm_harvest':
        now = datetime.now()
        elapsed = (now - player.last_farm_harvest).total_seconds() / 3600
        amount = int(elapsed * player.farm_level * 100) # 100 trigo/h por nivel
        if amount > 0:
            player.gold += amount; player.last_farm_harvest = now; db.commit()
            await query.answer(f"Vendeu por {amount}g!")
        else: await query.answer("Nada ainda.")
        await handle_menu(update, context) # Volta pro menu

    # Refresh
    elif data == 'menu_refresh':
        await show_main_menu(update, player)

    db.close()

def main_bot(token: str) -> Application:
    init_db()
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cheat", admin_cheat))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text_input))
    app.add_handler(CallbackQueryHandler(handle_class_selection, pattern='^class_')) # REGISTRADO!
    app.add_handler(CallbackQueryHandler(confirm_name_handler, pattern='^confirm_name_'))
    app.add_handler(CallbackQueryHandler(handle_menu))
    return app
