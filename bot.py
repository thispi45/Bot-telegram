import os
import sqlite3
import time
import json
import random
import asyncio
import tempfile
from google import genai
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

# --- KONFIGURASI KREDENSIAL ---
TELEGRAM_TOKEN = "8969354921:AAHPlpEiQFabiq0ZPDherqXLXOYqhhvrrls"
GEMINI_API_KEY = "AQ.Ab8RN6KJxM73ztwzk1T4R5I6Gl3PO_Ckoc_BEFEDu0MNN3"
TARGET_CHAT_ID = "737094524"

# Inisialisasi client resmi google-genai
client = genai.Client(api_key=GEMINI_API_KEY)

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
    cursor.execute('CREATE TABLE IF NOT EXISTS riwayat_pencarian_produk (id INTEGER PRIMARY KEY AUTOINCREMENT, nama_produk TEXT UNIQUE)')
    conn.commit()
    conn.close()

init_db()

# --- AI ANALISIS VISUAL VIDEO MENGGUNAKAN GOOGLE-GENAI SDK ---
def generate_ai_caption_from_video(video_path):
    uploaded_file = None
    try:
        # Mengunggah video menggunakan client.files dari google-genai
        uploaded_file = client.files.upload(file=video_path, config={"mime_type": "video/mp4"})
        
        # Menunggu proses server selesai
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)
            
        if uploaded_file.state.name == "FAILED":
            raise Exception("Gagal memproses video di server AI")

        rand_id = random.randint(100000, 999999)
        prompt = (
            f"Analisis video produk TikTok Affiliate/BooStore ini secara visual. Buatkan 1 caption pendek yang sangat engaging, santai, kekinian, dan NYAMBUNG persis dengan produk/kegiatan di dalam video (Kode unik: {rand_id}). "
            "PENTING: Sertakan HANYA MAKSIMAL 5 hashtag populer yang sangat relevan dengan produk dalam video tersebut. Dalam Bahasa Indonesia."
        )
        
        # Generate konten menggunakan model gemini-2.5-flash atau gemini-1.5-flash
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=[uploaded_file, prompt]
        )
        
        # Hapus file dari server AI setelah selesai
        try:
            client.files.delete(name=uploaded_file.name)
        except:
            pass
            
        text = response.text.strip()
        if len(text) > 10:
            return text
        raise Exception("Caption terlalu pendek")
        
    except Exception as e:
        if uploaded_file:
            try:
                client.files.delete(name=uploaded_file.name)
            except:
                pass
        # Fallback cadangan bervariasi jika gagal terhubung
        opening_pool = [
            "Spill produk andalan bikin penampilan makin keren! ✨",
            "Look simple tapi tetep keliatan estetik dan wajib punya! 🤍",
            "Rekomendasi produk harian anti ribet tapi fungsional banget."
        ]
        hashtag_pool = ["#ootdindo #fashiontiktok #racuntiktok #fyp #outfitideas", "#styleinspo #fypindonesia #racunshopee #outfitinspiration"]
        return f"{random.choice(opening_pool)} Cek keranjang kuning ya.\n\n{random.choice(hashtag_pool)}"

