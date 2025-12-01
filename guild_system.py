# guild_system.py
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import Player, Guild, GuildRequest
from utils import get_db, get_player, format_number, get_guild_level_data, check_guild_level_up

# --- PERMISSÕES E REGRAS ---
ROLES = {'lider': 4, 'coolider': 3, 'anciao': 2, 'membro': 1}

def can_manage(actor_role, target_role):
    """Retorna True se o actor tem cargo superior ao target"""
    return ROLES.get(actor_role, 0) > ROLES.get(target_role, 0)

def check_permission(player, action):
    role = player.guild_role
    if action in ['invite', 'accept', 'kick']: return role in ['lider', 'coolider', 'anciao']
    if action in ['promote_elder', 'promote_co', 'demote', 'mail', 'war']: return role in ['lider', 'coolider']
    if action == 'transfer_leadership': return role == 'lider'
    return False

# --- LÓGICA DE INATIVIDADE (SUCESSÃO) ---
def process_leadership_inactivity(guild, leader, db):
    now = datetime.now()
    if not leader.last_active: return None # Proteção se last_active for None
    days_inactive = (now - leader.last_active).days
    
    if guild.leadership_transfer_active and days_inactive < 60: # Líder voltou
        guild.leadership_transfer_active = False; guild.leadership_transfer_start = None; db.commit(); return None

    if not guild.leadership_transfer_active and days_inactive >= 60: # Iniciar processo
        guild.leadership_transfer_active = True; guild.leadership_transfer_start = now; db.commit()
        return "⚠️ **ALERTA DE SUCESSÃO:** Líder inativo há 60 dias! Troca em 30 dias."

    if guild.leadership_transfer_active:
        if not guild.leadership_transfer_start: # Proteção extra
             guild.leadership_transfer_start = now; db.commit()
             
        days_in_process = (now - guild.leadership_transfer_start).days
        if days_in_process >= 30: # TROCA AGORA
            successor = db.query(Player).filter(Player.guild_id == guild.id, Player.guild_role == 'coolider').order_by(Player.guild_join_date.asc()).first()
            if not successor: successor = db.query(Player).filter(Player.guild_id == guild.id, Player.guild_role == 'anciao').order_by(Player.guild_join_date.asc()).first()
            
            if successor:
                leader.guild_role = 'coolider'; successor.guild_role = 'lider'; guild.leader_id = successor.id
                guild.leadership_transfer_active = False; guild.leadership_transfer_start = None; db.commit()
                return f"👑 **NOVO LÍDER!**\nA liderança passou para **{successor.name}**!"
            else:
                return "⚠️ Processo de sucessão falhou: Nenhum sucessor elegível."
        else:
            return f"⚠️ **SUCESSÃO EM ANDAMENTO**: Faltam {30 - days_in_process} dias."
    return None

