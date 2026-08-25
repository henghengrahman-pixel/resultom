import asyncio
import hashlib
import hmac
import html
import json
import logging
import os
import re
import secrets
import shutil
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pytz
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.types import InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image, ImageDraw, ImageFont

from default_config import DEFAULT_CONFIG
from market_sources import (
    ResultRow,
    discover_market_codes,
    fetch_results,
    normalize_market_name,
    result_url,
    source_base,
)
from storage import load_json, save_json

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "template"
FONT_PATH = BASE_DIR / "assets" / "fonts" / "arialbd.ttf"
FONT_BOLD = FONT_PATH
JADWAL_FILE = BASE_DIR / "jadwal.json"

# Railway: set DATA_DIR=/data jika memakai Volume. Kalau /data tersedia, otomatis dipakai.
DEFAULT_DATA_DIR = "/data" if os.path.isdir("/data") and os.access("/data", os.W_OK) else str(BASE_DIR / "data")
DATA_DIR = Path(os.getenv("DATA_DIR", DEFAULT_DATA_DIR))
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = DATA_DIR / "config.json"
STATE_FILE = DATA_DIR / "auto_state.json"
LOG_FILE = DATA_DIR / "result_log.json"
NAIK_FILE = DATA_DIR / "naik.json"
FB_QUEUE_FILE = DATA_DIR / "facebook_queue.json"
FB_IMAGE_DIR = DATA_DIR / "facebook_images"
FB_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not TOKEN:
    raise RuntimeError("BOT_TOKEN belum diisi di Railway Variables")

DEFAULT_CHANNEL_ID = os.getenv("CHANNEL_ID", DEFAULT_CONFIG["channel_id"]).strip()
ADMIN_IDS = [
    int(x.strip()) for x in os.getenv(
        "ADMIN_IDS",
        "6918801560,5397964203,6670157806,5780186213,7230912053,8851258385",
    ).split(",") if x.strip().isdigit()
]
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "8008")
COOKIE_SECRET = os.getenv("SESSION_SECRET", DASHBOARD_PASSWORD + "-resultom-v2")
PORT = int(os.getenv("PORT", "8080"))
WIB = pytz.timezone("Asia/Jakarta")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("resultom")

bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)
pending_confirm: Dict[int, dict] = {}
auto_lock = asyncio.Lock()

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
    "12":"🐐 KAMBING","24":"🐐 KAMBING","36":"🐐 KAMBING","48":"🐐 KAMBING","60":"🐐 KAMBING","72":"🐐 KAMBING","84":"🐐 KAMBING","96":"🐐 KAMBING",
}


def get_shio_by_last2d(angka):
    return SHIO_FIX.get(str(angka)[-2:].zfill(2), "❓ Tidak Diketahui")


def is_admin(user_id):
    return user_id in ADMIN_IDS


def load_config():
    cfg = load_json(str(CONFIG_FILE), DEFAULT_CONFIG)
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    merged.update({k: v for k, v in cfg.items() if k not in ("market_codes", "market_enabled")})
    merged["market_codes"].update(cfg.get("market_codes", {}))
    merged["market_enabled"].update(cfg.get("market_enabled", {}))
    if not merged.get("channel_id"):
        merged["channel_id"] = DEFAULT_CHANNEL_ID
    return merged


def save_config(cfg):
    save_json(str(CONFIG_FILE), cfg)


def facebook_caption(caption: str) -> str:
    """Ubah caption HTML Telegram menjadi teks biasa untuk Facebook."""
    plain = re.sub(r"<[^>]+>", "", caption)
    return html.unescape(plain).strip()


def valid_facebook_group_url(value: str) -> str:
    value = str(value or "").strip().rstrip("/")
    if not re.match(r"^https://(www\.|web\.|m\.)?facebook\.com/groups/[^/?#]+", value, flags=re.I):
        raise ValueError("URL Grup Facebook tidak valid")
    return value


def load_fb_queue() -> list:
    return load_json(str(FB_QUEUE_FILE), [])


def save_fb_queue(items: list):
    save_json(str(FB_QUEUE_FILE), items[-500:])


def enqueue_facebook_job(cfg: dict, image_path: Path, caption: str, pasaran: str, angka: str) -> dict:
    if not cfg.get("facebook_enabled", False):
        return {"enabled": False, "queued": False, "message": "Facebook OFF"}
    group_url = valid_facebook_group_url(cfg.get("facebook_group_url", ""))
    job_id = uuid.uuid4().hex
    stored_image = FB_IMAGE_DIR / f"{job_id}.jpg"
    shutil.copyfile(image_path, stored_image)
    items = load_fb_queue()
    items.append({
        "id": job_id, "status": "pending", "group_url": group_url,
        "caption": facebook_caption(caption), "image_file": stored_image.name,
        "market": pasaran, "number": angka, "attempts": 0,
        "created_at": datetime.now(WIB).isoformat(), "updated_at": datetime.now(WIB).isoformat(),
        "error": None,
    })
    save_fb_queue(items)
    return {"enabled": True, "queued": True, "job_id": job_id}


def load_state():
    return load_json(str(STATE_FILE), {"sources": {}, "last_scan": None, "last_error": None})


def save_state(state):
    save_json(str(STATE_FILE), state)


def append_log(entry):
    data = load_json(str(LOG_FILE), [])
    data.append(entry)
    if len(data) > 500:
        data = data[-500:]
    save_json(str(LOG_FILE), data)


def load_naik():
    return load_json(str(NAIK_FILE), [])


def save_naik(data):
    save_json(str(NAIK_FILE), data)


def load_jadwal():
    return load_json(str(JADWAL_FILE), {})


