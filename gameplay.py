# gameplay.py
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import Player, Guild
from sqlalchemy import or_
from utils import get_db, get_player, format_number, check_level_up, generate_monster, apply_passive_healing, simulate_pvp_battle, is_admin
from config import *

# --- HELPER DE TECLADO ---
def get_main_keyboard():
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

# --- START & AUTH FLOW ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db = get_db()
    try:
        player = get_player(user.id, db)
        if player and player.is_banned:
            await update.message.reply_text("🚫 Conta Banida."); return

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
    finally: db.close()

async def show_main_menu(update: Update, player: Player):
    keyboard = get_main_keyboard()
    lvl = player.level if player.level else 1
    xp = player.xp if player.xp else 0
    needed = lvl * 100
    perc = (xp / needed) * 100 if needed > 0 else 0
    safe_name = str(player.name).replace("_", " ").replace("*", "").replace("`", "") if player.name else "Herói"
    
    text = (f"**{safe_name}** (Lvl {lvl} {player.class_name})\n"
            f"Exp: {format_number(xp)}/{format_number(needed)} ({perc:.1f}%)\n"
            f"❤️ HP: {player.health}/{player.max_health}\n"
            f"⚡ Stamina: {player.stamina}/{player.max_stamina}\n"
            f"💰 {format_number(player.gold)} | 💎 {player.gems}")
    
    if update.callback_query:
        try: await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        except: await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def handle_class_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query; await query.answer()
    c = query.data.split('_')[1]
    if c == 'Aleatorio': c = random.choice(VALID_CLASSES)
    context.user_data['temp_class'] = c
    context.user_data['waiting_name'] = True
    await query.edit_message_text(f"Classe **{c}** escolhida! 🔮\n\nAgora, diga-me: **Qual é o seu nome, herói?** (Mín 5 letras, sem espaços)", parse_mode='Markdown')

