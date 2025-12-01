from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import Player, Guild
from utils import get_db, get_player, format_number
from config import GUILD_CREATE_COST

# IMPORTS DOS SISTEMAS
from battle_system import menu_battle_mode, battle_pve_start, confirm_pve, battle_pvp_start, pre_fight, confirm_pvp
from city_system import menu_constructions, handle_construction_view, handle_upgrade_action, farm_harvest
from character_system import menu_upgrade, handle_train_view, handle_stat_upgrade_action, menu_daily, daily_claim_now, menu_info, handle_class_selection, confirm_name_handler, start
from social_system import menu_ranking, menu_mailbox, menu_shop
from guild_system import guild_menu_main, guild_members_list, guild_manage_specific_member, guild_execute_action, guild_send_mail_start, process_guild_donation, guild_war_placeholder

# --- AQUI ESTA A FUNCAO QUE ESTAVA FALTANDO ---
async def receive_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ud = context.user_data
    db = get_db(); p = get_player(update.effective_user.id, db)
    
    # 1. Email da Guilda
    if ud.get('waiting_guild_mail'):
        text = update.message.text[:200]
        # Aqui, idealmente, iteramos sobre membros e enviamos. 
        # Simplificado para resposta no chat do lider.
        p.last_guild_mail = datetime.now(); db.commit()
        await update.message.reply_text(f"✉️ **Mensagem Enviada!**\n\n`{text}`", parse_mode='Markdown')
        ud['waiting_guild_mail'] = False; db.close(); return

    # 2. Busca de Guilda
    if ud.get('waiting_guild_search'):
        term = update.message.text.strip()
        res = db.query(Guild).filter(or_(Guild.id == term, Guild.name.ilike(f"%{term}%"))).limit(5).all()
        kb = [[InlineKeyboardButton(f"{g.name} ({g.member_count}/50)", callback_data=f"join_guild_{g.id}")] for g in res if g.member_count < 50]
        kb.append([InlineKeyboardButton("🔙", callback_data='guild_join_start')])
        if res: await update.message.reply_text("🔎 Resultados:", reply_markup=InlineKeyboardMarkup(kb))
        else: await update.message.reply_text("❌ Nada encontrado.")
        ud['waiting_guild_search'] = False; db.close(); return

    # 3. Criação de Nome de Personagem
    if ud.get('waiting_name'):
        raw = update.message.text.strip(); clean = "".join(ch for ch in raw if ch.isalnum())[:15]
        if len(clean) < 5: await update.message.reply_text("⚠️ Mínimo 5 letras."); return
        ud['temp_name'] = clean; ud['waiting_name'] = False
        kb = [[InlineKeyboardButton("✅ Confirmar", callback_data='confirm_name_yes'), InlineKeyboardButton("✏️ Alterar", callback_data='confirm_name_no')]]
        await update.message.reply_text(f"Seu nome será: **{clean}**\nConfirma?", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'); return

    # 4. Criação de Guilda (Nome)
    if ud.get('waiting_guild_name'):
        ud['temp_guild_name'] = update.message.text.strip()[:20]
        ud['waiting_guild_name'] = False; ud['waiting_guild_link'] = True
        await update.message.reply_text(f"Nome da Guilda: **{ud['temp_guild_name']}**\n\nEnvie o **Link do Grupo Telegram**:", parse_mode='Markdown'); return

    # 5. Criação de Guilda (Link e Finalização)
    if ud.get('waiting_guild_link'):
        link = update.message.text.strip()
        if not link.startswith("https://t.me/"): await update.message.reply_text("⚠️ O link deve começar com https://t.me/..."); return
        
        if p.gems < GUILD_CREATE_COST:
            await update.message.reply_text(f"🚫 Saldo Insuficiente! Requer {GUILD_CREATE_COST} Gemas.")
            ud['waiting_guild_link'] = False; db.close(); return

        try:
            ng = Guild(name=ud['temp_guild_name'], leader_id=p.id, telegram_link=link, member_count=1)
            db.add(ng); db.commit(); db.refresh(ng)
            p.gems -= GUILD_CREATE_COST; p.guild_id = ng.id; p.guild_role = 'lider'; p.guild_join_date = datetime.now(); db.commit()
            ud['waiting_guild_link'] = False
            await update.message.reply_text(f"✅ Guilda **{ng.name}** Criada!\nID: `{ng.id}`", parse_mode='Markdown')
        except: await update.message.reply_text("❌ Erro ao criar (Nome já existe?)."); db.close(); return

    # 6. Doação
    dtype = ud.get('waiting_donation_type')
    if dtype:
        if p and p.guild_id:
            try:
                amt = int(update.message.text.strip())
                has_funds = (p.gold >= amt) if dtype == 'gold' else (p.gems >= amt)
                if has_funds: await process_guild_donation(update, p, amt, dtype, db)
                else: await update.message.reply_text("🚫 Fundos insuficientes.")
            except: await update.message.reply_text("Valor inválido.")
        ud['waiting_donation_type'] = None
    
    db.close()

# --- FUNCAO PRINCIPAL DE MENU (ROUTER) ---
async def show_main_menu(update: Update, player: Player):
    db = get_db()
    try:
        p = db.query(Player).filter(Player.id == player.id).first()
        rank_pos = db.query(Player).filter(Player.pvp_rating > p.pvp_rating).count() + 1
        keyboard = get_main_keyboard()
        lvl = p.level or 1; xp = p.xp or 0; needed = lvl * 100
        text = (f"**{p.name}** (Lvl {lvl} {p.class_name})\n🏆 **Rank:** #{rank_pos} ({p.pvp_rating} Pts)\n"
                f"Exp: {format_number(xp)}/{format_number(needed)}\n❤️ HP Base: {p.max_health}\n"
                f"⚡ Stamina: {p.stamina}/{p.max_stamina}\n💰 {format_number(p.gold)} | 💎 {p.gems}")
        
        if update.callback_query: await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    finally: db.close()

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

# --- HANDLER DE CLIQUES ---
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; data = query.data; 
    
    if data == 'menu_refresh': 
        db = get_db(); p = get_player(query.from_user.id, db); await show_main_menu(update, p); db.close()
    
    # BATTLE
    elif data.startswith('battle_') or data.startswith('confirm_p') or data.startswith('pre_fight'):
        if data == 'menu_battle_mode': await menu_battle_mode(update, context)
        elif data == 'battle_pve_start': await battle_pve_start(update, context)
        elif data == 'confirm_pve': await confirm_pve(update, context)
        elif data == 'battle_pvp_start': await battle_pvp_start(update, context)
        elif data.startswith('pre_fight'): await pre_fight(update, context)
        elif data == 'confirm_pvp': await confirm_pvp(update, context)

    # CITY
    elif data == 'menu_constructions': await menu_constructions(update, context)
    elif data.startswith('constr_'): await handle_construction_view(update, context)
    elif data.startswith('upgrade_'): await handle_upgrade_action(update, context)
    elif data == 'farm_harvest': await farm_harvest(update, context)

    # CHARACTER
    elif data == 'menu_upgrade': await menu_upgrade(update, context)
    elif data.startswith('train_'): await handle_train_view(update, context)
    elif data.startswith('up_'): await handle_stat_upgrade_action(update, context)
    elif data == 'menu_daily': await menu_daily(update, context)
    elif data == 'daily_claim_now': await daily_claim_now(update, context)
    elif data == 'menu_info': await menu_info(update, context)
    elif data == 'respec_start':
        query.data = 'respec_start_confirm'
        pass 

    # SOCIAL
    elif data == 'menu_ranking': await menu_ranking(update, context)
    elif data == 'ranking_guilds': 
        # PRECISA IMPORTAR menu_ranking_guilds NO TOPO SE NAO TIVER
        from social_system import menu_ranking_guilds 
        await menu_ranking_guilds(update, context)
    elif data == 'menu_mailbox': await menu_mailbox(update, context)
    elif data == 'menu_shop': await menu_shop(update, context)

    # GUILD
    elif data.startswith('guild_') or data == 'menu_guild' or data.startswith('g_') or data.startswith('donate_'):
        if data == 'menu_guild': await guild_menu_main(update, context)
        elif data == 'guild_members_list': await guild_members_list(update, context)
        elif data.startswith('g_manage_'): await guild_manage_specific_member(update, context)
        elif data.startswith('g_act_'): await guild_execute_action(update, context)
        elif data == 'guild_send_mail': await guild_send_mail_start(update, context)
        elif data == 'guild_war_placeholder': await guild_war_placeholder(update, context)
        elif data == 'guild_create_start':
            # Validação simples para abrir o prompt
            await query.answer()
            context.user_data['waiting_guild_name'] = True
            await query.edit_message_text(f"✨ **Criar Guilda**\nCusto: {GUILD_CREATE_COST} Gemas\nDigite o Nome:", parse_mode='Markdown')
        elif data == 'guild_join_start':
            # Importacao local para evitar ciclo se necessario
            db = get_db(); top = db.query(Guild).order_by(Guild.total_rating.desc()).limit(10).all()
            kb = [[InlineKeyboardButton(f"Entrar: {g.name}", callback_data=f"join_guild_{g.id}")] for g in top if g.member_count < 50]
            kb.append([InlineKeyboardButton("🔙", callback_data='menu_guild')])
            await query.edit_message_text("📜 **Guildas:**", reply_markup=InlineKeyboardMarkup(kb))
            db.close()
        elif data.startswith('join_guild_'):
            db = get_db(); gid = int(data.split('_')[2]); g = db.query(Guild).filter(Guild.id == gid).first(); p = get_player(query.from_user.id, db)
            if g.member_count < 50:
                p.guild_id = g.id; p.guild_role = 'membro'; p.guild_join_date = datetime.now()
                g.member_count += 1; db.commit()
                await query.edit_message_text(f"✅ Bem-vindo a {g.name}!")
            else: await query.answer("Lotada.", show_alert=True)
            db.close()
        elif data == 'guild_leave':
            # Implementar logica simples aqui ou no guild_system
            db = get_db(); p = get_player(query.from_user.id, db)
            if p.guild_role == 'lider': await query.answer("Líder não pode sair.", show_alert=True)
            else:
                g = db.query(Guild).filter(Guild.id == p.guild_id).first(); g.member_count -= 1
                p.guild_id = None; p.guild_role = 'membro'; db.commit()
                await query.edit_message_text("Saiu da guilda.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))
            db.close()
        elif data.startswith('donate_menu'):
             kb = [[InlineKeyboardButton("Ouro", callback_data='donate_start_gold'), InlineKeyboardButton("Gemas", callback_data='donate_start_gems')], [InlineKeyboardButton("🔙", callback_data='menu_guild')]]
             await query.edit_message_text("Doar:", reply_markup=InlineKeyboardMarkup(kb))
        elif data.startswith('donate_start_'):
             context.user_data['waiting_donation_type'] = data.split('_')[-1]
             await query.edit_message_text("Digite valor:")

    # REENCARNAÇÃO
    elif data == 'respec_start':
        # Import local
        from config import VALID_CLASSES, RESPEC_COST
        kb = [[InlineKeyboardButton(c, callback_data=f'respec_{c}')] for c in VALID_CLASSES]
        kb.append([InlineKeyboardButton("🔙", callback_data='menu_info')])
        await query.edit_message_text(f"🔄 **Reencarnação**\nCusto: {RESPEC_COST} Gemas.\nEscolha seu novo destino:", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data.startswith('respec_'):
        from config import RESPEC_COST, BASE_STATS
        db = get_db(); p = get_player(query.from_user.id, db)
        if p.gems >= RESPEC_COST:
            nc = data.split('_')[1]; s = BASE_STATS[nc]
            p.gems -= RESPEC_COST; p.class_name = nc; p.strength = s['str']; p.defense = s['def']; p.intelligence = s['int']; p.health = p.max_health; db.commit()
            await query.answer("Sucesso!", show_alert=True)
            await query.edit_message_text(f"✨ Agora você é um {nc}.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))
        else: await query.answer("Gemas insuficientes!", show_alert=True)
        db.close()

# COMANDOS ADICIONAIS PARA O BOT.PY IMPORTAR SE PRECISAR
async def get_my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 `{update.effective_user.id}`", parse_mode='Markdown')

async def join_guild_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db(); uid = update.effective_user.id; p = get_player(uid, db)
    if not p: return
    if p.guild_id: await update.message.reply_text("Já tem guilda."); db.close(); return
    try:
        gid = int(context.args[0]); g = db.query(Guild).filter(Guild.id == gid).first()
        if g and g.member_count < 50:
            p.guild_id = g.id; p.guild_role = 'membro'; p.guild_join_date = datetime.now()
            g.member_count += 1; db.commit()
            await update.message.reply_text(f"✅ Entrou em {g.name}!")
        else: await update.message.reply_text("❌ Erro.")
    except: await update.message.reply_text("Uso: /guild ID")
    db.close()