# --- MENUS ---
async def guild_menu_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    db = get_db(); player = get_player(update.effective_user.id, db)
    
    if not player.guild_id: await show_no_guild_menu(query); db.close(); return

    g = db.query(Guild).filter(Guild.id == player.guild_id).first()
    ldr = get_player(g.leader_id, db)
    
    # Inatividade Check
    alert_msg = process_leadership_inactivity(g, ldr, db)
    
    era_title, xp_next = get_guild_level_data(g.level)
    xp_bar = "🟩" * int((g.xp/xp_next)*10) + "⬜" * (10 - int((g.xp/xp_next)*10)) if xp_next > 0 else "🌟 MÁXIMO 🌟"
    xp_txt = f"{format_number(g.xp)} / {format_number(xp_next)}" if xp_next > 0 else "∞"
    
    kb = [[InlineKeyboardButton("💬 Grupo Telegram", url=g.telegram_link)],
          [InlineKeyboardButton("👥 Membros / Gestão", callback_data='guild_members_list')],
          [InlineKeyboardButton("💰 Doar Recursos", callback_data='donate_menu')]]

    if check_permission(player, 'mail'): kb.append([InlineKeyboardButton("✉️ Email do Clã (1h)", callback_data='guild_send_mail')])
    if check_permission(player, 'war'): kb.append([InlineKeyboardButton("⚔️ Guerra de Guildas", callback_data='guild_war_placeholder')])
    
    if player.guild_role != 'lider': kb.append([InlineKeyboardButton("🚪 Sair do Clã", callback_data='guild_leave')])
    kb.append([InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')])

    msg = (f"🛡️ **{g.name}**\n🏛️ **{era_title}** (Nvl {g.level})\n{xp_bar}\n✨ XP: {xp_txt}\n\n"
           f"📝 _{g.description}_\n👑 Líder: {ldr.name}\n👥 Membros: {g.member_count}/50\n"
           f"💰 Cofre: {g.treasury_gold}g | {g.treasury_gems}💎")
    if alert_msg: msg += f"\n\n{alert_msg}"

    try: await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    except: await query.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    db.close()

async def show_no_guild_menu(query):
    kb = [[InlineKeyboardButton("🔎 Listar Guildas", callback_data='guild_join_start')],
          [InlineKeyboardButton("✨ Criar Guilda", callback_data='guild_create_start')],
          [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
    await query.edit_message_text("🏰 **Sem Clã.**\nJunte-se a irmãos de armas!", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def guild_war_placeholder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    kb = [[InlineKeyboardButton("🔙 Voltar", callback_data='menu_guild')]]
    await query.edit_message_text(
        "⚔️ **Guerra de Guildas**\n\n"
        "🚧 **EM BREVE!**\n\n"
        "Prepare seu clã para batalhas épicas com **3 dias de duração**!\n"
        "Acumule ouro, recrute membros e suba de nível para estar pronto quando a guerra começar.",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'
    )

async def guild_members_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; db = get_db(); player = get_player(update.effective_user.id, db)
    
    if check_permission(player, 'accept'):
        req_count = db.query(GuildRequest).filter(GuildRequest.guild_id == player.guild_id).count()
        if req_count > 0: await query.message.reply_text("Gestão:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"🔔 Ver Pedidos ({req_count})", callback_data='guild_view_requests')]]))

    members = db.query(Player).filter(Player.guild_id == player.guild_id).order_by(Player.guild_role == 'lider', Player.guild_role == 'coolider').limit(20).all()
    kb = []
    for m in members:
        icon = {'lider': '👑', 'coolider': '🌟', 'anciao': '🛡️'}.get(m.guild_role, '👤')
        if m.id != player.id and can_manage(player.guild_role, m.guild_role):
            kb.append([InlineKeyboardButton(f"{icon} {m.name} [⚙️]", callback_data=f"g_manage_{m.id}")])
        else: kb.append([InlineKeyboardButton(f"{icon} {m.name}", callback_data="ignore")])
    
    kb.append([InlineKeyboardButton("🔙 Voltar", callback_data='menu_guild')])
    await query.edit_message_text(f"👥 **Membros**", reply_markup=InlineKeyboardMarkup(kb))
    db.close()

async def guild_manage_specific_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; tid = int(query.data.split('_')[2])
    db = get_db(); me = get_player(update.effective_user.id, db); target = get_player(tid, db)
    
    if not target or target.guild_id != me.guild_id: await query.answer("Erro."); db.close(); return

    kb = []
    if target.guild_role == 'membro' and check_permission(me, 'promote_elder'): kb.append([InlineKeyboardButton("⬆️ Promover a Ancião", callback_data=f"g_act_prom_elder_{tid}")])
    if target.guild_role in ['membro', 'anciao'] and check_permission(me, 'promote_co'): kb.append([InlineKeyboardButton("⬆️ Promover a Colíder", callback_data=f"g_act_prom_co_{tid}")])
    if target.guild_role in ['anciao', 'coolider'] and check_permission(me, 'demote') and can_manage(me.guild_role, target.guild_role): kb.append([InlineKeyboardButton("⬇️ Rebaixar", callback_data=f"g_act_demote_{tid}")])
    
    if check_permission(me, 'kick') and can_manage(me.guild_role, target.guild_role):
        cd_ok = True
        if me.guild_role == 'anciao' and (datetime.now() - me.last_kick_action) < timedelta(minutes=20): cd_ok = False
        if cd_ok: kb.append([InlineKeyboardButton("🥾 EXPULSAR", callback_data=f"g_act_kick_{tid}")])
        else: kb.append([InlineKeyboardButton("⏳ Kick em CD", callback_data="ignore")])

    if me.guild_role == 'lider' and target.guild_role == 'coolider': kb.append([InlineKeyboardButton("👑 TRANSFERIR LIDERANÇA", callback_data=f"g_act_transfer_{tid}")])
    
    kb.append([InlineKeyboardButton("🔙", callback_data='guild_members_list')])
    await query.edit_message_text(f"⚙️ Gerenciar: **{target.name}** ({target.guild_role})", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'); db.close()

async def guild_execute_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; parts = query.data.split('_'); act = parts[2] + "_" + parts[3] if parts[2] == "prom" else parts[2]; tid = int(parts[-1])
    db = get_db(); me = get_player(update.effective_user.id, db); target = get_player(tid, db)
    
    msg, success = "", False
    if not can_manage(me.guild_role, target.guild_role) and act != 'transfer': await query.answer("Permissão negada!"); db.close(); return

    if act == 'prom_elder': target.guild_role = 'anciao'; msg = "🛡️ Promovido a Ancião!"; success = True
    elif act == 'prom_co': target.guild_role = 'coolider'; msg = "🌟 Promovido a Colíder!"; success = True
    elif act == 'demote': target.guild_role = 'membro'; msg = "⬇️ Rebaixado."; success = True
    elif act == 'kick':
        if me.guild_role == 'anciao':
             if (datetime.now() - me.last_kick_action) < timedelta(minutes=20): await query.answer("Cooldown!"); db.close(); return
             me.last_kick_action = datetime.now()
        target.guild_id = None; target.guild_role = 'membro'; msg = "🥾 Expulso."; success = True
    elif act == 'transfer':
        if me.guild_role == 'lider':
            target.guild_role = 'lider'; me.guild_role = 'coolider'; g = db.query(Guild).filter(Guild.id == me.guild_id).first(); g.leader_id = target.id
            msg = "👑 Liderança Transferida!"; success = True

    if success: db.commit(); await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='guild_members_list')]]))
    db.close()

async def process_guild_donation(update, player, amount, type_res, db):
    g = db.query(Guild).filter(Guild.id == player.guild_id).first()
    xp = amount if type_res == 'gold' else amount * 200
    if type_res == 'gold': player.gold -= amount; g.treasury_gold += amount
    else: player.gems -= amount; g.treasury_gems += amount
    
    g.xp += xp
    lvl_msg = ""
    if check_guild_level_up(g): lvl_msg = f"\n🎉 **LEVEL UP!** Clã Nível {g.level}!"
    db.commit()
    await update.message.reply_text(f"✅ Doou {amount} {type_res} (+{xp} XP).{lvl_msg}", parse_mode='Markdown')

async def guild_send_mail_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; db = get_db(); p = get_player(update.effective_user.id, db)
    if (datetime.now() - p.last_guild_mail) < timedelta(hours=1): await query.answer("⏳ Aguarde 1 hora.", show_alert=True); db.close(); return
    context.user_data['waiting_guild_mail'] = True
    await query.edit_message_text("✉️ Digite a mensagem para o Clã:", parse_mode='Markdown'); db.close()
