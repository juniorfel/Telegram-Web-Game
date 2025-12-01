# gameplay.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import Player, Guild
from utils import get_db, get_player, format_number
from config import GUILD_CREATE_COST
from datetime import datetime
from sqlalchemy import or_

# --- IMPORTS DOS MÓDULOS (SISTEMAS) ---
# Isso permite que o gameplay.py seja o "Router" central
from battle_system import menu_battle_mode, battle_pve_start, confirm_pve, battle_pvp_start, pre_fight, confirm_pvp
from city_system import menu_constructions, handle_construction_view, handle_upgrade_action, farm_harvest
from character_system import (
    start, handle_class_selection, confirm_name_handler, # Funções de Start
    menu_upgrade, handle_train_view, handle_stat_upgrade_action, # Funções de Upgrade
    menu_daily, daily_claim_now, menu_info # Funções de Info/Diário
)
from social_system import menu_ranking, menu_ranking_guilds, menu_mailbox, menu_shop
from guild_system import (
    guild_menu_main, guild_members_list, guild_manage_specific_member, 
    guild_execute_action, guild_send_mail_start, process_guild_donation, 
    guild_war_placeholder
)

# --- FUNÇÕES AUXILIARES DE MENU ---

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

async def show_main_menu(update: Update, player: Player):
    """Exibe o menu principal com status atualizados"""
    db = get_db()
    try:
        # Recarrega o player do DB para garantir dados frescos
        p = db.query(Player).filter(Player.id == player.id).first()
        if not p: return 
        
        rank_pos = db.query(Player).filter(Player.pvp_rating > p.pvp_rating).count() + 1
        keyboard = get_main_keyboard()
        
        lvl = p.level or 1
        xp = p.xp or 0
        needed = lvl * 100
        perc = (xp / needed) * 100 if needed > 0 else 0
        
        text = (f"**{p.name}** (Lvl {lvl} {p.class_name})\n"
                f"🏆 **Rank Global:** #{rank_pos} ({p.pvp_rating} Pts)\n"
                f"Exp: {format_number(xp)}/{format_number(needed)} ({perc:.1f}%)\n"
                f"❤️ HP Base: {p.max_health}\n"
                f"⚡ Stamina: {p.stamina}/{p.max_stamina}\n"
                f"💰 {format_number(p.gold)} | 💎 {p.gems}")
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    finally:
        db.close()

# --- PROCESSAMENTO DE TEXTO (INPUTS) ---