def cleanup_expired_confirm():
    now = datetime.now(WIB)
    for k in [k for k, v in pending_confirm.items() if now - v.get("timestamp", now) > timedelta(hours=2)]:
        pending_confirm.pop(k, None)


def template_for_market(pasaran: str) -> Optional[Path]:
    target = re.sub(r"[^a-z0-9]", "", pasaran.lower())
    for p in TEMPLATE_DIR.iterdir():
        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png"):
            stem = re.sub(r"[^a-z0-9]", "", p.stem.lower())
            if stem == target:
                return p
    return None


def draw_centered_text(draw, text, font, y, fill="white", stroke_width=2, stroke_fill="white", letter_spacing=12):
    widths = []
    for ch in text:
        bbox = draw.textbbox((0, 0), ch, font=font, stroke_width=stroke_width)
        widths.append(bbox[2] - bbox[0])
    total_width = sum(widths) + max(0, (len(text) - 1) * letter_spacing)
    canvas_width = draw.im.size[0]
    x = (canvas_width - total_width) / 2
    for i, ch in enumerate(text):
        draw.text((x, y), ch, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)
        x += widths[i] + (letter_spacing if i < len(text) - 1 else 0)


def safe_result_number(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if not 2 <= len(digits) <= 6:
        raise ValueError("Angka result harus 2 sampai 6 digit")
    return digits


def image_date(row: Optional[ResultRow]) -> datetime:
    return row.parsed_at if row and row.parsed_at else datetime.now(WIB)


def make_result_image(pasaran: str, angka: str, row: Optional[ResultRow] = None, prefix="result") -> Path:
    template = template_for_market(pasaran)
    if not template:
        raise FileNotFoundError(f"Template untuk {pasaran} tidak ditemukan")
    angka = safe_result_number(angka)
    img = Image.open(template).convert("RGB")
    draw = ImageDraw.Draw(img)
    font_result = ImageFont.truetype(str(FONT_PATH), 195)
    font_tgl = ImageFont.truetype(str(FONT_BOLD), 27)
    dt = image_date(row)
    tgl_text = dt.strftime("%d %B %Y").upper()
    draw_centered_text(draw, angka, font_result, y=358, fill="white", stroke_width=2, stroke_fill="white", letter_spacing=12)
    draw.text((453, 305), tgl_text, font=font_tgl, fill="black", stroke_width=2, stroke_fill="white")
    out = DATA_DIR / f"{prefix}_{re.sub(r'[^a-z0-9_-]', '_', pasaran.lower())}_{os.getpid()}.jpg"
    img.save(out, "JPEG", quality=95)
    return out


async def send_result(pasaran: str, angka: str, row: Optional[ResultRow] = None, channel_id: Optional[str] = None):
    cfg = load_config()
    target = channel_id or cfg.get("channel_id") or DEFAULT_CHANNEL_ID
    result_path = make_result_image(pasaran, angka, row=row, prefix="result")
    dt = image_date(row)
    shio = get_shio_by_last2d(angka)
    period_line = f"\n🔢 <b>PERIODE :</b> <b>{html.escape(row.period)}</b>" if row else ""
    caption = f"""🎉 <b>HASIL RESMI {pasaran.upper()}</b> 🎉

📅 <b>TANGGAL :</b> <b>{dt.strftime('%d-%m-%Y')}</b>{period_line}

🏆 <b>PRIZE 1 :</b> 🔥 <b>{angka}</b> 🔥

🐲 <b>SHIO :</b> <b>{get_shio_by_last2d(angka)}</b>

✨ <b>Selamat kepada para pemenang!</b>
<b>Semoga makin hoki dan JP terus boskuu 🙏</b>

━━━━━━━━━━━━━━━
💎 <b>HADIAH & DISKON TERBAIK</b> 💎
🎯 <b>4D × 10,000</b>
🎯 <b>3D × 1,000</b>
🎯 <b>2D × 100</b>
━━━━━━━━━━━━━━━"""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("🔐 LOGIN OMTOGEL SEKARANG", url=os.getenv("LOGIN_URL", "https://omtogelsky.com/")),
        InlineKeyboardButton("💬 CHAT ADMIN OMTOGEL", url=os.getenv("CS_URL", "https://t.me/CSOMTOGEL2")),
        InlineKeyboardButton("💬 WHATSAPP OMTOGEL", url=os.getenv("LOMBA_URL", "https://layanancsomtogel.live/")),
    )
    report = {"telegram": {"ok": False}, "facebook": {"enabled": bool(cfg.get("facebook_enabled")), "queued": False}}
    try:
        sent = await bot.send_photo(target, InputFile(str(result_path)), caption=caption, reply_markup=keyboard)
        report["telegram"] = {"ok": True, "message_id": sent.message_id}
        if cfg.get("pin_result", True):
            try:
                await bot.pin_chat_message(target, sent.message_id, disable_notification=True)
            except Exception as e:
                log.warning("Pin gagal: %s", e)
        try:
            report["facebook"] = enqueue_facebook_job(cfg, result_path, caption, pasaran, angka)
        except Exception as e:
            # Telegram sudah sukses. Jangan raise agar scanner tidak mengirim ulang Telegram.
            report["facebook"] = {"enabled": True, "queued": False, "error": str(e)}
            log.error("Antrean Facebook gagal untuk %s: %s", pasaran, e)
        return report
    finally:
        try:
            result_path.unlink(missing_ok=True)
        except Exception:
            pass