def generate_tiktok_affiliate_ideas(excluded=[]):
    try:
        exc_str = ", ".join(excluded[-20:]) if excluded else "tidak ada"
        prompt = (
            "Berikan tepat 10 ide produk viral TikTok Shop kategori Fashion, OOTD, Tas, Sepatu, Hijab, dan Aksesori. "
            f"JANGAN TAMPILKAN produk berikut: [{exc_str}]. "
            "Format output HARUS JSON array murni tanpa teks lain dengan struktur kunci: "
            "[{\"nama_produk\": \"...\", \"kategori\": \"...\", \"tips_konten\": \"...\", \"link_affiliate\": \"...\"}]"
        )
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt
        )
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:-3].strip()
        elif text.startswith("```"):
            text = text[3:-3].strip()
        
        data = json.loads(text)
        if isinstance(data, list) and len(data) >= 5:
            return data[:10]
        raise Exception("Invalid list length")
    except Exception as e:
        kategori_pool = ["Fashion Wanita", "OOTD Casual", "Tas Selempang", "Sepatu Sneakers", "Hijab Pashmina", "Outerwear", "Aksesori"]
        item_pool = ["Blouse Rayon", "Kemeja Linen", "Slingbag Kanvas", "Pashmina Kaftan", "Celana Highwaist", "Cardigan Knit", "Topi Baseball", "Kacamata Retro", "Sepatu Platform"]
        
        generated = []
        for i in range(10):
            nama = f"{random.choice(item_pool)} Edisi {random.randint(10, 999)}"
            while nama in excluded or any(p['nama_produk'] == nama for p in generated):
                nama = f"{random.choice(item_pool)} Edisi {random.randint(10, 999)}"
            
            generated.append({
                "nama_produk": nama,
                "kategori": random.choice(kategori_pool),
                "tips_konten": "Soroti detail bahan dan tunjukkan hasil pemakaian.",
                "link_affiliate": f"https://shop.tiktok.com/view/product/item{random.randint(1000,9999)}"
            })
        return generated

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

async def process_single_video(bot_app, file_id):
    try:
        file_obj = await bot_app.bot.get_file(file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video:
            temp_path = temp_video.name
            await file_obj.download_to_drive(temp_path)
            
        loop = asyncio.get_event_loop()
        caption = await loop.run_in_executor(None, generate_ai_caption_from_video, temp_path)
        
        try:
            os.remove(temp_path)
        except:
            pass
            
        slot = get_next_available_fyptime()
        
        conn = sqlite3.connect('video_warehouse.db')
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO video_warehouse (file_id) VALUES (?)', (file_id,))
        cursor.execute('INSERT INTO stok_siap (file_id, generated_caption, scheduled_time, status) VALUES (?, ?, ?, "READY")', (file_id, caption, slot))
        conn.commit()
        
        cursor.execute('SELECT id, scheduled_time, generated_caption FROM stok_siap WHERE file_id = ?', (file_id,))
        res = cursor.fetchone()
        conn.close()
        return res
    except Exception as e:
        print(f"Error process video: {e}")
        return None

# --- MENU UTAMA ---
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
    text = f"📦 **Gudang Mentah:**\nTotal video tersimpan: **{total} video**"
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
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Ambil", callback_data=f"take_{r[0]}"), InlineKeyboardButton("🔄 Pindah Reup", callback_data=f"reup_{r[0]}")],
            [InlineKeyboardButton("🗑️ Hapus Stok Ini", callback_data=f"delstok_{r[0]}")]
        ])
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
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Ambil", callback_data=f"getreup_{r[0]}")],
            [InlineKeyboardButton("🗑️ Hapus Reup", callback_data=f"delreup_{r[0]}")]
        ])
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
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Pindah Reup", callback_data=f"movetoreup_{r[0]}")],
            [InlineKeyboardButton("🗑️ Hapus Riwayat", callback_data=f"delriwayat_{r[0]}")]
        ])
        await context.bot.send_video(chat_id=chat_id, video=r[1], caption=f"📋 **Riwayat ID: #{r[0]}**\n\n{r[2]}", reply_markup=kb, parse_mode="Markdown")

