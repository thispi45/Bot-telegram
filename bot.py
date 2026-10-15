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

# Slot waktu per hari (Maksimal 2 video sehari)
SCHEDULE_SLOTS = ["12:00 WIB", "19:00 WIB"]

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
            scheduled_time TEXT UNIQUE,
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
            nama_produk TEXT UNIQUE,
            kategori TEXT,
            link_affiliate TEXT,
            tips_konten TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# --- AI GENERATOR CAPTION & MAX 5 HASHTAG (FASHION/OOTD) ---
def generate_ai_caption():
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        seed_val = random.randint(1000, 9999)
        prompt = (
            f"Buatkan caption video pendek untuk TikTok Affiliate/BooStore (Fashion, OOTD, atau produk lifestyle) yang sangat engaging, santai, dan kekinian (Variasi gaya ke-{seed_val}). "
            "PENTING: Gunakan pilihan kata yang unik dan BERBEDA. "
            "Sertakan HANYA MAKSIMAL 5 hashtag yang sangat relevan, universal, atau berniche fashion/OOTD/racun tiktok. "
            "Jangan lebih dari 5 hashtag. Dalam Bahasa Indonesia."
        )
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return "OOTD andalan bikin penampilan makin keren! ✨ Cek keranjang kuning ya.\n\n#ootdindo #fashiontiktok #racuntiktok #fyp #inspirasifashion"

def generate_tiktok_affiliate_ideas(excluded_names=[]):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        exclude_str = ", ".join(excluded_names) if excluded_names else "tidak ada"
        prompt = (
            "Berikan tepat 10 ide produk spesifik yang sedang viral dan laris di TikTok Shop Affiliate Indonesia, khusus kategori Fashion, OOTD, Tas, Sepatu, Hijab, dan Lifestyle. "
            f"JANGAN tampilkan produk berikut karena sudah pernah dicari sebelumnya: [{exclude_str}]. "
            "Sertakan nama produk, kategori, tips sudut pandang konten (angle), format simulasi link TikTok Shop, serta URL gambar ilustrasi produk berformat publik (JPG/PNG). "
            "Format output HARUS berupa JSON array murni tanpa ada teks pengantar atau penutup di luar JSON, dengan struktur kunci persis: "
            "[{\"nama_produk\": \"...\", \"kategori\": \"...\", \"tips_konten\": \"...\", \"link_affiliate\": \"...\", \"image_url\": \"...\"}]"
        )
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        if text.startswith("```json"):
            text = text[7:-3].strip()
        elif text.startswith("```"):
            text = text[3:-3].strip()
            
        data = json.loads(text)
        if isinstance(data, list) and len(data) > 0:
            return data
        raise Exception("Format tidak valid")
    except Exception as e:
        # Bank cadangan produk kaya variasi agar selalu pas 10 produk dengan gambar ilustrasi valid
        fallback_pool = [
            {"nama_produk": "Lampu Meja LED Estetik", "kategori": "Room Decor", "tips_konten": "Soroti perubahan kamar dari gelap jadi estetik ala Pinterest", "link_affiliate": "https://shop.tiktok.com/view/product/lampuestetik", "image_url": "https://images.unsplash.com/photo-1507473885765-e6ed057f782c?w=500"},
            {"nama_produk": "Tas Selempang Kanvas Casual", "kategori": "Fashion / BooStore", "tips_konten": "Tunjukkan kapasitas tas yang muat banyak tapi tetap OOTD", "link_affiliate": "https://shop.tiktok.com/view/product/taskanvas", "image_url": "https://images.unsplash.com/photo-1544816155-12df9643f363?w=500"},
            {"nama_produk": "Kemeja Oversize Linen Wanita", "kategori": "Fashion / BooStore", "tips_konten": "Mix and match kemeja dengan celana Highwaist untuk nongkrong", "link_affiliate": "https://shop.tiktok.com/view/product/kemejalinen", "image_url": "https://images.unsplash.com/photo-1598554747436-c9293d6a588f?w=500"},
            {"nama_produk": "Culotte Pants Highwaist", "kategori": "Fashion / BooStore", "tips_konten": "Tunjukkan efek kaki jenjang saat memakai celana ini", "link_affiliate": "https://shop.tiktok.com/view/product/culottepants", "image_url": "https://images.unsplash.com/photo-1594633312681-425c7b97ccd1?w=500"},
            {"nama_produk": "Sepatu Sneakers Platform", "kategori": "Fashion / Shoes", "tips_konten": "Review kenyamanan buat jalan seharian dan menambah tinggi badan", "link_affiliate": "https://shop.tiktok.com/view/product/sneakersplatform", "image_url": "https://images.unsplash.com/photo-1595950653106-6c9ebd614d3a?w=500"},
            {"nama_produk": "Pashmina Kaftan Jersey Premium", "kategori": "Fashion / Hijab", "tips_konten": "Tutorial 3 gaya lilit pashmina anti ribet anti tembem", "link_affiliate": "https://shop.tiktok.com/view/product/pashminajersey", "image_url": "https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=500"},
            {"nama_produk": "Cardigan Knit Korean Style", "kategori": "Fashion / BooStore", "tips_konten": "Padukan dengan inner polos untuk look ala cewek kue/mamba", "link_affiliate": "https://shop.tiktok.com/view/product/cardiganknit", "image_url": "https://images.unsplash.com/photo-1434389677669-e08b4cac3105?w=500"},
            {"nama_produk": "Jam Tangan Kulit Minimalis", "kategori": "Accessories", "tips_konten": "Close up detail jam saat dipakai di pergelangan tangan", "link_affiliate": "https://shop.tiktok.com/view/product/jamtangankulit", "image_url": "https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?w=500"},
            {"nama_produk": "Topi Baseball Vintage Corduroy", "kategori": "Accessories", "tips_konten": "Cocok dipakai buat outfit sporty atau casual santai", "link_affiliate": "https://shop.tiktok.com/view/product/topibaseball", "image_url": "https://images.unsplash.com/photo-1588850561407-ed78c282e89b?w=500"},
            {"nama_produk": "Kacamata Hitam Retro Anti UV", "kategori": "Accessories", "tips_konten": "Review transisi look dari biasa aja jadi langsung keren", "link_affiliate": "https://shop.tiktok.com/view/product/kacamataretro", "image_url": "https://images.unsplash.com/photo-1511499767150-a48a237f0083?w=500"},
            {"nama_produk": "Slingbag Kulit Sintetis", "kategori": "Fashion / BooStore", "tips_konten": "Review kompartemen tas muat dompet dan HP", "link_affiliate": "https://shop.tiktok.com/view/product/slingbagkulit", "image_url": "https://images.unsplash.com/photo-1590874103328-eac38a683ce7?w=500"},
            {"nama_produk": "Blouse Rayon Crinkle", "kategori": "Fashion / BooStore", "tips_konten": "Bahan adem tidak mudah kusut buat kerja atau kuliah", "link_affiliate": "https://shop.tiktok.com/view/product/blousecrinkle", "image_url": "https://images.unsplash.com/photo-1576566588028-4147f3842f27?w=500"}
        ]
        # Filter yang belum pernah muncul
        filtered = [p for p in fallback_pool if p["nama_produk"] not in excluded_names]
        return filtered[:10] if len(filtered) >= 10 else fallback_pool[:10]

