# === IMPORT & KONFIGURASI ===
import os, json, pytz, asyncio, logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.types import InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image, ImageDraw, ImageFont

TOKEN = "7499685841:AAGMWsU0hLs82OLX9eKubnvP8f7ghRN45UU"
CHANNEL_ID = "@Prediksi_omtogel"
ADMIN_IDS = [6918801560, 5397964203, 6670157806, 5780186213, 7230912053]
TEMPLATE_DIR = "template"
FONT_PATH = "assets/fonts/arialbd.ttf"
FONT_BOLD = "assets/fonts/arialbd.ttf"
JADWAL_FILE = "jadwal.json"
NAIK_FILE = "naik.json"

bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)
pending_confirm = {}

# === SHIO ===
SHIO_FIX = {
    "01":"🐎 KUDA","13":"🐎 KUDA","25":"🐎 KUDA","37":"🐎 KUDA","49":"🐎 KUDA","61":"🐎 KUDA","73":"🐎 KUDA","85":"🐎 KUDA","97":"🐎 KUDA",
    "02":"🐍 ULAR","14":"🐍 ULAR","26":"🐍 ULAR","38":"🐍 ULAR","50":"🐍 ULAR","62":"🐍 ULAR","74":"🐍 ULAR","86":"🐍 ULAR","98":"🐍 ULAR",
    "03":"🐉 NAGA","15":"🐉 NAGA","27":"🐉 NAGA","39":"🐉 NAGA","51":"🐉 NAGA","63":"🐉 NAGA","75":"🐉 NAGA","87":"🐉 NAGA","99":"🐉 NAGA",
    "04":"🐇 KELINCI","16":"🐇 KELINCI","28":"🐇 KELINCI","40":"🐇 KELINCI","52":"🐇 KELINCI","64":"🐇 KELINCI","76":"🐇 KELINCI","88":"🐇 KELINCI","00":"🐇 KELINCI",
    "05":"🐅 HARIMAU","17":"🐅 HARIMAU","29":"🐅 HARIMAU","41":"🐅 HARIMAU","53":"🐅 HARIMAU","65":"🐅 HARIMAU","77":"🐅 HARIMAU","89":"🐅 HARIMAU",
    "06":"🐂 KERBAU","18":"🐂 KERBAU","30":"🐂 KERBAU","42":"🐂 KERBAU","54":"🐂 KERBAU","66":"🐂 KERBAU","78":"🐂 KERBAU","90":"🐂 KERBAU",
    "07":"🐀 TIKUS","19":"🐀 TIKUS","31":"🐀 TIKUS","43":"🐀 TIKUS","55":"🐀 TIKUS","67":"🐀 TIKUS","79":"🐀 TIKUS","91":"🐀 TIKUS",
    "08":"🐖 BABI","20":"🐖 BABI","32":"🐖 BABI","44":"🐖 BABI","56":"🐖 BABI","68":"🐖 BABI","80":"🐖 BABI","92":"🐖 BABI",
    "09":"🐕 ANJING","21":"🐕 ANJING","33":"🐕 ANJING","45":"🐕 ANJING","57":"🐕 ANJING","69":"🐕 ANJING","81":"🐕 ANJING","93":"🐕 ANJING",
    "10":"🐓 AYAM","22":"🐓 AYAM","34":"🐓 AYAM","46":"🐓 AYAM","58":"🐓 AYAM","70":"🐓 AYAM","82":"🐓 AYAM","94":"🐓 AYAM",
    "11":"🐒 MONYET","23":"🐒 MONYET","35":"🐒 MONYET","47":"🐒 MONYET","59":"🐒 MONYET","71":"🐒 MONYET","83":"🐒 MONYET","95":"🐒 MONYET",
    "12":"🐐 KAMBING","24":"🐐 KAMBING","36":"🐐 KAMBING","48":"🐐 KAMBING","60":"🐐 KAMBING","72":"🐐 KAMBING","84":"🐐 KAMBING","96":"🐐 KAMBING"
}
def get_shio_by_last2d(angka):
    dua_digit = str(angka)[-2:].zfill(2)
    return SHIO_FIX.get(dua_digit, "❓ Tidak Diketahui")

def is_admin(user_id): return user_id in ADMIN_IDS
def load_naik(): return json.load(open(NAIK_FILE, encoding="utf-8")) if os.path.exists(NAIK_FILE) else []
def save_naik(data): json.dump(data, open(NAIK_FILE, "w", encoding="utf-8"))

def cleanup_expired_confirm():
    now = datetime.now(pytz.timezone("Asia/Jakarta"))
    expired = [k for k, v in pending_confirm.items() if now - v.get("timestamp", now) > timedelta(hours=2)]
    for k in expired:
        pending_confirm.pop(k, None)

