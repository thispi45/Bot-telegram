import os
import sqlite3
import time
import json
import schedule
import google.generativeai as genai
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

# --- KONFIGURASI KREDENSIAL ---
TELEGRAM_TOKEN = "8969354921:AAEXq419n6hlh3Kmh7qG9"
GEMINI_API_KEY = "AQ.Ab8RN6KJxM73ztwzk1T4R5I6Gl3PO_Ckoc_BEFEDu0MNN3"
TARGET_CHAT_ID = "737094524"

genai.configure(api_key=GEMINI_API_KEY)

SCHEDULE_WEEKDAY = ["12:00", "19:00"]
SCHEDULE_WEEKEND = ["10:00", "15:00", "20:00"]

# --- SETUP DATABASE LOKAL ---
def init_db():
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS video_warehouse (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT UNIQUE,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stok_siap (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT UNIQUE,
            generated_caption TEXT,
            scheduled_time TEXT,
            status TEXT DEFAULT 'READY',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stok_reupload (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT UNIQUE,
            caption TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS riwayat_upload (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            caption TEXT,
            taken_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS produk_stok (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama_produk TEXT,
            kategori TEXT,
            link_affiliate TEXT,
            tips_konten TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# --- AI GENERATOR ---
def generate_ai_caption():
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = (
            "Buatkan caption video pendek yang sangat engaging, santai, kekinian, "
            "lengkap dengan 8-10 hashtag populer & universal yang sedang trending di TikTok "
            "dalam Bahasa Indonesia."
        )
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return "Konten menarik hari ini! 🔥 Jangan lupa tonton sampai habis ya.\n\n#fyp #viral #trending #foryoupage"

def generate_tiktok_affiliate_ideas():
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = (
            "Berikan 10 ide produk spesifik yang sedang viral dan laris di TikTok Shop Affiliate Indonesia. "
            "Sertakan nama produk, kategori, tips sudut pandang konten (angle), dan format simulasi link TikTok Shop (misal: https://shop.tiktok.com/view/product/...). "
            "Format output HARUS berupa JSON array murni tanpa teks tambahan, dengan struktur kunci: "
            "nama_produk, kategori, tips_konten, link_affiliate."
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
            {
                "nama_produk": "Lampu Meja LED Estetik", 
                "kategori": "Room Decor", 
                "tips_konten": "Soroti perubahan kamar dari gelap jadi estetik ala Pinterest", 
                "link_affiliate": "https://shop.tiktok.com/view/product/lampuestetik"
            },
            {
                "nama_produk": "Tas Selempang Kanvas Casual", 
                "kategori": "Fashion / BooStore", 
                "tips_konten": "Tunjukkan kapasitas tas yang muat banyak tapi tetap OOTD", 
                "link_affiliate": "https://shop.tiktok.com/view/product/taskanvas"
            }
        ]

def get_next_fyptime():
    now = datetime.now()
    is_weekend = now.weekday() >= 5
    active_schedule = SCHEDULE_WEEKEND if is_weekend else SCHEDULE_WEEKDAY
    return f"{now.strftime('%Y-%m-%d')} ({active_schedule[0]} WIB)"

async def process_incoming_video(bot_app, file_id):
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    
    smart_caption = generate_ai_caption()
    scheduled_slot = get_next_fyptime()

    try:
        cursor.execute('''
            INSERT OR REPLACE INTO stok_siap (file_id, generated_caption, scheduled_time, status) 
            VALUES (?, ?, ?, 'READY')
        ''', (file_id, smart_caption, scheduled_slot))
        conn.commit()
    except Exception as e:
        print(f"Error insert stok siap: {e}")

    cursor.execute("SELECT COUNT(*) FROM stok_siap WHERE status = 'READY'")
    sisa_stok = cursor.fetchone()[0]

    if sisa_stok <= 6:
        await bot_app.bot.send_message(
            chat_id=TARGET_CHAT_ID,
            text=f"⚠️ **PERINGATAN STOK MENIPIS!**\nStok siap upload tinggal **{sisa_stok} video lagi**.\nSegera kirim video baru ke gudang PM ini!"
        )

    conn.close()

# --- PANEL MENU UTAMA DENGAN TOMBOL INTERAKTIF ---
def get_main_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📁 Cek Gudang", callback_data="menu_gudang"),
            InlineKeyboardButton("🚀 Stok Siap", callback_data="menu_stok_siap")
        ],
        [
            InlineKeyboardButton("🔄 Reupload", callback_data="menu_reupload"),
            InlineKeyboardButton("📋 Riwayat", callback_data="menu_riwayat")
        ],
        [
            InlineKeyboardButton("🛍️ Cari Produk Affiliate", callback_data="menu_cari_produk"),
            InlineKeyboardButton("📦 Stok Produk Saya", callback_data="menu_produk_stok")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 **Asisten Konten & TikTok Affiliate Aktif!**\n\n"
        "Silakan pilih menu di bawah ini tanpa perlu mengetik, atau ketik perintah manual seperti `/stok_siap`:"
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=get_main_menu_keyboard())
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=get_main_menu_keyboard())

async def cmd_gudang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM video_warehouse')
    total = cursor.fetchone()[0]
    conn.close()
    
    text = f"📦 **Gudang Mentah:**\nTotal video tersimpan: **{total} video**"
    keyboard = [[InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu_home")]]
    
    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def cmd_stok_siap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, file_id, generated_caption, scheduled_time FROM stok_siap WHERE status = "READY" LIMIT 3')
    rows = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(*) FROM stok_siap WHERE status = 'READY'")
    total_siap = cursor.fetchone()[0]
    conn.close()

    chat_id = update.effective_chat.id

    if not rows:
        text = "📭 Stok siap upload kosong. Silakan kirim video baru ke chat ini!"
        keyboard = [[InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu_home")]]
        if update.message:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    await context.bot.send_message(chat_id=chat_id, text=f"🚀 **Menampilkan Stok Siap Upload (Total: {total_siap}):**")

    for r in rows:
        stock_id, file_id, caption, jadwal = r[0], r[1], r[2], r[3]
        keyboard = [
            [
                InlineKeyboardButton("✅ Ambil", callback_data=f"take_{stock_id}"),
                InlineKeyboardButton("🔄 Pindah Reup", callback_data=f"reup_{stock_id}")
            ]
        ]
        await context.bot.send_video(
            chat_id=chat_id,
            video=file_id,
            caption=f"📌 **ID: #{stock_id}** | 📅 **Jadwal:** `{jadwal}`\n\n📝 **Caption:**\n{caption}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def cmd_stok_reupload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, file_id, caption FROM stok_reupload LIMIT 3')
    rows = cursor.fetchall()
    conn.close()

    chat_id = update.effective_chat.id
    if not rows:
        text = "🔄 Stok reupload kosong."
        keyboard = [[InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu_home")]]
        if update.message:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    await context.bot.send_message(chat_id=chat_id, text="🔄 **Daftar Stok Reupload:**")
    for r in rows:
        reup_id, file_id, caption = r[0], r[1], r[2]
        keyboard = [[InlineKeyboardButton("🚀 Ambil Konten Ini", callback_data=f"getreup_{reup_id}")]]
        await context.bot.send_video(
            chat_id=chat_id,
            video=file_id,
            caption=f"🔄 **ID Reupload: #{reup_id}**\n\n📝 **Caption:**\n{caption}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def cmd_riwayat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, file_id, caption, taken_at FROM riwayat_upload ORDER BY id DESC LIMIT 3')
    rows = cursor.fetchall()
    conn.close()

    chat_id = update.effective_chat.id
    if not rows:
        text = "📂 Belum ada riwayat konten."
        keyboard = [[InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu_home")]]
        if update.message:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    await context.bot.send_message(chat_id=chat_id, text="📋 **Riwayat Konten Terakhir:**")
    for r in rows:
        hid, file_id, caption, waktu = r[0], r[1], r[2], r[3]
        keyboard = [[InlineKeyboardButton("🔄 Pindah ke Reupload", callback_data=f"movetoreup_{hid}")]]
        await context.bot.send_video(
            chat_id=chat_id,
            video=file_id,
            caption=f"📋 **Riwayat ID: #{hid}** ({waktu})\n\n📝 **Caption:**\n{caption}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# --- PENCARIAN PRODUK TIKTOK AFFILIATE ---
async def cmd_cari_produk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await context.bot.send_message(chat_id=chat_id, text="🔍 AI sedang meriset 10 produk tren TikTok Shop Affiliate...")
    
    products = generate_tiktok_affiliate_ideas()
    
    await context.bot.send_message(chat_id=chat_id, text="🛍️ **Rekomendasi 10 Produk TikTok Affiliate:**")
    
    for i, p in enumerate(products, 1):
        nama = p.get("nama_produk", "Produk Tren")
        kategori = p.get("kategori", "TikTok Shop")
        tips = p.get("tips_konten", "Buat konten kreatif.")
        link = p.get("link_affiliate", "https://shop.tiktok.com/...")
        
        text = (
            f"📦 **{i}. {nama}**\n"
            f"🏷️ Kategori: *{kategori}*\n"
            f"💡 Tips: {tips}\n\n"
            f"🔗 **Link Affiliate:** `{link}`"
        )
        
        conn = sqlite3.connect('video_warehouse.db')
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO produk_stok (nama_produk, kategori, link_affiliate, tips_konten) VALUES (?, ?, ?, ?)',
            (nama, kategori, link, tips)
        )
        saved_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        keyboard = [[InlineKeyboardButton("✅ Simpan ke Stok Produk Saya", callback_data=f"savedprod_{saved_id}")]]
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    refresh_keyboard = [
        [InlineKeyboardButton("🔄 Cari 10 Produk Lainnya (Refresh)", callback_data="refresh_products")],
        [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_home")]
    ]
    await context.bot.send_message(chat_id=chat_id, text="Ingin eksplorasi produk TikTok lainnya?", reply_markup=InlineKeyboardMarkup(refresh_keyboard))

async def cmd_produk_stok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, nama_produk, kategori, link_affiliate, tips_konten FROM produk_stok LIMIT 10')
    rows = cursor.fetchall()
    conn.close()

    chat_id = update.effective_chat.id
    if not rows:
        text = "📦 Stok produk affiliate Anda masih kosong.\nGunakan menu *Cari Produk Affiliate*."
        keyboard = [[InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu_home")]]
        if update.message:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    await context.bot.send_message(chat_id=chat_id, text="📦 **Daftar Stok Produk TikTok Affiliate Pilihan:**")
    for r in rows:
        spid, nama, kategori, link, tips = r[0], r[1], r[2], r[3], r[4]
        text = (
            f"📦 **{nama}**\n"
            f"🏷️ Kategori: *{kategori}*\n"
            f"💡 Tips: {tips}\n\n"
            f"🔗 **Link:** `{link}`"
        )
        keyboard = [[InlineKeyboardButton("🗑️ Hapus dari Stok", callback_data=f"delprod_{spid}")]]
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- HANDLER TOMBOL INTERAKTIF (CALLBACK) ---
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
        await query.message.edit_text("🔄 Menyegarkan daftar 10 produk TikTok baru...")
        await cmd_cari_produk(update, context)
        return

    parts = data.split("_")
    action, target_id = parts[0], parts[1]

    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()

    if action == "take":
        cursor.execute('SELECT file_id, generated_caption FROM stok_siap WHERE id = ?', (target_id,))
        row = cursor.fetchone()
        if row:
            cursor.execute('INSERT INTO riwayat_upload (file_id, caption) VALUES (?, ?)', (row[0], row[1]))
            cursor.execute('DELETE FROM stok_siap WHERE id = ?', (target_id,))
            conn.commit()
            await query.edit_message_caption(caption=f"✅ **ID #{target_id} Berhasil Diambil ke Riwayat!**")

    elif action == "reup" or action == "movetoreup":
        table = "stok_siap" if action == "reup" else "riwayat_upload"
        cursor.execute(f'SELECT file_id, { "generated_caption" if action=="reup" else "caption" } FROM {table} WHERE id = ?', (target_id,))
        row = cursor.fetchone()
        if row:
            cursor.execute('INSERT OR IGNORE INTO stok_reupload (file_id, caption) VALUES (?, ?)', (row[0], row[1]))
            if action == "reup":
                cursor.execute('DELETE FROM stok_siap WHERE id = ?', (target_id,))
            conn.commit()
            if action == "reup":
                await query.edit_message_caption(caption=f"🔄 **ID #{target_id} Dipindah ke Stok Reupload!**")
            else:
                await query.edit_message_caption(caption=f"🔄 **Riwayat ID #{target_id} Dipindah ke Stok Reupload!**")

    elif action == "getreup":
        cursor.execute('DELETE FROM stok_reupload WHERE id = ?', (target_id,))
        conn.commit()
        await query.edit_message_caption(caption=f"🚀 **Konten Reupload ID #{target_id} Selesai Digunakan!**")

    elif action == "savedprod":
        await query.edit_message_text(text=query.message.text + "\n\n✨ *[Status: Disimpan ke Stok Produk Saya]*", parse_mode="Markdown")

    elif action == "delprod":
        cursor.execute('DELETE FROM produk_stok WHERE id = ?', (target_id,))
        conn.commit()
        await query.edit_message_text(text="🗑️ **Produk Berhasil Dihapus dari Stok.**")

    conn.close()

# --- HANDLER VIDEO MASUK ---
async def handle_new_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.video:
        return

    if str(message.chat.id) != TARGET_CHAT_ID:
        return

    video = message.video
    file_id = video.file_id

    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('INSERT INTO video_warehouse (file_id) VALUES (?)', (file_id,))
        conn.commit()
        conn.close()

        status_msg = await message.reply_text("📥 **Video masuk Gudang PM!**\n🤖 AI sedang memproses caption...")

        await process_incoming_video(context.application, file_id)

        conn = sqlite3.connect('video_warehouse.db')
        cursor = conn.cursor()
        cursor.execute('SELECT generated_caption, scheduled_time, id FROM stok_siap WHERE file_id = ?', (file_id,))
        res = cursor.fetchone()
        conn.close()

        if res:
            caption_hasil, jadwal_fyp, stock_id = res[0], res[1], res[2]
            keyboard = [[InlineKeyboardButton("🔙 Buka Menu Utama", callback_data="menu_home")]]
            await status_msg.edit_text(
                f"✨ **Konten Masuk Stok Siap! (ID: #{stock_id})**\n\n"
                f"📅 **Jadwal:** {jadwal_fyp}\n\n"
                f"📝 **Caption:**\n{caption_hasil}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    except sqlite3.IntegrityError:
        await message.reply_text("⚠️ Video ini sudah pernah dimasukkan sebelumnya.")
        conn.close()

# --- MAIN ---
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
    app.add_handler(MessageHandler(filters.VIDEO & filters.ChatType.PRIVATE, handle_new_video))

    print("🤖 Asisten Konten & TikTok Affiliate Aktif 24 Jam...")
    app.run_polling()

if __name__ == '__main__':
    main()
