from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import Player, Guild
from utils import get_db, format_number
from config import OFFICIAL_CHANNEL_LINK

async def menu_ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ranking de Jogadores"""
    query = update.callback_query; db = get_db()
    top = db.query(Player).order_by(Player.pvp_rating.desc()).limit(10).all()
    txt = "🏆 **Top 10 Jogadores (PvP)**\n" + "\n".join([f"#{i+1} {p.name} ({p.pvp_rating} Pts)" for i, p in enumerate(top)])
    
    # Botão para alternar para Guildas
    kb = [[InlineKeyboardButton("🛡️ Ver Top Guildas", callback_data='ranking_guilds')],
          [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
    
    await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    db.close()

async def menu_ranking_guilds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ranking de Guildas"""
    query = update.callback_query; db = get_db()
    # Ordena por XP ou Rating (usaremos Rating Total aqui)
    top = db.query(Guild).order_by(Guild.total_rating.desc()).limit(10).all()
    
    if not top:
        txt = "🏆 **Top Guildas**\n\nNenhuma guilda formada ainda."
    else:
        txt = "🏆 **Top 10 Guildas**\n" + "\n".join([f"#{i+1} {g.name} (Lvl {g.level})" for i, g in enumerate(top)])
    
    # Botão para alternar para Jogadores
    kb = [[InlineKeyboardButton("👤 Ver Top Jogadores", callback_data='menu_ranking')],
          [InlineKeyboardButton("🔙 Voltar", callback_data='menu_refresh')]]
          
    await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    db.close()

async def menu_mailbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    kb = [[InlineKeyboardButton("📢 Canal Oficial", url=OFFICIAL_CHANNEL_LINK)], [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
    await query.edit_message_text("✉️ **Correio Real**\nFique atento aos decretos e eventos:", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def menu_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.edit_message_text("💎 **Mercado Negro VIP**\n\n🚧 Em breve via XSolla.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]), parse_mode='Markdown')