async def receive_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ud = context.user_data
    
    # 1. Guild Search
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

    # 2. Nome
    if ud.get('waiting_name'):
        raw = update.message.text.strip()
        clean = "".join(ch for ch in raw if ch.isalnum())[:15]
        if len(clean) < 5: await update.message.reply_text("⚠️ Nome inválido! Use **mínimo 5 letras/números**."); return
        ud['temp_name'] = clean; ud['waiting_name'] = False
        kb = [[InlineKeyboardButton("✅ Confirmar", callback_data='confirm_name_yes'), InlineKeyboardButton("✏️ Alterar", callback_data='confirm_name_no')]]
        await update.message.reply_text(f"Seu nome será: **{clean}**\nConfirma?", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        return

    # 3. Guild Create
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

    # 4. Doação
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

    name = context.user_data.get('temp_name')
    c_class = context.user_data.get('temp_class')
    if not name or not c_class: await query.edit_message_text("⚠️ **Sessão expirada.** Digite /start.", parse_mode='Markdown'); return

    user_id = update.effective_user.id
    db = get_db()
    if get_player(user_id, db):
        db.close(); await query.answer("Já tem char!"); p = get_player(user_id, get_db()); await show_main_menu(update, p); return

    s = BASE_STATS[c_class]
    p = Player(id=user_id, username=update.effective_user.username, name=name, class_name=c_class,
               health=s['hp'], max_health=s['hp'], strength=s['str'], intelligence=s['int'], defense=s['def'],
               speed=s['spd'], crit_chance=s['crit'], gold=INITIAL_GOLD, level=1, xp=0)
    db.add(p); db.commit(); db.refresh(p)
    
    rid = context.user_data.get('referrer_id')
    if rid:
        ref = get_player(rid, db)
        if ref:
            ref.gems += REFERRAL_GEMS_INVITER; ref.gold += REFERRAL_GOLD_INVITER
            p.gems += REFERRAL_GEMS_NEW; p.gold += REFERRAL_GOLD_NEW; db.commit()
            try: await context.bot.send_message(chat_id=ref.id, text=f"🤝 **Novo Aliado!**\nRecompensa: {REFERRAL_GEMS_INVITER}💎 {REFERRAL_GOLD_INVITER}g")
            except: pass
    
    await query.answer(f"Bem-vindo, {p.name}!", show_alert=True)
    await show_main_menu(update, p)
    db.close(); context.user_data['waiting_name'] = False

# --- BIG ROUTER (Handle Menu) ---
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    data = query.data; db = get_db()
    player = get_player(query.from_user.id, db)
    
    if player and player.is_banned: await query.edit_message_text("🚫 **Conta Banida.**"); db.close(); return
    if not player: return

    # Battle
    if data == 'menu_battle_mode':
        pwr = (player.strength * 2) + player.intelligence + player.defense
        msg = (f"⚔️ **Zona de Batalha**\nStatus: ❤️ {player.health}/{player.max_health} | ⚡ {player.stamina}\n⚔️ Poder: {pwr} | 🏆 Rank: {player.pvp_rating}")
        kb = [[InlineKeyboardButton("🗺️ Campanha PVE", callback_data='battle_pve_start'), InlineKeyboardButton("🆚 Arena PVP", callback_data='battle_pvp_start')], [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'battle_pve_start':
        m = generate_monster(player.current_phase_id); context.user_data['monster'] = m
        kb = [[InlineKeyboardButton("⚔️ ATACAR (1 Stamina)", callback_data='confirm_pve')], [InlineKeyboardButton("🔙 Recuar", callback_data='menu_battle_mode')]]
        await query.edit_message_text(f"🗺️ **Fase {player.current_phase_id}**\n🔥 **{m['name']}**\n❤️ HP: {m['hp']} | ⚡ {m['spd']}", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'confirm_pve':
        if player.stamina < STAMINA_COST: await query.answer("⚡ Exausto!", show_alert=True); return
        player.stamina -= STAMINA_COST; m = context.user_data.get('monster')
        win = random.random() < 0.6
        if win:
            player.gold += m['gold']; player.xp += m['xp']; player.current_phase_id += 1; check_level_up(player)
            msg = f"⚔️ **Vitória!**\n+{m['gold']}g | +{m['xp']}xp"
        else:
            dmg = 10; player.health = max(0, player.health - dmg); msg = f"☠️ **Derrota...**\n-{dmg} HP"
        db.commit()
        kb = [[InlineKeyboardButton("Continuar", callback_data='menu_battle_mode')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'battle_pvp_start':
        opp = db.query(Player).filter(Player.id != player.id).order_by(Player.pvp_rating.desc()).first()
        if not opp: await query.edit_message_text("Vazio.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_battle_mode')]])); return
        context.user_data['opponent_id'] = opp.id
        kb = [[InlineKeyboardButton("⚔️ DESAFIAR", callback_data='confirm_pvp')], [InlineKeyboardButton("🔙", callback_data='menu_battle_mode')]]
        await query.edit_message_text(f"🆚 **{opp.name}**\nRank: {opp.pvp_rating}", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'confirm_pvp':
        if player.stamina < STAMINA_COST: await query.answer("⚡ Exausto!", show_alert=True); return
        opp = db.query(Player).filter(Player.id == context.user_data.get('opponent_id')).first()
        player.stamina -= STAMINA_COST
        winner = simulate_pvp_battle(player, opp)
        if winner.id == player.id: player.pvp_rating += 25; msg = "🏆 **Vitória!**"
        else: player.pvp_rating = max(0, player.pvp_rating - 15); player.health = max(0, player.health - 20); msg = "🏳️ **Derrota...**"
        db.commit()
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Continuar", callback_data='menu_battle_mode')]]), parse_mode='Markdown')

    # Guilda
    elif data == 'menu_guild':
        if player.guild_id:
            g = db.query(Guild).filter(Guild.id == player.guild_id).first()
            kb = [[InlineKeyboardButton("💬 Grupo", url=g.telegram_link)],
                  [InlineKeyboardButton("💰 Doar Ouro", callback_data='donate_start_gold'), InlineKeyboardButton("💎 Doar Gemas", callback_data='donate_start_gems')],
                  [InlineKeyboardButton("🚪 Sair", callback_data='guild_leave')], [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
            await query.edit_message_text(f"🛡️ **{g.name}**\n💰 Cofre: {g.treasury_gold}g | {g.treasury_gems}💎", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        else:
            kb = [[InlineKeyboardButton("🔎 Listar", callback_data='guild_join_start'), InlineKeyboardButton("🔎 Buscar", callback_data='guild_search_manual')],
                  [InlineKeyboardButton(f"✨ Fundar ({GUILD_CREATE_COST} Gemas)", callback_data='guild_create_start')], [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
            await query.edit_message_text("Sem guilda.", reply_markup=InlineKeyboardMarkup(kb))

    elif data == 'guild_join_start':
        top = db.query(Guild).order_by(Guild.total_rating.desc()).limit(10).all()
        kb = []
        for g in top:
            if g.member_count < 50: kb.append([InlineKeyboardButton(f"{g.name} ({g.member_count}/50)", callback_data=f"join_guild_{g.id}")])
        kb.append([InlineKeyboardButton("🔙", callback_data='menu_guild')])
        await query.edit_message_text("Guildas:", reply_markup=InlineKeyboardMarkup(kb))

    elif data == 'guild_search_manual':
        context.user_data['waiting_guild_search'] = True
        await query.edit_message_text("🔎 Digite Nome/ID:", parse_mode='Markdown')

    elif data.startswith('join_guild_'):
        gid = int(data.split('_')[2]); g = db.query(Guild).filter(Guild.id == gid).first()
        if g and g.member_count < 50:
            player.guild_id = g.id; g.member_count += 1; db.commit(); await query.answer("Entrou!")
            await handle_menu(update, context) # Refresh
        else: await query.answer("Erro.", show_alert=True)

    elif data == 'guild_create_start':
        if player.level < GUILD_MIN_LEVEL: await query.answer("Nível baixo!", show_alert=True); return
        if player.gems < GUILD_CREATE_COST: await query.answer("Gemas insuficientes!", show_alert=True); return
        context.user_data['waiting_guild_name'] = True
        await query.edit_message_text("Nome da Guilda:")

    elif data == 'guild_leave':
        g = db.query(Guild).filter(Guild.id == player.guild_id).first()
        g.member_count -= 1; player.guild_id = None; db.commit()
        await query.edit_message_text("Saiu.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))

    elif data.startswith('donate_start_'):
        context.user_data['waiting_donation_type'] = data.split('_')[-1]
        await query.edit_message_text("Digite valor:")

    # Construcoes
    elif data == 'menu_constructions':
        msg = (f"🏗️ **Construções**\n🌾 Fazenda: Lvl {player.farm_level}\n🏚️ Celeiro: Lvl {player.barn_level}\n⚔️ Quartel: Lvl {player.barracks_level}\n🔮 Academia: Lvl {player.academy_level}\n🏃 Pista: Lvl {player.track_level}\n❤️ Clínica: Lvl {player.clinic_level}")
        kb = [[InlineKeyboardButton("Fazenda", callback_data='constr_fazenda'), InlineKeyboardButton("Quartel", callback_data='constr_quartel')],
              [InlineKeyboardButton("Academia", callback_data='constr_academia'), InlineKeyboardButton("Pista", callback_data='constr_pista')],
              [InlineKeyboardButton("Clínica", callback_data='constr_clinica'), InlineKeyboardButton("Celeiro", callback_data='constr_celeiro')],
              [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data.startswith('constr_') or data.startswith('upgrade_'):
        B = {'fazenda': {'a':'farm_level', 'c':500, 'd':'Produz Trigo'}, 'celeiro': {'a':'barn_level', 'c':500, 'd':'Estoque'},
             'quartel': {'a':'barracks_level', 'c':2000, 'd':'Força'}, 'academia': {'a':'academy_level', 'c':1500, 'd':'Inteligência'},
             'pista': {'a':'track_level', 'c':2500, 'd':'Velocidade'}, 'clinica': {'a':'clinic_level', 'c':3000, 'd':'Cura'}}
        k = data.split('_')[1]; c = B[k]; lvl = getattr(player, c['a']); cost = int(c['c']*(1.5**lvl))
        
        if data.startswith('upgrade_'):
            if player.gold >= cost: player.gold -= cost; setattr(player, c['a'], lvl+1); db.commit(); await query.answer("Up!"); lvl+=1; cost = int(c['c']*(1.5**lvl))
            else: await query.answer("Sem ouro!")
        
        kb = [[InlineKeyboardButton(f"⬆️ Melhorar ({cost}g)", callback_data=f'upgrade_{k}')]]
        if k == 'fazenda' and lvl > 0: kb.insert(0, [InlineKeyboardButton("💰 Vender", callback_data='farm_harvest')])
        kb.append([InlineKeyboardButton("🔙", callback_data='menu_constructions')])
        await query.edit_message_text(f"🏗️ **{k.capitalize()}** Lvl {lvl}\n_{c['d']}_", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'farm_harvest':
        now = datetime.now(); el = (now - player.last_farm_harvest).total_seconds()/3600
        amt = min(int(el * player.farm_level * 100), player.barn_level * 100)
        if amt > 0: player.gold += amt; player.last_farm_harvest = now; db.commit(); await query.answer(f"Vendeu {amt}g!")
        else: await query.answer("Vazio.")
        await handle_menu(update, context)

    # Upgrade/Respec
    elif data == 'menu_upgrade':
        kb = [[InlineKeyboardButton(f"💪 Treinar ({int(50+player.strength*20)}g)", callback_data='up_str')],
              [InlineKeyboardButton(f"🔄 Mudar Classe ({RESPEC_COST}g)", callback_data='respec_start')], [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
        await query.edit_message_text(f"💪 **Treino**\nForça: {player.strength}", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'up_str':
        c = int(50+player.strength*20)
        if player.gold >= c: player.gold -= c; player.strength += 1; db.commit(); await query.answer("Up!")
        else: await query.answer("Sem ouro!")
        await handle_menu(update, context)

    elif data == 'respec_start':
        kb = []; row = []
        for c in VALID_CLASSES:
            row.append(InlineKeyboardButton(c, callback_data=f'respec_{c}'))
            if len(row)==3: kb.append(row); row=[]
        if row: kb.append(row)
        kb.append([InlineKeyboardButton("🔙", callback_data='menu_upgrade')])
        await query.edit_message_text("Escolha:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith('respec_'):
        if player.gems >= RESPEC_COST:
            nc = data.split('_')[1]; s = BASE_STATS[nc]
            player.gems -= RESPEC_COST; player.class_name = nc; player.strength = s['str']; player.defense = s['def']; player.intelligence = s['int']; player.health = player.max_health; db.commit()
            await query.edit_message_text(f"Nova classe: {nc}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))
        else: await query.answer("Gemas insuficientes!")

    # Outros
    elif data == 'menu_mailbox':
        kb = [[InlineKeyboardButton("Canal", url=OFFICIAL_CHANNEL_LINK)], [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
        await query.edit_message_text("Correio:", reply_markup=InlineKeyboardMarkup(kb))

    elif data == 'menu_info':
        lnk = f"https://t.me/{BOT_USERNAME}?start={player.id}"
        await query.edit_message_text(f"**{player.name}**\nLink: `{lnk}`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]), parse_mode='Markdown')

    elif data == 'menu_daily':
        if (datetime.now() - player.last_daily_claim) > timedelta(hours=24):
            kb = [[InlineKeyboardButton("💰 Pegar", callback_data='daily_claim_now')], [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
            await query.edit_message_text("Disponível!", reply_markup=InlineKeyboardMarkup(kb))
        else: await query.edit_message_text("Volte amanhã.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))

    elif data == 'daily_claim_now':
        player.gold += 1000; player.xp += 1000; player.last_daily_claim = datetime.now(); player.stamina = player.max_stamina; check_level_up(player); db.commit()
        await query.edit_message_text("Pegou!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))

    elif data == 'menu_shop':
        await query.edit_message_text("💎 Em breve.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))

    elif data == 'menu_ranking':
        top = db.query(Player).order_by(Player.pvp_rating.desc()).limit(10).all()
        txt = "\n".join([f"{i+1}. {p.name} ({p.pvp_rating})" for i, p in enumerate(top)])
        await query.edit_message_text(f"🏆 **Top 10**\n{txt}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]), parse_mode='Markdown')

    elif data == 'menu_refresh':
        await show_main_menu(update, player)

    db.close()

# --- ARQUIVO 5: bot.py ---
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
    app.add_handler(CommandHandler("promote", admin_promote))
    app.add_handler(CommandHandler("demote", admin_demote))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text_input))
    app.add_handler(CallbackQueryHandler(handle_class_selection, pattern='^class_'))
    app.add_handler(CallbackQueryHandler(confirm_name_handler, pattern='^confirm_name_'))
    app.add_handler(CallbackQueryHandler(handle_menu))
    
    return app
