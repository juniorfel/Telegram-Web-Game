from telegram import Update
from telegram.ext import ContextTypes
from utils import get_db, get_player, is_admin, check_level_up

async def admin_cheat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = get_db()
    try:
        if not is_admin(update.effective_user.id, db): return
        p = get_player(update.effective_user.id, db)
        if p:
            p.gold += 50000; p.gems += 500; p.level = 50; p.stamina = p.max_stamina
            db.commit()
            msg = ("🕵️ **Modo Deus Ativado!**\n\n"
                   "👑 **Comandos GM:**\n"
                   "`/banir [ID]`\n`/conta [ID]` (Deletar)\n"
                   "`/ouro [ID] [QTD]`\n`/gemas [ID] [QTD]`\n"
                   "`/xp [ID] [QTD]`\n`/stamina [ID] [QTD]`\n"
                   "`/promote [ID]`\n`/demote [ID]`")
            await update.message.reply_text(msg, parse_mode='Markdown')
    finally: db.close()

async def admin_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db()
    try:
        if not is_admin(update.effective_user.id, db): return
        tid = int(context.args[0]); t = get_player(tid, db)
        if t: t.is_banned = True; db.commit(); await update.message.reply_text(f"🚫 {t.name} BANIDO.")
        else: await update.message.reply_text("Não encontrado.")
    except: await update.message.reply_text("Uso: /banir [ID]"); db.close()

async def admin_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db()
    try:
        if not is_admin(update.effective_user.id, db): return
        tid = int(context.args[0]); t = get_player(tid, db)
        if t: db.delete(t); db.commit(); await update.message.reply_text(f"🗑️ Conta {tid} DELETADA.")
        else: await update.message.reply_text("Não encontrado.")
    except: await update.message.reply_text("Uso: /conta [ID]"); db.close()

async def admin_give(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db()
    try:
        if not is_admin(update.effective_user.id, db): return
        cmd = update.message.text.split()[0].replace('/', '').split('@')[0]
        tid = int(context.args[0]); amt = int(context.args[1])
        t = get_player(tid, db)
        if t:
            if cmd == 'ouro': t.gold += amt
            elif cmd == 'gemas': t.gems += amt
            elif cmd == 'xp': t.xp += amt; check_level_up(t)
            db.commit(); await update.message.reply_text(f"✅ {amt} {cmd} para {t.name}.")
        else: await update.message.reply_text("Não encontrado.")
    except: await update.message.reply_text(f"Uso: /ouro [ID] [QTD]"); db.close()

# --- NOVO COMANDO STAMINA ---
async def admin_stamina(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db()
    try:
        if not is_admin(update.effective_user.id, db): return
        tid = int(context.args[0]); amt = int(context.args[1])
        t = get_player(tid, db)
        if t:
            t.stamina += amt
            # Opcional: Se quiser respeitar o limite máximo, descomente abaixo:
            # if t.stamina > t.max_stamina: t.stamina = t.max_stamina
            db.commit()
            await update.message.reply_text(f"⚡ Adicionado {amt} Stamina para {t.name} (Total: {t.stamina}).")
        else: await update.message.reply_text("Jogador não encontrado.")
    except: await update.message.reply_text("Uso: /stamina [ID] [QTD]"); db.close()

async def admin_promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db()
    try:
        if not is_admin(update.effective_user.id, db): return
        tid = int(context.args[0]); t = get_player(tid, db)
        if t: t.is_admin = True; db.commit(); await update.message.reply_text(f"👑 {t.name} agora é Admin!")
        else: await update.message.reply_text("Não encontrado.")
    except: await update.message.reply_text("Uso: /promote [ID]"); db.close()

async def admin_demote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db()
    try:
        if not is_admin(update.effective_user.id, db): return
        tid = int(context.args[0]); t = get_player(tid, db)
        if t: t.is_admin = False; db.commit(); await update.message.reply_text(f"👇 {t.name} removido de Admin.")
        else: await update.message.reply_text("Não encontrado.")
    except: await update.message.reply_text("Uso: /demote [ID]"); db.close()
