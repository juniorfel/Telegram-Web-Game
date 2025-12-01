from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import Player
from utils import get_db, get_player, format_number
from datetime import datetime

async def menu_constructions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; db = get_db(); player = get_player(query.from_user.id, db)
    msg = (f"🏗️ **Distrito de Construções**\n\n"
           f"🌾 Fazenda: Lvl {player.farm_level} ({player.farm_level*10}/h)\n"
           f"🏚️ Celeiro: Lvl {player.barn_level} (Cap: {player.barn_level*100})\n"
           f"⚔️ Quartel: Lvl {player.barracks_level}\n"
           f"🔮 Academia: Lvl {player.academy_level}\n"
           f"🏃 Pista: Lvl {player.track_level}\n"
           f"❤️ Clínica: Lvl {player.clinic_level}")
    kb = [[InlineKeyboardButton("Fazenda 🌾", callback_data='constr_fazenda'), InlineKeyboardButton("Quartel ⚔️", callback_data='constr_quartel')],
          [InlineKeyboardButton("Academia 🔮", callback_data='constr_academia'), InlineKeyboardButton("Pista 🏃‍♂️", callback_data='constr_pista')],
          [InlineKeyboardButton("Clínica ❤️", callback_data='constr_clinica'), InlineKeyboardButton("Celeiro 🏚️", callback_data='constr_celeiro')],
          [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    db.close()

async def handle_construction_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; key = query.data.split('_')[1]
    db = get_db(); player = get_player(query.from_user.id, db)
    
    B = {'fazenda': {'a':'farm_level', 'c':500, 'd':'Produção'}, 'celeiro': {'a':'barn_level', 'c':500, 'd':'Estoque'},
         'quartel': {'a':'barracks_level', 'c':2000, 'd':'Força/Defesa'}, 'academia': {'a':'academy_level', 'c':1500, 'd':'Int/XP'},
         'pista': {'a':'track_level', 'c':2500, 'd':'Spd/Crit'}, 'clinica': {'a':'clinic_level', 'c':3000, 'd':'Regen HP'}}
    conf = B.get(key)
    if not conf: db.close(); return

    lvl = getattr(player, conf['a'])
    cost_1 = int(conf['c'] * (1.5 ** lvl))
    cost_10 = 0
    temp_lvl = lvl
    for _ in range(10): cost_10 += int(conf['c'] * (1.5 ** temp_lvl)); temp_lvl += 1
        
    msg = (f"🏗️ **{key.capitalize()}** (Nível {lvl})\n_{conf['d']}_\n\n💰 Saldo: {format_number(player.gold)}g\n\nMelhorar:")
    kb = [[InlineKeyboardButton(f"⬆️ +1 ({format_number(cost_1)}g)", callback_data=f'upgrade_{key}_1'),
           InlineKeyboardButton(f"⬆️ +10 ({format_number(cost_10)}g)", callback_data=f'upgrade_{key}_10')]]
    if key == 'fazenda' and lvl > 0: kb.append([InlineKeyboardButton("💰 Vender Colheita", callback_data='farm_harvest')])
    kb.append([InlineKeyboardButton("🔙 Voltar", callback_data='menu_constructions')])
    
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    db.close()

async def handle_upgrade_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; parts = query.data.split('_'); key = parts[1]; qty = int(parts[2])
    db = get_db(); player = get_player(query.from_user.id, db)
    
    B = {'fazenda': {'a':'farm_level', 'c':500}, 'celeiro': {'a':'barn_level', 'c':500},
         'quartel': {'a':'barracks_level', 'c':2000}, 'academia': {'a':'academy_level', 'c':1500},
         'pista': {'a':'track_level', 'c':2500}, 'clinica': {'a':'clinic_level', 'c':3000}}
    conf = B.get(key)
    current_lvl = getattr(player, conf['a'])
    
    total_cost = 0
    temp_lvl = current_lvl
    for _ in range(qty): total_cost += int(conf['c'] * (1.5 ** temp_lvl)); temp_lvl += 1
        
    if player.gold >= total_cost:
        player.gold -= total_cost; setattr(player, conf['a'], current_lvl + qty); db.commit()
        await query.answer(f"Sucesso! +{qty} Níveis", show_alert=True)
        # Refresh do menu de construção
        query.data = f"constr_{key}"
        await handle_construction_view(update, context) # Recarrega a view
    else:
        await query.answer()
        await query.message.reply_text(f"🚫 **FALTA OURO!**\nCusto: {format_number(total_cost)}g\nVocê tem: {format_number(player.gold)}g", parse_mode='Markdown')
    db.close()

async def farm_harvest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; db = get_db(); player = get_player(query.from_user.id, db)
    now = datetime.now(); elapsed = (now - player.last_farm_harvest).total_seconds() / 3600
    amt = int(elapsed * player.farm_level * 100)
    if amt > 0: player.gold += amt; player.last_farm_harvest = now; db.commit(); await query.answer(f"💰 +{amt}g!", show_alert=True)
    else: await query.answer("Vazio.", show_alert=True)
    db.close()
