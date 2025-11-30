import logging
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from database import Player, Guild, SessionLocal, init_db
from sqlalchemy import func, or_

# --- Configuração ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

ADMIN_ID = 387214847
STAMINA_COST = 1
GUILD_CREATE_COST = 100
GUILD_MIN_LEVEL = 50
INITIAL_GOLD = 1000
RESPEC_COST = 100

# Constantes
REFERRAL_GEMS_NEW = 10
REFERRAL_GOLD_NEW = 2000
REFERRAL_GEMS_INVITER = 25
REFERRAL_GOLD_INVITER = 5000
OFFICIAL_CHANNEL_LINK = "https://t.me/idlewarchannel"
BOT_USERNAME = "IdleWarGamebot" 
HEAL_RATE_PER_HOUR = 0.05 

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

# --- Funções Auxiliares ---
def get_db(): return SessionLocal()
def get_player(user_id, db): return db.query(Player).filter(Player.id == user_id).first()
def format_number(num): return str(int(num))

def check_level_up(player):
    leveled_up = False
    while player.xp >= player.level * 100:
        player.xp -= player.level * 100
        player.level += 1
        player.max_health += 5; player.health = player.max_health
        player.strength += 1; player.defense += 1
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
    elapsed = (now - player.last_stamina_gain).total_seconds() / 3600
    clinic_level = player.clinic_level
    if clinic_level > 0 and player.health < player.max_health:
        total_heal = int(player.max_health * HEAL_RATE_PER_HOUR * clinic_level * elapsed)
        player.health = min(player.max_health, player.health + total_heal)
        player.last_stamina_gain = now 
        return total_heal
    if player.health == player.max_health: player.last_stamina_gain = now 
    return 0

# --- COMANDOS ADMIN ---
def is_admin(user_id): return user_id == ADMIN_ID

async def admin_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    try:
        target_id = int(context.args[0])
        db = get_db(); target = get_player(target_id, db)
        if target: target.is_banned = True; db.commit(); await update.message.reply_text(f"🚫 {target.name} BANIDO.")
        else: await update.message.reply_text("Não encontrado.")
        db.close()
    except: await update.message.reply_text("Uso: /banir [ID]")

async def admin_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    try:
        target_id = int(context.args[0])
        db = get_db(); target = get_player(target_id, db)
        if target: db.delete(target); db.commit(); await update.message.reply_text(f"🗑️ Conta {target_id} deletada.")
        else: await update.message.reply_text("Não encontrado.")
        db.close()
    except: await update.message.reply_text("Uso: /conta [ID]")

async def admin_give(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    try:
        cmd = update.message.text.split()[0].replace('/', '')
        tid = int(context.args[0]); amt = int(context.args[1])
        db = get_db(); t = get_player(tid, db)
        if t:
            if cmd == 'ouro': t.gold += amt
            elif cmd == 'gemas': t.gems += amt
            elif cmd == 'xp': t.xp += amt; check_level_up(t)
            db.commit(); await update.message.reply_text(f"✅ {amt} {cmd} para {t.name}.")
        db.close()
    except: await update.message.reply_text(f"Uso: /{cmd} [ID] [QTD]")

async def admin_cheat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id): return
    db = get_db(); p = get_player(update.effective_user.id, db)
    if p:
        p.gold += 50000; p.gems += 500; p.level = 50; p.stamina = p.max_stamina
        db.commit()
        await update.message.reply_text("🕵️ **Modo Deus.** Recursos concedidos.")
    db.close()