# === [FIX] Helper center + letter spacing untuk angka result ===
def draw_centered_text(draw, text, font, y, fill="white", stroke_width=2, stroke_fill="white", letter_spacing=12):
    """
    Menggambar teks dengan posisi X di tengah canvas (horizontal centered),
    dan memberi jarak antar karakter (letter_spacing).
    """
    # Hitung total lebar: jumlahkan lebar tiap karakter + spasi antar karakter
    widths = []
    for ch in text:
        bbox = draw.textbbox((0, 0), ch, font=font, stroke_width=stroke_width)
        widths.append(bbox[2] - bbox[0])
    total_width = sum(widths) + max(0, (len(text) - 1) * letter_spacing)

    canvas_width = draw.im.size[0]
    x = (canvas_width - total_width) / 2

    # Gambar per karakter dengan jarak
    for i, ch in enumerate(text):
        draw.text((x, y), ch, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)
        x += widths[i] + (letter_spacing if i < len(text) - 1 else 0)

# === COMMAND ===
@dp.message_handler(commands=["listpasaran"])
async def list_pasaran(msg: types.Message):
    if not is_admin(msg.from_user.id): return
    with open(JADWAL_FILE) as f: jadwal = json.load(f)
    daftar = "\n".join([f"🔹 <b>{k.upper()}</b> - {v}" for k, v in jadwal.items()])
    await msg.reply(f"<b>DAFTAR PASARAN</b>\n\n{daftar}")

@dp.message_handler(commands=["naiklist"])
async def list_naik(msg: types.Message):
    if not is_admin(msg.from_user.id): return
    naik = load_naik()
    teks = "\n".join([f"✅ {p.upper()}" for p in naik]) if naik else "Belum ada pasaran yang dinaikkan hari ini."
    await msg.reply(f"<b>SUDAH NAIK HARI INI:</b>\n\n{teks}")

@dp.message_handler(commands=["result"])
async def result_handler(msg: types.Message):
    if not is_admin(msg.from_user.id): return
    try:
        _, pasaran, angka = msg.text.strip().split()
        pending_confirm[msg.from_user.id] = {"pasaran": pasaran, "angka": angka, "timestamp": datetime.now(pytz.timezone("Asia/Jakarta"))}
        await preview_result(msg.chat.id, pasaran, angka)
    except Exception as e:
        await msg.reply(f"❌ Format salah. Contoh: /result singapore 9384\n\nError: {e}")

@dp.message_handler(lambda m: m.reply_to_message and "waktunya result" in m.reply_to_message.text.lower())
async def admin_balasan_result(msg: types.Message):
    if not is_admin(msg.from_user.id): return
    try:
        angka = msg.text.strip()
        pasaran = msg.reply_to_message.text.split("Pasaran")[1].split("waktunya")[0].strip().lower()
        pending_confirm[msg.from_user.id] = {"pasaran": pasaran, "angka": angka, "timestamp": datetime.now(pytz.timezone("Asia/Jakarta"))}
        await preview_result(msg.chat.id, pasaran, angka)
    except Exception as e:
        await msg.reply(f"Error konfirmasi: {e}")

@dp.message_handler(lambda msg: is_admin(msg.from_user.id) and msg.from_user.id in pending_confirm)
async def handle_revisi_angka(msg: types.Message):
    cleanup_expired_confirm()
    if msg.from_user.id not in pending_confirm:
        return await msg.reply("❌ Data konfirmasi kadaluarsa. Kirim ulang result.")
    angka_baru = msg.text.strip()
    user_id = msg.from_user.id
    pending_confirm[user_id]["angka"] = angka_baru
    await preview_result(msg.chat.id, pending_confirm[user_id]["pasaran"], angka_baru)

@dp.callback_query_handler(lambda c: c.data in ["kirim_channel", "revisi_angka"])
async def konfirmasi_callback(callback: types.CallbackQuery):
    cleanup_expired_confirm()
    user_id = callback.from_user.id
    if not is_admin(user_id): return
    await callback.answer()
    data = pending_confirm.get(user_id)
    if not data:
        await bot.send_message(user_id, "❌ Tidak ada data yang bisa dikonfirmasi.")
        return
    pasaran, angka = data["pasaran"], data["angka"]
    if callback.data == "revisi_angka":
        await bot.send_message(user_id, "🔁 Silakan kirim ulang angkanya.")
    elif callback.data == "kirim_channel":
        await proses_kirim_result(pasaran, angka)
        naik = load_naik()
        if pasaran not in naik:
            naik.append(pasaran)
            save_naik(naik)
        pending_confirm.pop(user_id, None)
        await bot.send_message(user_id, f"✅ Result <b>{pasaran.upper()}</b> dikirim ke channel.")

