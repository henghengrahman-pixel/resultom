import re
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Optional, Dict
from urllib.parse import urljoin, urlparse

import aiohttp
import pytz
from bs4 import BeautifulSoup

WIB = pytz.timezone("Asia/Jakarta")


@dataclass
class ResultRow:
    period: str
    date_text: str
    number: str
    parsed_at: Optional[datetime] = None

    @property
    def key(self) -> str:
        return f"{self.period}|{self.date_text}|{self.number}"

    def to_dict(self):
        d = asdict(self)
        if self.parsed_at:
            d["parsed_at"] = self.parsed_at.isoformat()
        return d


def normalize_market_name(value: str) -> str:
    value = (value or "").upper().strip()
    value = value.replace("4D", "").replace("5D", "")
    value = re.sub(r"\bPOOL\b", "", value)
    value = re.sub(r"[^A-Z0-9]+", "", value)
    return value


def source_base(source_url: str) -> str:
    raw = (source_url or "").strip()
    if not raw:
        raise ValueError("URL sumber data kosong")
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    p = urlparse(raw)
    if not p.netloc:
        raise ValueError("URL sumber data tidak valid")
    path = p.path.rstrip("/")
    suffix = "/history/number"
    if path.lower().endswith(suffix):
        path = path[: -len(suffix)]
    return f"{p.scheme}://{p.netloc}{path}".rstrip("/")


def result_url(source_url: str, path_template: str, code: str) -> str:
    base = source_base(source_url) + "/"
    path = (path_template or "/history/result/{code}/kosong").replace("{code}", code)
    return urljoin(base, path.lstrip("/"))


def parse_datetime(text: str) -> Optional[datetime]:
    text = (text or "").strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            return WIB.localize(dt)
        except ValueError:
            pass
    return None


def parse_results(html: str) -> List[ResultRow]:
    soup = BeautifulSoup(html or "", "html.parser")
    rows: List[ResultRow] = []

    # Prioritas tabel yang punya header Periode/Tanggal/Nomor.
    # Index kolom dibaca dari header supaya tetap benar jika ada kolom tambahan, mis. "Hari".
    tables = soup.find_all("table")
    candidate_tables = []
    for table in tables:
        headers = [th.get_text(" ", strip=True).lower() for th in table.find_all("th")]
        if "periode" in headers and "tanggal" in headers and "nomor" in headers:
            candidate_tables.append((table, headers.index("periode"), headers.index("tanggal"), headers.index("nomor")))
    if not candidate_tables:
        candidate_tables = [(table, 0, 1, 2) for table in tables]

    for table, period_idx, date_idx, number_idx in candidate_tables:
        needed = max(period_idx, date_idx, number_idx)
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) <= needed:
                continue
            cells = [td.get_text(" ", strip=True) for td in tds]
            period = cells[period_idx]
            date_text = cells[date_idx]
            number = cells[number_idx]
            number_digits = re.sub(r"\D", "", number)
            if not period or not date_text or not number_digits:
                continue
            # Result dapat 2D/3D/4D/5D. Batasi supaya tidak salah ambil kolom lain.
            if len(number_digits) < 2 or len(number_digits) > 6:
                continue
            rows.append(ResultRow(period=period.strip(), date_text=date_text.strip(), number=number_digits, parsed_at=parse_datetime(date_text)))
        if rows:
            break
    return rows


def parse_market_codes(html: str) -> Dict[str, str]:
    soup = BeautifulSoup(html or "", "html.parser")
    out: Dict[str, str] = {}
    select = soup.select_one("#pool-name") or soup.find("select")
    if not select:
        return out
    for opt in select.find_all("option"):
        code = (opt.get("data-code") or "").strip()
        name = (opt.get("data-name") or opt.get_text(" ", strip=True) or "").strip()
        if code and name:
            out[name] = code
    return out


async def fetch_text(url: str, timeout_seconds: int = 15) -> str:
    timeout = aiohttp.ClientTimeout(total=max(5, int(timeout_seconds)))
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ResultOMBot/2.0)",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(url, allow_redirects=True) as resp:
            text = await resp.text(errors="replace")
            if resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status} dari {url}")
            return text


async def fetch_results(source_url: str, path_template: str, code: str, timeout_seconds: int = 15) -> List[ResultRow]:
    url = result_url(source_url, path_template, code)
    html = await fetch_text(url, timeout_seconds)
    rows = parse_results(html)
    if not rows:
        raise RuntimeError(f"Tabel result tidak ditemukan/format berubah untuk code {code}")
    return rows


async def discover_market_codes(source_url: str, timeout_seconds: int = 15) -> Dict[str, str]:
    base = source_base(source_url)
    url = base + "/history/number"
    html = await fetch_text(url, timeout_seconds)
    mapping = parse_market_codes(html)
    if not mapping:
        raise RuntimeError("Daftar pasaran (#pool-name) tidak ditemukan pada halaman sumber")
    return mapping