async def preview_result(chat_id, pasaran, angka):
    try:
        angka = safe_result_number(angka)
        preview_path = make_result_image(pasaran, angka, prefix="preview")
    except Exception as e:
        await bot.send_message(chat_id, f"❌ {html.escape(str(e))}")
        return
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📈 Naikkan Pasaran", callback_data="kirim_channel"),
        InlineKeyboardButton("✏️ Revisi Angka", callback_data="revisi_angka"),
    )
    try:
        await bot.send_photo(
            chat_id,
            photo=InputFile(str(preview_path)),
            caption=f"📅 Konfirmasi Result\n\n<b>Pasaran:</b> {pasaran.upper()}\n<b>Angka:</b> <code>{angka}</code>",
            reply_markup=keyboard,
        )
    finally:
        preview_path.unlink(missing_ok=True)


def _time_distance_minutes(a: datetime, hhmm: str) -> int:
    try:
        hh, mm = [int(x) for x in hhmm.split(":", 1)]
    except Exception:
        return 999999
    target = a.replace(hour=hh, minute=mm, second=0, microsecond=0)
    diffs = [abs((a - target).total_seconds()), abs((a - (target - timedelta(days=1))).total_seconds()), abs((a - (target + timedelta(days=1))).total_seconds())]
    return int(min(diffs) // 60)


def choose_market_for_row(markets: List[str], row: ResultRow) -> str:
    if len(markets) == 1:
        return markets[0]
    jadwal = load_jadwal()
    dt = row.parsed_at or datetime.now(WIB)
    ranked = sorted(markets, key=lambda m: _time_distance_minutes(dt, jadwal.get(m, jadwal.get(m.capitalize(), ""))))
    return ranked[0]


def new_rows_from_state(rows: List[ResultRow], source_state: Optional[dict]) -> List[ResultRow]:
    if not rows:
        return []
    if not source_state or not source_state.get("key"):
        return []
    old_key = source_state.get("key")
    for idx, row in enumerate(rows):
        if row.key == old_key:
            # Situs menampilkan result terbaru di baris paling atas.
            return list(reversed(rows[:idx]))
    # State sudah terlalu lama/tidak ada di window. Kirim latest saja agar tidak banjir.
    if rows[0].key != old_key:
        return [rows[0]]
    return []


async def scan_auto_results(force: bool = False):
    if auto_lock.locked() and not force:
        return {"ok": False, "message": "scan masih berjalan"}
    async with auto_lock:
        cfg = load_config()
        if not cfg.get("auto_enabled", True) and not force:
            return {"ok": True, "message": "AUTO OFF"}

        state = load_state()
        source_states = state.setdefault("sources", {})
        enabled = cfg.get("market_enabled", {})
        market_codes = cfg.get("market_codes", {})
        groups: Dict[str, List[str]] = {}
        for market, code in market_codes.items():
            if enabled.get(market, True) and code:
                groups.setdefault(str(code).strip(), []).append(market)

        sent_count = 0
        errors = []
        for code, markets in groups.items():
            try:
                rows = await fetch_results(
                    cfg["source_url"],
                    cfg.get("result_path_template", "/history/result/{code}/kosong"),
                    code,
                    int(cfg.get("request_timeout_seconds", 15)),
                )
                latest = rows[0]
                previous = source_states.get(code)
                if not previous:
                    source_states[code] = {
                        "key": latest.key,
                        "period": latest.period,
                        "date_text": latest.date_text,
                        "number": latest.number,
                        "seen_at": datetime.now(WIB).isoformat(),
                        "recent_sent": [],
                    }
                    if cfg.get("send_on_first_sync", False):
                        target = choose_market_for_row(markets, latest)
                        await send_result(target, latest.number, row=latest)
                        sent_count += 1
                        source_states[code]["recent_sent"] = [latest.key]
                        save_state(state)
                        append_log({"at": datetime.now(WIB).isoformat(), "mode": "auto-first", "market": target, "code": code, **latest.to_dict()})
                    continue

                sent_keys = list(previous.get("recent_sent", []))[-30:]
                pending = new_rows_from_state(rows, previous)
                for row in pending:
                    if row.key in sent_keys:
                        continue
                    target = choose_market_for_row(markets, row)
                    await send_result(target, row.number, row=row)
                    sent_count += 1
                    sent_keys.append(row.key)
                    sent_keys = sent_keys[-30:]
                    # Simpan sent key langsung setelah Telegram sukses untuk mencegah duplicate
                    # jika proses berikutnya gagal di tengah batch.
                    previous["recent_sent"] = sent_keys
                    source_states[code] = previous
                    save_state(state)
                    append_log({"at": datetime.now(WIB).isoformat(), "mode": "auto", "market": target, "code": code, **row.to_dict()})

                # selalu maju ke latest setelah semua pending berhasil diproses
                source_states[code] = {
                    "key": latest.key,
                    "period": latest.period,
                    "date_text": latest.date_text,
                    "number": latest.number,
                    "seen_at": datetime.now(WIB).isoformat(),
                    "recent_sent": sent_keys[-30:],
                }
            except Exception as e:
                msg = f"{code} ({', '.join(markets)}): {e}"
                errors.append(msg)
                log.warning("Auto scan error %s", msg)

        state["last_scan"] = datetime.now(WIB).isoformat()
        state["last_error"] = "\n".join(errors[:10]) if errors else None
        save_state(state)
        return {"ok": not errors, "sent": sent_count, "errors": errors}


async def auto_result_loop():
    await asyncio.sleep(4)
    while True:
        try:
            cfg = load_config()
            await scan_auto_results()
            delay = max(5, min(300, int(cfg.get("poll_seconds", 15))))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("Loop auto result error: %s", e)
            delay = 15
        await asyncio.sleep(delay)


async def notifikasi_jelang_result():
    last_notice = {}
    while True:
        try:
            jadwal = load_jadwal()
            now = datetime.now(WIB)
            if now.hour == 0 and now.minute < 2:
                save_naik([])
            for pasaran, jam in jadwal.items():
                try:
                    naive = datetime.strptime(jam, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
                    jam_obj = WIB.localize(naive)
                except Exception:
                    continue
                selisih = jam_obj - now
                key = f"{now.date()}|{pasaran}|{jam}"
                if timedelta(minutes=-1) < selisih <= timedelta(minutes=1) and last_notice.get(key) != now.minute:
                    last_notice[key] = now.minute
                    for admin_id in ADMIN_IDS:
                        try:
                            await bot.send_message(admin_id, f"⏰ Pasaran <b>{pasaran.upper()}</b> waktunya result sekarang!\nAUTO akan cek web. Jika perlu manual, balas dengan angka.")
                        except Exception:
                            pass
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("Error notifikasi: %s", e)
        await asyncio.sleep(30)


@dp.message_handler(commands=["listpasaran"])
async def list_pasaran(msg: types.Message):
    if not is_admin(msg.from_user.id): return
    jadwal = load_jadwal()
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
        _, pasaran, angka = msg.text.strip().split(maxsplit=2)
        angka = safe_result_number(angka)
        pending_confirm[msg.from_user.id] = {"pasaran": pasaran.lower(), "angka": angka, "timestamp": datetime.now(WIB)}
        await preview_result(msg.chat.id, pasaran.lower(), angka)
    except Exception as e:
        await msg.reply(f"❌ Format salah. Contoh: /result srilanka 9384\n\n{html.escape(str(e))}")


@dp.message_handler(commands=["autostatus"])
async def auto_status(msg: types.Message):
    if not is_admin(msg.from_user.id): return
    cfg, state = load_config(), load_state()
    await msg.reply(
        f"🤖 <b>AUTO RESULT</b>\n"
        f"Status: <b>{'ON' if cfg.get('auto_enabled') else 'OFF'}</b>\n"
        f"URL: <code>{html.escape(cfg.get('source_url',''))}</code>\n"
        f"Interval: <b>{cfg.get('poll_seconds')} detik</b>\n"
        f"Last scan: <code>{html.escape(str(state.get('last_scan') or '-'))}</code>\n"
        f"Last error: <code>{html.escape(str(state.get('last_error') or '-'))}</code>"
    )


@dp.message_handler(commands=["autoon", "autooff"])
async def auto_toggle(msg: types.Message):
    if not is_admin(msg.from_user.id): return
    cfg = load_config()
    cfg["auto_enabled"] = msg.get_command().lower().endswith("autoon")
    save_config(cfg)
    await msg.reply(f"✅ AUTO RESULT {'ON' if cfg['auto_enabled'] else 'OFF'}")


@dp.message_handler(commands=["setsource"])
async def set_source(msg: types.Message):
    if not is_admin(msg.from_user.id): return
    try:
        url = msg.get_args().strip()
        source_base(url)
        cfg = load_config()
        cfg["source_url"] = url
        save_config(cfg)
        await msg.reply(f"✅ URL sumber diganti:\n<code>{html.escape(url)}</code>\nPerubahan langsung dipakai tanpa redeploy.")
    except Exception as e:
        await msg.reply(f"❌ {html.escape(str(e))}")


@dp.message_handler(commands=["setinterval"])
async def set_interval(msg: types.Message):
    if not is_admin(msg.from_user.id): return
    try:
        sec = int(msg.get_args().strip())
        if sec < 5 or sec > 300:
            raise ValueError("Interval harus 5-300 detik")
        cfg = load_config(); cfg["poll_seconds"] = sec; save_config(cfg)
        await msg.reply(f"✅ Interval cek menjadi {sec} detik.")
    except Exception as e:
        await msg.reply(f"❌ {html.escape(str(e))}")


@dp.message_handler(commands=["checknow"])
async def check_now(msg: types.Message):
    if not is_admin(msg.from_user.id): return
    await msg.reply("🔎 Scan sumber sekarang...")
    res = await scan_auto_results(force=True)
    errs = "\n".join(res.get("errors", [])[:5])
    await msg.reply(f"✅ Scan selesai. Terkirim: <b>{res.get('sent',0)}</b>" + (f"\n⚠️ {html.escape(errs)}" if errs else ""))


@dp.message_handler(lambda m: m.reply_to_message and m.reply_to_message.text and "waktunya result" in m.reply_to_message.text.lower())
async def admin_balasan_result(msg: types.Message):
    if not is_admin(msg.from_user.id): return
    try:
        angka = safe_result_number(msg.text.strip())
        pasaran = msg.reply_to_message.text.split("Pasaran", 1)[1].split("waktunya", 1)[0].strip().lower()
        pending_confirm[msg.from_user.id] = {"pasaran": pasaran, "angka": angka, "timestamp": datetime.now(WIB)}
        await preview_result(msg.chat.id, pasaran, angka)
    except Exception as e:
        await msg.reply(f"Error konfirmasi: {html.escape(str(e))}")


@dp.message_handler(lambda msg: is_admin(msg.from_user.id) and msg.from_user.id in pending_confirm)
async def handle_revisi_angka(msg: types.Message):
    cleanup_expired_confirm()
    if msg.from_user.id not in pending_confirm:
        return await msg.reply("❌ Data konfirmasi kadaluarsa. Kirim ulang result.")
    try:
        angka_baru = safe_result_number(msg.text.strip())
    except Exception as e:
        return await msg.reply(f"❌ {html.escape(str(e))}")
    pending_confirm[msg.from_user.id]["angka"] = angka_baru
    await preview_result(msg.chat.id, pending_confirm[msg.from_user.id]["pasaran"], angka_baru)


@dp.callback_query_handler(lambda c: c.data in ["kirim_channel", "revisi_angka"])
async def konfirmasi_callback(callback: types.CallbackQuery):
    cleanup_expired_confirm()
    user_id = callback.from_user.id
    if not is_admin(user_id): return
    await callback.answer()
    data = pending_confirm.get(user_id)
    if not data:
        return await bot.send_message(user_id, "❌ Tidak ada data yang bisa dikonfirmasi.")
    pasaran, angka = data["pasaran"], data["angka"]
    if callback.data == "revisi_angka":
        return await bot.send_message(user_id, "🔁 Silakan kirim ulang angkanya.")
    report = await send_result(pasaran, angka)
    naik = load_naik()
    if pasaran not in naik:
        naik.append(pasaran); save_naik(naik)
    pending_confirm.pop(user_id, None)
    append_log({"at": datetime.now(WIB).isoformat(), "mode": "manual", "market": pasaran, "number": angka})
    fb = report.get("facebook", {})
    fb_text = "Facebook OFF"
    if fb.get("enabled"):
        fb_text = "Masuk antrean Facebook Extension" if fb.get("queued") else f"Antrean Facebook gagal: {html.escape(str(fb.get('error', '-')))}"
    await bot.send_message(user_id, f"✅ Result <b>{pasaran.upper()}</b> dikirim ke Telegram.\n{'✅' if fb.get('queued') else '⚠️'} {fb_text}")


# ---------------- WEB ADMIN ----------------
def auth_token():
    return hmac.new(COOKIE_SECRET.encode(), b"resultom-admin", hashlib.sha256).hexdigest()


def is_web_auth(request: web.Request) -> bool:
    return hmac.compare_digest(request.cookies.get("resultom_auth", ""), auth_token())


def esc(v):
    return html.escape(str(v if v is not None else ""), quote=True)


async def login_get(request):
    return web.Response(text="""<!doctype html><html><head><meta name=viewport content='width=device-width,initial-scale=1'><title>ResultOM Login</title><style>body{font-family:Arial;background:#111;color:#eee;display:grid;place-items:center;height:100vh;margin:0}.box{width:min(92vw,420px);background:#1b1b1b;padding:28px;border-radius:14px}input,button{box-sizing:border-box;width:100%;padding:13px;margin-top:12px;border-radius:8px;border:1px solid #444}button{background:#e6b800;font-weight:700;cursor:pointer}</style></head><body><form class=box method=post action=/login><h2>ResultOM Admin</h2><input type=password name=password placeholder='Password dashboard' required><button>LOGIN</button></form></body></html>""", content_type="text/html")


async def login_post(request):
    data = await request.post()
    if not hmac.compare_digest(str(data.get("password", "")), DASHBOARD_PASSWORD):
        return web.Response(text="Password salah", status=401)
    resp = web.HTTPFound("/admin")
    resp.set_cookie("resultom_auth", auth_token(), httponly=True, samesite="Lax", max_age=60*60*24*30)
    return resp


async def logout(request):
    resp = web.HTTPFound("/login")
    resp.del_cookie("resultom_auth")
    return resp


def dashboard_html(cfg, state, notice=""):
    jadwal = load_jadwal()
    logs = list(reversed(load_json(str(LOG_FILE), [])))[:20]
    rows = []
    for market in sorted(cfg.get("market_codes", {})):
        code = cfg["market_codes"].get(market, "")
        checked = "checked" if cfg.get("market_enabled", {}).get(market, True) else ""
        last = state.get("sources", {}).get(code, {}) if code else {}
        rows.append(f"<tr><td>{esc(market.upper())}</td><td>{esc(jadwal.get(market, jadwal.get(market.capitalize(), '-')))}</td><td><input name='code__{esc(market)}' value='{esc(code)}'></td><td><input type=checkbox name='enabled__{esc(market)}' value=1 {checked}></td><td>{esc(last.get('period','-'))}</td><td>{esc(last.get('number','-'))}</td><td>{esc(last.get('date_text','-'))}</td></tr>")
    log_rows = "".join(f"<tr><td>{esc(x.get('at'))}</td><td>{esc(x.get('mode'))}</td><td>{esc(x.get('market'))}</td><td>{esc(x.get('period','-'))}</td><td>{esc(x.get('number','-'))}</td></tr>" for x in logs) or "<tr><td colspan=5>Belum ada log</td></tr>"
    fb_jobs = list(reversed(load_fb_queue()))[:20]
    fb_counts = {s: sum(1 for x in load_fb_queue() if x.get("status") == s) for s in ("pending", "processing", "posted", "failed")}
    fb_rows = "".join(f"<tr><td>{esc(x.get('created_at','-'))}</td><td>{esc(x.get('market','-'))}</td><td>{esc(x.get('number','-'))}</td><td>{esc(x.get('status','-'))}</td><td>{esc(x.get('attempts',0))}</td><td>{esc(x.get('error') or '-')}</td></tr>" for x in fb_jobs) or "<tr><td colspan=6>Belum ada antrean Facebook</td></tr>"
    status = "ON" if cfg.get("auto_enabled") else "OFF"
    return f"""<!doctype html><html><head><meta name=viewport content='width=device-width,initial-scale=1'><title>ResultOM Admin</title><style>
body{{font-family:Arial;background:#101010;color:#eee;margin:0}}.wrap{{max-width:1250px;margin:auto;padding:20px}}.card{{background:#1b1b1b;border:1px solid #333;border-radius:12px;padding:18px;margin-bottom:18px}}input,select,button{{padding:9px;border-radius:6px;border:1px solid #444;background:#111;color:#eee}}input[type=text],input[type=url],input[type=number]{{width:100%;box-sizing:border-box}}button{{background:#e6b800;color:#111;font-weight:700;cursor:pointer}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}label{{display:block;font-size:12px;color:#aaa;margin-bottom:5px}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{border-bottom:1px solid #333;padding:8px;text-align:left}}td input:not([type=checkbox]){{width:120px}}.scroll{{overflow:auto}}.ok{{background:#173b22;padding:10px;border-radius:8px}}.err{{background:#4b1c1c;padding:10px;border-radius:8px}}a{{color:#f0c929}}small{{color:#aaa}}</style></head><body><div class=wrap>
<h1>ResultOM Auto Result</h1><p>Status AUTO: <b>{status}</b> | Last scan: {esc(state.get('last_scan') or '-')} | <a href=/logout>Logout</a></p>
{f'<div class=ok>{esc(notice)}</div>' if notice else ''}
{f'<div class=err>Last error:<br>{esc(state.get("last_error"))}</div>' if state.get('last_error') else ''}
<form method=post action=/admin/save>
<div class=card><h3>Pengaturan Sumber Data</h3><div class=grid>
<div><label>URL History OM</label><input type=url name=source_url value='{esc(cfg.get('source_url'))}' required></div>
<div><label>Path Result ({{code}} wajib ada)</label><input type=text name=result_path_template value='{esc(cfg.get('result_path_template'))}' required></div>
<div><label>Interval cek (5-300 detik)</label><input type=number min=5 max=300 name=poll_seconds value='{esc(cfg.get('poll_seconds'))}'></div>
<div><label>Timeout request (5-60 detik)</label><input type=number min=5 max=60 name=request_timeout_seconds value='{esc(cfg.get('request_timeout_seconds'))}'></div>
<div><label>Channel / Group Telegram</label><input type=text name=channel_id value='{esc(cfg.get('channel_id'))}'></div>
<div><label>Posting Facebook</label><select name=facebook_enabled><option value=1 {'selected' if cfg.get('facebook_enabled') else ''}>ON</option><option value=0 {'selected' if not cfg.get('facebook_enabled') else ''}>OFF</option></select></div>
<div><label>URL Grup Facebook</label><input type=url name=facebook_group_url value='{esc(cfg.get('facebook_group_url'))}' placeholder='https://www.facebook.com/groups/...' ></div>
<div><label>API Key Extension</label><input type=text readonly value='{esc(cfg.get('extension_api_key'))}' onclick='this.select()'></div>
<div><label>Maksimal retry Facebook (1-10)</label><input type=number min=1 max=10 name=facebook_job_max_attempts value='{esc(cfg.get('facebook_job_max_attempts', 3))}'></div>
<div><label>Mode</label><select name=auto_enabled><option value=1 {'selected' if cfg.get('auto_enabled') else ''}>AUTO ON</option><option value=0 {'selected' if not cfg.get('auto_enabled') else ''}>AUTO OFF</option></select></div>
<div><label>First sync</label><select name=send_on_first_sync><option value=0 {'selected' if not cfg.get('send_on_first_sync') else ''}>Seed saja (aman)</option><option value=1 {'selected' if cfg.get('send_on_first_sync') else ''}>Kirim latest</option></select></div>
<div><label>Pin result</label><select name=pin_result><option value=1 {'selected' if cfg.get('pin_result') else ''}>YA</option><option value=0 {'selected' if not cfg.get('pin_result') else ''}>TIDAK</option></select></div>
</div><p><button type=submit>SIMPAN SEMUA</button></p><small>Kalau domain OM berubah, cukup ganti URL di sini lalu Simpan. Bot membaca config baru pada scan berikutnya tanpa redeploy.</small></div>
<div class=card><h3>Mapping Pasaran → Kode Web</h3><p><button formaction=/admin/discover formmethod=post>DETECT KODE DARI URL BARU</button> <button formaction=/admin/check formmethod=post>SCAN SEKARANG</button></p><div class=scroll><table><thead><tr><th>Pasaran</th><th>Jadwal</th><th>Kode</th><th>ON</th><th>Periode terakhir</th><th>Nomor</th><th>Waktu result</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></div></form>
<div class=card><h3>Log Result Terakhir</h3><div class=scroll><table><tr><th>Waktu</th><th>Mode</th><th>Pasaran</th><th>Periode</th><th>Nomor</th></tr>{log_rows}</table></div></div>
<div class=card><h3>Antrean Facebook Extension</h3><p>Menunggu: <b>{fb_counts['pending']}</b> | Diproses: <b>{fb_counts['processing']}</b> | Sukses: <b>{fb_counts['posted']}</b> | Gagal permanen: <b>{fb_counts['failed']}</b></p><div class=scroll><table><tr><th>Waktu</th><th>Pasaran</th><th>Nomor</th><th>Status</th><th>Percobaan</th><th>Error</th></tr>{fb_rows}</table></div></div>
</div></body></html>"""


async def admin_get(request):
    if not is_web_auth(request): return web.HTTPFound("/login")
    return web.Response(text=dashboard_html(load_config(), load_state()), content_type="text/html")


async def _apply_form_to_config(request):
    data = await request.post()
    cfg = load_config()
    if data.get("source_url"):
        source_base(str(data.get("source_url")))
        cfg["source_url"] = str(data.get("source_url")).strip()
    path_tpl = str(data.get("result_path_template", cfg.get("result_path_template"))).strip()
    if "{code}" not in path_tpl:
        raise ValueError("Path Result wajib mengandung {code}")
    cfg["result_path_template"] = path_tpl
    cfg["poll_seconds"] = max(5, min(300, int(data.get("poll_seconds", cfg.get("poll_seconds", 15)))))
    cfg["request_timeout_seconds"] = max(5, min(60, int(data.get("request_timeout_seconds", cfg.get("request_timeout_seconds", 15)))))
    cfg["channel_id"] = str(data.get("channel_id", cfg.get("channel_id", DEFAULT_CHANNEL_ID))).strip()
    cfg["facebook_enabled"] = str(data.get("facebook_enabled", "0")) == "1"
    cfg["facebook_group_url"] = str(data.get("facebook_group_url", cfg.get("facebook_group_url", ""))).strip()
    cfg["facebook_job_max_attempts"] = max(1, min(10, int(data.get("facebook_job_max_attempts", cfg.get("facebook_job_max_attempts", 3)))))
    if cfg["facebook_enabled"]:
        valid_facebook_group_url(cfg["facebook_group_url"])
    cfg["auto_enabled"] = str(data.get("auto_enabled", "0")) == "1"
    cfg["send_on_first_sync"] = str(data.get("send_on_first_sync", "0")) == "1"
    cfg["pin_result"] = str(data.get("pin_result", "0")) == "1"
    # Checkbox yang tidak dikirim dianggap OFF.
    for market in list(cfg.get("market_codes", {}).keys()):
        code_key = f"code__{market}"
        if code_key in data:
            cfg["market_codes"][market] = str(data.get(code_key, "")).strip()
            cfg["market_enabled"][market] = f"enabled__{market}" in data
    save_config(cfg)
    return cfg


async def admin_save(request):
    if not is_web_auth(request): return web.HTTPFound("/login")
    try:
        cfg = await _apply_form_to_config(request)
        return web.Response(text=dashboard_html(cfg, load_state(), "✅ Pengaturan tersimpan dan langsung aktif."), content_type="text/html")
    except Exception as e:
        return web.Response(text=dashboard_html(load_config(), load_state(), f"❌ Gagal simpan: {e}"), content_type="text/html", status=400)


async def admin_check(request):
    if not is_web_auth(request): return web.HTTPFound("/login")
    try:
        cfg = await _apply_form_to_config(request)
        res = await scan_auto_results(force=True)
        notice = f"✅ Scan selesai. Terkirim: {res.get('sent',0)}. Error: {len(res.get('errors',[]))}."
        return web.Response(text=dashboard_html(cfg, load_state(), notice), content_type="text/html")
    except Exception as e:
        return web.Response(text=dashboard_html(load_config(), load_state(), f"❌ Scan gagal: {e}"), content_type="text/html", status=500)


async def admin_discover(request):
    if not is_web_auth(request): return web.HTTPFound("/login")
    try:
        cfg = await _apply_form_to_config(request)
        found = await discover_market_codes(cfg["source_url"], int(cfg.get("request_timeout_seconds", 15)))

        def exact_norm(name):
            value = str(name or "").upper().replace("POOL", "")
            return re.sub(r"[^A-Z0-9]+", "", value)

        # Exact normalization sengaja mempertahankan 4D/5D agar TOTO MACAU 4D dan 5D tidak tertukar.
        norm_found = {exact_norm(name): code for name, code in found.items()}
        updated = 0
        aliases = {
            "JOWO09": "JOWO0900",
        }
        multi_special = {
            "kingkong4dp2",
            "totomacau4dp6", "totomacau4dp1", "totomacau5dp1", "totomacau5dp2",
            "totomacaup2", "totomacaup3", "totomacaup4", "totomacaup5",
        }
        for market in cfg.get("market_codes", {}):
            if market in multi_special:
                continue
            norm = exact_norm(market)
            key = aliases.get(norm, norm)
            if key in norm_found:
                cfg["market_codes"][market] = norm_found[key]
                updated += 1

        # Multi draw: satu code web dipakai beberapa jadwal/template; routing akhirnya berdasarkan waktu result.
        four_d_code = norm_found.get("TOTOMACAU") or norm_found.get("TOTOMACAU4D") or norm_found.get("TOTOMACAO4D")
        five_d_code = norm_found.get("TOTOMACAO5D") or norm_found.get("TOTOMACAU5D")
        king_code = norm_found.get("KINGKONG4D")
        if four_d_code:
            for m in ["totomacau4dp6","totomacau4dp1","totomacaup2","totomacaup3","totomacaup4","totomacaup5"]:
                cfg["market_codes"][m] = four_d_code
        if five_d_code:
            for m in ["totomacau5dp1", "totomacau5dp2"]:
                cfg["market_codes"][m] = five_d_code
        if king_code:
            cfg["market_codes"]["kingkong4d"] = king_code
            cfg["market_codes"]["kingkong4dp2"] = king_code
        save_config(cfg)
        return web.Response(text=dashboard_html(cfg, load_state(), f"✅ Detect selesai: {len(found)} kode ditemukan, {updated} mapping langsung cocok."), content_type="text/html")
    except Exception as e:
        return web.Response(text=dashboard_html(load_config(), load_state(), f"❌ Detect gagal: {e}"), content_type="text/html", status=500)


def extension_authorized(request: web.Request, cfg: dict) -> bool:
    supplied = request.headers.get("X-Extension-Key", "") or request.query.get("key", "")
    expected = str(cfg.get("extension_api_key", ""))
    return bool(expected) and hmac.compare_digest(str(supplied), expected)


async def facebook_jobs_get(request: web.Request):
    cfg = load_config()
    if not extension_authorized(request, cfg):
        return web.json_response({"ok": False, "error": "API key salah"}, status=401)
    now = datetime.now(WIB)
    items = load_fb_queue()
    chosen = None
    for job in items:
        if job.get("status") == "processing":
            try:
                stale = now - datetime.fromisoformat(job.get("updated_at", "")) > timedelta(minutes=5)
            except Exception:
                stale = True
            if stale:
                job["status"] = "pending"
        if job.get("status") == "pending" and int(job.get("attempts", 0)) < int(cfg.get("facebook_job_max_attempts", 3)):
            chosen = job
            break
    if chosen:
        chosen["status"] = "processing"
        chosen["attempts"] = int(chosen.get("attempts", 0)) + 1
        chosen["updated_at"] = now.isoformat()
        save_fb_queue(items)
        public = {k: chosen.get(k) for k in ("id", "group_url", "caption", "market", "number", "attempts", "created_at")}
        public["image_url"] = f"/api/facebook/jobs/{chosen['id']}/image"
        return web.json_response({"ok": True, "job": public})
    save_fb_queue(items)
    return web.json_response({"ok": True, "job": None})


async def facebook_job_image(request: web.Request):
    cfg = load_config()
    if not extension_authorized(request, cfg):
        return web.json_response({"ok": False, "error": "API key salah"}, status=401)
    job_id = request.match_info["job_id"]
    job = next((x for x in load_fb_queue() if x.get("id") == job_id), None)
    if not job:
        raise web.HTTPNotFound(text="Job tidak ditemukan")
    path = FB_IMAGE_DIR / Path(str(job.get("image_file", ""))).name
    if not path.is_file():
        raise web.HTTPNotFound(text="Gambar tidak ditemukan")
    return web.FileResponse(path, headers={"Cache-Control": "no-store"})


async def facebook_job_status(request: web.Request):
    cfg = load_config()
    if not extension_authorized(request, cfg):
        return web.json_response({"ok": False, "error": "API key salah"}, status=401)
    job_id = request.match_info["job_id"]
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "JSON tidak valid"}, status=400)
    status = str(body.get("status", ""))
    if status not in ("posted", "failed", "pending"):
        return web.json_response({"ok": False, "error": "Status tidak valid"}, status=400)
    items = load_fb_queue()
    job = next((x for x in items if x.get("id") == job_id), None)
    if not job:
        return web.json_response({"ok": False, "error": "Job tidak ditemukan"}, status=404)
    job["status"] = status
    job["error"] = str(body.get("error", ""))[:1000] or None
    job["updated_at"] = datetime.now(WIB).isoformat()
    if status == "posted":
        job["posted_at"] = job["updated_at"]
    elif status == "failed" and int(job.get("attempts", 0)) < int(cfg.get("facebook_job_max_attempts", 3)):
        job["status"] = "pending"
    save_fb_queue(items)
    return web.json_response({"ok": True, "status": job["status"], "attempts": job.get("attempts", 0)})


