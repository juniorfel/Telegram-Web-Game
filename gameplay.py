import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import Player, Guild, GuildRequest
from sqlalchemy import or_, func
from utils import get_db, get_player, format_number, check_level_up, generate_monster, apply_passive_healing, simulate_pvp_battle, is_admin, get_total_stats, calculate_daily_bonus
from config import *
from guild_system import guild_menu_main, guild_members_list, guild_manage_specific_member, guild_execute_action, guild_send_mail_start, process_guild_donation, guild_war_placeholder

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user; db = get_db()
    try:
        player = get_player(user.id, db)
        if player and player.is_banned: await update.message.reply_text("🚫 Conta Banida."); return
        if context.args and not player:
            try:
                rid = int(context.args[0])
                if rid != user.id: context.user_data['referrer_id'] = rid
            except ValueError: pass 
        if not player:
            summary = ""
            for name, data in BASE_STATS.items():
                summary += f"\n**{name}**: {data['desc']}\n   ❤️ {data['hp']} | 💪 {data['str']} | 🧠 {data['int']} | 🛡️ {data['def']}"
            kb = []; row = []
            for c in VALID_CLASSES + ['Aleatorio']:
                row.append(InlineKeyboardButton(f"{c} 🎲" if c=='Aleatorio' else c, callback_data=f'class_{c}'))
                if len(row) == 3: kb.append(row); row = []
            if row: kb.append(row)
            await update.message.reply_text(f"✨ **Bem-vindo a Aerthos!**\nEscolha sua classe:\n{summary}", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        else:
            apply_passive_healing(player, db); db.commit()
            await show_main_menu(update, player)
    finally: db.close()

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

async def handle_class_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query; await query.answer()
    c = query.data.split('_')[1]
    if c == 'Aleatorio': c = random.choice(VALID_CLASSES)
    context.user_data['temp_class'] = c; context.user_data['waiting_name'] = True
    await query.edit_message_text(f"Classe **{c}**! Qual seu nome? (Min 5 letras)", parse_mode='Markdown')

async def receive_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ud = context.user_data
    
    if ud.get('waiting_guild_mail'):
        text = update.message.text[:200]; db = get_db(); p = get_player(update.effective_user.id, db)
        p.last_guild_mail = datetime.now(); db.commit()
        await update.message.reply_text(f"✉️ **Enviado:**\n`{text}`", parse_mode='Markdown')
        ud['waiting_guild_mail'] = False; db.close(); return

    if ud.get('waiting_guild_search'):
        term = update.message.text.strip(); db = get_db()
        res = db.query(Guild).filter(or_(Guild.id == term, Guild.name.ilike(f"%{term}%"))).limit(5).all()
        kb = []
        if res:
            for g in res: 
                if g.member_count < 50: kb.append([InlineKeyboardButton(f"{g.name} ({g.member_count}/50)", callback_data=f"join_guild_{g.id}")])
            kb.append([InlineKeyboardButton("🔙", callback_data='guild_join_start')])
            await update.message.reply_text(f"Resultados:", reply_markup=InlineKeyboardMarkup(kb))
        else: await update.message.reply_text("❌ Nada encontrado.")
        ud['waiting_guild_search'] = False; db.close(); return

    if ud.get('waiting_name'):
        raw = update.message.text.strip(); clean = "".join(ch for ch in raw if ch.isalnum())[:15]
        if len(clean) < 5: await update.message.reply_text("⚠️ Mínimo 5 letras."); return
        ud['temp_name'] = clean; ud['waiting_name'] = False
        kb = [[InlineKeyboardButton("✅ Confirmar", callback_data='confirm_name_yes'), InlineKeyboardButton("✏️ Alterar", callback_data='confirm_name_no')]]
        await update.message.reply_text(f"Nome: **{clean}**. Confirma?", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'); return

    if ud.get('waiting_guild_name'):
        ud['temp_guild_name'] = update.message.text.strip()[:20]
        ud['waiting_guild_name'] = False; ud['waiting_guild_link'] = True
        await update.message.reply_text(f"Nome: **{ud['temp_guild_name']}**\n\n🔗 Agora envie o **Link do Grupo Telegram**:", parse_mode='Markdown'); return

    if ud.get('waiting_guild_link'):
        link = update.message.text.strip()
        if not link.startswith("https://t.me/"): await update.message.reply_text("⚠️ O link deve começar com https://t.me/..."); return
        
        db = get_db(); p = get_player(update.effective_user.id, db)
        
        if p.gems < GUILD_CREATE_COST:
            await update.message.reply_text(f"🚫 **Erro:** Você precisa de {GUILD_CREATE_COST} Gemas para fundar a guilda!\nSeu saldo atual: {p.gems} 💎", parse_mode='Markdown')
            ud['waiting_guild_link'] = False
            db.close(); return

        try:
            ng = Guild(name=ud['temp_guild_name'], leader_id=p.id, telegram_link=link, member_count=1)
            db.add(ng); db.commit(); db.refresh(ng)
            
            p.gems -= GUILD_CREATE_COST
            p.guild_id = ng.id; p.guild_role = 'lider'; p.guild_join_date = datetime.now(); db.commit()
            
            ud['waiting_guild_link'] = False
            await update.message.reply_text(
                f"✅ **Guilda Fundada com Sucesso!**\n\n"
                f"🛡️ **{ng.name}**\n"
                f"🆔 ID: `{ng.id}`\n"
                f"💎 Custo: -{GUILD_CREATE_COST} Gemas\n\n"
                f"Convide membros com `/guild {ng.id}`", 
                parse_mode='Markdown'
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Erro ao criar (Nome já existe?). Tente novamente."); 
            print(f"Erro Guilda: {e}")
        db.close(); return

    dtype = ud.get('waiting_donation_type')
    if dtype:
        db = get_db(); p = get_player(update.effective_user.id, db)
        if p and p.guild_id:
            try:
                amt = int(update.message.text.strip())
                if amt <= 0: raise ValueError
                has_funds = (p.gold >= amt) if dtype == 'gold' else (p.gems >= amt)
                if has_funds: await process_guild_donation(update, p, amt, dtype, db)
                else: await update.message.reply_text("🚫 Fundos insuficientes.")
            except: await update.message.reply_text("Valor inválido.")
        ud['waiting_donation_type'] = None; db.close()

async def confirm_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query; await query.answer()
    if query.data == 'confirm_name_no': context.user_data['waiting_name'] = True; await query.edit_message_text("Digite o nome:"); return
    
    name = context.user_data.get('temp_name'); c_class = context.user_data.get('temp_class')
    user_id = update.effective_user.id; db = get_db()
    if get_player(user_id, db): db.close(); await show_main_menu(update, get_player(user_id, get_db())); return

    s = BASE_STATS[c_class]
    p = Player(id=user_id, username=update.effective_user.username, name=name, class_name=c_class,
               health=s['hp'], max_health=s['hp'], strength=s['str'], intelligence=s['int'], defense=s['def'],
               speed=s['spd'], crit_chance=s['crit'], gold=INITIAL_GOLD, level=1, xp=0)
    db.add(p); db.commit()
    
    await query.answer(f"Bem-vindo!", show_alert=True); await show_main_menu(update, p); db.close()

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer(); data = query.data; db = get_db()
    player = get_player(query.from_user.id, db)
    if not player: return

    # --- MENU DE BATALHA (MOSTRANDO STAMINA) ---
    if data == 'menu_battle_mode':
        st = get_total_stats(player) # Mostra stats reais
        msg = (f"⚔️ **Zona de Batalha**\n\n"
               f"⚡ **Stamina: {player.stamina}/{player.max_stamina}**\n" # <--- MOSTRANDO CLARAMENTE
               f"📊 **Atributos:**\n"
               f"💪 {st['str']} | 🧠 {st['int']} | 🛡️ {st['def']}\n"
               f"💨 {st['spd']} | ❤️ {st['hp']}\n"
               f"🏆 Rank: {player.pvp_rating}")
        kb = [[InlineKeyboardButton("🗺️ Campanha PVE", callback_data='battle_pve_start'), 
               InlineKeyboardButton("🆚 Arena PVP", callback_data='battle_pvp_start')], 
              [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'battle_pve_start':
        m = generate_monster(player.current_phase_id)
        context.user_data['monster'] = m
        msg = (f"🗺️ **Campanha: Fase {player.current_phase_id}**\n\n"
               f"⚡ **Sua Stamina: {player.stamina}/{player.max_stamina}**\n\n" # <--- MOSTRANDO
               f"🔥 {m['name']}\n❤️ HP: {m['hp']} | ⚡ Spd: {m['spd']}\n💰 {m['gold']}g | ✨ {m['xp']}xp")
        kb = [[InlineKeyboardButton("⚔️ ATACAR (1 Stamina)", callback_data='confirm_pve')], [InlineKeyboardButton("🔙", callback_data='menu_battle_mode')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'confirm_pve':
        if player.stamina < STAMINA_COST: 
            await query.answer(f"🚫 Sem Stamina! Você tem {player.stamina}/{STAMINA_COST}.", show_alert=True) # <--- AVISO CLARO
            return
        
        m = context.user_data.get('monster')
        
        # Gate de Boss
        st = get_total_stats(player)
        if m['is_boss'] and (st['str'] + st['int'] + st['def']) < (player.current_phase_id * 5):
            await query.answer("Muito fraco para o Boss!", show_alert=True); return

        player.stamina -= STAMINA_COST
        
        p_pow = (st['str'] * 2) + st['int'] + st['def']
        m_pow = m['atk'] + m['def'] + m['hp'] / 10
        chance = max(0.1, min(0.9, 0.5 + ((p_pow - m_pow) / 500)))
        
        if random.random() < chance:
            player.gold += m['gold']; player.xp += m['xp']; player.current_phase_id += 1; check_level_up(player)
            loot = ""
            if random.random() < 0.1: # 10% Drop
                if random.choice([True, False]): player.gems += 2; loot = "\n💎 Drop Raro: +2 Gemas!"
                else: player.stamina += 2; loot = "\n⚡ Drop: +2 Stamina!"
            msg = f"⚔️ **Vitória!**\n+{m['gold']}g | +{m['xp']}xp{loot}"
        else: msg = "☠️ **Derrota...**"
        db.commit(); kb = [[InlineKeyboardButton("Continuar", callback_data='menu_battle_mode')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'battle_pvp_start':
        rating_range = 200; min_r = max(0, player.pvp_rating - rating_range); max_r = player.pvp_rating + rating_range
        opps = db.query(Player).filter(Player.id != player.id, Player.pvp_rating >= min_r, Player.pvp_rating <= max_r).order_by(func.random()).limit(4).all()
        if not opps: opps = db.query(Player).filter(Player.id != player.id).order_by(func.random()).limit(4).all()
        
        kb = []
        for o in opps:
            icon = "🟢" if o.pvp_rating <= player.pvp_rating else "🔴"
            kb.append([InlineKeyboardButton(f"{icon} {o.name} ({o.pvp_rating})", callback_data=f'pre_fight_{o.id}')])
        kb.append([InlineKeyboardButton("🔄 Atualizar", callback_data='battle_pvp_start'), InlineKeyboardButton("🔙", callback_data='menu_battle_mode')])
        await query.edit_message_text(f"⚔️ **Arena PvP**\n⚡ **Stamina: {player.stamina}/{player.max_stamina}**\nSeus Pontos: {player.pvp_rating}", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data.startswith('pre_fight_'):
        oid = int(data.split('_')[2]); opp = db.query(Player).filter(Player.id == oid).first()
        context.user_data['opponent_id'] = opp.id
        kb = [[InlineKeyboardButton("⚔️ LUTAR (1 Stamina)", callback_data='confirm_pvp')], [InlineKeyboardButton("🔙", callback_data='battle_pvp_start')]]
        await query.edit_message_text(f"🆚 **{opp.name}**\nRating: {opp.pvp_rating}\n\n⚡ **Sua Stamina: {player.stamina}/{player.max_stamina}**\n\nVitória: +25 | Derrota: -15", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'confirm_pvp':
        if player.stamina < STAMINA_COST:
            await query.answer(f"🚫 Sem Stamina! Você tem {player.stamina}/{STAMINA_COST}.", show_alert=True) # <--- AVISO CLARO
            return
            
        opp = db.query(Player).filter(Player.id == context.user_data.get('opponent_id')).first()
        player.stamina -= STAMINA_COST
        winner = simulate_pvp_battle(player, opp)
        
        if winner.id == player.id:
            player.pvp_rating += 25
            msg = "🏆 **Vitória!**\n+25 Pontos!"
            if player.guild_id: 
                g = db.query(Guild).filter(Guild.id == player.guild_id).first()
                g.xp += 10; msg += "\n🛡️ +10 XP Clã"
                if check_level_up(g): msg += " (LEVEL UP!)"
        else:
            player.pvp_rating = max(0, player.pvp_rating - 15); msg = "🏳️ **Derrota...**\n-15 Pontos."
        db.commit()
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Continuar", callback_data='battle_pvp_start')]]), parse_mode='Markdown')

    # --- GUILD SYSTEM ---
    elif data.startswith('guild_') or data == 'menu_guild' or data.startswith('g_'):
        if data == 'menu_guild': await guild_menu_main(update, context)
        elif data == 'guild_members_list': await guild_members_list(update, context)
        elif data.startswith('g_manage_'): await guild_manage_specific_member(update, context)
        elif data.startswith('g_act_'): await guild_execute_action(update, context)
        elif data == 'guild_send_mail': await guild_send_mail_start(update, context)
        elif data == 'guild_war_placeholder': await guild_war_placeholder(update, context)
        
        elif data == 'guild_create_start':
            # --- VALIDAÇÃO DE GEMAS INICIAL ---
            if player.gems < GUILD_CREATE_COST:
                await query.answer(f"🚫 Saldo Insuficiente!\nVocê precisa de {GUILD_CREATE_COST} Gemas.", show_alert=True)
                return
            context.user_data['waiting_guild_name'] = True
            await query.edit_message_text(f"✨ **Criar Nova Guilda**\n\n💰 Custo: **{GUILD_CREATE_COST} Gemas**\n\n🛡️ Digite o **Nome da Guilda** no chat:", parse_mode='Markdown')
            
        elif data == 'guild_join_start':
            top = db.query(Guild).order_by(Guild.total_rating.desc()).limit(10).all()
            kb = [[InlineKeyboardButton(f"Entrar: {g.name}", callback_data=f"join_guild_{g.id}")] for g in top if g.member_count < 50]
            kb.append([InlineKeyboardButton("🔙", callback_data='menu_guild')])
            await query.edit_message_text("📜 **Guildas:**", reply_markup=InlineKeyboardMarkup(kb))
        elif data.startswith('join_guild_'):
            gid = int(data.split('_')[2]); g = db.query(Guild).filter(Guild.id == gid).first()
            if g.member_count < 50:
                player.guild_id = g.id; player.guild_role = 'membro'; player.guild_join_date = datetime.now()
                g.member_count += 1; db.commit()
                await query.edit_message_text(f"✅ Bem-vindo a {g.name}!")
            else: await query.answer("Lotada.", show_alert=True)
        elif data == 'guild_leave':
            if player.guild_role == 'lider': await query.answer("Líder não pode sair.", show_alert=True)
            else:
                g = db.query(Guild).filter(Guild.id == player.guild_id).first()
                g.member_count -= 1; player.guild_id = None; player.guild_role = 'membro'
                db.commit(); await query.edit_message_text("Saiu da guilda.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))

    elif data.startswith('donate_start_'):
        context.user_data['waiting_donation_type'] = data.split('_')[-1]
        await query.edit_message_text("🏦 Quanto quer doar?")

    elif data == 'donate_menu':
        kb = [[InlineKeyboardButton("💰 Doar Ouro", callback_data='donate_start_gold'), InlineKeyboardButton("💎 Doar Gemas", callback_data='donate_start_gems')], [InlineKeyboardButton("🔙", callback_data='menu_guild')]]
        await query.edit_message_text("🏦 **Cofre da Guilda**\nEscolha o recurso:", reply_markup=InlineKeyboardMarkup(kb))

    elif data == 'menu_daily':
        now = datetime.now()
        if (now - player.last_daily_claim) > timedelta(hours=24):
            g = db.query(Guild).filter(Guild.id == player.guild_id).first() if player.guild_id else None
            gold, xp, gems, b_msg = calculate_daily_bonus(player, g)
            await query.edit_message_text(f"🎁 **Diário**\n💰 {gold}\n✨ {xp} {f'| 💎 {gems}' if gems else ''}{b_msg}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Receber", callback_data='daily_claim_now')]]), parse_mode='Markdown')
        else: await query.edit_message_text("⏳ Volte amanhã.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))

    elif data == 'daily_claim_now':
        g = db.query(Guild).filter(Guild.id == player.guild_id).first() if player.guild_id else None
        gold, xp, gems, _ = calculate_daily_bonus(player, g)
        player.gold += gold; player.xp += xp; player.gems += gems; player.last_daily_claim = datetime.now(); player.stamina = player.max_stamina
        check_level_up(player); db.commit()
        await query.edit_message_text("✅ Resgatado!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))

    elif data == 'menu_refresh': await show_main_menu(update, player)
    
    # --- MENUS DE CONSTRUÇÃO E UPGRADE ---
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
        conf = B.get(key)
        
        if conf:
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

    # --- MENUS RESTANTES (UPGRADE, RANKING, ETC) ---
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

    elif data == 'menu_mailbox':
        kb = [[InlineKeyboardButton("📢 Canal Oficial", url=OFFICIAL_CHANNEL_LINK)], [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
        await query.edit_message_text("✉️ **Correio Real**\nFique atento aos decretos e eventos:", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'menu_info':
        lnk = f"https://t.me/{BOT_USERNAME}?start={player.id}"
        await query.edit_message_text(f"📜 **Pergaminho de Status**\n\n**{player.name}**\n💪 {player.strength} | 🧠 {player.intelligence}\n🛡️ {player.defense} | ⚡ {player.speed}\n\n🔗 **Recrutamento:**\n`{lnk}`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]), parse_mode='Markdown')

    elif data == 'menu_shop':
        await query.edit_message_text("💎 **Mercado Negro VIP**\n\n🚧 Os mercadores estão viajando. (Em breve via XSolla)", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]), parse_mode='Markdown')

    elif data == 'menu_ranking':
        top = db.query(Player).order_by(Player.pvp_rating.desc()).limit(10).all()
        txt = "🏆 **Salão da Fama**\n" + "\n".join([f"#{i+1} {p.name} ({p.pvp_rating} Pts)" for i, p in enumerate(top)])
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]), parse_mode='Markdown')

    elif data == 'menu_refresh': await show_main_menu(update, player)
    
    db.close()

# COMANDOS NOVOS
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
