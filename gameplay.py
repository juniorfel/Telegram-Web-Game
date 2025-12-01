from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import Player, Guild
from utils import get_db, get_player, format_number
from config import GUILD_CREATE_COST

# IMPORTS
from battle_system import menu_battle_mode, battle_pve_start, confirm_pve, battle_pvp_start, pre_fight, confirm_pvp
from city_system import menu_constructions, handle_construction_view, handle_upgrade_action, farm_harvest
from character_system import menu_upgrade, handle_train_view, handle_stat_upgrade_action, menu_daily, daily_claim_now, menu_info, handle_class_selection, confirm_name_handler, start
from social_system import menu_ranking, menu_ranking_guilds, menu_mailbox, menu_shop
from guild_system import guild_menu_main, guild_members_list, guild_manage_specific_member, guild_execute_action, guild_send_mail_start, process_guild_donation, guild_war_placeholder

# ... (get_main_keyboard, show_main_menu, receive_text_input, confirm_name_handler mantidos iguais ao anterior) ...
# COPIE O INÍCIO DO ARQUIVO ANTERIOR ATÉ O "async def handle_menu"

# ...

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
        # Reencarnar: Simplesmente abre a msg de confirmação (mesma lógica do up)
        query.data = 'respec_start_confirm' # Criar handler se quiser tela separada ou usar a do character_system
        # No character_system já tem o botão 'respec_start', então aqui só chama a view do upgrade que tem o botao ou info
        pass 

    # SOCIAL
    elif data == 'menu_ranking': await menu_ranking(update, context)
    elif data == 'ranking_guilds': await menu_ranking_guilds(update, context) # <--- NOVO
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
            # Copiar logica de validacao de gemas
            pass
        elif data.startswith('donate_menu'):
             kb = [[InlineKeyboardButton("Ouro", callback_data='donate_start_gold'), InlineKeyboardButton("Gemas", callback_data='donate_start_gems')], [InlineKeyboardButton("🔙", callback_data='menu_guild')]]
             await query.edit_message_text("Doar:", reply_markup=InlineKeyboardMarkup(kb))
        elif data.startswith('donate_start_'):
             context.user_data['waiting_donation_type'] = data.split('_')[-1]
             await query.edit_message_text("Digite valor:")

    # REENCARNAÇÃO (Lógica simples mantida aqui ou movida se preferir)
    elif data == 'respec_start':
        kb = []; row = []
        for c in VALID_CLASSES:
            row.append(InlineKeyboardButton(c, callback_data=f'respec_{c}'))
            if len(row)==3: kb.append(row); row=[]
        if row: kb.append(row)
        kb.append([InlineKeyboardButton("🔙", callback_data='menu_info')]) # Voltar para Info
        await query.edit_message_text(f"🔄 **Reencarnação**\nCusto: {RESPEC_COST} Gemas.\nEscolha seu novo destino:", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

    elif data.startswith('respec_'):
        db = get_db(); p = get_player(query.from_user.id, db)
        if p.gems >= RESPEC_COST:
            nc = data.split('_')[1]; s = BASE_STATS[nc]
            p.gems -= RESPEC_COST; p.class_name = nc; p.strength = s['str']; p.defense = s['def']; p.intelligence = s['int']; p.health = p.max_health; db.commit()
            await query.answer("Sucesso!", show_alert=True)
            await query.edit_message_text(f"✨ Agora você é um {nc}.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))
        else: await query.answer("Gemas insuficientes!", show_alert=True)
        db.close()

# COMANDOS
async def get_my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 `{update.effective_user.id}`", parse_mode='Markdown')

async def join_guild_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Logica de join command
    pass