# --- START & MENU ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db = get_db()
    player = get_player(user.id, db)

    # Ban check
    if player and player.is_banned:
        await update.message.reply_text("🚫 Conta Banida."); db.close(); return

    if context.args and not player:
        try:
            rid = int(context.args[0])
            if rid != user.id: context.user_data['referrer_id'] = rid
        except ValueError: pass 

    if not player:
        summary = ""
        for name, data in BASE_STATS.items():
            summary += f"\n**{name}**: {data['desc']}\n   ❤️ {data['hp']} | 💪 {data['str']} | 🧠 {data['int']} | 🛡️ {data['def']}"

        msg = (f"✨ **A Névoa se Dissipa!** ✨\n\n"
               f"Viajante, o destino dos Reinos de Aerthos aguarda sua escolha.\n\n"
               f"💰 **Recursos Iniciais:**\n{INITIAL_GOLD} Ouro\n0 Gemas\n\n"
               f"Qual poder ancestral você irá empunhar?\n{summary}")

        kb = []; row = []
        for c in VALID_CLASSES + ['Aleatorio']:
            row.append(InlineKeyboardButton(f"{c} 🎲" if c=='Aleatorio' else c, callback_data=f'class_{c}'))
            if len(row) == 3: kb.append(row); row = []
        if row: kb.append(row)

        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    else:
        heal = apply_passive_healing(player, db)
        db.commit()
        await show_main_menu(update, player)
        if heal > 0: await context.bot.send_message(chat_id=user.id, text=f"✨ Clínica: **+{heal} HP** recuperados.", parse_mode='Markdown')
    db.close()