async def receive_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ud = context.user_data
    user_id = update.effective_user.id
    db = get_db()
    p = get_player(user_id, db)
    
    # 1. Email da Guilda
    if ud.get('waiting_guild_mail'):
        text = update.message.text[:200]
        # Em um bot real, aqui você faria um loop para enviar msg a todos os membros
        p.last_guild_mail = datetime.now()
        db.commit()
        await update.message.reply_text(f"✉️ **Mensagem Enviada aos Membros!**\n\n`{text}`", parse_mode='Markdown')
        ud['waiting_guild_mail'] = False
        db.close(); return

    # 2. Busca de Guilda
    if ud.get('waiting_guild_search'):
        term = update.message.text.strip()
        res = db.query(Guild).filter(or_(Guild.id == term, Guild.name.ilike(f"%{term}%"))).limit(5).all()
        kb = []
        if res:
            for g in res:
                if g.member_count < 50:
                    kb.append([InlineKeyboardButton(f"{g.name} ({g.member_count}/50)", callback_data=f"join_guild_{g.id}")])
            kb.append([InlineKeyboardButton("🔙 Voltar", callback_data='guild_join_start')])
            await update.message.reply_text(f"🔎 Resultados para '{term}':", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.message.reply_text("❌ Nenhuma guilda encontrada.")
        ud['waiting_guild_search'] = False
        db.close(); return

    # 3. Criação de Nome de Personagem (Fallback se não usar botão)
    if ud.get('waiting_name'):
        raw = update.message.text.strip()
        clean = "".join(ch for ch in raw if ch.isalnum())[:15]
        if len(clean) < 5:
            await update.message.reply_text("⚠️ Nome inválido! Use **mínimo 5 letras/números**.")
            return
        ud['temp_name'] = clean
        ud['waiting_name'] = False
        kb = [[InlineKeyboardButton("✅ Confirmar", callback_data='confirm_name_yes'), InlineKeyboardButton("✏️ Alterar", callback_data='confirm_name_no')]]
        await update.message.reply_text(f"Seu nome será: **{clean}**\nConfirma?", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        db.close(); return

    # 4. Criação de Guilda - Passo 1: Nome
    if ud.get('waiting_guild_name'):
        ud['temp_guild_name'] = update.message.text.strip()[:20]
        ud['waiting_guild_name'] = False
        ud['waiting_guild_link'] = True
        await update.message.reply_text(f"Nome da Guilda: **{ud['temp_guild_name']}**\n\n🔗 Agora envie o **Link do Grupo Telegram**:", parse_mode='Markdown')
        db.close(); return

    # 5. Criação de Guilda - Passo 2: Link e Finalização
    if ud.get('waiting_guild_link'):
        link = update.message.text.strip()
        if not link.startswith("https://t.me/"):
            await update.message.reply_text("🚫 O link deve começar com https://t.me/...")
            return
        
        # Verificação final de saldo
        if p.gems < GUILD_CREATE_COST:
            await update.message.reply_text(f"🚫 **Saldo Insuficiente!**\nVocê precisa de {GUILD_CREATE_COST} Gemas.", parse_mode='Markdown')
            ud['waiting_guild_link'] = False
            db.close(); return

        try:
            # Cria a Guilda
            ng = Guild(name=ud['temp_guild_name'], leader_id=p.id, telegram_link=link, member_count=1)
            db.add(ng)
            db.commit()
            db.refresh(ng) # Pega o ID gerado
            
            # Atualiza o Jogador (Gasta gemas e define como lider)
            p.gems -= GUILD_CREATE_COST
            p.guild_id = ng.id
            p.guild_role = 'lider'
            p.guild_join_date = datetime.now()
            db.commit()
            
            ud['waiting_guild_link'] = False
            await update.message.reply_text(
                f"✅ **Guilda Fundada com Sucesso!**\n\n"
                f"🛡️ **{ng.name}**\n"
                f"🆔 ID da Guilda: `{ng.id}`\n"
                f"💎 Custo: -{GUILD_CREATE_COST} Gemas\n\n"
                f"Convide membros mandando eles digitarem:\n`/guild {ng.id}`", 
                parse_mode='Markdown'
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Erro ao criar (Nome já existe?): {e}")
        
        db.close(); return

    # 6. Doação
    dtype = ud.get('waiting_donation_type')
    if dtype:
        if p and p.guild_id:
            try:
                amt = int(update.message.text.strip())
                if amt <= 0: raise ValueError
                
                has_funds = (p.gold >= amt) if dtype == 'gold' else (p.gems >= amt)
                if has_funds:
                    await process_guild_donation(update, p, amt, dtype, db)
                else:
                    await update.message.reply_text("🚫 **Recursos insuficientes!**")
            except ValueError:
                await update.message.reply_text("Valor inválido.")
        ud['waiting_donation_type'] = None
    
    db.close()

# --- ROTEADOR PRINCIPAL (CALLBACK HANDLER) ---

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    # 1. Refresh Geral
    if data == 'menu_refresh': 
        db = get_db()
        p = get_player(query.from_user.id, db)
        await show_main_menu(update, p)
        db.close()
        return
    
    # 2. SISTEMA DE BATALHA
    if data == 'menu_battle_mode' or data.startswith('battle_') or data.startswith('confirm_p') or data.startswith('pre_fight'):
        if data == 'menu_battle_mode': await menu_battle_mode(update, context)
        elif data == 'battle_pve_start': await battle_pve_start(update, context)
        elif data == 'confirm_pve': await confirm_pve(update, context)
        elif data == 'battle_pvp_start': await battle_pvp_start(update, context)
        elif data.startswith('pre_fight'): await pre_fight(update, context)
        elif data == 'confirm_pvp': await confirm_pvp(update, context)

    # 3. SISTEMA DE CIDADE/CONSTRUÇÃO
    elif data == 'menu_constructions' or data.startswith('constr_') or data.startswith('upgrade_') or data == 'farm_harvest':
        if data == 'menu_constructions': await menu_constructions(update, context)
        elif data.startswith('constr_'): await handle_construction_view(update, context)
        elif data.startswith('upgrade_'): await handle_upgrade_action(update, context)
        elif data == 'farm_harvest': await farm_harvest(update, context)

    # 4. SISTEMA DE PERSONAGEM
    elif data == 'menu_upgrade' or data.startswith('train_') or data.startswith('up_') or data.startswith('menu_d') or data.startswith('daily_') or data == 'menu_info' or data.startswith('respec_'):
        if data == 'menu_upgrade': await menu_upgrade(update, context)
        elif data.startswith('train_'): await handle_train_view(update, context)
        elif data.startswith('up_'): await handle_stat_upgrade_action(update, context)
        elif data == 'menu_daily': await menu_daily(update, context)
        elif data == 'daily_claim_now': await daily_claim_now(update, context)
        elif data == 'menu_info': await menu_info(update, context)
        
        # Reencarnação (Lógica simples mantida aqui para acesso rápido)
        elif data == 'respec_start':
            from config import VALID_CLASSES, RESPEC_COST
            kb = [[InlineKeyboardButton(c, callback_data=f'respec_{c}')] for c in VALID_CLASSES]
            kb.append([InlineKeyboardButton("🔙", callback_data='menu_info')])
            await query.edit_message_text(f"🔄 **Reencarnação**\nCusto: {RESPEC_COST} Gemas.\nEscolha seu novo destino:", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

        elif data.startswith('respec_'):
            from config import RESPEC_COST, BASE_STATS
            db = get_db(); p = get_player(query.from_user.id, db)
            if p.gems >= RESPEC_COST:
                nc = data.split('_')[1]; s = BASE_STATS[nc]
                p.gems -= RESPEC_COST; p.class_name = nc; p.strength = s['str']; p.defense = s['def']; p.intelligence = s['int']; p.health = p.max_health
                db.commit()
                await query.answer("Sucesso!", show_alert=True)
                await query.edit_message_text(f"✨ Agora você é um {nc}.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))
            else:
                await query.answer("Gemas insuficientes!", show_alert=True)
            db.close()

    # 5. SISTEMA SOCIAL
    elif data == 'menu_ranking': await menu_ranking(update, context)
    elif data == 'ranking_guilds': await menu_ranking_guilds(update, context)
    elif data == 'menu_mailbox': await menu_mailbox(update, context)
    elif data == 'menu_shop': await menu_shop(update, context)

    # 6. SISTEMA DE GUILDA
    elif data.startswith('guild_') or data == 'menu_guild' or data.startswith('g_') or data.startswith('donate_'):
        if data == 'menu_guild': await guild_menu_main(update, context)
        elif data == 'guild_members_list': await guild_members_list(update, context)
        elif data.startswith('g_manage_'): await guild_manage_specific_member(update, context)
        elif data.startswith('g_act_'): await guild_execute_action(update, context)
        elif data == 'guild_send_mail': await guild_send_mail_start(update, context)
        elif data == 'guild_war_placeholder': await guild_war_placeholder(update, context)
        
        elif data == 'guild_create_start':
            # Validação inicial rápida antes de pedir o nome
            db = get_db(); p = get_player(query.from_user.id, db)
            if p.gems < GUILD_CREATE_COST:
                await query.answer(f"🚫 Saldo Insuficiente!\nRequer {GUILD_CREATE_COST} Gemas.", show_alert=True)
            else:
                context.user_data['waiting_guild_name'] = True
                await query.edit_message_text(f"✨ **Criar Nova Guilda**\n\n💰 Custo: **{GUILD_CREATE_COST} Gemas**\n\n🛡️ Digite o **Nome da Guilda** no chat:", parse_mode='Markdown')
            db.close()
            
        elif data == 'guild_join_start':
            db = get_db()
            top = db.query(Guild).order_by(Guild.total_rating.desc()).limit(10).all()
            kb = [[InlineKeyboardButton(f"Entrar: {g.name}", callback_data=f"join_guild_{g.id}")] for g in top if g.member_count < 50]
            kb.append([InlineKeyboardButton("🔙", callback_data='menu_guild')])
            await query.edit_message_text("📜 **Guildas Recrutando (Top 10)**", reply_markup=InlineKeyboardMarkup(kb))
            db.close()
            
        elif data.startswith('join_guild_'):
            db = get_db()
            gid = int(data.split('_')[2])
            g = db.query(Guild).filter(Guild.id == gid).first()
            p = get_player(query.from_user.id, db)
            
            if g and g.member_count < 50:
                p.guild_id = g.id
                p.guild_role = 'membro'
                p.guild_join_date = datetime.now()
                g.member_count += 1
                db.commit()
                await query.edit_message_text(f"✅ Bem-vindo a **{g.name}**!", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Menu da Guilda", callback_data='menu_guild')]]))
            else:
                await query.answer("Guilda cheia ou inexistente.", show_alert=True)
            db.close()
            
        elif data == 'guild_leave':
            db = get_db(); p = get_player(query.from_user.id, db)
            if p.guild_role == 'lider':
                await query.answer("Líder não pode sair! Transfira a liderança primeiro.", show_alert=True)
            else:
                g = db.query(Guild).filter(Guild.id == p.guild_id).first()
                if g: g.member_count -= 1
                p.guild_id = None
                p.guild_role = 'membro'
                db.commit()
                await query.edit_message_text("Você deixou a guilda.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))
            db.close()
            
        elif data.startswith('donate_menu'):
             kb = [[InlineKeyboardButton("💰 Ouro", callback_data='donate_start_gold'), InlineKeyboardButton("💎 Gemas", callback_data='donate_start_gems')], [InlineKeyboardButton("🔙", callback_data='menu_guild')]]
             await query.edit_message_text("🏦 **Cofre da Guilda**\nSelecione o recurso para doar:", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
             
        elif data.startswith('donate_start_'):
             context.user_data['waiting_donation_type'] = data.split('_')[-1]
             await query.edit_message_text("Digite o valor para doar no chat:")

# --- COMANDOS AUXILIARES (Para o bot.py importar) ---

async def get_my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 **Seu ID:** `{update.effective_user.id}`", parse_mode='Markdown')

async def join_guild_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /guild [ID]"""
    db = get_db()
    try:
        p = get_player(update.effective_user.id, db)
        if not p: return
        if p.guild_id: 
            await update.message.reply_text("🚫 Você já tem guilda."); db.close(); return
            
        if not context.args:
            await update.message.reply_text("Uso: `/guild ID`", parse_mode='Markdown'); db.close(); return
            
        gid = int(context.args[0])
        g = db.query(Guild).filter(Guild.id == gid).first()
        
        if g and g.member_count < 50:
            p.guild_id = g.id
            p.guild_role = 'membro'
            p.guild_join_date = datetime.now()
            g.member_count += 1
            db.commit()
            await update.message.reply_text(f"✅ Entrou em **{g.name}**!", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Guilda cheia ou não encontrada.")
    except ValueError:
        await update.message.reply_text("O ID deve ser um número.")
    finally:
        db.close()
