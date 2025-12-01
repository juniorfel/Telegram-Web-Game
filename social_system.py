from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import Player
from utils import get_db, format_number
from config import OFFICIAL_CHANNEL_LINK

async def menu_ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; db = get_db()
    top = db.query(Player).order_by(Player.pvp_rating.desc()).limit(10).all()
    txt = "🏆 **Salão da Fama**\n" + "\n".join([f"#{i+1} {p.name} ({p.pvp_rating} Pts)" for i, p in enumerate(top)])
    await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]), parse_mode='Markdown')
    db.close()

async def menu_mailbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    kb = [[InlineKeyboardButton("📢 Canal Oficial", url=OFFICIAL_CHANNEL_LINK)], [InlineKeyboardButton("🔙", callback_data='menu_refresh')]]
    await query.edit_message_text("✉️ **Correio Real**\nFique atento aos decretos e eventos:", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def menu_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.edit_message_text("💎 **Mercado Negro VIP**\n\n🚧 Em breve via XSolla.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='menu_refresh')]]), parse_mode='Markdown')