async def show_main_menu(update: Update, player: Player):
    kb = [
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
    
    needed = player.level * 100
    perc = (player.xp / needed) * 100
    text = (f"**{player.name}** (Lvl {player.level} {player.class_name})\n"
            f"Exp: {format_number(player.xp)}/{format_number(needed)} ({perc:.1f}%)\n"
            f"❤️ HP: {player.health}/{player.max_health}\n"
            f"⚡ Stamina: {player.stamina}/{player.max_stamina}\n"
            f"💰 {format_number(player.gold)} | 💎 {player.gems}")
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except: pass

# --- REGISTRO E TEXTO ---
async def handle_class_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query; await query.answer()
    c = query.data.split('_')[1]
    if c == 'Aleatorio': c = random.choice(VALID_CLASSES)
    context.user_data['temp_class'] = c
    context.user_data['waiting_name'] = True
    await query.edit_message_text(f"Classe **{c}** escolhida! 🔮\n\nAgora, diga-me: **Qual é o seu nome, herói?** (Mín 5 letras, sem espaços)", parse_mode='Markdown')

async def receive_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ud = context.user_data
    
    if ud.get('waiting_guild_search'):
        term = update.message.text.strip()
        db = get_db()
        res = db.query(Guild).filter(or_(Guild.id == term, Guild.name.ilike(f"%{term}%"))).limit(5).all()
        kb = []
        if res:
            for g in res:
                if g.member_count < 50: kb.append([InlineKeyboardButton(f"Entrar: {g.name} ({g.member_count}/50)", callback_data=f"join_guild_{g.id}")])
            kb.append([InlineKeyboardButton("🔙 Voltar", callback_data='guild_join_start')])
            await update.message.reply_text(f"🔎 Resultados para '{term}':", reply_markup=InlineKeyboardMarkup(kb))
        else: await update.message.reply_text("❌ Nenhuma guilda encontrada.")
        ud['waiting_guild_search'] = False; db.close(); return

    if ud.get('waiting_name'):
        clean = update.message.text.strip().replace(" ", "")[:15]
        if len(clean) < 5: await update.message.reply_text("⚠️ Nome muito curto! Mínimo **5 letras**."); return
        ud['temp_name'] = clean; ud['waiting_name'] = False
        kb = [[InlineKeyboardButton("✅ Confirmar", callback_data='confirm_name_yes'), InlineKeyboardButton("✏️ Alterar", callback_data='confirm_name_no')]]
        await update.message.reply_text(f"Seu nome será: **{clean}**\nConfirma?", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        return

    if ud.get('waiting_guild_name'):
        ud['temp_guild_name'] = update.message.text.strip().replace(" ", "")[:15]
        ud['waiting_guild_name'] = False; ud['waiting_guild_link'] = True
        await update.message.reply_text(f"Nome da Guilda: **{ud['temp_guild_name']}**\n\nEnvie o **Link do Grupo Telegram**:", parse_mode='Markdown')
        return

    if ud.get('waiting_guild_link'):
        link = update.message.text.strip()
        if not link.startswith("https://t.me/"): await update.message.reply_text("🚫 Deve começar com https://t.me/..."); return
        db = get_db()
        p = get_player(update.effective_user.id, db)
        try:
            ng = Guild(name=ud['temp_guild_name'], leader_id=p.id, telegram_link=link, member_count=1)
            db.add(ng); db.commit()
            p.gems -= GUILD_CREATE_COST; p.guild_id = ng.id; db.commit()
            ud['waiting_guild_link'] = False
            await update.message.reply_text(f"✅ Guilda **{ng.name}** fundada!")
        except: await update.message.reply_text("❌ Nome já existe.")
        db.close(); return

    dtype = ud.get('waiting_donation_type')
    if dtype:
        db = get_db(); p = get_player(update.effective_user.id, db)
        if p and p.guild_id:
            try:
                amt = int(update.message.text.strip())
                if amt <= 0: raise ValueError
                g = db.query(Guild).filter(Guild.id == p.guild_id).first()
                if dtype == 'gold' and p.gold >= amt: p.gold -= amt; g.treasury_gold += amt; await update.message.reply_text(f"💰 Doou **{amt}g**!")
                elif dtype == 'gems' and p.gems >= amt: p.gems -= amt; g.treasury_gems += amt; await update.message.reply_text(f"💎 Doou **{amt} gems**!")
                else: await update.message.reply_text("🚫 **Recursos insuficientes!**")
                db.commit()
            except: await update.message.reply_text("Valor inválido.")
        ud['waiting_donation_type'] = None; db.close()

async def confirm_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query; await query.answer()
    if query.data == 'confirm_name_no':
        context.user_data['waiting_name'] = True
        await query.edit_message_text("Digite o nome novamente:")
        return

    # BLINDAGEM: Verifica se sessão existe
    name = context.user_data.get('temp_name')
    c_class = context.user_data.get('temp_class')
    
    if not name or not c_class:
        await query.edit_message_text("⚠️ **Sessão expirada.** Digite /start.", parse_mode='Markdown')
        return

    user_id = update.effective_user.id
    db = get_db()
    
    # BLINDAGEM: Verifica duplicidade no DB
    if get_player(user_id, db):
        db.close()
        await query.edit_message_text("⚠️ Você já tem um personagem! Redirecionando...")
        player = get_player(user_id, get_db()) # Reabre sessão
        await show_main_menu(update, player)
        get_db().close()
        return

    s = BASE_STATS[c_class]
    p = Player(id=user_id, username=update.effective_user.username, name=name, class_name=c_class,
               health=s['hp'], max_health=s['hp'], strength=s['str'], intelligence=s['int'], defense=s['def'],
               speed=s['spd'], crit_chance=s['crit'], gold=INITIAL_GOLD)
    db.add(p); db.commit()
    
    # Afiliado
    msg = ""
    rid = context.user_data.get('referrer_id')
    if rid:
        ref = get_player(rid, db)
        if ref:
            ref.gems += REFERRAL_GEMS_INVITER; ref.gold += REFERRAL_GOLD_INVITER
            p.gems += REFERRAL_GEMS_NEW; p.gold += REFERRAL_GOLD_NEW; db.commit()
            msg = f"\n\n🎁 **BÔNUS AFILIADO!**"
            try: await context.bot.send_message(chat_id=ref.id, text=f"🤝 **Novo Aliado!**\nAlguém entrou pelo seu link!\nVocê ganhou {REFERRAL_GEMS_INVITER}💎 e {REFERRAL_GOLD_INVITER}💰.")
            except: pass
    
    # SUCESSO: Carrega Menu Automaticamente
    await query.answer(f"🎉 Bem-vindo, {p.name}!", show_alert=True)
    await show_main_menu(update, p) # <--- AQUI ESTÁ O AUTO-START
    
    db.close()
    context.user_data['waiting_name'] = False

# --- HANDLER GERAL ---
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    data = query.data; db = get_db()
    player = get_player(query.from_user.id, db)
    
    if player and player.is_banned:
        await query.edit_message_text("🚫 **Conta Banida.**"); db.close(); return
        
    if not player: return

    # --- BATALHA (PAINEL TÁTICO) ---
    if data == 'menu_battle_mode':
        power = (player.strength * 2) + player.intelligence + player.defense
        msg = (f"⚔️ **Zona de Batalha**\n\n"
               f"📊 **Seus Status:**\n"
               f"❤️ HP: {player.health}/{player.max_health} | ⚡ Stamina: {player.stamina}/{player.max_stamina}\n"
               f"⚔️ Poder: {power} | 🏆 Rank: {player.pvp_rating}\n\n"
               f"Escolha seu destino:")
        kb = [[InlineKeyboardButton("🗺️ Campanha PVE", callback_data='battle_pve_start'), 
               InlineKeyboardButton("🆚 Arena PVP", callback_data='battle_pvp_start')], 
              [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'battle_pve_start':
        m = generate_monster(player.current_phase_id)
        context.user_data['monster'] = m
        msg = (f"🗺️ **Campanha: Fase {player.current_phase_id}**\n\n"
               f"🔥 **Inimigo:** {m['name']}\n"
               f"❤️ HP: {m['hp']} | ⚡ Spd: {m['spd']}\n"
               f"💰 Recompensa: {m['gold']}g | ✨ {m['xp']}xp")
        kb = [[InlineKeyboardButton("⚔️ ATACAR (1 Stamina)", callback_data='confirm_pve')], 
              [InlineKeyboardButton("🔙 Recuar", callback_data='menu_battle_mode')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'confirm_pve':
        if player.stamina < STAMINA_COST: await query.answer("⚡ Exausto! Seus heróis precisam descansar.", show_alert=True); return
        player.stamina -= STAMINA_COST
        m = context.user_data.get('monster')
        win = random.random() < 0.6
        if win:
            player.gold += m['gold']; player.xp += m['xp']; player.current_phase_id += 1; check_level_up(player)
            msg = f"⚔️ **Vitória Gloriosa!**\nO inimigo caiu perante sua força.\nSaque: +{m['gold']}g | +{m['xp']}xp"
        else:
            dmg = 10; player.health = max(0, player.health - dmg)
            msg = f"☠️ **Derrota...**\nVocê foi superado e perdeu {dmg} HP."
        db.commit()
        kb = [[InlineKeyboardButton("Continuar", callback_data='menu_battle_mode')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'battle_pvp_start':
        opp = db.query(Player).filter(Player.id != player.id).order_by(Player.pvp_rating.desc()).first()
        if not opp: await query.edit_message_text("🏜️ A Arena está vazia...", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_battle_mode')]])); return
        context.user_data['opponent_id'] = opp.id
        msg = (f"🆚 **Arena Ranqueada**\n\n"
               f"Oponente: **{opp.name}**\n"
               f"Classe: {opp.class_name} | Rating: {opp.pvp_rating}\n\n"
               f"Deseja desafiá-lo?")
        kb = [[InlineKeyboardButton("⚔️ DESAFIAR", callback_data='confirm_pvp')], [InlineKeyboardButton("🔙 Fugir", callback_data='menu_battle_mode')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'confirm_pvp':
        if player.stamina < STAMINA_COST: await query.answer("⚡ Exausto!", show_alert=True); return
        opp = db.query(Player).filter(Player.id == context.user_data.get('opponent_id')).first()
        player.stamina -= STAMINA_COST
        my_pow = player.strength + player.defense
        opp_pow = opp.strength + opp.defense
        if my_pow > opp_pow:
            player.pvp_rating += 25; msg = f"🏆 **Vitória na Arena!**\nVocê derrotou {opp.name}."
        else:
            player.pvp_rating = max(0, player.pvp_rating - 15); msg = "🏳️ **Derrota Humilhante...**\nTreine mais."
        db.commit()
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Continuar", callback_data='menu_battle_mode')]]), parse_mode='Markdown')

    # --- GUILDA ---
    elif data == 'menu_guild':
        if player.guild_id:
            g = db.query(Guild).filter(Guild.id == player.guild_id).first()
            ldr = db.query(Player.name).filter(Player.id == g.leader_id).scalar()
            kb = [[InlineKeyboardButton("💬 Acessar Grupo", url=g.telegram_link)],
                  [InlineKeyboardButton("💰 Doar Ouro", callback_data='donate_start_gold'), InlineKeyboardButton("💎 Doar Gemas", callback_data='donate_start_gems')],
                  [InlineKeyboardButton("🚪 Abandonar Guilda", callback_data='guild_leave')],
                  [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
            await query.edit_message_text(f"🛡️ **{g.name}**\n👑 Líder: {ldr}\n💰 Cofre: {g.treasury_gold}g | {g.treasury_gems}💎\n👥 Membros: {g.member_count}/50", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        else:
            kb = [[InlineKeyboardButton("🔎 QUADRO DE GUILDAS", callback_data='guild_join_start')],
                  [InlineKeyboardButton("🔎 Buscar Nome/ID", callback_data='guild_search_manual')],
                  [InlineKeyboardButton(f"✨ Fundar ({GUILD_CREATE_COST} Gemas)", callback_data='guild_create_start')],
                  [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
            await query.edit_message_text("🏰 **Salão das Guildas**\n\nJunte-se a uma ordem ou crie a sua!", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'guild_join_start':
        top_guilds = db.query(Guild).order_by(Guild.total_rating.desc()).limit(10).all()
        kb = []
        if top_guilds:
            for g in top_guilds:
                if g.member_count < 50: kb.append([InlineKeyboardButton(f"Entrar: {g.name} ({g.member_count}/50)", callback_data=f"join_guild_{g.id}")])
        else: kb.append([InlineKeyboardButton("Nenhuma guilda encontrada.", callback_data='ignore')])
        kb.append([InlineKeyboardButton("🔙 Voltar", callback_data='menu_guild')])
        await query.edit_message_text("📜 **Guildas Recrutando (Top 10)**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'guild_search_manual':
        context.user_data['waiting_guild_search'] = True
        await query.edit_message_text("🔎 Digite o **Nome** ou **ID** da guilda:", parse_mode='Markdown')

    elif data.startswith('join_guild_'):
        gid = int(data.split('_')[2])
        g = db.query(Guild).filter(Guild.id == gid).first()
        if g and g.member_count < 50:
            player.guild_id = g.id; g.member_count += 1; db.commit()
            await query.edit_message_text(f"✅ **Alistamento Aceito!**\nBem-vindo à **{g.name}**!\nLink: {g.telegram_link}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Menu da Guilda", callback_data='menu_guild')]]))
        else: await query.answer("❌ Cheia ou inexistente.", show_alert=True)

    elif data == 'guild_create_start':
        if player.level < GUILD_MIN_LEVEL: await query.answer(f"Requer Nível {GUILD_MIN_LEVEL}!", show_alert=True); return
        if player.gems < GUILD_CREATE_COST: await query.answer("Gemas insuficientes!", show_alert=True); return
        context.user_data['waiting_guild_name'] = True
        await query.edit_message_text("🛡️ Digite o **Nome da Guilda**:", parse_mode='Markdown')

    elif data == 'guild_leave':
        g = db.query(Guild).filter(Guild.id == player.guild_id).first()
        g.member_count -= 1; player.guild_id = None; db.commit()
        await query.edit_message_text("Você deixou a guilda.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))

    elif data.startswith('donate_start_'):
        context.user_data['waiting_donation_type'] = data.split('_')[-1]
        await query.edit_message_text(f"🏦 Digite o valor para doar:")

    # --- MENU DE CONSTRUÇÕES ---
    elif data == 'menu_constructions':
        prod_h = player.farm_level * 10
        cap = player.barn_level * 100
        msg = (f"🏗️ **Distrito de Construções**\n\n"
               f"🌾 Fazenda: Lvl {player.farm_level} ({prod_h}/h)\n"
               f"🏚️ Celeiro: Lvl {player.barn_level} (Cap: {cap})\n"
               f"⚔️ Quartel: Lvl {player.barracks_level}\n"
               f"🔮 Academia: Lvl {player.academy_level}\n"
               f"🏃 Pista: Lvl {player.track_level}\n"
               f"❤️ Clínica: Lvl {player.clinic_level}\n\n"
               f"Selecione uma estrutura para expandir:")
        
        kb = [[InlineKeyboardButton("Fazenda 🌾", callback_data='constr_fazenda'), InlineKeyboardButton("Quartel ⚔️", callback_data='constr_quartel')],
              [InlineKeyboardButton("Academia 🔮", callback_data='constr_academia'), InlineKeyboardButton("Pista 🏃‍♂️", callback_data='constr_pista')],
              [InlineKeyboardButton("Clínica ❤️", callback_data='constr_clinica'), InlineKeyboardButton("Celeiro 🏚️", callback_data='constr_celeiro')],
              [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data.startswith('constr_') or data.startswith('upgrade_'):
        B = {'fazenda': {'a':'farm_level', 'c':500, 'd':'Produz Trigo/Ouro'}, 
             'celeiro': {'a':'barn_level', 'c':500, 'd':'Aumenta capacidade de estoque'},
             'quartel': {'a':'barracks_level', 'c':2000, 'd':'Aumenta Força e Defesa'},
             'academia': {'a':'academy_level', 'c':1500, 'd':'Aumenta Inteligência e XP'},
             'pista': {'a':'track_level', 'c':2500, 'd':'Aumenta Velocidade e Crítico'},
             'clinica': {'a':'clinic_level', 'c':3000, 'd':'Regenera HP offline'}}
        
        key = data.split('_')[1]
        conf = B[key]
        lvl = getattr(player, conf['a'])
        cost = int(conf['c'] * (1.5 ** lvl))
        
        if data.startswith('upgrade_'):
            if player.gold >= cost:
                player.gold -= cost; setattr(player, conf['a'], lvl+1); db.commit()
                await query.answer("🔨 Construção Melhorada!"); lvl += 1; cost = int(conf['c'] * (1.5 ** lvl))
            else: await query.answer("🚫 Ouro insuficiente!", show_alert=True)

        kb = [[InlineKeyboardButton(f"⬆️ Melhorar (Custo: {cost}g)", callback_data=f'upgrade_{key}')]]
        if key == 'fazenda' and lvl > 0: kb.insert(0, [InlineKeyboardButton("💰 Vender Colheita", callback_data='farm_harvest')])
        kb.append([InlineKeyboardButton("🔙 Voltar", callback_data='menu_constructions')])
        
        await query.edit_message_text(f"🏗️ **{key.capitalize()}** (Nível {lvl})\n_{conf['d']}_", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'farm_harvest':
        now = datetime.now(); elapsed = (now - player.last_farm_harvest).total_seconds() / 3600
        amount = int(elapsed * player.farm_level * 100)
        if amount > 0:
            player.gold += amount; player.last_farm_harvest = now; db.commit()
            await query.answer(f"💰 Vendeu por {amount}g!")
        else: await query.answer("🌾 Colheita vazia.")
        await handle_menu(update, context)

    # --- UPGRADE ---
    elif data == 'menu_upgrade':
        msg = (f"💪 **Centro de Treinamento**\n\n"
               f"📊 **Seus Atributos:**\n"
               f"💪 Força: {player.strength}\n"
               f"🧠 Inteligência: {player.intelligence}\n"
               f"🛡️ Defesa: {player.defense}\n"
               f"⚡ Velocidade: {player.speed}\n"
               f"💥 Crítico: {player.crit_chance}%\n\n"
               f"💰 Saldo: {player.gold}g | {player.gems}💎")
        
        c_str = int(50 + (player.strength * 20))
        kb = [[InlineKeyboardButton(f"💪 Treinar Força ({c_str}g)", callback_data='up_str')],
              [InlineKeyboardButton(f"🔄 Reencarnar (Mudar Classe)", callback_data='respec_start')],
              [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data.startswith('up_'):
        c = int(50 + (player.strength * 20))
        if player.gold >= c:
            player.gold -= c; player.strength += 1; db.commit()
            await query.answer("💪 +1 Força!")
            await handle_menu(update, context)
        else: await query.answer("🚫 Ouro insuficiente!", show_alert=True)

    elif data == 'respec_start':
        kb = []; row = []
        for c in VALID_CLASSES:
            row.append(InlineKeyboardButton(c, callback_data=f'respec_{c}'))
            if len(row)==3: kb.append(row); row=[]
        if row: kb.append(row)
        kb.append([InlineKeyboardButton("🔙", callback_data='menu_upgrade')])
        await query.edit_message_text(f"🔄 **Reencarnação**\nCusto: {RESPEC_COST} Gemas.\nEscolha seu novo destino:", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data.startswith('respec_'):
        if player.gems >= RESPEC_COST:
            nc = data.split('_')[1]; s = BASE_STATS[nc]
            player.gems -= RESPEC_COST; player.class_name = nc; player.strength = s['str']; player.defense = s['def']; player.intelligence = s['int']; player.health = player.max_health; db.commit()
            await query.edit_message_text(f"✨ **Renascimento Completo!**\nVocê agora é um {nc}.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]), parse_mode='Markdown')
        else: await query.answer("🚫 Gemas insuficientes!", show_alert=True)

    # --- OUTROS ---
    elif data == 'menu_mailbox':
        kb = [[InlineKeyboardButton("📢 Canal Oficial", url=OFFICIAL_CHANNEL_LINK)], [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
        await query.edit_message_text("✉️ **Correio Real**\nFique atento aos decretos e eventos:", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'menu_info':
        lnk = f"https://t.me/{BOT_USERNAME}?start={player.id}"
        await query.edit_message_text(f"📜 **Pergaminho de Status**\n\n**{player.name}**\n💪 {player.strength} | 🧠 {player.intelligence}\n🛡️ {player.defense} | ⚡ {player.speed}\n\n🔗 **Recrutamento:**\n`{lnk}`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]), parse_mode='Markdown')

    elif data == 'menu_daily':
        now = datetime.now()
        if (now - player.last_daily_claim) > timedelta(hours=24):
            await query.edit_message_text("🎁 **Recompensa Diária**\nOs deuses lhe abençoam.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 Receber", callback_data='daily_claim_now')]]))
        else:
            await query.edit_message_text("⏳ **Aguarde...**\nVolte amanhã para mais recursos.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))

    elif data == 'daily_claim_now':
        player.gold += 1000; player.xp += 1000; player.last_daily_claim = datetime.now(); player.stamina = player.max_stamina; check_level_up(player); db.commit()
        await query.edit_message_text("✅ **Bênção Recebida!**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))

    elif data == 'menu_shop':
        await query.edit_message_text("💎 **Mercado Negro VIP**\n\n🚧 Os mercadores estão viajando. (Em breve via XSolla)", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))

    elif data == 'menu_ranking':
        top = db.query(Player).order_by(Player.pvp_rating.desc()).limit(10).all()
        txt = "🏆 **Salão da Fama**\n" + "\n".join([f"#{i+1} {p.name} ({p.pvp_rating})" for i, p in enumerate(top)])
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]), parse_mode='Markdown')

    elif data == 'menu_refresh':
        await show_main_menu(update, player)

    db.close()

def main_bot(token: str) -> Application:
    init_db()
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cheat", admin_cheat))
    app.add_handler(CommandHandler("banir", admin_ban))
    app.add_handler(CommandHandler("conta", admin_delete))
    app.add_handler(CommandHandler("ouro", admin_give))
    app.add_handler(CommandHandler("gemas", admin_give))
    app.add_handler(CommandHandler("xp", admin_give))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text_input))
    app.add_handler(CallbackQueryHandler(handle_class_selection, pattern='^class_'))
    app.add_handler(CallbackQueryHandler(confirm_name_handler, pattern='^confirm_name_'))
    app.add_handler(CallbackQueryHandler(handle_menu))
    return app
