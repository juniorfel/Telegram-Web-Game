from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import Player, Guild
from sqlalchemy import func
from utils import get_db, get_player, generate_monster, check_level_up, get_total_stats, simulate_pvp_battle
from config import STAMINA_COST
import random

async def menu_battle_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; db = get_db()
    player = get_player(query.from_user.id, db)
    st = get_total_stats(player)
    
    msg = (f"⚔️ **Zona de Batalha**\n\n"
           f"⚡ **Stamina: {player.stamina}/{player.max_stamina}**\n" 
           f"📊 **Atributos:**\n"
           f"💪 {st['str']} | 🧠 {st['int']} | 🛡️ {st['def']}\n"
           f"💨 {st['spd']} | ❤️ {st['hp']}\n"
           f"🏆 Rank: {player.pvp_rating}")
    kb = [[InlineKeyboardButton("🗺️ Campanha PVE", callback_data='battle_pve_start'), 
           InlineKeyboardButton("🆚 Arena PVP", callback_data='battle_pvp_start')], 
          [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    db.close()

async def battle_pve_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; db = get_db(); player = get_player(query.from_user.id, db)
    m = generate_monster(player.current_phase_id)
    context.user_data['monster'] = m
    msg = (f"🗺️ **Campanha: Fase {player.current_phase_id}**\n\n"
           f"⚡ **Stamina: {player.stamina}/{player.max_stamina}**\n\n"
           f"🔥 {m['name']}\n❤️ HP: {m['hp']} | ⚡ Spd: {m['spd']}\n💰 {m['gold']}g | ✨ {m['xp']}xp")
    kb = [[InlineKeyboardButton("⚔️ ATACAR (1 Stamina)", callback_data='confirm_pve')], [InlineKeyboardButton("🔙", callback_data='menu_battle_mode')]]
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    db.close()

async def confirm_pve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; db = get_db(); player = get_player(query.from_user.id, db)
    
    if player.stamina < STAMINA_COST:
        await query.answer()
        await query.message.reply_text(f"🚫 **SEM STAMINA!**\n{player.stamina}/{player.max_stamina} disponível.", parse_mode='Markdown')
        db.close(); return

    m = context.user_data.get('monster')
    st = get_total_stats(player)
    
    # Gate de Boss
    if m and m['is_boss'] and (st['str'] + st['int'] + st['def']) < (player.current_phase_id * 5):
        await query.message.reply_text("🚫 **MUITO FRACO!**\nMelhore seus atributos para o Boss!", parse_mode='Markdown')
        db.close(); return

    player.stamina -= STAMINA_COST
    p_pow = (st['str'] * 2) + st['int'] + st['def']
    m_pow = m['atk'] + m['def'] + m['hp'] / 10
    chance = max(0.1, min(0.9, 0.5 + ((p_pow - m_pow) / 500)))
    
    if random.random() < chance:
        player.gold += m['gold']; player.xp += m['xp']; player.current_phase_id += 1; check_level_up(player)
        loot = ""
        if random.random() < 0.1: # Drop Raro
            if random.choice([True, False]): player.gems += 2; loot = "\n💎 Drop Raro: +2 Gemas!"
            else: player.stamina += 2; loot = "\n⚡ Drop: +2 Stamina!"
        msg = f"⚔️ **Vitória!**\n+{m['gold']}g | +{m['xp']}xp{loot}"
    else: msg = "☠️ **Derrota...**"
    
    db.commit()
    kb = [[InlineKeyboardButton("Continuar", callback_data='menu_battle_mode')]]
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    db.close()

async def battle_pvp_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; db = get_db(); player = get_player(query.from_user.id, db)
    min_r = max(0, player.pvp_rating - 200); max_r = player.pvp_rating + 200
    opps = db.query(Player).filter(Player.id != player.id, Player.pvp_rating >= min_r, Player.pvp_rating <= max_r).order_by(func.random()).limit(4).all()
    if not opps: opps = db.query(Player).filter(Player.id != player.id).order_by(func.random()).limit(4).all()
    
    kb = [[InlineKeyboardButton(f"{('🟢' if o.pvp_rating <= player.pvp_rating else '🔴')} {o.name} ({o.pvp_rating})", callback_data=f'pre_fight_{o.id}')] for o in opps]
    kb.append([InlineKeyboardButton("🔄 Atualizar", callback_data='battle_pvp_start'), InlineKeyboardButton("🔙", callback_data='menu_battle_mode')])
    await query.edit_message_text(f"⚔️ **Arena PvP**\n⚡ **Stamina: {player.stamina}/{player.max_stamina}**\nSeus Pontos: {player.pvp_rating}", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    db.close()

async def pre_fight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; db = get_db(); player = get_player(query.from_user.id, db)
    oid = int(query.data.split('_')[2]); opp = db.query(Player).filter(Player.id == oid).first()
    context.user_data['opponent_id'] = opp.id
    kb = [[InlineKeyboardButton("⚔️ LUTAR (1 Stamina)", callback_data='confirm_pvp')], [InlineKeyboardButton("🔙", callback_data='battle_pvp_start')]]
    await query.edit_message_text(f"🆚 **{opp.name}**\nRating: {opp.pvp_rating}\n\n⚡ **Stamina: {player.stamina}/{player.max_stamina}**\n\nVitória: +25 | Derrota: -15", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    db.close()

async def confirm_pvp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; db = get_db(); player = get_player(query.from_user.id, db)
    
    if player.stamina < STAMINA_COST:
        await query.answer()
        await query.message.reply_text(f"🚫 **SEM STAMINA!**\nVocê está exausto.", parse_mode='Markdown')
        db.close(); return
        
    opp = db.query(Player).filter(Player.id == context.user_data.get('opponent_id')).first()
    player.stamina -= STAMINA_COST
    winner = simulate_pvp_battle(player, opp)
    
    if winner.id == player.id:
        player.pvp_rating += 25; msg = "🏆 **Vitória!**\n+25 Pontos!"
        if player.guild_id: 
            g = db.query(Guild).filter(Guild.id == player.guild_id).first()
            g.xp += 10; msg += "\n🛡️ +10 XP Clã"
    else:
        player.pvp_rating = max(0, player.pvp_rating - 15); msg = "🏳️ **Derrota...**\n-15 Pontos."
    
    db.commit()
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Continuar", callback_data='battle_pvp_start')]]), parse_mode='Markdown')
    db.close()