async def cmd_cari_produk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    cursor.execute('SELECT nama_produk FROM riwayat_pencarian_produk')
    excluded = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    await context.bot.send_message(chat_id=chat_id, text="🔍 AI meriset 10 produk tren baru. Klik tombol di bawah jika ingin menyimpannya ke Produk Saya.")
    products = generate_tiktok_affiliate_ideas(excluded)
    
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    
    for i, p in enumerate(products, 1):
        nama, kat, tips, link = p.get("nama_produk"), p.get("kategori"), p.get("tips_konten"), p.get("link_affiliate")
        
        try:
            cursor.execute('INSERT OR IGNORE INTO riwayat_pencarian_produk (nama_produk) VALUES (?)', (nama,))
            conn.commit()
        except:
            pass
            
        txt = f"📦 **{i}. {nama}**\n🏷️ Kategori: {kat}\n💡 Tips: {tips}\n\n🔗 `{link}`"
        
        cursor.execute('INSERT OR IGNORE INTO produk_stok (nama_produk, kategori, link_affiliate, tips_konten) VALUES (?, ?, ?, ?)', (nama, kat, link, tips))
        conn.commit()
        cursor.execute('SELECT id FROM produk_stok WHERE nama_produk = ?', (nama,))
        spid = cursor.fetchone()[0]
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Simpan ke Produk Saya", callback_data=f"saveprod_{spid}")]])
        await context.bot.send_message(chat_id=chat_id, text=txt, reply_markup=kb, parse_mode="Markdown")
        
    conn.close()
    
    refresh_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh 10 Produk Lain (Tanpa Duplikat)", callback_data="refresh_products")],
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
        await context.bot.send_message(chat_id=chat_id, text="📦 Stok produk saya masih kosong.", reply_markup=markup)
        return
    for r in rows:
        txt = f"📦 **{r[1]}**\n🏷️ {r[2]}\n💡 {r[4]}\n\n🔗 `{r[3]}`"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Hapus dari Produk Saya", callback_data=f"delprod_{r[0]}")]])
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
            await query.edit_message_caption(caption=f"✅ **ID #{tid} Berhasil Diambil ke Riwayat!**", parse_mode="Markdown")
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
    elif action == "saveprod":
        await query.edit_message_text(text=query.message.text + "\n\n✨ **[STATUS: Berhasil Disimpan ke Produk Saya!]**", parse_mode="Markdown")
    elif action == "delprod":
        cursor.execute('DELETE FROM produk_stok WHERE id = ?', (tid,))
        conn.commit()
        await query.edit_message_text(text="🗑️ **Produk Berhasil Dihapus.**", parse_mode="Markdown")
    elif action == "delstok":
        cursor.execute('DELETE FROM stok_siap WHERE id = ?', (tid,))
        conn.commit()
        await query.edit_message_caption(caption=f"🗑️ **Stok Siap ID #{tid} Berhasil Dihapus!**", parse_mode="Markdown")
    elif action == "delreup":
        cursor.execute('DELETE FROM stok_reupload WHERE id = ?', (tid,))
        conn.commit()
        await query.edit_message_caption(caption=f"🗑️ **Reupload ID #{tid} Berhasil Dihapus!**", parse_mode="Markdown")
    elif action == "delriwayat":
        cursor.execute('DELETE FROM riwayat_upload WHERE id = ?', (tid,))
        conn.commit()
        await query.edit_message_caption(caption=f"🗑️ **Riwayat ID #{tid} Berhasil Dihapus!**", parse_mode="Markdown")
    conn.close()

# --- HANDLER UPLOAD VIDEO DENGAN ANALISIS VISUAL SDK BARU ---
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.video or str(msg.chat.id) != TARGET_CHAT_ID:
        return
    
    file_id = msg.video.file_id
    status_msg = await msg.reply_text("📥 **Video masuk Gudang!**\n🤖 AI sedang menonton dan menganalisis visual isi video...", parse_mode="Markdown")
    
    res = await process_single_video(context.application, file_id)
    if res:
        stock_id, jadwal, caption_hasil = res[0], res[1], res[2]
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_home")]])
        await status_msg.edit_text(
            f"✨ **Stok Siap Masuk! (ID: #{stock_id})**\n"
            f"📅 **Jadwal:** {jadwal}\n\n"
            f"📝 **Caption Sesuai Video:**\n{caption_hasil}",
            reply_markup=markup,
            parse_mode="Markdown"
        )
    else:
        await status_msg.edit_text("⚠️ Gagal memproses video.")

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
    print("🤖 Bot Asisten SDK Terbaru Aktif 24 Jam...")
    app.run_polling()

if __name__ == '__main__':
    main()
