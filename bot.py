import os
import sqlite3
import time
import json
import random
import google.generativeai as genai
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

# --- KONFIGURASI KREDENSIAL ---
TELEGRAM_TOKEN = "8969354921:AAHPlpEiQFabiq0ZPDherqXLXOYqhhvrrls"
GEMINI_API_KEY = "AQ.Ab8RN6KJxM73ztwzk1T4R5I6Gl3PO_Ckoc_BEFEDu0MNN3"
TARGET_CHAT_ID = "737094524"

genai.configure(api_key=GEMINI_API_KEY)

SCHEDULE_SLOTS = ["12:00 WIB", "19:00 WIB"]

# --- SETUP DATABASE ---
def init_db():
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS video_warehouse (id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT UNIQUE, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS stok_siap (id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT UNIQUE, generated_caption TEXT, scheduled_time TEXT UNIQUE, status TEXT DEFAULT "READY", created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS stok_reupload (id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT UNIQUE, caption TEXT, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS riwayat_upload (id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT, caption TEXT, taken_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS produk_stok (id INTEGER PRIMARY KEY AUTOINCREMENT, nama_produk TEXT UNIQUE, kategori TEXT, link_affiliate TEXT, tips_konten TEXT, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    conn.commit()
    conn.close()

init_db()

# --- AI GENERATOR ---
def generate_ai_caption():
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        seed = random.randint(1000, 9999)
        prompt = (
            f"Buatkan caption video pendek untuk TikTok Affiliate/BooStore (Fashion, OOTD) yang engaging & santai (Gaya {seed}). "
            "Sertakan HANYA MAKSIMAL 5 hashtag populer yang relevan. Dalam Bahasa Indonesia."
        )
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return "OOTD andalan bikin penampilan makin keren! ✨ Cek keranjang kuning ya.\n\n#ootdindo #fashiontiktok #racuntiktok #fyp #inspirasifashion"

def generate_tiktok_affiliate_ideas(excluded=[]):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        exc_str = ", ".join(excluded) if excluded else "tidak ada"
        prompt = (
            "Berikan 10 ide produk viral TikTok Shop kategori Fashion, OOTD, Tas, Sepatu, Hijab. "
            f"Kecualikan produk berikut: [{exc_str}]. "
            "Format output HARUS JSON array murni tanpa teks lain: "
            "[{\"nama_produk\": \"...\", \"kategori\": \"...\", \"tips_konten\": \"...\", \"link_affiliate\": \"...\", \"image_url\": \"...\"}]"
        )
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:-3].strip()
        elif text.startswith("```"):
            text = text[3:-3].strip()
        return json.loads(text)
    except Exception as e:
        return [
            {"nama_produk": "Tas Selempang Kanvas Casual", "kategori": "Fashion", "tips_konten": "Tunjukkan kapasitas tas", "link_affiliate": "https://shop.tiktok.com/view/product/taskanvas", "image_url": "https://images.unsplash.com/photo-1544816155-12df9643f363?w=500"},
            {"nama_produk": "Kemeja Oversize Linen Wanita", "kategori": "Fashion", "tips_konten": "Mix and match kemeja", "link_affiliate": "https://shop.tiktok.com/view/product/kemejalinen", "image_url": "https://images.unsplash.com/photo-1598554747436-c9293d6a588f?w=500"}
        ]

def get_next_available_fyptime():
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    cursor.execute("SELECT scheduled_time FROM stok_siap")
    existing = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    offset = 0
    while True:
        target = datetime.now().timestamp() + (offset * 86400)
        f_date = datetime.fromtimestamp(target).strftime('%Y-%m-%d')
        for slot in SCHEDULE_SLOTS:
            cand = f"{f_date} ({slot})"
            if cand not in existing:
                return cand
        offset += 1

async def process_incoming_video(app, file_id):
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    caption = generate_ai_caption()
    slot = get_next_available_fyptime()
    try:
        cursor.execute('INSERT INTO stok_siap (file_id, generated_caption, scheduled_time, status) VALUES (?, ?, ?, "READY")', (file_id, caption, slot))
        conn.commit()
    except Exception as e:
        print(e)
    conn.close()

# --- MENU & HANDLER ---
def get_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📁 Cek Gudang", callback_data="menu_gudang"), InlineKeyboardButton("🚀 Stok Siap", callback_data="menu_stok_siap")],
        [InlineKeyboardButton("🔄 Reupload", callback_data="menu_reupload"), InlineKeyboardButton("📋 Riwayat", callback_data="menu_riwayat")],
        [InlineKeyboardButton("🛍️ Cari Produk", callback_data="menu_cari_produk"), InlineKeyboardButton("📦 Produk Saya", callback_data="menu_produk_stok")]
    ])

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "👋 **Asisten Konten & TikTok Affiliate Aktif!**\nPilih menu di bawah:"
    if update.message:
        await update.message.reply_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")
    else:
        await update.callback_query.message.edit_text(text, reply_markup=get_main_menu(), parse_mode="Markdown")

async def cmd_gudang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM video_warehouse')
    total = cursor.fetchone()[0]
    conn.close()
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_home")]])
    text = f"📦 **Gudang Mentah:**\nTotal video: **{total} video**"
    if update.message:
        await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
    else:
        await update.callback_query.message.edit_text(text, reply_markup=markup, parse_mode="Markdown")

async def cmd_stok_siap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, file_id, generated_caption, scheduled_time FROM stok_siap WHERE status = "READY" ORDER BY scheduled_time ASC')
    rows = cursor.fetchall()
    conn.close()
    chat_id = update.effective_chat.id
    if not rows:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_home")]])
        await context.bot.send_message(chat_id=chat_id, text="📭 Stok siap upload kosong.", reply_markup=markup)
        return
    for r in rows:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Ambil", callback_data=f"take_{r[0]}"), InlineKeyboardButton("🔄 Pindah Reup", callback_data=f"reup_{r[0]}")]])
        await context.bot.send_video(chat_id=chat_id, video=r[1], caption=f"📌 **ID: #{r[0]}** | 📅 `{r[3]}`\n\n{r[2]}", reply_markup=kb, parse_mode="Markdown")

async def cmd_stok_reupload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, file_id, caption FROM stok_reupload')
    rows = cursor.fetchall()
    conn.close()
    chat_id = update.effective_chat.id
    if not rows:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_home")]])
        await context.bot.send_message(chat_id=chat_id, text="🔄 Stok reupload kosong.", reply_markup=markup)
        return
    for r in rows:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Ambil", callback_data=f"getreup_{r[0]}")]])
        await context.bot.send_video(chat_id=chat_id, video=r[1], caption=f"🔄 **Reup ID: #{r[0]}**\n\n{r[2]}", reply_markup=kb, parse_mode="Markdown")

async def cmd_riwayat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, file_id, caption, taken_at FROM riwayat_upload ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()
    chat_id = update.effective_chat.id
    if not rows:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_home")]])
        await context.bot.send_message(chat_id=chat_id, text="📂 Riwayat kosong.", reply_markup=markup)
        return
    for r in rows:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Pindah Reup", callback_data=f"movetoreup_{r[0]}")]])
        await context.bot.send_video(chat_id=chat_id, video=r[1], caption=f"📋 **Riwayat ID: #{r[0]}**\n\n{r[2]}", reply_markup=kb, parse_mode="Markdown")

async def cmd_cari_produk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    cursor.execute('SELECT nama_produk FROM produk_stok')
    existing = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    await context.bot.send_message(chat_id=chat_id, text="🔍 AI meriset produk tren baru...")
    products = generate_tiktok_affiliate_ideas(existing)
    
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    for i, p in enumerate(products, 1):
        nama, kat, tips, link, img = p.get("nama_produk"), p.get("kategori"), p.get("tips_konten"), p.get("link_affiliate"), p.get("image_url")
        try:
            cursor.execute('INSERT OR IGNORE INTO produk_stok (nama_produk, kategori, link_affiliate, tips_konten) VALUES (?, ?, ?, ?)', (nama, kat, link, tips))
            conn.commit()
            cursor.execute('SELECT id FROM produk_stok WHERE nama_produk = ?', (nama,))
            spid = cursor.fetchone()[0]
        except:
            spid = 1
        
        txt = f"📦 **{i}. {nama}**\n🏷️ {kat}\n💡 {tips}\n\n🔗 `{link}`"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Simpan", callback_data=f"savedprod_{spid}")]])
        try:
            await context.bot.send_photo(chat_id=chat_id, photo=img, caption=txt, reply_markup=kb, parse_mode="Markdown")
        except:
            await context.bot.send_message(chat_id=chat_id, text=txt, reply_markup=kb, parse_mode="Markdown")
    conn.close()
    
    refresh_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh 10 Produk Lain", callback_data="refresh_products")],
        [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_home")]
    ])
    await context.bot.send_message(chat_id=chat_id, text="Eksplorasi produk lainnya:", reply_markup=refresh_kb)

async def cmd_produk_stok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, nama_produk, kategori, link_affiliate, tips_konten FROM produk_stok')
    rows = cursor.fetchall()
    conn.close()
    chat_id = update.effective_chat.id
    if not rows:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_home")]])
        await context.bot.send_message(chat_id=chat_id, text="📦 Stok produk kosong.", reply_markup=markup)
        return
    for r in rows:
        txt = f"📦 **{r[1]}**\n🏷️ {r[2]}\n💡 {r[4]}\n\n🔗 `{r[3]}`"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Hapus", callback_data=f"delprod_{r[0]}")]])
        await context.bot.send_message(chat_id=chat_id, text=txt, reply_markup=kb, parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "menu_home":
        await cmd_start(update, context)
        return
    elif data == "menu_gudang":
        await cmd_gudang(update, context)
        return
    elif data == "menu_stok_siap":
        await cmd_stok_siap(update, context)
        return
    elif data == "menu_reupload":
        await cmd_stok_reupload(update, context)
        return
    elif data == "menu_riwayat":
        await cmd_riwayat(update, context)
        return
    elif data == "menu_cari_produk":
        await cmd_cari_produk(update, context)
        return
    elif data == "menu_produk_stok":
        await cmd_produk_stok(update, context)
        return
    elif data == "refresh_products":
        await cmd_cari_produk(update, context)
        return

    parts = data.split("_")
    action, tid = parts[0], parts[1]
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()

    if action == "take":
        cursor.execute('SELECT file_id, generated_caption FROM stok_siap WHERE id = ?', (tid,))
        row = cursor.fetchone()
        if row:
            cursor.execute('INSERT INTO riwayat_upload (file_id, caption) VALUES (?, ?)', (row[0], row[1]))
            cursor.execute('DELETE FROM stok_siap WHERE id = ?', (tid,))
            conn.commit()
            await query.edit_message_caption(caption=f"✅ **ID #{tid} Berhasil Diambil!**", parse_mode="Markdown")
    elif action == "reup" or action == "movetoreup":
        tbl = "stok_siap" if action == "reup" else "riwayat_upload"
        cap_col = "generated_caption" if action == "reup" else "caption"
        cursor.execute(f'SELECT file_id, {cap_col} FROM {tbl} WHERE id = ?', (tid,))
        row = cursor.fetchone()
        if row:
            cursor.execute('INSERT OR IGNORE INTO stok_reupload (file_id, caption) VALUES (?, ?)', (row[0], row[1]))
            if action == "reup":
                cursor.execute('DELETE FROM stok_siap WHERE id = ?', (tid,))
            conn.commit()
            await query.edit_message_caption(caption=f"🔄 **ID #{tid} Dipindah ke Reupload!**", parse_mode="Markdown")
    elif action == "getreup":
        cursor.execute('DELETE FROM stok_reupload WHERE id = ?', (tid,))
        conn.commit()
        await query.edit_message_caption(caption=f"🚀 **Reupload ID #{tid} Selesai!**", parse_mode="Markdown")
    elif action == "savedprod":
        try:
            await query.edit_message_caption(caption=query.message.caption + "\n\n✨ *[Disimpan]*", parse_mode="Markdown")
        except:
            pass
    elif action == "delprod":
        cursor.execute('DELETE FROM produk_stok WHERE id = ?', (tid,))
        conn.commit()
        await query.edit_message_text(text="🗑️ **Produk Dihapus.**", parse_mode="Markdown")
    conn.close()

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.video or str(msg.chat.id) != TARGET_CHAT_ID:
        return
    file_id = msg.video.file_id
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO video_warehouse (file_id) VALUES (?)', (file_id,))
        conn.commit()
        conn.close()
        status_msg = await msg.reply_text("📥 **Video masuk Gudang!** AI meriset caption...", parse_mode="Markdown")
        await process_incoming_video(context.application, file_id)
        
        conn = sqlite3.connect('video_warehouse.db')
        cursor = conn.cursor()
        cursor.execute('SELECT generated_caption, scheduled_time, id FROM stok_siap WHERE file_id = ?', (file_id,))
        res = cursor.fetchone()
        conn.close()
        if res:
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_home")]])
            await status_msg.edit_text(f"✨ **Stok Siap (ID: #{res[2]})**\n📅 {res[1]}\n\n{res[0]}", reply_markup=markup, parse_mode="Markdown")
    except sqlite3.IntegrityError:
        await msg.reply_text("⚠️ Video sudah ada.")
        conn.close()

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("gudang", cmd_gudang))
    app.add_handler(CommandHandler("stok_siap", cmd_stok_siap))
    app.add_handler(CommandHandler("stok_reupload", cmd_stok_reupload))
    app.add_handler(CommandHandler("riwayat", cmd_riwayat))
    app.add_handler(CommandHandler("cari_produk", cmd_cari_produk))
    app.add_handler(CommandHandler("produk_stok", cmd_produk_stok))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.VIDEO & filters.ChatType.PRIVATE, handle_video))
    print("🤖 Bot Aktif...")
    app.run_polling()

if __name__ == '__main__':
    main()