# === PREVIEW & KIRIM ===
async def preview_result(chat_id, pasaran, angka):
    template_file = f"{TEMPLATE_DIR}/{pasaran}.jpg"
    if not os.path.exists(template_file):
        await bot.send_message(chat_id, "❌ Template tidak ditemukan.")
        return
    img = Image.open(template_file)
    draw = ImageDraw.Draw(img)

    font_result = ImageFont.truetype(FONT_PATH, 195)
    font_tgl = ImageFont.truetype(FONT_BOLD, 27)
    tgl_text = datetime.now(pytz.timezone("Asia/Jakarta")).strftime('%d %B %Y').upper()

    # === [FIX] Center + jarak antar karakter (letter_spacing=12), Y tetap 358
    draw_centered_text(draw, angka.upper(), font_result, y=358, fill="white", stroke_width=2, stroke_fill="white", letter_spacing=12)

    # Tanggal tetap pakai posisi lama (tidak diubah)
    draw.text((453, 305), tgl_text, font=font_tgl, fill="black", stroke_width=2, stroke_fill="white")

    preview_path = f"preview_{pasaran}.jpg"
    img.convert("RGB").save(preview_path)

    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📈 Naikkan Pasaran", callback_data="kirim_channel"),
        InlineKeyboardButton("✏️ Revisi Angka", callback_data="revisi_angka")
    )
    await bot.send_photo(
        chat_id,
        photo=InputFile(preview_path),
        caption=f"📅 Konfirmasi Result\n\n<b>Pasaran:</b> {pasaran.upper()}\n<b>Angka:</b> <code>{angka.upper()}</code>",
        reply_markup=keyboard
    )
    os.remove(preview_path)

async def proses_kirim_result(pasaran, angka):
    img_path = f"{TEMPLATE_DIR}/{pasaran}.jpg"
    if not os.path.exists(img_path): return
    img = Image.open(img_path)
    draw = ImageDraw.Draw(img)

    font_result = ImageFont.truetype(FONT_PATH, 195)
    font_tgl = ImageFont.truetype(FONT_BOLD, 27)
    tgl_text = datetime.now(pytz.timezone("Asia/Jakarta")).strftime('%d %B %Y').upper()

    # === [FIX] Center + jarak antar karakter (letter_spacing=12), Y tetap 358
    draw_centered_text(draw, angka.upper(), font_result, y=358, fill="white", stroke_width=2, stroke_fill="white", letter_spacing=12)

    # Tanggal tetap pakai posisi lama (tidak diubah)
    draw.text((453, 305), tgl_text, font=font_tgl, fill="black", stroke_width=2, stroke_fill="white")

    result_path = f"result_{pasaran}.jpg"
    img.convert("RGB").save(result_path)

    shio = get_shio_by_last2d(angka)
    caption = f"""
🎉 <b>HASIL RESMI {pasaran.upper()}</b> 🎉

📅 <b>TANGGAL :</b> <b>{datetime.now(pytz.timezone("Asia/Jakarta")).strftime('%d-%m-%Y')}</b>

🏆 <b>PRIZE 1 :</b> 🔥 <b>{angka.upper()}</b> 🔥

🐲 <b>SHIO :</b> <b>{shio}</b>

✨ <b>Selamat kepada para pemenang!</b>  
<b>Semoga makin hoki dan JP terus boskuu 🙏</b>

━━━━━━━━━━━━━━━
💎 <b>HADIAH & DISKON TERBAIK</b> 💎
🎯 <b>4D × 10,000</b>
🎯 <b>3D × 1,000</b>
🎯 <b>2D × 100</b>
━━━━━━━━━━━━━━━
"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("🔐 LOGIN OMTOGEL SEKARANG", url="https://omtogelbonanza.xyz/"),
        InlineKeyboardButton("💬 CHAT ADMIN OMTOGEL", url="https://t.me/CSOMTOGEL2"),
        InlineKeyboardButton("🏆 ROOM LOMBA TEBAK ANGKA 2D", url="https://t.me/LOMBA2D_OMTOGEL")
    )

    # === [FIX AUTO PIN] kirim & pin pesan di channel/grup ===
    sent = await bot.send_photo(CHANNEL_ID, InputFile(result_path), caption=caption, reply_markup=keyboard)
    try:
        await bot.pin_chat_message(CHANNEL_ID, sent.message_id, disable_notification=True)
    except Exception as e:
        print("[PIN ERROR]", e)

    os.remove(result_path)

# === NOTIFIKASI OTOMATIS ===
async def notifikasi_jelang_result():
    while True:
        try:
            jadwal = json.load(open(JADWAL_FILE))
            now = datetime.now(pytz.timezone("Asia/Jakarta"))
            if now.hour == 0 and now.minute < 2:
                save_naik([])
            for pasaran, jam in jadwal.items():
                try:
                    jam_obj = pytz.timezone("Asia/Jakarta").localize(
                        datetime.strptime(jam, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
                    )
                except:
                    continue
                selisih = jam_obj - now
                if timedelta(minutes=-1) < selisih <= timedelta(minutes=1):
                    for admin_id in ADMIN_IDS:
                        await bot.send_message(
                            admin_id,
                            f"⏰ Pasaran <b>{pasaran.upper()}</b> waktunya result sekarang!\nBalas dengan angka.",
                            parse_mode="HTML"
                        )
        except Exception as e:
            print("[!] Error notifikasi:", e)
        await asyncio.sleep(60)

# === START ===
if __name__ == "__main__":
    import sys
    from aiogram import executor

    async def on_startup(dispatcher):
        asyncio.create_task(notifikasi_jelang_result())
        print("✅ BOT AKTIF! Jangan dijalankan dobel ya bre 🚫")

    try:
        executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
    except Exception as e:
        print(f"❌ BOT GAGAL JALAN: {e}")
        sys.exit()
