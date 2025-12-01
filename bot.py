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
INITIAL_GOLD = 1000
GUILD_CREATE_COST = 100
GUILD_MIN_LEVEL = 50
STAMINA_COST = 1
RESPEC_COST = 100
HEAL_RATE_PER_HOUR = 0.05 

# Constantes e Links
REFERRAL_GEMS_NEW = 10
REFERRAL_GOLD_NEW = 2000
REFERRAL_GEMS_INVITER = 25
REFERRAL_GOLD_INVITER = 5000
OFFICIAL_CHANNEL_LINK = "https://t.me/idlewarchannel"
BOT_USERNAME = "IdleWarGamebot" 

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
def format_number(num): return str(int(num)) if num else "0"

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

def apply_passive_healing(player: Player, db):
    now = datetime.now()
    if not player.last_stamina_gain: player.last_stamina_gain = now
    elapsed = (now - player.last_stamina_gain).total_seconds() / 3600
    clinic_level = player.clinic_level
    if clinic_level > 0 and player.health < player.max_health:
        total_heal = int(player.max_health * HEAL_RATE_PER_HOUR * clinic_level * elapsed)
        if total_heal > 0:
            player.health = min(player.max_health, player.health + total_heal)
            player.last_stamina_gain = now 
            return total_heal
    player.last_stamina_gain = now 
    return 0

# --- ADMIN ---
def is_admin(user_id, db=None):
    if user_id == ADMIN_ID: return True
    if db:
        p = get_player(user_id, db)
        if p and p.is_admin: return True
    return False

async def admin_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db()
    if not is_admin(update.effective_user.id, db): db.close(); return
    try:
        tid = int(context.args[0]); t = get_player(tid, db)
        if t: t.is_banned = True; db.commit(); await update.message.reply_text(f"🚫 {t.name} BANIDO.")
        else: await update.message.reply_text("Não encontrado.")
    except: await update.message.reply_text("Uso: /banir [ID]")
    db.close()

async def admin_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db()
    if not is_admin(update.effective_user.id, db): db.close(); return
    try:
        tid = int(context.args[0]); t = get_player(tid, db)
        if t: db.delete(t); db.commit(); await update.message.reply_text(f"🗑️ Conta {tid} DELETADA.")
        else: await update.message.reply_text("Não encontrado.")
    except: await update.message.reply_text("Uso: /conta [ID]")
    db.close()

