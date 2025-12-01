from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import Player
from utils import get_db, get_player, format_number, apply_passive_healing, check_level_up, calculate_daily_bonus
from config import BASE_STATS, VALID_CLASSES, INITIAL_GOLD, RESPEC_COST, BOT_USERNAME
import random
from datetime import datetime, timedelta

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        # PRECISA IMPORTAR show_main_menu DE GAMEPLAY (Evitar ciclo com import dentro da função)
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

async def menu_upgrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; db = get_db(); player = get_player(query.from_user.id, db)
    msg = (f"💪 **Centro de Treinamento**\n📊 Seus Atributos:\n"
           f"💪 {player.strength} | 🧠 {player.intelligence}\n🛡️ {player.defense} | ⚡ {player.speed} | 💥 {player.crit_chance}%\n"
           f"💰 Saldo: {format_number(player.gold)}g\nEscolha:")
    kb = [[InlineKeyboardButton("💪 Força", callback_data='train_str'), InlineKeyboardButton("🧠 Inteligência", callback_data='train_int')],
          [InlineKeyboardButton("🛡️ Defesa", callback_data='train_def'), InlineKeyboardButton("⚡ Velocidade", callback_data='train_spd')],
          [InlineKeyboardButton("💥 Crítico", callback_data='train_crit')],
          [InlineKeyboardButton("🔄 Reencarnar", callback_data='respec_start'), InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'); db.close()

async def handle_train_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; stat_key = query.data.split('_')[1]
    db = get_db(); player = get_player(query.from_user.id, db)
    
    smap = {'str': 'strength', 'int': 'intelligence', 'def': 'defense', 'spd': 'speed', 'crit': 'crit_chance'}
    curr = getattr(player, smap[stat_key])
    
    cost_1 = int(50 + (curr * 20))
    cost_10 = 0; temp = curr
    for _ in range(10): cost_10 += int(50 + (temp * 20)); temp += 1
    
    msg = f"Treinar **{stat_key.upper()}**\nAtual: {curr}\n💰 {player.gold}g"
    kb = [[InlineKeyboardButton(f"+1 ({cost_1}g)", callback_data=f'up_{stat_key}_1'), InlineKeyboardButton(f"+10 ({cost_10}g)", callback_data=f'up_{stat_key}_10')],
          [InlineKeyboardButton("🔙", callback_data='menu_upgrade')]]
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown'); db.close()

async def handle_stat_upgrade_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; parts = query.data.split('_'); key = parts[1]; qty = int(parts[2])
    db = get_db(); player = get_player(query.from_user.id, db)
    
    smap = {'str': 'strength', 'int': 'intelligence', 'def': 'defense', 'spd': 'speed', 'crit': 'crit_chance'}
    curr = getattr(player, smap[key])
    
    total = 0; temp = curr
    for _ in range(qty): total += int(50 + (temp * 20)); temp += 1
    
    if player.gold >= total:
        player.gold -= total; setattr(player, smap[key], curr + qty); db.commit()
        await query.answer(f"+{qty} {key.upper()}", show_alert=True)
        query.data = f"train_{key}"; await handle_train_view(update, context)
    else:
        await query.answer()
        await query.message.reply_text(f"🚫 **FALTA OURO!**\nCusto: {total}g\nTem: {player.gold}g", parse_mode='Markdown')
    db.close()

async def menu_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; db = get_db(); player = get_player(query.from_user.id, db)
    if (datetime.now() - player.last_daily_claim) > timedelta(hours=24):
        from database import Guild # Local import
        g = db.query(Guild).filter(Guild.id == player.guild_id).first() if player.guild_id else None
        gold, xp, gems, b_msg = calculate_daily_bonus(player, g)
        await query.edit_message_text(f"🎁 **Diário**\n💰 {gold}\n✨ {xp} {f'| 💎 {gems}' if gems else ''}{b_msg}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Receber", callback_data='daily_claim_now')]]), parse_mode='Markdown')
    else: await query.edit_message_text("⏳ Volte amanhã.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))
    db.close()

async def daily_claim_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; db = get_db(); player = get_player(query.from_user.id, db)
    from database import Guild
    g = db.query(Guild).filter(Guild.id == player.guild_id).first() if player.guild_id else None
    gold, xp, gems, _ = calculate_daily_bonus(player, g)
    player.gold += gold; player.xp += xp; player.gems += gems; player.last_daily_claim = datetime.now(); player.stamina = player.max_stamina
    check_level_up(player); db.commit()
    await query.edit_message_text("✅ Resgatado!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]))
    db.close()

async def menu_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; db = get_db(); player = get_player(query.from_user.id, db)
    lnk = f"https://t.me/{BOT_USERNAME}?start={player.id}"
    await query.edit_message_text(f"📜 **Perfil**\n**{player.name}**\n💪 {player.strength} | 🧠 {player.intelligence}\n🛡️ {player.defense} | ⚡ {player.speed}\n\n🔗 **Recrutamento:**\n`{lnk}`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]), parse_mode='Markdown'); db.close()