async def facebook_retry_failed(request: web.Request):
    cfg = load_config()
    if not extension_authorized(request, cfg):
        return web.json_response({"ok": False, "error": "API key salah"}, status=401)
    items = load_fb_queue()
    reset = 0
    for job in items:
        if job.get("status") == "failed":
            job["status"] = "pending"
            job["attempts"] = 0
            job["error"] = None
            job["updated_at"] = datetime.now(WIB).isoformat()
            reset += 1
    save_fb_queue(items)
    return web.json_response({"ok": True, "reset": reset})


async def facebook_queue_status(request: web.Request):
    if not is_web_auth(request): return web.HTTPFound("/login")
    items = load_fb_queue()
    counts = {s: sum(1 for x in items if x.get("status") == s) for s in ("pending", "processing", "posted", "failed")}
    return web.json_response({"ok": True, "counts": counts, "latest": items[-20:]})


async def health(request):
    cfg, state = load_config(), load_state()
    return web.json_response({"ok": True, "bot": "resultom", "auto": bool(cfg.get("auto_enabled")), "last_scan": state.get("last_scan")})


async def start_web_server():
    app = web.Application(client_max_size=1024 * 1024)
    app.router.add_get("/", lambda r: web.HTTPFound("/admin"))
    app.router.add_get("/login", login_get)
    app.router.add_post("/login", login_post)
    app.router.add_get("/logout", logout)
    app.router.add_get("/admin", admin_get)
    app.router.add_post("/admin/save", admin_save)
    app.router.add_post("/admin/check", admin_check)
    app.router.add_post("/admin/discover", admin_discover)
    app.router.add_get("/admin/facebook-queue", facebook_queue_status)
    app.router.add_get("/api/facebook/jobs", facebook_jobs_get)
    app.router.add_get("/api/facebook/jobs/{job_id}/image", facebook_job_image)
    app.router.add_post("/api/facebook/jobs/{job_id}/status", facebook_job_status)
    app.router.add_post("/api/facebook/jobs/retry-failed", facebook_retry_failed)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    log.info("Dashboard aktif di port %s", PORT)
    return runner


async def on_startup(dispatcher):
    cfg = load_config()
    cfg["channel_id"] = cfg.get("channel_id") or DEFAULT_CHANNEL_ID
    if not cfg.get("extension_api_key"):
        cfg["extension_api_key"] = secrets.token_urlsafe(32)
    save_config(cfg)
    await start_web_server()
    asyncio.create_task(auto_result_loop(), name="auto_result_loop")
    asyncio.create_task(notifikasi_jelang_result(), name="result_schedule_notice")
    log.info("BOT AKTIF | AUTO=%s | URL=%s", cfg.get("auto_enabled"), cfg.get("source_url"))


if __name__ == "__main__":
    from aiogram import executor
    try:
        executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
    except Exception as e:
        log.exception("BOT GAGAL JALAN: %s", e)
        sys.exit(1)