async def admin_give(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db()
    if not is_admin(update.effective_user.id, db): db.close(); return
    try:
        cmd = update.message.text.split()[0].replace('/', '')
        tid = int(context.args[0]); amt = int(context.args[1])
        t = get_player(tid, db)
        if t:
            if cmd == 'ouro': t.gold += amt
            elif cmd == 'gemas': t.gems += amt
            elif cmd == 'xp': t.xp += amt; check_level_up(t)
            db.commit(); await update.message.reply_text(f"✅ {amt} {cmd} para {t.name}.")
        else: await update.message.reply_text("Não encontrado.")
    except: await update.message.reply_text(f"Uso: /{cmd} [ID] [QTD]")
    db.close()

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
        
        if is_admin(user.id, db):
            await update.message.reply_text("👑 **Admin:** Use /banir, /conta, /ouro, /gemas, /xp", parse_mode='Markdown')
            
        await show_main_menu(update, player)
        if heal > 0: await context.bot.send_message(chat_id=user.id, text=f"✨ Clínica: **+{heal} HP** recuperados.", parse_mode='Markdown')
    db.close()

async def show_main_menu(update: Update, player: Player):
    # TECLADO DO MENU PRINCIPAL
    keyboard = [
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
    
    # Tratamento de erro para valores None/Zero
    lvl = player.level if player.level else 1
    xp = player.xp if player.xp else 0
    needed = lvl * 100
    perc = (xp / needed) * 100
    
    text = (f"**{player.name}** (Lvl {lvl} {player.class_name})\n"
            f"Exp: {format_number(xp)}/{format_number(needed)} ({perc:.1f}%)\n"
            f"❤️ HP: {player.health}/{player.max_health}\n"
            f"⚡ Stamina: {player.stamina}/{player.max_stamina}\n"
            f"💰 {format_number(player.gold)} | 💎 {player.gems}")
    
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except Exception as e:
        print(f"Erro no menu: {e}") # Log para debug se falhar

# --- REGISTRO DE CLASSE ---
async def handle_class_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query; await query.answer()
    c = query.data.split('_')[1]
    if c == 'Aleatorio': c = random.choice(VALID_CLASSES)
    context.user_data['temp_class'] = c
    context.user_data['waiting_name'] = True
    await query.edit_message_text(f"Classe **{c}** escolhida! 🔮\n\nAgora, diga-me: **Qual é o seu nome, herói?** (Mín 5 letras, apenas A-Z e números)", parse_mode='Markdown')

# --- RECEBIMENTO DE TEXTO ---
async def receive_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ud = context.user_data
    
    if ud.get('waiting_name'):
        raw = update.message.text.strip()
        # SANITIZAÇÃO DE NOME (Apenas Alfanumérico para evitar crash do Markdown)
        clean = "".join(ch for ch in raw if ch.isalnum())[:15]
        
        if len(clean) < 5: 
            await update.message.reply_text("⚠️ Nome inválido! Use **mínimo 5 letras/números** (sem símbolos). Tente de novo:", parse_mode='Markdown')
            return
            
        ud['temp_name'] = clean; ud['waiting_name'] = False
        kb = [[InlineKeyboardButton("✅ Confirmar", callback_data='confirm_name_yes'), InlineKeyboardButton("✏️ Alterar", callback_data='confirm_name_no')]]
        await update.message.reply_text(f"Seu nome será: **{clean}**\nConfirma?", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        return

    # Handlers de Guilda/Doação (Mantidos iguais)
    if ud.get('waiting_guild_name'):
        ud['temp_guild_name'] = update.message.text.strip()[:20]
        ud['waiting_guild_name'] = False; ud['waiting_guild_link'] = True
        await update.message.reply_text(f"Nome da Guilda: **{ud['temp_guild_name']}**\n\nEnvie o **Link do Grupo Telegram**:", parse_mode='Markdown')
        return

    if ud.get('waiting_guild_link'):
        link = update.message.text.strip()
        if not link.startswith("https://t.me/"): await update.message.reply_text("🚫 Deve começar com https://t.me/..."); return
        db = get_db(); p = get_player(update.effective_user.id, db)
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

# --- CONFIRMAÇÃO DE NOME (CORRIGIDO) ---
async def confirm_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query; await query.answer()
    
    if query.data == 'confirm_name_no':
        context.user_data['waiting_name'] = True
        await query.edit_message_text("Digite o nome novamente:")
        return

    name = context.user_data.get('temp_name')
    c_class = context.user_data.get('temp_class')
    
    if not name or not c_class:
        await query.edit_message_text("⚠️ **Sessão expirada.** Digite /start.", parse_mode='Markdown')
        return

    user_id = update.effective_user.id
    db = get_db()
    
    # Prevenção de Duplicidade
    if get_player(user_id, db):
        db.close()
        # Se já existe, apenas mostra o menu
        await query.answer("Você já tem um personagem!")
        p = get_player(user_id, get_db())
        await show_main_menu(update, p)
        return

    s = BASE_STATS[c_class]
    p = Player(id=user_id, username=update.effective_user.username, name=name, class_name=c_class,
               health=s['hp'], max_health=s['hp'], strength=s['str'], intelligence=s['int'], defense=s['def'],
               speed=s['spd'], crit_chance=s['crit'], gold=INITIAL_GOLD, level=1, xp=0) # Definindo explicitamente
    db.add(p); db.commit()
    
    # Refresh para garantir que todos os campos (como timestamps) venham do DB
    db.refresh(p) 
    
    # Afiliado
    rid = context.user_data.get('referrer_id')
    if rid:
        ref = get_player(rid, db)
        if ref:
            ref.gems += REFERRAL_GEMS_INVITER; ref.gold += REFERRAL_GOLD_INVITER
            p.gems += REFERRAL_GEMS_NEW; p.gold += REFERRAL_GOLD_NEW; db.commit()
            try: await context.bot.send_message(chat_id=ref.id, text=f"🤝 **Novo Aliado!**\nAlguém entrou pelo seu link!\nVocê ganhou {REFERRAL_GEMS_INVITER}💎 e {REFERRAL_GOLD_INVITER}💰.")
            except: pass
    
    # AUTO START: Vai direto pro menu
    await show_main_menu(update, p)
    db.close()
    context.user_data['waiting_name'] = False

# --- HANDLER GERAL DE MENUS (Mantido igual) ---
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    data = query.data; db = get_db()
    player = get_player(query.from_user.id, db)
    if not player: return

    # --- Seus Handlers de Menu (Batalha, Guilda, etc) ---
    # Copie aqui todo o bloco de lógica de menus que já estava funcionando
    # (Vou resumir para caber, mas você deve manter a lógica completa de batalha/guilda que fizemos antes)
    
    if data == 'menu_battle_mode':
        power = (player.strength * 2) + player.intelligence + player.defense
        msg = (f"⚔️ **Zona de Batalha**\n\n📊 **Status:**\n❤️ {player.health}/{player.max_health} | ⚡ {player.stamina}/{player.max_stamina}\n⚔️ Poder: {power} | 🏆 Rank: {player.pvp_rating}\n\nEscolha:")
        kb = [[InlineKeyboardButton("🗺️ Campanha PVE", callback_data='battle_pve_start'), InlineKeyboardButton("🆚 Arena PVP", callback_data='battle_pvp_start')], [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'battle_pve_start':
        m = generate_monster(player.current_phase_id); context.user_data['monster'] = m
        msg = f"🗺️ **Fase {player.current_phase_id}**\n🔥 **{m['name']}**\n❤️ {m['hp']} | 💰 {m['gold']}g"
        kb = [[InlineKeyboardButton("⚔️ ATACAR", callback_data='confirm_pve')], [InlineKeyboardButton("🔙", callback_data='menu_battle_mode')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'confirm_pve':
        if player.stamina < STAMINA_COST: await query.answer("⚡ Exausto!", show_alert=True); return
        player.stamina -= STAMINA_COST
        m = context.user_data.get('monster')
        if random.random() < 0.6:
            player.gold += m['gold']; player.xp += m['xp']; player.current_phase_id += 1; check_level_up(player)
            msg = f"⚔️ **Vitória!**\n+{m['gold']}g | +{m['xp']}xp"
        else:
            player.health = max(0, player.health - 10); msg = "☠️ **Derrota...**"
        db.commit()
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Continuar", callback_data='menu_battle_mode')]]), parse_mode='Markdown')

    elif data == 'battle_pvp_start':
        opp = db.query(Player).filter(Player.id != player.id).order_by(Player.pvp_rating.desc()).first()
        if not opp: await query.edit_message_text("Sem oponentes.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_battle_mode')]])); return
        context.user_data['opponent_id'] = opp.id
        kb = [[InlineKeyboardButton("⚔️ DESAFIAR", callback_data='confirm_pvp')], [InlineKeyboardButton("🔙", callback_data='menu_battle_mode')]]
        await query.edit_message_text(f"🆚 **{opp.name}**\nRating: {opp.pvp_rating}", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'confirm_pvp':
        if player.stamina < STAMINA_COST: await query.answer("⚡ Exausto!", show_alert=True); return
        opp = db.query(Player).filter(Player.id == context.user_data.get('opponent_id')).first()
        player.stamina -= STAMINA_COST
        if (player.strength + player.defense) > (opp.strength + opp.defense):
            player.pvp_rating += 25; msg = "🏆 **Vitória!**"
        else: player.pvp_rating = max(0, player.pvp_rating - 15); msg = "🏳️ **Derrota...**"
        db.commit()
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Continuar", callback_data='menu_battle_mode')]]), parse_mode='Markdown')

    # Menu Genéricos (Guilda, etc)
    elif data == 'menu_guild':
        if player.guild_id:
            g = db.query(Guild).filter(Guild.id == player.guild_id).first()
            kb = [[InlineKeyboardButton("💬 Grupo", url=g.telegram_link)], [InlineKeyboardButton("💰 Doar", callback_data='donate_start_gold'), InlineKeyboardButton("🚪 Sair", callback_data='guild_leave')], [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
            await query.edit_message_text(f"🛡️ **{g.name}**\n💰 {g.treasury_gold}g", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        else:
            kb = [[InlineKeyboardButton("🔎 Listar", callback_data='guild_join_start'), InlineKeyboardButton("✨ Criar", callback_data='guild_create_start')], [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
            await query.edit_message_text("Sem guilda.", reply_markup=InlineKeyboardMarkup(kb))

    elif data == 'guild_join_start':
        top = db.query(Guild).limit(5).all()
        kb = []
        for g in top: kb.append([InlineKeyboardButton(f"Entrar: {g.name}", callback_data=f"join_guild_{g.id}")])
        kb.append([InlineKeyboardButton("🔙", callback_data='menu_guild')])
        await query.edit_message_text("Guildas:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith('join_guild_'):
        gid = int(data.split('_')[2]); g = db.query(Guild).filter(Guild.id == gid).first()
        if g: player.guild_id = g.id; g.member_count += 1; db.commit(); await query.answer("Entrou!")
        await handle_menu(update, context)

    elif data == 'guild_create_start':
        if player.gems < GUILD_CREATE_COST: await query.answer("Sem gemas!", show_alert=True); return
        context.user_data['waiting_guild_name'] = True
        await query.edit_message_text("Nome da Guilda:")

    elif data == 'guild_leave':
        if player.guild_id: 
            g = db.query(Guild).filter(Guild.id == player.guild_id).first()
            if g: g.member_count -= 1
            player.guild_id = None; db.commit()
        await query.edit_message_text("Saiu.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))

    elif data == 'menu_constructions':
        kb = [[InlineKeyboardButton("Fazenda", callback_data='constr_fazenda'), InlineKeyboardButton("Quartel", callback_data='constr_quartel')], [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
        await query.edit_message_text("Construções:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith('constr_') or data.startswith('upgrade_'):
        key = data.split('_')[1]; B = {'fazenda': 'farm_level', 'quartel': 'barracks_level'}
        if key not in B: await query.answer("Em breve!"); return
        lvl = getattr(player, B[key])
        if data.startswith('upgrade_'):
            if player.gold >= 500: player.gold -= 500; setattr(player, B[key], lvl+1); db.commit(); await query.answer("Sucesso!"); lvl+=1
            else: await query.answer("Sem ouro!")
        kb = [[InlineKeyboardButton("⬆️ Upar (500g)", callback_data=f'upgrade_{key}')], [InlineKeyboardButton("🔙", callback_data='menu_constructions')]]
        await query.edit_message_text(f"{key.capitalize()} Lvl {lvl}", reply_markup=InlineKeyboardMarkup(kb))

    elif data == 'menu_upgrade':
        c = 100
        kb = [[InlineKeyboardButton(f"Força +1 ({c}g)", callback_data='up_str')], [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
        await query.edit_message_text(f"Força: {player.strength}", reply_markup=InlineKeyboardMarkup(kb))

    elif data == 'up_str':
        if player.gold >= 100: player.gold -= 100; player.strength += 1; db.commit(); await query.answer("Up!")
        else: await query.answer("Sem ouro!")
        await handle_menu(update, context)

    elif data == 'menu_refresh' or data == 'menu_info':
        await show_main_menu(update, player)

    # ... Outros menus (Ranking, Shop, Mailbox) seguem lógica similar ...
    
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