# --- PENENTU JADWAL UNIK TANPA BENTROK (2 VIDEO PER HARI) ---
def get_next_available_fyptime():
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    cursor.execute("SELECT scheduled_time FROM stok_siap")
    existing_slots = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    day_offset = 0
    while True:
        target_timestamp = datetime.now().timestamp() + (day_offset * 86400)
        formatted_date = datetime.fromtimestamp(target_timestamp).strftime('%Y-%m-%d')
        
        for slot in SCHEDULE_SLOTS:
            candidate = f"{formatted_date} ({slot})"
            if candidate not in existing_slots:
                return candidate
        day_offset += 1

async def process_incoming_video(bot_app, file_id):
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    smart_caption = generate_ai_caption()
    scheduled_slot = get_next_available_fyptime()

    try:
        cursor.execute('''
            INSERT INTO stok_siap (file_id, generated_caption, scheduled_time, status) 
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

# --- PANEL MENU UTAMA ---
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
        "Silakan pilih menu di bawah ini tanpa perlu mengetik:"
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
    markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(text, reply_markup=markup)
    else:
        await update.callback_query.message.edit_text(text, reply_markup=markup)

async def cmd_stok_siap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, file_id, generated_caption, scheduled_time FROM stok_siap WHERE status = "READY" ORDER BY scheduled_time ASC')
    rows = cursor.fetchall()
    total_siap = len(rows)
    conn.close()

    chat_id = update.effective_chat.id

    if not rows:
        text = "📭 Stok siap upload kosong. Silakan kirim video baru ke chat ini!"
        keyboard = [[InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu_home")]]
        markup = InlineKeyboardMarkup(keyboard)
        if update.message:
            await update.message.reply_text(text, reply_markup=markup)
        else:
            await update.callback_query.message.reply_text(text, reply_markup=markup)
        return

    await context.bot.send_message(chat_id=chat_id, text=f"🚀 **Daftar Seluruh Stok Siap Upload (Total: {total_siap}):**")

    for r in rows:
        stock_id, file_id, caption, jadwal = r[0], r[1], r[2], r[3]
        keyboard = [
            [
                InlineKeyboardButton("✅ Ambil", callback_data=f"take_{stock_id}"),
                InlineKeyboardButton("🔄 Pindah Reup", callback_data=f"reup_{stock_id}")
            ]
        ]
        msg_caption = f"📌 **ID: #{stock_id}** | 📅 **Jadwal:** `{jadwal}`\n\n📝 **Caption:**\n{caption}"
        await context.bot.send_video(
            chat_id=chat_id,
            video=file_id,
            caption=msg_caption,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def cmd_stok_reupload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, file_id, caption FROM stok_reupload')
    rows = cursor.fetchall()
    conn.close()

    chat_id = update.effective_chat.id
    if not rows:
        text = "🔄 Stok reupload kosong."
        keyboard = [[InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu_home")]]
        markup = InlineKeyboardMarkup(keyboard)
        if update.message:
            await update.message.reply_text(text, reply_markup=markup)
        else:
            await update.callback_query.message.reply_text(text, reply_markup=markup)
        return

    await context.bot.send_message(chat_id=chat_id, text="🔄 **Daftar Stok Reupload:**")
    for r in rows:
        reup_id, file_id, caption = r[0], r[1], r[2]
        keyboard = [[InlineKeyboardButton("🚀 Ambil Konten Ini", callback_data=f"getreup_{reup_id}")]]
        msg_caption = f"🔄 **ID Reupload: #{reup_id}**\n\n📝 **Caption:**\n{caption}"
        await context.bot.send_video(
            chat_id=chat_id,
            video=file_id,
            caption=msg_caption,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def cmd_riwayat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, file_id, caption, taken_at FROM riwayat_upload ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()

    chat_id = update.effective_chat.id
    if not rows:
        text = "📂 Belum ada riwayat konten."
        keyboard = [[InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu_home")]]
        markup = InlineKeyboardMarkup(keyboard)
        if update.message:
            await update.message.reply_text(text, reply_markup=markup)
        else:
            await update.callback_query.message.reply_text(text, reply_markup=markup)
        return

    await context.bot.send_message(chat_id=chat_id, text="📋 **Semua Riwayat Konten:**")
    for r in rows:
        hid, file_id, caption, waktu = r[0], r[1], r[2], r[3]
        keyboard = [[InlineKeyboardButton("🔄 Pindah ke Reupload", callback_data=f"movetoreup_{hid}")]]
        msg_caption = f"📋 **Riwayat ID: #{hid}** ({waktu})\n\n📝 **Caption:**\n{caption}"
        await context.bot.send_video(
            chat_id=chat_id,
            video=file_id,
            caption=msg_caption,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# --- PENCARIAN PRODUK TIKTOK AFFILIATE DENGAN GAMBAR & ANTI-DUPLIKAT ---
async def cmd_cari_produk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    # Ambil produk yang sudah pernah tersimpan di database agar tidak muncul lagi saat refresh
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    cursor.execute('SELECT nama_produk FROM produk_stok')
    existing_products = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    await context.bot.send_message(chat_id=chat_id, text="🔍 AI sedang meriset 10 produk tren baru kategori Fashion & OOTD...")
    
    products = generate_tiktok_affiliate_ideas(existing_products)
    
    await context.bot.send_message(chat_id=chat_id, text="🛍️ **Rekomendasi 10 Produk TikTok Affiliate (Lengkap dengan Ilustrasi):**")
    
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    
    for i, p in enumerate(products, 1):
        nama = p.get("nama_produk", "Produk Tren")
        kategori = p.get("kategori", "TikTok Shop")
        tips = p.get("tips_konten", "Buat konten kreatif.")
        link = p.get("link_affiliate", "https://shop.tiktok.com/...")
        img_url = p.get("image_url", "https://images.unsplash.com/photo-1544816155-12df9643f363?w=500")
        
        try:
            cursor.execute(
                'INSERT OR IGNORE INTO produk_stok (nama_produk, kategori, link_affiliate, tips_konten) VALUES (?, ?, ?, ?)',
                (nama, kategori, link, tips)
            )
            conn.commit()
            cursor.execute('SELECT id FROM produk_stok WHERE nama_produk = ?', (nama,))
            saved_id = cursor.fetchone()[0]
        except Exception:
            saved_id = 1
        
        text = (
            f"📦 **{i}. {nama}**\n"
            f"🏷️ Kategori: *{kategori}*\n"
            f"💡 Tips: {tips}\n\n"
            f"🔗 **Link:** `{link}`"
        )
        
        keyboard = [[InlineKeyboardButton("✅ Simpan ke Stok Produk Saya", callback_data=f"savedprod_{saved_id}")]]
        markup = InlineKeyboardMarkup(keyboard)
        
        try:
            # Mengirim foto produk beserta teks informasi dan tombol interaktif
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=img_url,
                caption=text,
                reply_markup=markup,
                parse_mode="Markdown"
            )
        except Exception:
            # Fallback jika URL gambar gagal dimuat oleh Telegram
            await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup, parse_mode="Markdown")

    conn.close()

    refresh_keyboard = [
        [InlineKeyboardButton("🔄 Cari 10 Produk Lainnya (Refresh Tanpa Duplikat)", callback_data="refresh_products")],
        [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_home")]
    ]
    await context.bot.send_message(chat_id=chat_id, text="Ingin eksplorasi produk TikTok lainnya?", reply_markup=InlineKeyboardMarkup(refresh_keyboard))

async def cmd_produk_stok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('video_warehouse.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, nama_produk, kategori, link_affiliate, tips_konten FROM produk_stok')
    rows = cursor.fetchall()
    conn.close()

    chat_id = update.effective_chat.id
    if not rows:
        text = "📦 Stok produk affiliate Anda masih kosong.\nGunakan menu *Cari Produk Affiliate*."
        keyboard = [[InlineKeyboardButton("🔙 Kembali ke 
