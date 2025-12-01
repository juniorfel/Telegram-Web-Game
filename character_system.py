from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import Player
from utils import get_db, get_player, format_number, apply_passive_healing, check_level_up, calculate_daily_values
from config import BASE_STATS, VALID_CLASSES, INITIAL_GOLD, RESPEC_COST, BOT_USERNAME
import random
from datetime import datetime, timedelta

# Mapas de Atributos
STAT_MAP = {'str': 'strength', 'int': 'intelligence', 'def': 'defense', 'spd': 'speed', 'crit': 'crit_chance'}
EMOJI_MAP = {'str':'💪', 'int':'🧠', 'def':'🛡️', 'spd':'⚡', 'crit':'💥'}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # (Mantido igual - Start e Criação)
    user = update.effective_user; db = get_db()
    player = get_player(user.id, db)
    if player and player.is_banned: await update.message.reply_text("🚫 Banido."); return
    if context.args and not player:
        try: context.user_data['referrer_id'] = int(context.args[0])
        except: pass
    if not player:
        summary = "".join([f"\n**{n}**: {d['desc']}" for n, d in BASE_STATS.items()])
        kb = [[InlineKeyboardButton(f"{c}", callback_data=f'class_{c}')] for c in VALID_CLASSES + ['Aleatorio']]
        await update.message.reply_text(f"✨ **Bem-vindo!**\nEscolha:\n{summary}", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    else:
        apply_passive_healing(player, db); db.commit()
        from gameplay import show_main_menu
        await show_main_menu(update, player)
    db.close()

async def handle_class_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    c = query.data.split('_')[1]
    if c == 'Aleatorio': c = random.choice(VALID_CLASSES)
    context.user_data['temp_class'] = c; context.user_data['waiting_name'] = True
    await query.edit_message_text(f"Classe **{c}**! Qual seu nome? (Min 5 letras)", parse_mode='Markdown')

async def confirm_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    if query.data == 'confirm_name_no': context.user_data['waiting_name'] = True; await query.edit_message_text("Nome:"); return
    
    name = context.user_data.get('temp_name'); c_class = context.user_data.get('temp_class')
    user_id = update.effective_user.id; db = get_db()
    if get_player(user_id, db): db.close(); return

    s = BASE_STATS[c_class]
    p = Player(id=user_id, username=update.effective_user.username, name=name, class_name=c_class,
               health=s['hp'], max_health=s['hp'], strength=s['str'], intelligence=s['int'], defense=s['def'],
               speed=s['spd'], crit_chance=s['crit'], gold=INITIAL_GOLD, level=1, xp=0)
    db.add(p); db.commit(); db.close()
    await query.answer("Bem-vindo!", show_alert=True)
    from gameplay import show_main_menu
    await show_main_menu(update, p)

# --- MENU DE UPGRADE (SELEÇÃO) ---
async def menu_upgrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; db = get_db(); player = get_player(query.from_user.id, db)
    
    msg = (f"💪 **Centro de Treinamento**\n"
           f"📊 Seus Atributos:\n"
           f"💪 {player.strength} | 🧠 {player.intelligence}\n"
           f"🛡️ {player.defense} | ⚡ {player.speed} | 💥 {player.crit_chance}%\n\n"
           f"💰 Saldo: {format_number(player.gold)}g\n"
           f"Escolha o atributo para treinar:")
           
    kb = [[InlineKeyboardButton("💪 Força", callback_data='train_str'), InlineKeyboardButton("🧠 Inteligência", callback_data='train_int')],
          [InlineKeyboardButton("🛡️ Defesa", callback_data='train_def'), InlineKeyboardButton("⚡ Velocidade", callback_data='train_spd')],
          [InlineKeyboardButton("💥 Crítico", callback_data='train_crit')],
          [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
          
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    db.close()

# --- MENU DE DETALHES DE ATRIBUTO (1x / 10x) ---
async def handle_train_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Pega a chave (str, int, etc) do índice 1. 
    # Funciona para 'train_str' e 'up_str_1'
    stat_key = query.data.split('_')[1]
    
    db = get_db(); player = get_player(query.from_user.id, db)
    attr_name = STAT_MAP.get(stat_key)
    current_val = getattr(player, attr_name)
    
    # Custo 1x
    cost_1 = int(50 + (current_val * 20))
    
    # Custo 10x
    cost_10 = 0
    temp_val = current_val
    for _ in range(10):
        cost_10 += int(50 + (temp_val * 20))
        temp_val += 1
    
    emoji = EMOJI_MAP.get(stat_key, '')
    
    msg = (f"{emoji} **Treinando {stat_key.capitalize()}**\n\n"
           f"Nível Atual: {current_val}\n"
           f"💰 Saldo: {format_number(player.gold)}g\n\n"
           f"Selecione a intensidade:")
           
    kb = [[InlineKeyboardButton(f"+1 ({format_number(cost_1)}g)", callback_data=f'up_{stat_key}_1'), 
           InlineKeyboardButton(f"+10 ({format_number(cost_10)}g)", callback_data=f'up_{stat_key}_10')],
          [InlineKeyboardButton("🔙 Voltar", callback_data='menu_upgrade')]]
          
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    db.close()

# --- AÇÃO DE UPGRADE DE ATRIBUTO ---
async def handle_stat_upgrade_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Formato: up_str_10
    parts = query.data.split('_')
    key = parts[1]
    qty = int(parts[2])
    
    db = get_db(); player = get_player(query.from_user.id, db)
    attr_name = STAT_MAP.get(key)
    curr = getattr(player, attr_name)
    
    total = 0; temp = curr
    for _ in range(qty):
        total += int(50 + (temp * 20))
        temp += 1
    
    if player.gold >= total:
        player.gold -= total
        setattr(player, attr_name, curr + qty)
        db.commit()
        await query.answer(f"+{qty} {key.upper()}", show_alert=True)
        # Recarrega a view chamando diretamente a função
        await handle_train_view(update, context)
    else:
        await query.answer() # Fecha loading
        await query.message.reply_text(
            f"🚫 **FALTA OURO!**\n\n"
            f"Custo: {format_number(total)}g\n"
            f"Você tem: {format_number(player.gold)}g", 
            parse_mode='Markdown'
        )
    db.close()

# ... (Resto do arquivo: menu_daily, daily_claim_now, menu_info - Mantidos iguais) ...
async def menu_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; db = get_db(); player = get_player(query.from_user.id, db)
    now = datetime.now(); collected_today = (now - player.last_daily_claim) < timedelta(hours=24)
    from database import Guild
    g = db.query(Guild).filter(Guild.id == player.guild_id).first() if player.guild_id else None
    gold, xp, gems, streak, is_double = calculate_daily_values(player, g)
    days_to_bonus = 7 - (streak % 7); bonus_text = "🔥 **HOJE É O DIA DO BÔNUS (2x)!** 🔥" if is_double else f"💎 Bônus 2x em: {days_to_bonus} dias"
    
    if collected_today:
        rem = 24 - int((now - player.last_daily_claim).total_seconds() / 3600)
        status = f"✅ **JÁ COLETADO!**\nVolte em {rem} horas."
        kb = [[InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
    else:
        status = f"🎁 **DISPONÍVEL!**"; kb = [[InlineKeyboardButton("💰 RECEBER AGORA", callback_data='daily_claim_now')], [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]

    msg = (f"{status}\n\n📅 **Streak:** {player.daily_streak} dias\n{bonus_text}\n\n💰 {gold} Ouro\n✨ {xp} XP\n💎 {gems} Gemas")
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'); db.close()

async def daily_claim_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; db = get_db(); player = get_player(query.from_user.id, db)
    if (datetime.now() - player.last_daily_claim) < timedelta(hours=24): await query.answer("Já coletou!", show_alert=True); db.close(); return
    from database import Guild
    g = db.query(Guild).filter(Guild.id == player.guild_id).first() if player.guild_id else None
    gold, xp, gems, new_streak, is_double = calculate_daily_values(player, g)
    player.gold += gold; player.xp += xp; player.gems += gems; player.last_daily_claim = datetime.now(); player.daily_streak = new_streak; player.stamina = player.max_stamina
    check_level_up(player); db.commit()
    msg_double = " 🔥 **BÔNUS DUPLO!**" if is_double else ""
    await query.edit_message_text(f"✅ **Recebido!**{msg_double}\nVolte amanhã!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]), parse_mode='Markdown'); db.close()

async def menu_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; db = get_db(); player = get_player(query.from_user.id, db)
    lnk = f"https://t.me/{BOT_USERNAME}?start={player.id}"
    msg = (f"📜 **Ficha de Personagem**\n\n🆔 **ID:** `{player.id}`\n👥 **Indicados:** {player.referral_count}\n\n👤 **{player.name}**\n🎭 Classe: {player.class_name}\n🏅 Nível: {player.level}\n\n⚔️ **Atributos:**\n💪 {player.strength} | 🧠 {player.intelligence}\n🛡️ {player.defense} | ⚡ {player.speed}\n\n🔗 **Link de Convite:**\n`{lnk}`")
    kb = [[InlineKeyboardButton("🔄 Reencarnar (Mudar Classe)", callback_data='respec_start')], [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'); db.close()
