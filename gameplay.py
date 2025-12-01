# gameplay.py
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import Player, Guild
from sqlalchemy import or_, func
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
            apply_passive_healing(player, db) 
            db.commit()
            await show_main_menu(update, player)
    finally: db.close()

async def show_main_menu(update: Update, player: Player):
    db = get_db()
    try:
        p = db.query(Player).filter(Player.id == player.id).first()
        
        # --- CÁLCULO DO RANKING (Pontos) ---
        rank_pos = db.query(Player).filter(Player.pvp_rating > p.pvp_rating).count() + 1
        
        keyboard = get_main_keyboard()
        lvl = p.level if p.level else 1
        xp = p.xp if p.xp else 0
        needed = lvl * 100
        perc = (xp / needed) * 100 if needed > 0 else 0
        safe_name = str(p.name).replace("_", " ").replace("*", "").replace("`", "") if p.name else "Herói"
        
        text = (f"**{safe_name}** (Lvl {lvl} {p.class_name})\n"
                f"🏆 **Rank Global:** #{rank_pos} ({p.pvp_rating} Pontos)\n"
                f"Exp: {format_number(xp)}/{format_number(needed)} ({perc:.1f}%)\n"
                f"❤️ HP Base: {p.max_health}\n"
                f"⚡ Stamina: {p.stamina}/{p.max_stamina}\n"
                f"💰 {format_number(p.gold)} | 💎 {p.gems}")
        
        if update.callback_query:
            try: await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            except: await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    finally:
        db.close()

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

