from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import Player
from utils import get_db, get_player, format_number
from datetime import datetime

# Configuração Centralizada das Construções
BUILDINGS_CONFIG = {
    'fazenda': {'attr':'farm_level', 'cost':500, 'desc':'Produz Ouro e Trigo'}, 
    'celeiro': {'attr':'barn_level', 'cost':500, 'desc':'Aumenta Capacidade'},
    'quartel': {'attr':'barracks_level', 'cost':2000, 'desc':'Aumenta Força e Defesa'}, 
    'academia': {'attr':'academy_level', 'cost':1500, 'desc':'Aumenta Inteligência e XP'},
    'pista': {'attr':'track_level', 'cost':2500, 'desc':'Aumenta Velocidade e Crítico'},
    'clinica': {'attr':'clinic_level', 'cost':3000, 'desc':'Regeneração de HP Offline'}
}

async def menu_constructions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; db = get_db(); player = get_player(query.from_user.id, db)
    
    # Cálculos visuais
    prod_h = player.farm_level * 10
    cap = player.barn_level * 100
    
    msg = (f"🏗️ **Distrito de Construções**\n\n"
           f"🌾 Fazenda: Lvl {player.farm_level} ({prod_h}/h)\n"
           f"🏚️ Celeiro: Lvl {player.barn_level} (Cap: {cap})\n"
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
    query = update.callback_query
    # Pega o ID (ex: 'fazenda') do indice 1. Funciona para 'constr_fazenda' e 'upgrade_fazenda_1'
    key = query.data.split('_')[1]
    
    db = get_db(); player = get_player(query.from_user.id, db)
    conf = BUILDINGS_CONFIG.get(key)
    
    if not conf: 
        await query.answer("Erro: Construção não encontrada."); db.close(); return

    lvl = getattr(player, conf['attr'])
    
    # Custo 1x
    cost_1 = int(conf['cost'] * (1.5 ** lvl))
    
    # Custo 10x
    cost_10 = 0
    temp_lvl = lvl
    for _ in range(10):
        cost_10 += int(conf['cost'] * (1.5 ** temp_lvl))
        temp_lvl += 1
        
    msg = (f"🏗️ **{key.capitalize()}** (Nível {lvl})\n_{conf['desc']}_\n\n"
           f"💰 Saldo: {format_number(player.gold)}g\n\n"
           f"Melhorar estrutura:")
           
    kb = [[InlineKeyboardButton(f"⬆️ +1 ({format_number(cost_1)}g)", callback_data=f'upgrade_{key}_1'),
           InlineKeyboardButton(f"⬆️ +10 ({format_number(cost_10)}g)", callback_data=f'upgrade_{key}_10')]]
    
    if key == 'fazenda' and lvl > 0:
        kb.append([InlineKeyboardButton("💰 Vender Colheita", callback_data='farm_harvest')])
        
    kb.append([InlineKeyboardButton("🔙 Voltar", callback_data='menu_constructions')])
    
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    db.close()

async def handle_upgrade_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Formato: upgrade_fazenda_10
    parts = query.data.split('_')
    key = parts[1]
    qty = int(parts[2])
    
    db = get_db(); player = get_player(query.from_user.id, db)
    conf = BUILDINGS_CONFIG.get(key)
    
    current_lvl = getattr(player, conf['attr'])
    
    # Calcula Custo Real
    total_cost = 0
    temp_lvl = current_lvl
    for _ in range(qty):
        total_cost += int(conf['cost'] * (1.5 ** temp_lvl))
        temp_lvl += 1
        
    if player.gold >= total_cost:
        player.gold -= total_cost
        setattr(player, conf['attr'], current_lvl + qty)
        db.commit()
        await query.answer(f"Construção Melhorada! +{qty} Níveis", show_alert=True)
        # Recarrega a view chamando a função diretamente
        # Como o botão clicado foi 'upgrade_fazenda...', a função view vai pegar 'fazenda' corretamente
        await handle_construction_view(update, context) 
    else:
        await query.answer() # Fecha o loading do botão
        await query.message.reply_text(
            f"🚫 **FALTA OURO!**\n\n"
            f"Custo: {format_number(total_cost)}g\n"
            f"Você tem: {format_number(player.gold)}g", 
            parse_mode='Markdown'
        )
    db.close()

async def farm_harvest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; db = get_db(); player = get_player(query.from_user.id, db)
    now = datetime.now()
    elapsed = (now - player.last_farm_harvest).total_seconds() / 3600
    amt = int(elapsed * player.farm_level * 100)
    
    if amt > 0:
        player.gold += amt
        player.last_farm_harvest = now
        db.commit()
        await query.answer(f"💰 Vendeu por {amt}g!", show_alert=True)
    else:
        await query.answer("🌾 Colheita vazia. Espere mais tempo.", show_alert=True)
    
    # Recarrega menu da fazenda
    await handle_construction_view(update, context)
    db.close()