# --- HANDLER GERAL ---
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    data = query.data; db = get_db()
    player = get_player(query.from_user.id, db)
    if not player: return

    if data == 'menu_battle_mode':
        power = (player.strength * 2) + player.intelligence + player.defense
        msg = (f"⚔️ **Zona de Batalha**\n\n"
               f"📊 **Seus Status:**\n"
               f"❤️ HP Base: {player.max_health} | ⚡ Stamina: {player.stamina}/{player.max_stamina}\n"
               f"⚔️ Poder: {power} | 🏆 Rank: {player.pvp_rating}\n\n"
               f"Escolha seu destino:")
        kb = [[InlineKeyboardButton("🗺️ Campanha PVE", callback_data='battle_pve_start'), 
               InlineKeyboardButton("🆚 Arena PVP", callback_data='battle_pvp_start')], 
              [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    # --- PVE / CAMPANHA ---
    elif data == 'battle_pve_start':
        m = generate_monster(player.current_phase_id)
        context.user_data['monster'] = m
        
        # Aviso se for Boss
        boss_warn = "\n⚠️ **ALERTA DE CHEFE!**" if m['is_boss'] else ""
        
        msg = (f"🗺️ **Campanha: Fase {player.current_phase_id}**{boss_warn}\n\n"
               f"🔥 **Inimigo:** {m['name']}\n"
               f"❤️ HP: {m['hp']} | ⚡ Spd: {m['spd']}\n"
               f"💰 Recompensa: {m['gold']}g | ✨ {m['xp']}xp")
        
        kb = [[InlineKeyboardButton("⚔️ ATACAR (1 Stamina)", callback_data='confirm_pve')], 
              [InlineKeyboardButton("🔙 Recuar", callback_data='menu_battle_mode')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'confirm_pve':
        if player.stamina < STAMINA_COST: await query.answer("⚡ Exausto!", show_alert=True); return
        
        m = context.user_data.get('monster')
        if not m: await handle_menu(update, context); return
        
        # --- LÓGICA DE GATE DE BOSS (OPÇÃO 3) ---
        if m['is_boss']:
            # Poder necessário = Fase * 5 (Ex: Fase 10 precisa de 50 stats totais)
            total_stats = player.strength + player.defense + player.intelligence
            required = player.current_phase_id * 5
            
            if total_stats < required:
                await query.answer(f"🚫 MUITO FRACO! Precisa de {required} status totais.", show_alert=True)
                msg = (f"🔒 **O Guardião bloqueia sua passagem!**\n\n"
                       f"O {m['name']} ri da sua fraqueza.\n"
                       f"Seu Poder: {total_stats}\n"
                       f"Necessário: {required}\n\n"
                       f"Vá treinar no menu 'Upgrade'!")
                kb = [[InlineKeyboardButton("💪 Ir Treinar", callback_data='menu_upgrade'), InlineKeyboardButton("🔙 Voltar", callback_data='menu_battle_mode')]]
                await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
                return

        player.stamina -= STAMINA_COST
        
        # LÓGICA DE BATALHA
        p_pow = (player.strength * 2) + player.intelligence + player.defense
        m_pow = m['atk'] + m['def'] + m['hp'] / 10
        
        chance = 0.5 + ((p_pow - m_pow) / 500) 
        chance = max(0.1, min(0.9, chance))
        
        if random.random() < chance:
            player.gold += m['gold']; player.xp += m['xp']; player.current_phase_id += 1; check_level_up(player)
            
            # --- LÓGICA DE DROPS RAROS (OPÇÃO 2) ---
            loot_msg = ""
            if random.random() < 0.10: # 10% de chance
                drop_type = random.choice(['gems', 'stamina'])
                if drop_type == 'gems':
                    gems_found = random.randint(1, 3)
                    player.gems += gems_found
                    loot_msg = f"\n💎 **SORTUDO!** Você achou {gems_found} Gemas!"
                else:
                    player.stamina = min(player.max_stamina, player.stamina + 2)
                    loot_msg = f"\n⚡ **ENERGIA!** Recuperou 2 Stamina!"
            
            msg = f"⚔️ **Vitória Gloriosa!**\nO inimigo caiu.\nSaque: +{m['gold']}g | +{m['xp']}xp{loot_msg}"
        else:
            msg = f"☠️ **Derrota...**\nO inimigo era muito forte. Tente melhorar seus atributos."
        
        db.commit()
        kb = [[InlineKeyboardButton("Continuar", callback_data='menu_battle_mode')]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    # --- PVP / ARENA (ATUALIZADO PARA PONTOS) ---
    elif data == 'battle_pvp_start':
        my_rank = db.query(Player).filter(Player.pvp_rating > player.pvp_rating).count() + 1
        
        # Faixa de busca (+/- 200 Pontos)
        rating_range = 200
        min_r = max(0, player.pvp_rating - rating_range)
        max_r = player.pvp_rating + rating_range
        
        opponents = db.query(Player).filter(
            Player.id != player.id,
            Player.pvp_rating >= min_r, 
            Player.pvp_rating <= max_r
        ).order_by(func.random()).limit(4).all()
        
        if len(opponents) == 0:
            opponents = db.query(Player).filter(Player.id != player.id).order_by(func.random()).limit(4).all()

        kb = []
        for opp in opponents:
            diff_icon = "🟢" 
            if opp.pvp_rating > player.pvp_rating + 50: diff_icon = "🔴"
            elif opp.pvp_rating > player.pvp_rating: diff_icon = "🟡"
            
            btn_text = f"{diff_icon} {opp.name} ({opp.pvp_rating})"
            kb.append([InlineKeyboardButton(btn_text, callback_data=f'pre_fight_{opp.id}')])

        if not opponents:
            kb.append([InlineKeyboardButton("Ninguém à vista...", callback_data='ignore')])

        kb.append([
            InlineKeyboardButton("🔄 Atualizar Lista", callback_data='battle_pvp_start'),
            InlineKeyboardButton("🔙 Voltar", callback_data='menu_battle_mode')
        ])

        msg = (f"⚔️ **Arena PvP - Lobby**\n\n"
               f"ℹ️ **Regras:** Vitória: +25 Pontos | Derrota: -15 Pontos\n\n"
               f"👤 **Seu Rank:** #{my_rank}\n"
               f"🏆 **Seus Pontos:** {player.pvp_rating}\n\n"
               f"Escolha um oponente:")
        
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data.startswith('pre_fight_'):
        opp_id = int(data.split('_')[2])
        opp = db.query(Player).filter(Player.id == opp_id).first()
        
        if not opp:
            await query.answer("Oponente sumiu!", show_alert=True)
            await handle_menu(update, context); return

        context.user_data['opponent_id'] = opp.id
        
        diff = opp.pvp_rating - player.pvp_rating
        chance_est = "Média"
        if diff > 100: chance_est = "Baixa ☠️"
        elif diff < -100: chance_est = "Alta 🔥"

        kb = [
            [InlineKeyboardButton("⚔️ LUTAR AGORA (1 Stamina)", callback_data='confirm_pvp')],
            [InlineKeyboardButton("🔙 Escolher Outro", callback_data='battle_pvp_start')]
        ]
        
        msg = (f"🆚 **Previsão de Batalha**\n\n"
               f"🫵 **Você** vs **{opp.name}**\n"
               f"📊 Pontos: {player.pvp_rating} vs {opp.pvp_rating}\n"
               f"🎲 Chance de Vitória: {chance_est}\n\n"
               f"Deseja gastar 1 Stamina para atacar?")
        
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data == 'confirm_pvp':
        if player.stamina < STAMINA_COST: await query.answer("⚡ Exausto!", show_alert=True); return
        opp = db.query(Player).filter(Player.id == context.user_data.get('opponent_id')).first()
        
        if not opp:
             await query.answer("Oponente inválido.", show_alert=True)
             await handle_menu(update, context); return

        player.stamina -= STAMINA_COST
        
        winner = simulate_pvp_battle(player, opp)
        
        if winner.id == player.id:
            player.pvp_rating += 25
            msg = f"🏆 **Vitória!**\nVocê derrotou {opp.name}.\n+25 Pontos no Ranking!"
        else:
            player.pvp_rating = max(0, player.pvp_rating - 15)
            msg = f"🏳️ **Derrota...**\n{opp.name} era mais forte.\n-15 Pontos..."
            
        db.commit()
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Continuar", callback_data='battle_pvp_start')]]), parse_mode='Markdown')

    # --- RESTANTE DO MENU (GUILDA, CONSTRUÇÃO, UPGRADE, ETC) ---
    # Mantido idêntico para não quebrar funcionalidades
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
        if g: g.member_count -= 1
        player.guild_id = None; db.commit()
        await query.edit_message_text("Você deixou a guilda.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))

    elif data.startswith('donate_start_'):
        context.user_data['waiting_donation_type'] = data.split('_')[-1]
        await query.edit_message_text(f"🏦 Digite o valor para doar:")

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
        txt = "🏆 **Salão da Fama**\n" + "\n".join([f"#{i+1} {p.name} ({p.pvp_rating} Pts)" for i, p in enumerate(top)])
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]), parse_mode='Markdown')

    elif data == 'menu_refresh':
        await show_main_menu(update, player)

    db.close()
