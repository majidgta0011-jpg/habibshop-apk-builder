# -*- coding: utf-8 -*-
"""
main.py
🛒 موجودی‌های سایت حبیب | سامانه تخصصی مدیریت موجودی، قیمت و لاگ کامل ادمین‌ها
مجهز به موتور تطبیق خودکار با صفحه هر مدل گوشی اندروید (Auto-Responsive + SafeArea)
"""

import os
import sys
import csv
import json
import time
import base64
import threading
import subprocess
import urllib.parse
from datetime import datetime
import requests
import urllib3
import flet as ft

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CONFIG_FILE = "habib_config.json"
SANDBOX_FILE = "habib_sandbox_db.json"
ADMIN_LOGS_FILE = "habib_admin_logs.json"
IMAGE_CACHE_MEMORY = {}


# ==============================================================================
# ۱. توابع تخصصی فارسی: اعداد کیبورد فارسی، قیمت به حروف، تاریخ شمسی با ثانیه دقیق
# ==============================================================================
def fa_to_en_digits(text: str) -> str:
    if text is None:
        return ""
    s = str(text)
    fa_map = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return s.translate(fa_map).replace(",", "").replace("٬", "").strip()


def format_price(val, is_rial=False) -> str:
    try:
        clean = fa_to_en_digits(val)
        if not clean:
            return "۰"
        num = int(float(clean))
        if is_rial:
            num = num // 10
        return f"{num:,}"
    except Exception:
        return str(val)


def number_to_persian_words(val, is_rial=False) -> str:
    try:
        clean = fa_to_en_digits(val)
        if not clean:
            return "معادل: صفر تومان"
        num = int(float(clean))
        if is_rial:
            num = num // 10
        if num <= 0:
            return "معادل: صفر تومان"

        ones = ["", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه"]
        tens = ["", "ده", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود"]
        teens = ["ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده", "شانزده", "هفده", "هجده", "نوزده"]
        hundreds = ["", "صد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد", "هشتصد", "نهصد"]

        def three_digits_to_fa(n: int) -> str:
            if n == 0:
                return ""
            h = n // 100
            rem = n % 100
            parts = []
            if h > 0:
                parts.append(hundreds[h])
            if 10 <= rem <= 19:
                parts.append(teens[rem - 10])
            else:
                t = rem // 10
                o = rem % 10
                if t > 0:
                    parts.append(tens[t])
                if o > 0:
                    parts.append(ones[o])
            return " و ".join(parts)

        billions = num // 1000000000
        millions = (num % 1000000000) // 1000000
        thousands = (num % 1000000) // 1000
        remainder = num % 1000

        res_parts = []
        if billions > 0:
            res_parts.append(f"{three_digits_to_fa(billions)} میلیارد")
        if millions > 0:
            res_parts.append(f"{three_digits_to_fa(millions)} میلیون")
        if thousands > 0:
            res_parts.append(f"{three_digits_to_fa(thousands)} هزار")
        if remainder > 0:
            res_parts.append(three_digits_to_fa(remainder))

        return "معادل: " + " و ".join(res_parts) + " تومان"
    except Exception:
        return ""


def gregorian_to_jalali_full(date_str: str, include_seconds=True) -> str:
    """
    تبدیل تاریخ و ساعت میلادی به تاریخ شمسی دقیق همراه با ساعت، دقیقه و ثانیه
    """
    if not date_str:
        return "نامشخص"
    clean = str(date_str).strip()
    if clean.startswith("13") or clean.startswith("14"):
        return clean
    try:
        date_part = clean[:10]
        time_part = (
            clean[11:19]
            if (include_seconds and len(clean) >= 19)
            else (clean[11:16] if len(clean) >= 16 else "00:00")
        )
        gy, gm, gd = [int(x) for x in date_part.split("-")]
        g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
        if gy > 1600:
            jy = 979
            gy -= 1600
        else:
            jy = 0
            gy -= 621
        gy2 = gy + 1 if gm > 2 else gy
        days = (
            (365 * gy)
            + ((gy2 + 3) // 4)
            - ((gy2 + 99) // 100)
            + ((gy2 + 399) // 400)
            - 80
            + gd
            + g_d_m[gm - 1]
        )
        jy += 33 * (days // 12053)
        days %= 12053
        jy += 4 * (days // 1461)
        days %= 1461
        if days > 365:
            jy += (days - 1) // 365
            days = (days - 1) % 365
        if days < 186:
            jm = 1 + (days // 31)
            jd = 1 + (days % 31)
        else:
            jm = 7 + ((days - 186) // 30)
            jd = 1 + ((days - 186) % 30)
        return f"{jy:04d}/{jm:02d}/{jd:02d} - ساعت {time_part}"
    except Exception:
        return clean[:19].replace("T", " ")


def calc_time_ago_fa(date_str: str) -> str:
    if not date_str:
        return "زمان نامشخص"
    try:
        clean = str(date_str).strip()[:19].replace(" ", "T")
        dt = datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S")
        diff = datetime.now() - dt
        total_seconds = int(diff.total_seconds())
        if total_seconds < 60:
            return "🔥 همین الان"
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        mins = (total_seconds % 3600) // 60
        if days == 0:
            if hours == 0:
                return f"🔥 امروز ({mins} دقیقه پیش)"
            return f"🔥 امروز ({hours} ساعت و {mins} دقیقه پیش)"
        elif days == 1:
            return f"⏳ دیروز ({hours} ساعت پیش)"
        else:
            return f"⏳ {days} روز و {hours} ساعت پیش"
    except Exception:
        return "ثبت‌شده در سیستم"


# ==============================================================================
# ۲. موتور ضدتحریم عکس‌های سایت حبیب (پشتیبانی از WebP، لینک فارسی و گالری)
# ==============================================================================
def normalize_wc_image_url(url: str) -> str:
    if not url or not isinstance(url, str):
        return ""
    url = url.strip()
    if os.path.exists(url):
        return url
    if not (url.startswith("http://") or url.startswith("https://")):
        return ""
    try:
        parsed = urllib.parse.urlsplit(url)
        unquoted_path = urllib.parse.unquote(parsed.path)
        safe_path = urllib.parse.quote(unquoted_path, safe="/:@&+$,;=-_.~")
        return urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, safe_path, parsed.query, parsed.fragment)
        )
    except Exception:
        return url


def extract_wc_product_image(product_dict: dict) -> str:
    if product_dict.get("image_url"):
        return normalize_wc_image_url(product_dict["image_url"])

    images = product_dict.get("images", [])
    if isinstance(images, list) and len(images) > 0:
        first_img = images[0]
        if isinstance(first_img, dict):
            src = first_img.get("src") or first_img.get("thumbnail") or ""
            if src:
                return normalize_wc_image_url(src)
        elif isinstance(first_img, str):
            return normalize_wc_image_url(first_img)

    for key in ("featured_src", "thumbnail", "image"):
        val = product_dict.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return normalize_wc_image_url(val)
        elif isinstance(val, dict) and val.get("src"):
            return normalize_wc_image_url(val["src"])

    return ""


def fetch_image_as_base64(url: str) -> str:
    if not url:
        return ""
    if url in IMAGE_CACHE_MEMORY:
        return IMAGE_CACHE_MEMORY[url]
    if os.path.exists(url):
        try:
            with open(url, "rb") as f:
                b64_str = base64.b64encode(f.read()).decode("utf-8")
                IMAGE_CACHE_MEMORY[url] = b64_str
                return b64_str
        except Exception:
            return ""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, verify=False, timeout=8)
        if r.status_code == 200 and r.content:
            b64_str = base64.b64encode(r.content).decode("utf-8")
            IMAGE_CACHE_MEMORY[url] = b64_str
            return b64_str
    except Exception:
        pass
    return ""


# ==============================================================================
# ۳. داده‌های پیش‌فرض محیط آزمایشی «موجودی‌های سایت حبیب»
# ==============================================================================
def get_default_sandbox_data() -> dict:
    now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    return {
        "categories": [
            {"id": 101, "name": "لبنیات و بستنی", "slug": "dairy"},
            {"id": 102, "name": "برنج و غلات", "slug": "rice-grains"},
            {"id": 103, "name": "نوشیدنی و چای", "slug": "beverages"},
            {"id": 104, "name": "روغن و رب", "slug": "oils-sauces"},
            {"id": 105, "name": "تنقلات", "slug": "snacks"},
            {"id": 106, "name": "شوینده", "slug": "detergents"},
        ],
        "products": [
            {
                "id": 201,
                "name": "شیر پرچرب کاله ۱ لیتری",
                "sku": "6260101001",
                "type": "simple",
                "regular_price": "38000",
                "sale_price": "35500",
                "stock_quantity": 0,
                "stock_status": "outofstock",
                "manage_stock": True,
                "not_in_store": False,
                "not_in_store_reason": "",
                "last_admin": "حبیب (مدیر کل)",
                "permalink": "https://habibshop.ir/?p=201",
                "image_url": "https://images.unsplash.com/photo-1563636619-e9143da7973b?w=300&q=80",
                "categories": [{"id": 101, "name": "لبنیات و بستنی"}],
                "date_created": "2025-02-18T09:15:20",
                "date_modified": now_str,
            },
            {
                "id": 202,
                "name": "برنج هاشمی درجه یک گیلان (چندوزنی)",
                "sku": "6260101002",
                "type": "variable",
                "regular_price": "1180000",
                "sale_price": "1120000",
                "stock_quantity": 0,
                "stock_status": "outofstock",
                "manage_stock": True,
                "not_in_store": False,
                "not_in_store_reason": "",
                "last_admin": "علی (انباردار)",
                "permalink": "https://habibshop.ir/?p=202",
                "image_url": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=300&q=80",
                "categories": [{"id": 102, "name": "برنج و غلات"}],
                "date_created": "2025-01-10T11:00:00",
                "date_modified": "2025-02-23T18:30:45",
                "variations": [
                    {"id": 2021, "name": "کیسه ۵ کیلویی", "regular_price": "610000", "sale_price": "580000", "stock_quantity": 0},
                    {"id": 2022, "name": "کیسه ۱۰ کیلویی", "regular_price": "1180000", "sale_price": "1120000", "stock_quantity": 0},
                ],
            },
            {
                "id": 203,
                "name": "روغن مایع آفتابگردان لادن ۱.۸ لیتری",
                "sku": "6260101003",
                "type": "simple",
                "regular_price": "142000",
                "sale_price": "",
                "stock_quantity": 0,
                "stock_status": "outofstock",
                "manage_stock": True,
                "not_in_store": False,
                "not_in_store_reason": "",
                "last_admin": "حبیب (مدیر کل)",
                "permalink": "https://habibshop.ir/?p=203",
                "image_url": "https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?w=300&q=80",
                "categories": [{"id": 104, "name": "روغن و رب"}],
                "date_created": "2025-02-22T08:40:10",
                "date_modified": "2025-02-24T14:15:30",
            },
            {
                "id": 204,
                "name": "چای ارل گری احمد ۵۰۰ گرمی",
                "sku": "6260101005",
                "type": "simple",
                "regular_price": "310000",
                "sale_price": "295000",
                "stock_quantity": 0,
                "stock_status": "outofstock",
                "manage_stock": True,
                "not_in_store": True,
                "not_in_store_reason": "شرکت پخش ندارد",
                "last_admin": "حبیب (مدیر کل)",
                "permalink": "https://habibshop.ir/?p=204",
                "image_url": "https://images.unsplash.com/photo-1597481499750-3e6b22637e12?w=300&q=80",
                "categories": [{"id": 103, "name": "نوشیدنی و چای"}],
                "date_created": "2025-02-15T07:50:00",
                "date_modified": "2025-02-20T19:45:12",
            },
            {
                "id": 205,
                "name": "چیپس سرکه نمکی مزمز بزرگ",
                "sku": "6260101006",
                "type": "simple",
                "regular_price": "45000",
                "sale_price": "",
                "stock_quantity": 2,
                "stock_status": "instock",
                "manage_stock": True,
                "not_in_store": False,
                "not_in_store_reason": "",
                "last_admin": "علی (انباردار)",
                "permalink": "https://habibshop.ir/?p=205",
                "image_url": "https://images.unsplash.com/photo-1566478989037-eec170784d0b?w=300&q=80",
                "categories": [{"id": 105, "name": "تنقلات"}],
                "date_created": "2025-01-25T16:00:00",
                "date_modified": "2025-02-24T12:00:00",
            },
            {
                "id": 206,
                "name": "پنیر فتا دوشه هراز ۴۰۰ گرمی",
                "sku": "6260101008",
                "type": "simple",
                "regular_price": "76000",
                "sale_price": "71000",
                "stock_quantity": 3,
                "stock_status": "instock",
                "manage_stock": True,
                "not_in_store": False,
                "not_in_store_reason": "",
                "last_admin": "حبیب (مدیر کل)",
                "permalink": "https://habibshop.ir/?p=206",
                "image_url": "https://images.unsplash.com/photo-1486297678162-eb2a19b0a32d?w=300&q=80",
                "categories": [{"id": 101, "name": "لبنیات و بستنی"}],
                "date_created": "2025-02-05T10:00:00",
                "date_modified": "2025-02-21T09:30:00",
            },
            {
                "id": 207,
                "name": "رب گوجه‌فرنگی روژین ۸۰۰ گرمی",
                "sku": "6260101009",
                "type": "simple",
                "regular_price": "98000",
                "sale_price": "91500",
                "stock_quantity": 40,
                "stock_status": "instock",
                "manage_stock": True,
                "not_in_store": False,
                "not_in_store_reason": "",
                "last_admin": "حبیب (مدیر کل)",
                "permalink": "https://habibshop.ir/?p=207",
                "image_url": "https://images.unsplash.com/photo-1592924357228-91a4daadcfea?w=300&q=80",
                "categories": [{"id": 104, "name": "روغن و رب"}],
                "date_created": "2025-02-08T11:20:00",
                "date_modified": "2025-02-20T15:00:00",
            },
            {
                "id": 208,
                "name": "ماکارونی فرمی زرماکارون ۵۰۰ گرمی (نمونه بدون عکس)",
                "sku": "6260101015",
                "type": "simple",
                "regular_price": "0",
                "sale_price": "",
                "stock_quantity": 0,
                "stock_status": "outofstock",
                "manage_stock": True,
                "not_in_store": False,
                "not_in_store_reason": "",
                "last_admin": "علی (انباردار)",
                "permalink": "https://habibshop.ir/?p=208",
                "image_url": "",
                "categories": [{"id": 102, "name": "برنج و غلات"}],
                "date_created": "2025-02-24T11:20:00",
                "date_modified": now_str,
            },
        ],
    }


# ==============================================================================
# ۴. هسته تخصصی «موجودی‌های سایت حبیب» + تاریخچه کامل لاگ هر کالا
# ==============================================================================
class HabibInventoryBackend:
    def __init__(self, logger_func):
        self.log = logger_func
        self.config = self.load_config()
        self.sandbox = self.load_sandbox()
        self.admin_logs = self.load_admin_logs()
        self.categories_cache = None
        self.live_products_cache = None

    def load_config(self) -> dict:
        default_cfg = {
            "mode": "sandbox",
            "view_mode": "a35",
            "a35_color": "#1E293B",
            "is_rial": False,
            "edit_locked": False,
            "current_admin": "حبیب (مدیر کل)",
            "admins_list": [
                "حبیب (مدیر کل)",
                "علی (انباردار)",
                "رضا (مسئول قیمت)",
                "ادمین شیفت عصر",
            ],
            "not_in_store_map": {
                "204": {
                    "reason": "شرکت پخش ندارد",
                    "admin": "حبیب (مدیر کل)",
                    "time": "2025-02-20T19:45:12",
                }
            },
            "low_stock_threshold": 5,
            "site_url": "https://habibshop.ir",
            "consumer_key": "",
            "consumer_secret": "",
            "github_token": "",
            "github_repo": "habibshop-apk-builder",
            "ready_for_apk": False,
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    default_cfg.update(saved)
            except Exception:
                pass
        return default_cfg

    def save_config(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def load_sandbox(self) -> dict:
        if os.path.exists(SANDBOX_FILE):
            try:
                with open(SANDBOX_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        data = get_default_sandbox_data()
        self.save_sandbox(data)
        return data

    def save_sandbox(self, data=None):
        if data is not None:
            self.sandbox = data
        with open(SANDBOX_FILE, "w", encoding="utf-8") as f:
            json.dump(self.sandbox, f, ensure_ascii=False, indent=2)

    def load_admin_logs(self) -> list:
        if os.path.exists(ADMIN_LOGS_FILE):
            try:
                with open(ADMIN_LOGS_FILE, "r", encoding="utf-8") as f:
                    logs = json.load(f)
                    if isinstance(logs, list) and len(logs) >= 2:
                        return logs
            except Exception:
                pass
        # نمونه لاگ‌های اولیه برای تست دکمه «مشاهده لاگ‌های بیشتر» روی کالاها
        sample_logs = [
            {
                "id": 1003,
                "timestamp": "2025-02-25T11:40:18",
                "jalali_time": gregorian_to_jalali_full("2025-02-25T11:40:18", True),
                "admin": "حبیب (مدیر کل)",
                "product_id": 201,
                "product_name": "شیر پرچرب کاله ۱ لیتری",
                "action_type": "✖️ ناموجود کردن کالا",
                "old_stock": 6,
                "new_stock": 0,
                "old_status": "instock",
                "new_status": "outofstock",
                "old_reg_price": "38000",
                "new_reg_price": "38000",
                "old_sale_price": "35500",
                "new_sale_price": "35500",
                "old_not_in_store": False,
                "new_not_in_store": False,
                "note": "اتمام بار روزانه",
            },
            {
                "id": 1002,
                "timestamp": "2025-02-22T09:15:05",
                "jalali_time": gregorian_to_jalali_full("2025-02-22T09:15:05", True),
                "admin": "رضا (مسئول قیمت)",
                "product_id": 201,
                "product_name": "شیر پرچرب کاله ۱ لیتری",
                "action_type": "✏️ ویرایش قیمت و موجودی",
                "old_stock": 12,
                "new_stock": 6,
                "old_status": "instock",
                "new_status": "instock",
                "old_reg_price": "35000",
                "new_reg_price": "38000",
                "old_sale_price": "",
                "new_sale_price": "35500",
                "old_not_in_store": False,
                "new_not_in_store": False,
                "note": "افزایش قیمت بار جدید",
            },
            {
                "id": 1001,
                "timestamp": "2025-02-20T19:45:12",
                "jalali_time": gregorian_to_jalali_full("2025-02-20T19:45:12", True),
                "admin": "حبیب (مدیر کل)",
                "product_id": 204,
                "product_name": "چای ارل گری احمد ۵۰۰ گرمی",
                "action_type": "🚫 انتقال به در فروشگاه موجود نیست",
                "old_stock": 0,
                "new_stock": 0,
                "old_status": "outofstock",
                "new_status": "outofstock",
                "old_reg_price": "310000",
                "new_reg_price": "310000",
                "old_sale_price": "295000",
                "new_sale_price": "295000",
                "old_not_in_store": False,
                "new_not_in_store": True,
                "note": "شرکت پخش ندارد",
            },
        ]
        self.save_admin_logs(sample_logs)
        return sample_logs

    def save_admin_logs(self, logs=None):
        if logs is not None:
            self.admin_logs = logs
        with open(ADMIN_LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.admin_logs, f, ensure_ascii=False, indent=2)

    def record_admin_log(
        self,
        product_obj: dict,
        action_type: str,
        new_stock: int,
        new_status: str,
        new_reg: str,
        new_sale: str,
        new_not_in_store: bool,
        note: str = "",
    ):
        now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        admin_name = self.config.get("current_admin", "حبیب (مدیر کل)")
        entry = {
            "id": int(time.time() * 1000),
            "timestamp": now_iso,
            "jalali_time": gregorian_to_jalali_full(now_iso, include_seconds=True),
            "admin": admin_name,
            "product_id": product_obj["id"],
            "product_name": product_obj.get("name", ""),
            "action_type": action_type,
            "old_stock": int(product_obj.get("stock_quantity") or 0),
            "new_stock": int(new_stock),
            "old_status": product_obj.get("stock_status", "outofstock"),
            "new_status": new_status,
            "old_reg_price": str(product_obj.get("regular_price") or "0"),
            "new_reg_price": str(new_reg),
            "old_sale_price": str(product_obj.get("sale_price") or ""),
            "new_sale_price": str(new_sale),
            "old_not_in_store": bool(product_obj.get("not_in_store", False)),
            "new_not_in_store": bool(new_not_in_store),
            "note": note,
        }
        self.admin_logs.insert(0, entry)
        self.save_admin_logs()
        self.log(
            f"👤 ثبت در لاگ [{admin_name}]: {action_type} روی «{entry['product_name']}» | موجودی: {entry['old_stock']}⬅️{entry['new_stock']} | قیمت: {entry['old_reg_price']}⬅️{entry['new_reg_price']}"
        )
        return entry

    def undo_admin_log_entry(self, log_id: int) -> bool:
        target_log = next(
            (lg for lg in self.admin_logs if lg.get("id") == log_id), None
        )
        if not target_log:
            return False

        pid = target_log["product_id"]
        old_st = int(target_log.get("old_stock", 0))
        old_status = target_log.get("old_status", "outofstock")
        old_reg = target_log.get("old_reg_price", "0")
        old_sale = target_log.get("old_sale_price", "")
        old_nis = bool(target_log.get("old_not_in_store", False))

        if old_status == "instock" and old_st == 0:
            st_mode = "instock_unmanaged"
        elif old_status == "instock" and old_st > 0:
            st_mode = "instock_count"
        else:
            st_mode = "outofstock"

        ok = self.save_product_full_edit(
            product_id=pid,
            new_stock=old_st,
            stock_mode=st_mode,
            regular_price=old_reg,
            sale_price=old_sale,
            not_in_store=old_nis,
            not_in_store_reason="بازگشت به حالت قبل (Undo دو مرحله‌ای)",
            action_label=f"↩️ واگرد تغییرِ {target_log.get('admin', '')}",
        )
        return ok

    def reset_sandbox(self):
        self.sandbox = get_default_sandbox_data()
        self.live_products_cache = None
        self.categories_cache = None
        self.save_sandbox()
        self.log("🔄 داده‌های آزمایشی «موجودی‌های سایت حبیب» بازنشانی شدند.")

    def is_live(self) -> bool:
        return self.config.get("mode") == "live"

    def _wc_url(self, endpoint: str) -> str:
        base = self.config.get("site_url", "").rstrip("/")
        return f"{base}/wp-json/wc/v3/{endpoint.lstrip('/')}"

    def _wc_auth(self) -> tuple:
        return (
            self.config.get("consumer_key", "").strip(),
            self.config.get("consumer_secret", "").strip(),
        )

    def _req_headers(self) -> dict:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }

    def import_sample_products_from_habib_site(self, target_url: str = "") -> tuple:
        base_url = (target_url or self.config.get("site_url", "")).strip().rstrip("/")
        if not base_url.startswith("http"):
            base_url = "https://" + base_url
        self.config["site_url"] = base_url
        self.save_config()

        self.log(f"🌐 در حال دریافت کالاها و عکس‌های واقعی از سایت حبیب ({base_url})...")
        imported_products = []

        if self.config.get("consumer_key") and self.config.get("consumer_secret"):
            try:
                r = requests.get(
                    f"{base_url}/wp-json/wc/v3/products",
                    auth=self._wc_auth(),
                    headers=self._req_headers(),
                    params={"per_page": 40},
                    verify=False,
                    timeout=15,
                )
                if r.status_code == 200 and isinstance(r.json(), list):
                    for p in r.json():
                        imported_products.append(self._normalize_wc_product(p))
            except Exception as e:
                self.log(f"⚠️ تست روش اول: {e}")

        if not imported_products:
            try:
                r_store = requests.get(
                    f"{base_url}/wp-json/wc/store/v1/products?per_page=35",
                    headers=self._req_headers(),
                    verify=False,
                    timeout=15,
                )
                if r_store.status_code == 200 and isinstance(r_store.json(), list):
                    for p in r_store.json():
                        img = extract_wc_product_image(p)
                        prices = p.get("prices", {})
                        reg_p = str(
                            prices.get("regular_price") or prices.get("price") or "0"
                        )
                        sale_p = str(prices.get("sale_price") or "")
                        if sale_p == reg_p:
                            sale_p = ""
                        is_in = p.get("is_in_stock", True)
                        imported_products.append(
                            {
                                "id": p["id"],
                                "name": p.get("name", "کالای سایت حبیب"),
                                "sku": p.get("sku") or str(p["id"]),
                                "type": p.get("type", "simple"),
                                "regular_price": reg_p,
                                "sale_price": sale_p,
                                "stock_quantity": 10 if is_in else 0,
                                "stock_status": "instock" if is_in else "outofstock",
                                "manage_stock": True,
                                "not_in_store": False,
                                "not_in_store_reason": "",
                                "last_admin": self.config.get("current_admin"),
                                "permalink": p.get("permalink", base_url),
                                "image_url": img,
                                "categories": p.get("categories")
                                or [{"id": 101, "name": "کالاهای سایت حبیب"}],
                                "date_created": datetime.now().strftime(
                                    "%Y-%m-%dT%H:%M:%S"
                                ),
                                "date_modified": datetime.now().strftime(
                                    "%Y-%m-%dT%H:%M:%S"
                                ),
                            }
                        )
            except Exception as e:
                self.log(f"⚠️ تست روش دوم: {e}")

        if imported_products:
            self.sandbox["products"] = imported_products
            self.save_sandbox()
            with_img = sum(1 for x in imported_products if x.get("image_url"))
            msg = f"🎉 تعداد {len(imported_products)} کالا به همراه {with_img} عکس واقعی از سایت حبیب استخراج شد!"
            self.log(msg)
            return True, msg

        return False, "❌ امکان دریافت خودکار نبود. آدرس سایت یا کلیدهای API را بررسی کنید."

    def _normalize_wc_product(self, p: dict) -> dict:
        pid_str = str(p["id"])
        nis_map = self.config.get("not_in_store_map", {})
        meta_list = p.get("meta_data", [])

        not_in_store = pid_str in nis_map
        nis_reason = nis_map.get(pid_str, {}).get("reason", "")
        last_adm = nis_map.get(pid_str, {}).get(
            "admin", self.config.get("current_admin", "حبیب (مدیر کل)")
        )

        for m in meta_list:
            if m.get("key") == "_habib_not_in_store":
                not_in_store = m.get("value") == "yes"
            elif m.get("key") == "_habib_nis_reason":
                nis_reason = str(m.get("value") or "")
            elif m.get("key") == "_habib_last_admin":
                last_adm = str(m.get("value") or last_adm)

        return {
            "id": p["id"],
            "name": p.get("name", "بدون نام"),
            "sku": p.get("sku") or str(p["id"]),
            "type": p.get("type", "simple"),
            "regular_price": str(p.get("regular_price") or p.get("price") or "0"),
            "sale_price": str(p.get("sale_price") or ""),
            "stock_quantity": int(p.get("stock_quantity") or 0),
            "stock_status": p.get("stock_status", "instock"),
            "manage_stock": bool(p.get("manage_stock", True)),
            "not_in_store": not_in_store,
            "not_in_store_reason": nis_reason,
            "last_admin": last_adm,
            "permalink": p.get("permalink", self.config.get("site_url", "")),
            "image_url": extract_wc_product_image(p),
            "categories": p.get("categories") or [{"id": 101, "name": "عمومی"}],
            "date_created": p.get("date_created", ""),
            "date_modified": p.get("date_modified", ""),
        }

    def get_categories(self, force_refresh=False) -> list:
        if not self.is_live():
            return self.sandbox.get("categories", [])
        if self.categories_cache is not None and not force_refresh:
            return self.categories_cache
        try:
            r = requests.get(
                self._wc_url("products/categories"),
                auth=self._wc_auth(),
                headers=self._req_headers(),
                params={"per_page": 100},
                verify=False,
                timeout=20,
            )
            if r.status_code == 200:
                self.categories_cache = [
                    {"id": c["id"], "name": c["name"]} for c in r.json()
                ]
                return self.categories_cache
        except Exception:
            pass
        return self.categories_cache or []

    def get_all_cached_or_live_products(self, force_network=False) -> list:
        if not self.is_live():
            prods = list(self.sandbox.get("products", []))
            nis_map = self.config.get("not_in_store_map", {})
            for p in prods:
                p["image_url"] = extract_wc_product_image(p)
                if str(p["id"]) in nis_map:
                    p["not_in_store"] = True
                    p["not_in_store_reason"] = nis_map[str(p["id"])].get("reason", "")
            return prods

        if self.live_products_cache is not None and not force_network:
            return self.live_products_cache

        collected = []
        try:
            for pg in range(1, 4):
                self.log(f"🔄 دریافت صفحه {pg} موجودی کالاهای سایت حبیب...")
                r = requests.get(
                    self._wc_url("products"),
                    auth=self._wc_auth(),
                    headers=self._req_headers(),
                    params={"per_page": 100, "page": pg},
                    verify=False,
                    timeout=25,
                )
                if r.status_code != 200:
                    break
                batch = r.json()
                if not batch:
                    break
                for raw_p in batch:
                    collected.append(self._normalize_wc_product(raw_p))
                if len(batch) < 100:
                    break
            self.live_products_cache = collected
            self.log(f"✔️ مجموعاً {len(collected)} کالا از سایت حبیب بارگذاری شد.")
        except Exception as e:
            self.log(f"❌ خطا در دریافت کالاها: {e}")
        return self.live_products_cache or []

    def get_product_by_id(self, product_id: int) -> dict:
        for p in self.get_all_cached_or_live_products(force_network=False):
            if int(p["id"]) == int(product_id):
                return p
        return {}

    def get_product_variations(self, product_id: int) -> list:
        if not self.is_live():
            p = self.get_product_by_id(product_id)
            return p.get(
                "variations",
                [
                    {
                        "id": int(product_id) * 10 + 1,
                        "name": "بسته استاندارد ۱",
                        "regular_price": p.get("regular_price", "0"),
                        "sale_price": p.get("sale_price", ""),
                        "stock_quantity": p.get("stock_quantity", 0),
                    }
                ],
            )
        try:
            r = requests.get(
                self._wc_url(f"products/{product_id}/variations"),
                auth=self._wc_auth(),
                headers=self._req_headers(),
                verify=False,
                timeout=20,
            )
            if r.status_code == 200:
                res = []
                for v in r.json():
                    attrs = " - ".join(
                        [a.get("option", "") for a in v.get("attributes", [])]
                    )
                    res.append(
                        {
                            "id": v["id"],
                            "name": attrs or f"مدل #{v['id']}",
                            "regular_price": str(v.get("regular_price") or "0"),
                            "sale_price": str(v.get("sale_price") or ""),
                            "stock_quantity": int(v.get("stock_quantity") or 0),
                        }
                    )
                return res
        except Exception:
            pass
        return []

    def update_single_variation(
        self, product_id: int, variation_id: int, stock: int, reg_p: str, sale_p: str
    ) -> bool:
        clean_r = fa_to_en_digits(reg_p) or "0"
        clean_s = fa_to_en_digits(sale_p)
        if not self.is_live():
            p = self.get_product_by_id(product_id)
            if p:
                for v in p.get("variations", []):
                    if int(v["id"]) == int(variation_id):
                        v["stock_quantity"] = stock
                        v["regular_price"] = clean_r
                        v["sale_price"] = clean_s
                p["stock_quantity"] = sum(
                    int(x.get("stock_quantity") or 0) for x in p.get("variations", [])
                )
                p["stock_status"] = (
                    "instock" if p["stock_quantity"] > 0 else "outofstock"
                )
                self.save_sandbox()
                self.record_admin_log(
                    p,
                    f"⚖️ ویرایش مدل #{variation_id}",
                    p["stock_quantity"],
                    p["stock_status"],
                    clean_r,
                    clean_s,
                    False,
                )
                return True
            return False
        try:
            payload = {
                "manage_stock": True,
                "stock_quantity": stock,
                "stock_status": "instock" if stock > 0 else "outofstock",
                "regular_price": clean_r,
                "sale_price": clean_s,
            }
            r = requests.put(
                self._wc_url(f"products/{product_id}/variations/{variation_id}"),
                auth=self._wc_auth(),
                headers=self._req_headers(),
                json=payload,
                verify=False,
                timeout=20,
            )
            return r.status_code == 200
        except Exception:
            return False

    def save_product_full_edit(
        self,
        product_id: int,
        new_stock: int,
        stock_mode: str,  # instock_count | instock_unmanaged | outofstock
        regular_price: str,
        sale_price: str,
        not_in_store: bool = False,
        not_in_store_reason: str = "",
        new_image_url: str = "",
        action_label: str = "",
    ) -> bool:
        now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        admin_name = self.config.get("current_admin", "حبیب (مدیر کل)")
        clean_reg = fa_to_en_digits(regular_price) or "0"
        clean_sale = fa_to_en_digits(sale_price)
        if clean_sale in ("0", "0.0"):
            clean_sale = ""

        if stock_mode == "instock_unmanaged":
            final_status = "instock"
            manage_st = False
            final_qty = 0
            not_in_store = False
        elif stock_mode == "instock_count":
            final_status = "instock"
            manage_st = True
            final_qty = max(1, int(new_stock))
            not_in_store = False
        else:
            final_status = "outofstock"
            manage_st = True
            final_qty = 0

        all_items = self.get_all_cached_or_live_products(force_network=False)
        target_p = next(
            (x for x in all_items if int(x["id"]) == int(product_id)), None
        )
        if not target_p:
            return False

        if not action_label:
            if not_in_store:
                action_label = "🚫 انتقال به در فروشگاه موجود نیست"
            elif (
                final_status == "instock"
                and target_p.get("stock_status") == "outofstock"
            ):
                action_label = "🟢 موجود کردن کالای ناموجود"
            elif final_status == "outofstock" and target_p.get("stock_status") == "instock":
                action_label = "✖️ ناموجود کردن کالا"
            else:
                action_label = "✏️ ویرایش قیمت / موجودی"

        self.record_admin_log(
            product_obj=target_p,
            action_type=action_label,
            new_stock=final_qty,
            new_status=final_status,
            new_reg=clean_reg,
            new_sale=clean_sale,
            new_not_in_store=not_in_store,
            note=not_in_store_reason,
        )

        nis_map = self.config.setdefault("not_in_store_map", {})
        if not_in_store:
            nis_map[str(product_id)] = {
                "reason": not_in_store_reason.strip(),
                "admin": admin_name,
                "time": now_iso,
            }
        else:
            nis_map.pop(str(product_id), None)
        self.save_config()

        target_p["stock_quantity"] = final_qty
        target_p["stock_status"] = final_status
        target_p["manage_stock"] = manage_st
        target_p["regular_price"] = clean_reg
        target_p["sale_price"] = clean_sale
        target_p["not_in_store"] = not_in_store
        target_p["not_in_store_reason"] = (
            not_in_store_reason.strip() if not_in_store else ""
        )
        target_p["last_admin"] = admin_name
        target_p["date_modified"] = now_iso
        if new_image_url.strip():
            target_p["image_url"] = normalize_wc_image_url(new_image_url.strip())

        if not self.is_live():
            self.save_sandbox()
            return True

        try:
            payload = {
                "manage_stock": manage_st,
                "stock_quantity": final_qty,
                "stock_status": final_status,
                "regular_price": clean_reg,
                "sale_price": clean_sale,
                "meta_data": [
                    {
                        "key": "_habib_not_in_store",
                        "value": "yes" if not_in_store else "no",
                    },
                    {"key": "_habib_nis_reason", "value": not_in_store_reason.strip()},
                    {"key": "_habib_last_admin", "value": admin_name},
                    {"key": "_habib_oos_time", "value": now_iso},
                ],
            }
            if new_image_url.strip().startswith("http"):
                payload["images"] = [
                    {"src": normalize_wc_image_url(new_image_url.strip())}
                ]

            r = requests.put(
                self._wc_url(f"products/{product_id}"),
                auth=self._wc_auth(),
                headers=self._req_headers(),
                json=payload,
                verify=False,
                timeout=25,
            )
            return r.status_code == 200
        except Exception as e:
            self.log(f"❌ خطا در ارسال به سایت: {e}")
        return False

    def export_outofstock_to_csv(self) -> str:
        all_p = self.get_all_cached_or_live_products(force_network=False)
        items = [
            p
            for p in all_p
            if (
                p.get("stock_status") == "outofstock"
                or int(p.get("stock_quantity") or 0) <= 0
            )
            and not p.get("not_in_store")
        ]
        filename = "habib_mojoodi_list.csv"
        with open(filename, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "کد",
                    "نام کالا",
                    "بارکد",
                    "موجودی",
                    "قیمت (تومان)",
                    "زمان دقیق ناموجودی",
                    "آخرین ادمین",
                ]
            )
            for p in items:
                writer.writerow(
                    [
                        p.get("id"),
                        p.get("name"),
                        p.get("sku", "-"),
                        p.get("stock_quantity", 0),
                        p.get("regular_price", 0),
                        gregorian_to_jalali_full(p.get("date_modified", ""), True),
                        p.get("last_admin", "-"),
                    ]
                )
        return os.path.abspath(filename)

    def test_wc_connection(self) -> tuple:
        if not self.config.get("site_url") or not self.config.get("consumer_key"):
            return False, "لطفاً آدرس سایت و کلیدهای ووکامرس را وارد کنید."
        try:
            r = requests.get(
                self._wc_url("products"),
                auth=self._wc_auth(),
                headers=self._req_headers(),
                params={"per_page": 1},
                verify=False,
                timeout=15,
            )
            if r.status_code == 200:
                self.live_products_cache = None
                return True, "اتصال به سایت حبیب برقرار شد."
            return False, f"خطای سرور (کد {r.status_code})"
        except Exception as e:
            return False, f"خطا: {e}"


def main(page: ft.Page):
    page.title = "🛒 موجودی‌های سایت حبیب | سامانه تخصصی مدیریت موجودی و لاگ ادمین‌ها"
    page.rtl = True
    page.theme_mode = ft.ThemeMode.LIGHT

    # تشخیص هوشمند اجرای واقعی روی گوشی اندروید در برابر شبیه‌ساز ویندوز
    is_real_mobile = (
        page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS)
        or "ANDROID_ARGUMENT" in os.environ
    )

    page.padding = 0 if is_real_mobile else 12
    page.bgcolor = "#F1F5F9" if is_real_mobile else "#0F172A"
    if not is_real_mobile:
        page.window_width = 1260
        page.window_height = 920

    local_font = os.path.join("assets", "Vazirmatn-Regular.ttf")
    font_src = (
        local_font
        if os.path.exists(local_font)
        else "https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/fonts/ttf/Vazirmatn-Regular.ttf"
    )
    page.fonts = {"Vazirmatn": font_src}
    page.theme = ft.Theme(font_family="Vazirmatn")

    terminal_list = ft.ListView(expand=True, spacing=5, auto_scroll=True)

    def log_to_terminal(msg: str):
        now = datetime.now().strftime("%H:%M:%S")
        color = (
            "#4ADE80"
            if ("✔️" in msg or "🎉" in msg or "🟢" in msg)
            else (
                "#F87171"
                if ("❌" in msg or "⚠️" in msg or "🚫" in msg)
                else "#38BDF8"
            )
        )
        terminal_list.controls.append(
            ft.Text(f"[{now}] {msg}", color=color, size=12, selectable=True)
        )
        try:
            page.update()
        except Exception:
            pass

    backend = HabibInventoryBackend(log_to_terminal)

    loading_bar = ft.ProgressBar(
        width=float("inf"), color="#FACC15", bgcolor="#0F766E", visible=False
    )

    def set_loading(state: bool):
        loading_bar.visible = state
        try:
            page.update()
        except Exception:
            pass

    def run_in_bg(task_func):
        def _wrapper():
            set_loading(True)
            try:
                task_func()
            except Exception as exc:
                log_to_terminal(f"❌ خطا: {exc}")
            finally:
                set_loading(False)

        threading.Thread(target=_wrapper, daemon=True).start()

    def show_snack(text: str, bg="#0F766E"):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(text, color="white", weight=ft.FontWeight.BOLD, size=13),
            bgcolor=bg,
        )
        page.snack_bar.open = True
        page.update()

    # انتخابگر فایل برای آپلود عکس کالا از گالری گوشی یا کامپیوتر
    selected_gallery_target = {"callback": None}

    def on_file_picked(e: ft.FilePickerResultEvent):
        if e.files and len(e.files) > 0 and selected_gallery_target["callback"]:
            selected_gallery_target["callback"](e.files[0].path)

    file_picker = ft.FilePicker(on_result=on_file_picked)
    page.overlay.append(file_picker)

    # وضعیت‌های ناوبری و حفظ تب قبلی هنگام ویرایش مجدد کالا
    current_stock_tab = ["oos"]  # oos | nis | low | instock | warnings
    current_cat_id = ["all"]
    current_bottom_nav = [0]  # 0: کالاها | 1: لاگ ادمین‌ها | 2: تنظیمات سایت
    return_to_nav_idx = [0]
    current_filtered_ids = []
    is_in_fullscreen_editor = [False]

    def on_key_event(e: ft.KeyboardEvent):
        if e.key in ("Escape", "Back"):
            if page.dialog and page.dialog.open:
                page.dialog.open = False
                page.update()
            elif is_in_fullscreen_editor[0]:
                close_fullscreen_editor()
            elif current_bottom_nav[0] != 0:
                switch_bottom_nav(0)

    page.on_keyboard_event = on_key_event

    # موتور تطبیق خودکار اندازه عکس و المان‌ها با عرض هر مدل گوشی اندروید
    def get_responsive_thumb_size() -> int:
        if is_real_mobile and page.width and page.width < 365:
            return 58
        return 68

    # ==========================================================================
    # موتور پس‌زمینه ضدتحریم عکس‌ها در لیست اصلی (مدل ۱)
    # ==========================================================================
    def preload_images_in_bg(products_list: list, img_controls_map: dict):
        tsize = get_responsive_thumb_size()

        def _loader():
            updated_any = False
            for p in products_list:
                url = p.get("image_url", "")
                pid = p.get("id")
                if url and pid in img_controls_map and url not in IMAGE_CACHE_MEMORY:
                    b64 = fetch_image_as_base64(url)
                    if b64:
                        ctrl_holder = img_controls_map[pid]
                        ctrl_holder.content = ft.Image(
                            src_base64=b64,
                            width=tsize,
                            height=tsize,
                            fit=ft.ImageFit.COVER,
                        )
                        updated_any = True
            if updated_any:
                try:
                    page.update()
                except Exception:
                    pass

        threading.Thread(target=_loader, daemon=True).start()

    def build_product_thumbnail_m1(p: dict, border_col: str, img_map: dict):
        tsize = get_responsive_thumb_size()
        img_url = p.get("image_url", "")
        pid = p.get("id")
        b64_cached = IMAGE_CACHE_MEMORY.get(img_url, "")

        if b64_cached:
            inner = ft.Image(
                src_base64=b64_cached, width=tsize, height=tsize, fit=ft.ImageFit.COVER
            )
        elif img_url:
            inner = ft.Image(
                src=img_url,
                width=tsize,
                height=tsize,
                fit=ft.ImageFit.COVER,
                error_content=ft.Container(
                    alignment=ft.alignment.center,
                    bgcolor="#F1F5F9",
                    content=ft.Text("🖼️", size=20),
                ),
            )
        else:
            inner = ft.Container(
                alignment=ft.alignment.center,
                bgcolor="#FEF2F2",
                content=ft.Text(
                    "بدون عکس", size=9, color="#DC2626", weight=ft.FontWeight.BOLD
                ),
            )

        holder = ft.Container(
            width=tsize,
            height=tsize,
            border_radius=12,
            bgcolor="#F8FAFC",
            border=ft.border.all(1.5, border_col),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            on_click=lambda e, prod_id=pid: open_fullscreen_editor(prod_id),
            content=inner,
        )
        img_map[pid] = holder
        return holder

    # ==========================================================================
    # ۱. تایید دو مرحله‌ای (۲ بار سوال پرسیدن) برای برگرداندن تغییر در لاگ ادمین‌ها (Undo)
    # ==========================================================================
    def ask_two_step_undo_confirmation(log_entry: dict):
        if backend.config.get("edit_locked"):
            show_snack("🔒 قفل امنیت ویرایش فعال است! ابتدا قفل بالای صفحه را باز کنید.", "#DC2626")
            return

        lid = log_entry["id"]
        pname = log_entry.get("product_name", "")
        adm = log_entry.get("admin", "")
        old_st = log_entry.get("old_stock", 0)
        new_st = log_entry.get("new_stock", 0)
        old_pr = format_price(log_entry.get("old_reg_price", 0))
        new_pr = format_price(log_entry.get("new_reg_price", 0))

        def open_step_two_dialog(e):
            dlg_step1.open = False
            page.update()

            def execute_final_undo(ev):
                dlg_step2.open = False
                page.update()

                def _task():
                    if backend.undo_admin_log_entry(lid):
                        show_snack(
                            f"↩️ تایید دو مرحله‌ای انجام شد: «{pname}» به قیمت و موجودی قبلی برگشت!"
                        )
                        if current_bottom_nav[0] == 1:
                            build_admin_logs_view()
                        else:
                            rebuild_inventory_screen()

                run_in_bg(_task)

            dlg_step2 = ft.AlertDialog(
                title=ft.Text(
                    "🚨 تایید نهایی (مرحله ۲ از ۲) - واقعاً مطمئن هستید؟",
                    size=14,
                    weight=ft.FontWeight.BOLD,
                    color="#DC2626",
                ),
                content=ft.Column(
                    tight=True,
                    spacing=6,
                    controls=[
                        ft.Text(
                            f"با زدن دکمه زیر، اطلاعات کالای «{pname}» در سایت به حالت قبل برمی‌گردد:",
                            size=12,
                        ),
                        ft.Container(
                            padding=10,
                            border_radius=10,
                            bgcolor="#FEF2F2",
                            border=ft.border.all(1, "#FCA5A5"),
                            content=ft.Column(
                                spacing=4,
                                controls=[
                                    ft.Text(
                                        f"🔢 موجودی از {new_st} عدد ⬅️ برمی‌گردد به: {old_st} عدد",
                                        size=12,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Text(
                                        f"💰 قیمت از {new_pr} ت ⬅️ برمی‌گردد به: {old_pr} تومان",
                                        size=12,
                                        weight=ft.FontWeight.BOLD,
                                        color="#0F766E",
                                    ),
                                ],
                            ),
                        ),
                    ],
                ),
                actions=[
                    ft.ElevatedButton(
                        "✔️ بله، ۱۰۰٪ مطمئنم، همین الان برگردان!",
                        bgcolor="#DC2626",
                        color="white",
                        on_click=execute_final_undo,
                    ),
                    ft.TextButton(
                        "انصراف",
                        on_click=lambda ev: (
                            setattr(dlg_step2, "open", False),
                            page.update(),
                        ),
                    ),
                ],
            )
            page.dialog = dlg_step2
            dlg_step2.open = True
            page.update()

        dlg_step1 = ft.AlertDialog(
            title=ft.Text(
                "⚠️ سوال اول (مرحله ۱ از ۲): بازگرداندن تغییر ادمین",
                size=14,
                weight=ft.FontWeight.BOLD,
                color="#B45309",
            ),
            content=ft.Text(
                f"آیا می‌خواهید تغییری که توسط ادمین «{adm}» روی کالای «{pname}» انجام شده را به حالت قبلی برگردانید؟",
                size=12,
            ),
            actions=[
                ft.ElevatedButton(
                    "بله، ادامه به مرحله تایید نهایی (۲)",
                    bgcolor="#D97706",
                    color="white",
                    on_click=open_step_two_dialog,
                ),
                ft.TextButton(
                    "خیر، منصرف شدم",
                    on_click=lambda e: (
                        setattr(dlg_step1, "open", False),
                        page.update(),
                    ),
                ),
            ],
        )
        page.dialog = dlg_step1
        dlg_step1.open = True
        page.update()

    # ==========================================================================
    # ۲. پنجره «📜 مشاهده تمام آپدیت‌های کالا به تفکیک تاریخ و ساعت دقیق»
    # ==========================================================================
    def show_full_product_logs_dialog(p: dict):
        pid = p["id"]
        pname = p.get("name", "")
        all_prod_logs = [
            lg for lg in backend.admin_logs if int(lg.get("product_id", 0)) == int(pid)
        ]

        history_col = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, tight=True)
        if not all_prod_logs:
            history_col.controls.append(
                ft.Text("هیچ سابقه آپدیتی برای این کالا ثبت نشده است.", size=12)
            )
        else:
            for idx, lg in enumerate(all_prod_logs, start=1):
                note_part = f" | یادداشت: {lg['note']}" if lg.get("note") else ""
                history_col.controls.append(
                    ft.Container(
                        padding=10,
                        border_radius=10,
                        bgcolor="#F8FAFC",
                        border=ft.border.all(1, "#CBD5E1"),
                        content=ft.Column(
                            spacing=4,
                            controls=[
                                ft.Row(
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    controls=[
                                        ft.Text(
                                            f"#{idx} 👤 {lg.get('admin')}",
                                            size=11,
                                            weight=ft.FontWeight.BOLD,
                                            color="#0F766E",
                                        ),
                                        ft.Text(
                                            f"📅 {lg.get('jalali_time')}",
                                            size=10,
                                            color="#334155",
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                    ],
                                ),
                                ft.Text(
                                    f"🛠️ {lg.get('action_type')}{note_part}",
                                    size=11,
                                    color="#0284C7",
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Text(
                                    f"🔢 موجودی: {lg.get('old_stock')} عدد ⬅️ {lg.get('new_stock')} عدد",
                                    size=11,
                                ),
                                ft.Text(
                                    f"💰 قیمت عادی: {format_price(lg.get('old_reg_price'))} ت ⬅️ {format_price(lg.get('new_reg_price'))} ت",
                                    size=11,
                                    color="#15803D",
                                    weight=ft.FontWeight.BOLD,
                                ),
                            ],
                        ),
                    )
                )

        dlg_hist = ft.AlertDialog(
            title=ft.Text(
                f"📜 تمام تاریخچه آپدیت‌های «{pname}» ({len(all_prod_logs)} مورد)",
                size=13,
                weight=ft.FontWeight.BOLD,
            ),
            content=ft.Container(width=360, height=360, content=history_col),
            actions=[
                ft.ElevatedButton(
                    "🔙 بازگشت به بررسی کالا",
                    bgcolor="#0F766E",
                    color="white",
                    on_click=lambda e: (
                        setattr(dlg_hist, "open", False),
                        show_inspect_dialog(p),
                    ),
                ),
                ft.TextButton(
                    "بستن",
                    on_click=lambda e: (setattr(dlg_hist, "open", False), page.update()),
                ),
            ],
        )
        page.dialog = dlg_hist
        dlg_hist.open = True
        page.update()

    # ==========================================================================
    # ۳. پنجره «🔍 بررسی کالا» (نمایش فقط آخرین لاگ + دکمه لاگ‌های بیشتر)
    # ==========================================================================
    def show_inspect_dialog(p: dict):
        pid = p["id"]
        pname = p.get("name", "")
        psku = p.get("sku", "-")
        mod_raw = p.get("date_modified", "")
        crt_raw = p.get("date_created", "")
        time_ago_txt = calc_time_ago_fa(mod_raw)
        exact_jalali_mod = gregorian_to_jalali_full(mod_raw, include_seconds=True)
        exact_jalali_crt = gregorian_to_jalali_full(crt_raw, include_seconds=False)
        last_adm = p.get("last_admin", "ثبت نشده")
        is_nis = bool(p.get("not_in_store", False))
        nis_reason = p.get("not_in_store_reason", "")

        # استخراج کل لاگ‌های این کالا، اما نمایش فقط آخرین لاگ (۱ مورد اول)
        all_prod_logs = [
            lg for lg in backend.admin_logs if int(lg.get("product_id", 0)) == int(pid)
        ]

        latest_log_box = ft.Container()
        if all_prod_logs:
            lg = all_prod_logs[0]
            latest_log_box = ft.Container(
                padding=8,
                border_radius=10,
                bgcolor="#F8FAFC",
                border=ft.border.all(1, "#CBD5E1"),
                content=ft.Column(
                    spacing=3,
                    controls=[
                        ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                ft.Text(
                                    f"👤 {lg['admin']}",
                                    size=11,
                                    weight=ft.FontWeight.BOLD,
                                    color="#0F766E",
                                ),
                                ft.Text(
                                    f"🕒 {lg['jalali_time']}",
                                    size=10,
                                    color="#475569",
                                ),
                            ],
                        ),
                        ft.Text(
                            f"🛠️ {lg['action_type']}",
                            size=11,
                            color="#0284C7",
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            f"🔢 موجودی: {lg['old_stock']}⬅️{lg['new_stock']} | 💰 قیمت: {format_price(lg['old_reg_price'])}⬅️{format_price(lg['new_reg_price'])} ت",
                            size=11,
                            color="#1E293B",
                        ),
                    ],
                ),
            )
        else:
            latest_log_box = ft.Text(
                "هنوز لاگ ویرایشی برای این کالا ثبت نشده است.",
                size=11,
                color="#94A3B8",
            )

        reason_tf = ft.TextField(
            label="علت اختیاری (فقط اگر مایلید بنویسید)",
            value=nis_reason,
            dense=True,
            text_size=11,
        )

        def set_quick_reason(txt_r: str):
            reason_tf.value = txt_r
            page.update()

        def on_toggle_nis(e):
            if backend.config.get("edit_locked"):
                show_snack("🔒 قفل امنیت ویرایش فعال است!", "#DC2626")
                return
            dlg.open = False
            page.update()
            target_nis = not is_nis

            def _task():
                backend.save_product_full_edit(
                    product_id=pid,
                    new_stock=0,
                    stock_mode="outofstock",
                    regular_price=p.get("regular_price", "0"),
                    sale_price=p.get("sale_price", ""),
                    not_in_store=target_nis,
                    not_in_store_reason=reason_tf.value.strip(),
                    action_label="🚫 انتقال به در فروشگاه موجود نیست"
                    if target_nis
                    else "♻️ بازگرداندن به لیست ناموجودها",
                )
                show_snack(
                    "🚫 کالا به تب «در فروشگاه موجود نیست» منتقل شد."
                    if target_nis
                    else "♻️ کالا به لیست ناموجودها بازگردانده شد."
                )
                rebuild_inventory_screen()

            run_in_bg(_task)

        dlg = ft.AlertDialog(
            title=ft.Text(f"🔍 بررسی کالا: {pname}", size=13, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=360,
                content=ft.Column(
                    tight=True,
                    spacing=7,
                    controls=[
                        ft.Container(
                            padding=10,
                            border_radius=12,
                            bgcolor="#FEF2F2"
                            if int(p.get("stock_quantity") or 0) <= 0
                            else "#F0FDFA",
                            border=ft.border.all(
                                1,
                                "#FCA5A5"
                                if int(p.get("stock_quantity") or 0) <= 0
                                else "#5EEAD4",
                            ),
                            content=ft.Column(
                                spacing=3,
                                controls=[
                                    ft.Text(
                                        f"⏰ زمان تغییر/اتمام: {time_ago_txt}",
                                        size=12,
                                        weight=ft.FontWeight.BOLD,
                                        color="#DC2626"
                                        if int(p.get("stock_quantity") or 0) <= 0
                                        else "#0F766E",
                                    ),
                                    ft.Text(
                                        f"📅 تاریخ و ساعت دقیق: {exact_jalali_mod}",
                                        size=11,
                                        color="#1E293B",
                                    ),
                                    ft.Text(
                                        f"👤 آخرین ادمین: {last_adm} | ثبت اولیه: {exact_jalali_crt[:10]}",
                                        size=10,
                                        color="#64748B",
                                    ),
                                ],
                            ),
                        ),
                        ft.Text(
                            "🕘 آخرین لاگ ثبت‌شده روی این کالا:",
                            size=11,
                            weight=ft.FontWeight.BOLD,
                        ),
                        latest_log_box,
                        ft.Container(
                            width=float("inf"),
                            content=ft.OutlinedButton(
                                f"📜 مشاهده لاگ‌های بیشتر ({len(all_prod_logs)} آپدیت به تاریخ و ساعت)",
                                height=32,
                                on_click=lambda e: (
                                    setattr(dlg, "open", False),
                                    show_full_product_logs_dialog(p),
                                ),
                            ),
                        ),
                        ft.Divider(height=4),
                        ft.Row(
                            spacing=4,
                            wrap=True,
                            controls=[
                                ft.OutlinedButton(
                                    "شرکت پخش ندارد",
                                    height=26,
                                    on_click=lambda e: set_quick_reason(
                                        "شرکت پخش ندارد"
                                    ),
                                ),
                                ft.OutlinedButton(
                                    "توقف تولید",
                                    height=26,
                                    on_click=lambda e: set_quick_reason("توقف تولید"),
                                ),
                                ft.OutlinedButton(
                                    "در راه است",
                                    height=26,
                                    on_click=lambda e: set_quick_reason(
                                        "سفارش دادیم در راه است"
                                    ),
                                ),
                            ],
                        ),
                        reason_tf,
                        ft.Container(
                            width=float("inf"),
                            content=ft.ElevatedButton(
                                "♻️ بازگرداندن به لیست ناموجودها"
                                if is_nis
                                else "🚫 انتقال به «در فروشگاه موجود نیست»",
                                bgcolor="#0284C7" if is_nis else "#475569",
                                color="white",
                                height=34,
                                on_click=on_toggle_nis,
                            ),
                        ),
                    ],
                ),
            ),
            actions=[
                ft.ElevatedButton(
                    "✏️ صفحه کامل ویرایش",
                    bgcolor="#0F766E",
                    color="white",
                    on_click=lambda e: (
                        setattr(dlg, "open", False),
                        open_fullscreen_editor(pid),
                    ),
                ),
                ft.TextButton(
                    "بستن",
                    on_click=lambda e: (setattr(dlg, "open", False), page.update()),
                ),
            ],
        )
        page.dialog = dlg
        dlg.open = True
        page.update()

    # ==========================================================================
    # ۴. پنجره مدیریت وزن‌ها و مدل‌ها برای کالاهای متغیر
    # ==========================================================================
    def show_variations_dialog(p: dict):
        pid = p["id"]
        title = p.get("name", "")
        vars_list = backend.get_product_variations(pid)
        vars_col = ft.Column(spacing=8, tight=True, scroll=ft.ScrollMode.AUTO)

        for v in vars_list:
            vid = v["id"]
            vname = v.get("name", f"مدل #{vid}")
            st_in = ft.TextField(
                label="موجودی",
                value=str(v.get("stock_quantity", 0)),
                width=75,
                dense=True,
                text_size=11,
            )
            rg_in = ft.TextField(
                label="قیمت عادی",
                value=str(v.get("regular_price", "")),
                expand=True,
                dense=True,
                text_size=11,
            )
            sl_in = ft.TextField(
                label="قیمت ویژه",
                value=str(v.get("sale_price", "")),
                expand=True,
                dense=True,
                text_size=11,
            )

            def make_save_var(var_id, s_tf, r_tf, sl_tf, v_title):
                def _sv(e):
                    def _task():
                        if backend.update_single_variation(
                            pid,
                            var_id,
                            int(fa_to_en_digits(s_tf.value) or 0),
                            r_tf.value,
                            sl_tf.value,
                        ):
                            show_snack(f"✔️ مدل «{v_title}» بروزرسانی شد.")

                    run_in_bg(_task)

                return _sv

            vars_col.controls.append(
                ft.Container(
                    padding=8,
                    border_radius=10,
                    bgcolor="#F8FAFC",
                    border=ft.border.all(1, "#CBD5E1"),
                    content=ft.Column(
                        spacing=4,
                        controls=[
                            ft.Text(f"⚖️ {vname}", size=12, weight=ft.FontWeight.BOLD),
                            ft.Row(spacing=4, controls=[st_in, rg_in, sl_in]),
                            ft.Container(
                                width=float("inf"),
                                content=ft.ElevatedButton(
                                    "💾 ذخیره این وزن/مدل",
                                    bgcolor="#0F766E",
                                    color="white",
                                    height=30,
                                    on_click=make_save_var(
                                        vid, st_in, rg_in, sl_in, vname
                                    ),
                                ),
                            ),
                        ],
                    ),
                )
            )

        dlg_v = ft.AlertDialog(
            title=ft.Text(
                f"⚖️ وزن‌ها و مدل‌های «{title}»", size=13, weight=ft.FontWeight.BOLD
            ),
            content=ft.Container(width=360, height=320, content=vars_col),
            actions=[
                ft.TextButton(
                    "بستن",
                    on_click=lambda e: (setattr(dlg_v, "open", False), page.update()),
                )
            ],
        )
        page.dialog = dlg_v
        dlg_v.open = True
        page.update()

    # ==========================================================================
    # ۵. 🖥️ صفحه کامل ویرایش کالا (مدل ۳ - رفع هر ۶ باگ تخصصی)
    # ==========================================================================
    fullscreen_editor_container = ft.Container(
        expand=True, bgcolor="white", padding=12
    )

    def close_fullscreen_editor(e=None):
        is_in_fullscreen_editor[0] = False
        a35_bottom_bar.visible = True
        # بازگشت دقیق به همان تبی که کاربر از آن وارد ویرایش شده بود (رفع باگ ویرایش مجدد کالا)
        switch_bottom_nav(return_to_nav_idx[0])

    def open_fullscreen_editor(product_id: int, from_nav_idx: int = None):
        if backend.config.get("edit_locked"):
            show_snack(
                "🔒 قفل امنیت ویرایش فعال است! ابتدا قفل بالای صفحه را باز کنید.",
                "#DC2626",
            )
            return

        p = backend.get_product_by_id(product_id)
        if not p:
            show_snack("کالا در لیست یافت نشد!", "#DC2626")
            return

        if not is_in_fullscreen_editor[0]:
            return_to_nav_idx[0] = (
                from_nav_idx if from_nav_idx is not None else current_bottom_nav[0]
            )

        is_in_fullscreen_editor[0] = True
        a35_bottom_bar.visible = False  # مخفی شدن منوی پایین برای باز شدن فضای کامل مدل ۳

        pid = p["id"]
        pname = p.get("name", "")
        psku = p.get("sku", "-")
        ptype = p.get("type", "simple")
        img_url = p.get("image_url", "")
        cur_qty = int(p.get("stock_quantity") or 0)
        cur_status = p.get("stock_status", "outofstock")
        cur_managed = bool(p.get("manage_stock", True))
        old_reg_float = float(fa_to_en_digits(p.get("regular_price") or "0") or 0)
        is_nis = bool(p.get("not_in_store", False))

        if pid in current_filtered_ids:
            pos_idx = current_filtered_ids.index(pid)
            total_in_list = len(current_filtered_ids)
        else:
            pos_idx = 0
            total_in_list = max(1, len(current_filtered_ids))

        def go_adjacent(delta: int):
            if not current_filtered_ids:
                return
            new_idx = (pos_idx + delta) % len(current_filtered_ids)
            open_fullscreen_editor(
                current_filtered_ids[new_idx], from_nav_idx=return_to_nav_idx[0]
            )

        # تشخیص دقیق وضعیت فعلی کالا تا با باز کردن ویرایش، وضعیتش ناخواسته عوض نشود
        if cur_status == "instock" and not cur_managed:
            initial_st_mode = "instock_unmanaged"
        elif cur_status == "instock" and cur_qty > 0:
            initial_st_mode = "instock_count"
        else:
            initial_st_mode = "outofstock"

        stock_mode_val = [initial_st_mode]

        stock_tf = ft.TextField(
            label="تعداد موجودی",
            value=str(cur_qty if cur_qty > 0 else 15),
            width=105,
            dense=True,
            text_size=15,
            text_align=ft.TextAlign.CENTER,
        )

        reg_tf = ft.TextField(
            label="💰 قیمت فروش عادی (تومان)",
            value=str(p.get("regular_price", "")),
            dense=True,
            text_size=15,
        )

        price_words_txt = ft.Text(
            number_to_persian_words(
                p.get("regular_price", "0"), backend.config.get("is_rial")
            ),
            size=12,
            color="#0F766E",
            weight=ft.FontWeight.BOLD,
        )

        zero_warning_box = ft.Container(
            visible=False,
            padding=8,
            border_radius=8,
            bgcolor="#FEF3C7",
            border=ft.border.all(1, "#FDE68A"),
            content=ft.Text(
                "⚠️ هشدار محافظ قیمت: قیمت جدید بیش از ۲ برابر با قیمت قبلی تفاوت دارد! صفرها را چک کنید.",
                size=11,
                color="#B45309",
                weight=ft.FontWeight.BOLD,
            ),
        )

        sale_tf = ft.TextField(
            label="🏷️ قیمت فروش ویژه (خالی = بدون تخفیف)",
            value=str(p.get("sale_price", "")),
            dense=True,
            text_size=14,
        )

        sale_words_txt = ft.Text(
            number_to_persian_words(
                p.get("sale_price", "0"), backend.config.get("is_rial")
            )
            if p.get("sale_price")
            else "بدون قیمت فروش ویژه",
            size=11,
            color="#0284C7",
        )

        def on_reg_price_change(e):
            clean_v = fa_to_en_digits(reg_tf.value)
            price_words_txt.value = number_to_persian_words(
                clean_v, backend.config.get("is_rial")
            )
            try:
                new_f = float(clean_v or 0)
                if old_reg_float > 0 and (
                    new_f >= old_reg_float * 2.0
                    or (new_f > 0 and new_f <= old_reg_float * 0.45)
                ):
                    zero_warning_box.visible = True
                else:
                    zero_warning_box.visible = False
            except Exception:
                zero_warning_box.visible = False
            page.update()

        def on_sale_price_change(e):
            clean_s = fa_to_en_digits(sale_tf.value)
            sale_words_txt.value = (
                number_to_persian_words(clean_s, backend.config.get("is_rial"))
                if clean_s and int(float(clean_s or 0)) > 0
                else "بدون قیمت فروش ویژه"
            )
            page.update()

        reg_tf.on_change = on_reg_price_change
        sale_tf.on_change = on_sale_price_change

        img_tf = ft.TextField(
            label="🖼️ لینک یا مسیر تصویر کالا",
            value=img_url,
            dense=True,
            text_size=11,
            expand=True,
        )

        nis_checkbox = ft.Checkbox(
            label="🚫 انتقال به تب «در فروشگاه موجود نیست» (خلوت کردن ناموجودها)",
            value=is_nis,
        )
        nis_reason_tf = ft.TextField(
            label="علت اختیاری (مثلاً: شرکت پخش ندارد / توقف تولید)",
            value=p.get("not_in_store_reason", ""),
            dense=True,
            text_size=11,
        )

        stepper_row = ft.Row(
            spacing=6,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        btn_mode_count = ft.ElevatedButton(
            "🔢 موجود با تعداد", expand=True, height=34
        )
        btn_mode_unmanaged = ft.ElevatedButton(
            "🟢 موجود (بدون عدد)", expand=True, height=34
        )
        btn_mode_oos = ft.ElevatedButton(
            "✖️ ناموجود (۰)", expand=True, height=34
        )

        def refresh_mode_buttons_style():
            m_name = stock_mode_val[0]
            btn_mode_count.bgcolor = (
                "#0F766E" if m_name == "instock_count" else "#E2E8F0"
            )
            btn_mode_count.color = (
                "white" if m_name == "instock_count" else "#334155"
            )

            btn_mode_unmanaged.bgcolor = (
                "#16A34A" if m_name == "instock_unmanaged" else "#E2E8F0"
            )
            btn_mode_unmanaged.color = (
                "white" if m_name == "instock_unmanaged" else "#334155"
            )

            btn_mode_oos.bgcolor = "#DC2626" if m_name == "outofstock" else "#FEE2E2"
            btn_mode_oos.color = "white" if m_name == "outofstock" else "#DC2626"

            stepper_row.visible = m_name == "instock_count"

        def set_editor_stock_mode(m_name: str):
            stock_mode_val[0] = m_name
            if m_name == "outofstock":
                stock_tf.value = "0"
            elif m_name == "instock_count":
                nis_checkbox.value = False
                if int(fa_to_en_digits(stock_tf.value) or 0) <= 0:
                    stock_tf.value = "15"
            elif m_name == "instock_unmanaged":
                nis_checkbox.value = False
            refresh_mode_buttons_style()
            page.update()

        btn_mode_count.on_click = lambda e: set_editor_stock_mode("instock_count")
        btn_mode_unmanaged.on_click = lambda e: set_editor_stock_mode(
            "instock_unmanaged"
        )
        btn_mode_oos.on_click = lambda e: set_editor_stock_mode("outofstock")
        refresh_mode_buttons_style()

        def add_stock_val(delta: int):
            stock_mode_val[0] = "instock_count"
            nis_checkbox.value = False
            cur_v = int(fa_to_en_digits(stock_tf.value) or 0)
            stock_tf.value = str(max(1, cur_v + delta))
            refresh_mode_buttons_style()
            page.update()

        stepper_row.controls = [
            ft.OutlinedButton(
                "-1", width=48, height=36, on_click=lambda e: add_stock_val(-1)
            ),
            stock_tf,
            ft.OutlinedButton(
                "+1", width=48, height=36, on_click=lambda e: add_stock_val(1)
            ),
            ft.ElevatedButton(
                "+5",
                bgcolor="#CCFBF1",
                color="#0F766E",
                width=52,
                height=36,
                on_click=lambda e: add_stock_val(5),
            ),
            ft.ElevatedButton(
                "+10",
                bgcolor="#CCFBF1",
                color="#0F766E",
                width=56,
                height=36,
                on_click=lambda e: add_stock_val(10),
            ),
        ]

        def apply_disc_pct(pct: int):
            try:
                bp = float(fa_to_en_digits(reg_tf.value) or 0)
                if bp > 0:
                    disc_val = int(round(bp * (100 - pct) / 100.0, -2))
                    sale_tf.value = str(disc_val)
                    on_sale_price_change(None)
            except Exception:
                pass

        def on_pick_gallery_img(e):
            selected_gallery_target["callback"] = lambda path_s: (
                setattr(img_tf, "value", path_s),
                page.update(),
            )
            file_picker.pick_files(allow_multiple=False)

        def save_and_finish(go_next: bool, force_instock_now: bool = False):
            if force_instock_now and stock_mode_val[0] == "outofstock":
                stock_mode_val[0] = "instock_count"
                nis_checkbox.value = False
                if int(fa_to_en_digits(stock_tf.value) or 0) <= 0:
                    stock_tf.value = "15"

            qty_int = int(fa_to_en_digits(stock_tf.value) or 0)
            clean_r = fa_to_en_digits(reg_tf.value) or "0"
            clean_s = fa_to_en_digits(sale_tf.value)
            if clean_s and float(clean_s) >= float(clean_r) and float(clean_r) > 0:
                show_snack(
                    "⚠️ قیمت فروش ویژه نمی‌تواند بیشتر یا مساوی قیمت عادی باشد!",
                    "#DC2626",
                )
                return

            next_target_id = None
            if go_next and current_filtered_ids:
                for cand_id in current_filtered_ids:
                    if cand_id != pid:
                        next_target_id = cand_id
                        break

            def _task():
                ok = backend.save_product_full_edit(
                    product_id=pid,
                    new_stock=0 if nis_checkbox.value else qty_int,
                    stock_mode="outofstock"
                    if nis_checkbox.value
                    else stock_mode_val[0],
                    regular_price=clean_r,
                    sale_price=clean_s,
                    not_in_store=bool(nis_checkbox.value),
                    not_in_store_reason=nis_reason_tf.value.strip(),
                    new_image_url=img_tf.value.strip(),
                )
                if ok:
                    show_snack(
                        f"✔️ «{pname}» توسط [{backend.config.get('current_admin')}] ذخیره شد!"
                    )
                    if go_next and next_target_id:
                        open_fullscreen_editor(
                            next_target_id, from_nav_idx=return_to_nav_idx[0]
                        )
                    else:
                        close_fullscreen_editor()

            run_in_bg(_task)

        b64_img = fetch_image_as_base64(img_url) if img_url else ""
        big_img_widget = (
            ft.Image(src_base64=b64_img, width=96, height=96, fit=ft.ImageFit.COVER)
            if b64_img
            else (
                ft.Image(src=img_url, width=96, height=96, fit=ft.ImageFit.COVER)
                if img_url
                else ft.Container(
                    alignment=ft.alignment.center,
                    bgcolor="#FEF2F2",
                    content=ft.Text("بدون عکس", size=11, color="#DC2626"),
                )
            )
        )

        variations_btn_holder = (
            ft.Container(
                width=float("inf"),
                content=ft.OutlinedButton(
                    "⚖️ مدیریت جداگانه وزن‌ها و مدل‌های این کالا",
                    height=34,
                    on_click=lambda e: show_variations_dialog(p),
                ),
            )
            if ptype == "variable"
            else ft.Container()
        )

        fullscreen_editor_container.content = ft.Column(
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            controls=[
                # نوار بالای صفحه کامل ویرایش (مدل ۳)
                ft.Container(
                    padding=ft.padding.symmetric(horizontal=8, vertical=6),
                    border_radius=12,
                    bgcolor="#F8FAFC",
                    border=ft.border.all(1, "#E2E8F0"),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Row(
                                spacing=4,
                                controls=[
                                    ft.OutlinedButton(
                                        "➡️ قبلی",
                                        height=30,
                                        on_click=lambda e: go_adjacent(-1),
                                    ),
                                    ft.Text(
                                        f"({pos_idx + 1} از {total_in_list})",
                                        size=11,
                                        weight=ft.FontWeight.BOLD,
                                        color="#0F766E",
                                    ),
                                    ft.OutlinedButton(
                                        "بعدی ⬅️",
                                        height=30,
                                        on_click=lambda e: go_adjacent(1),
                                    ),
                                ],
                            ),
                            ft.ElevatedButton(
                                "برگشت ✕",
                                bgcolor="#FEE2E2",
                                color="#DC2626",
                                height=30,
                                on_click=close_fullscreen_editor,
                            ),
                        ],
                    ),
                ),
                # مشخصات و عکس بزرگ کالا
                ft.Row(
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(
                            width=96,
                            height=96,
                            border_radius=16,
                            border=ft.border.all(2, "#0F766E"),
                            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                            content=big_img_widget,
                        ),
                        ft.Column(
                            expand=True,
                            spacing=3,
                            controls=[
                                ft.Text(
                                    pname,
                                    size=13,
                                    weight=ft.FontWeight.BOLD,
                                    color="#0F172A",
                                ),
                                ft.Text(
                                    f"بارکد: {psku} | وضعیت فعلی: {'موجود' if cur_status == 'instock' else 'ناموجود'}",
                                    size=11,
                                    color="#64748B",
                                ),
                                ft.Text(
                                    f"⏰ آخرین تغییر: {calc_time_ago_fa(p.get('date_modified', ''))}",
                                    size=11,
                                    color="#DC2626"
                                    if cur_status != "instock"
                                    else "#0F766E",
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Text(
                                    f"👤 ادمین: {backend.config.get('current_admin')}",
                                    size=11,
                                    color="#0284C7",
                                ),
                            ],
                        ),
                    ],
                ),
                variations_btn_holder,
                ft.Divider(height=4),
                ft.Text(
                    "۱. تعیین وضعیت موجودی انبار:",
                    size=11,
                    weight=ft.FontWeight.BOLD,
                    color="#334155",
                ),
                ft.Row(
                    spacing=5,
                    controls=[btn_mode_count, btn_mode_unmanaged, btn_mode_oos],
                ),
                stepper_row,
                ft.Text(
                    "۲. تنظیم قیمت عادی و فروش ویژه:",
                    size=11,
                    weight=ft.FontWeight.BOLD,
                    color="#334155",
                ),
                reg_tf,
                price_words_txt,
                zero_warning_box,
                ft.Row(
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text("تخفیف سریع:", size=11, color="#64748B"),
                        ft.OutlinedButton(
                            "5%", height=28, on_click=lambda e: apply_disc_pct(5)
                        ),
                        ft.OutlinedButton(
                            "10%", height=28, on_click=lambda e: apply_disc_pct(10)
                        ),
                        ft.OutlinedButton(
                            "15%", height=28, on_click=lambda e: apply_disc_pct(15)
                        ),
                    ],
                ),
                sale_tf,
                sale_words_txt,
                ft.Row(
                    spacing=6,
                    controls=[
                        img_tf,
                        ft.OutlinedButton(
                            "📂 گالری", height=36, on_click=on_pick_gallery_img
                        ),
                    ],
                ),
                ft.Container(
                    padding=8,
                    border_radius=10,
                    bgcolor="#F8FAFC",
                    border=ft.border.all(1, "#CBD5E1"),
                    content=ft.Column(
                        spacing=4,
                        controls=[nis_checkbox, nis_reason_tf],
                    ),
                ),
                # دکمه‌های ذخیره (هم حفظ وضعیت فعلی و هم موجود کردن فوری + رفتن به بعدی)
                ft.Container(
                    width=float("inf"),
                    content=ft.ElevatedButton(
                        "🟢 موجود کن و در سایت ذخیره کن",
                        bgcolor="#16A34A",
                        color="white",
                        height=40,
                        on_click=lambda e: save_and_finish(
                            go_next=False, force_instock_now=True
                        ),
                    ),
                ),
                ft.Row(
                    spacing=6,
                    controls=[
                        ft.ElevatedButton(
                            "💾 ذخیره همین وضعیت",
                            bgcolor="#0F766E",
                            color="white",
                            expand=True,
                            height=38,
                            on_click=lambda e: save_and_finish(
                                go_next=False, force_instock_now=False
                            ),
                        ),
                        ft.ElevatedButton(
                            "⏭️ موجود کن و برو بعدی",
                            bgcolor="#2563EB",
                            color="white",
                            expand=True,
                            height=38,
                            on_click=lambda e: save_and_finish(
                                go_next=True, force_instock_now=True
                            ),
                        ),
                    ],
                ),
                # فضای خالی هوشمند برای کیبورد در گوشی‌های اندروید
                ft.Container(height=60),
            ],
        )

        mobile_body_holder.content = fullscreen_editor_container
        page.update()

    # ==========================================================================
    # صفحه اصلی ۱: موجودی و کالاها (مدل ۱: کارت افقی + دسته‌بندی کپسولی + ۴ تب بالا)
    # ==========================================================================
    tab_btn_oos = ft.Container(
        expand=True, padding=6, border_radius=10, alignment=ft.alignment.center
    )
    tab_btn_nis = ft.Container(
        expand=True, padding=6, border_radius=10, alignment=ft.alignment.center
    )
    tab_btn_low = ft.Container(
        expand=True, padding=6, border_radius=10, alignment=ft.alignment.center
    )
    tab_btn_in = ft.Container(
        expand=True, padding=6, border_radius=10, alignment=ft.alignment.center
    )

    search_tf = ft.TextField(
        label="🔍 جستجوی نام کالا یا بارکد...",
        dense=True,
        text_size=12,
        expand=True,
        on_change=lambda e: rebuild_inventory_screen(),
    )

    sort_dd = ft.Dropdown(
        value="newest",
        width=112,
        dense=True,
        text_size=11,
        options=[
            ft.dropdown.Option("newest", "جدیدترین"),
            ft.dropdown.Option("oldest", "قدیمی‌ترین"),
            ft.dropdown.Option("price_desc", "گران‌ترین"),
            ft.dropdown.Option("price_asc", "ارزان‌ترین"),
        ],
        on_change=lambda e: rebuild_inventory_screen(),
    )

    capsule_cats_row = ft.Row(spacing=6, scroll=ft.ScrollMode.AUTO)

    warning_alert_banner = ft.Container(
        visible=False,
        padding=ft.padding.symmetric(horizontal=10, vertical=6),
        border_radius=10,
        bgcolor="#FEF3C7",
        border=ft.border.all(1.5, "#F59E0B"),
    )

    cards_list_col = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)

    def switch_stock_tab(tab_key: str):
        current_stock_tab[0] = tab_key
        rebuild_inventory_screen()

    def select_capsule_cat(cat_key: str):
        current_cat_id[0] = cat_key
        rebuild_inventory_screen()

    def rebuild_inventory_screen():
        all_prods = backend.get_all_cached_or_live_products(force_network=False)
        low_limit = int(backend.config.get("low_stock_threshold", 5))
        is_rial = backend.config.get("is_rial", False)

        oos_list, nis_list, low_list, in_list, warn_list = [], [], [], [], []

        for p in all_prods:
            qty = int(p.get("stock_quantity") or 0)
            st = p.get("stock_status", "outofstock")
            managed = bool(p.get("manage_stock", True))
            nis = bool(p.get("not_in_store", False))
            reg_val = float(fa_to_en_digits(p.get("regular_price") or "0") or 0)
            has_img = bool(p.get("image_url", "").strip())

            if not has_img or reg_val <= 1000:
                warn_list.append(p)

            if nis:
                nis_list.append(p)
            elif st == "outofstock" or (managed and qty <= 0):
                oos_list.append(p)
            elif managed and 0 < qty <= low_limit:
                low_list.append(p)
                in_list.append(p)
            else:
                in_list.append(p)

        if warn_list:
            no_img_cnt = sum(
                1 for x in warn_list if not x.get("image_url", "").strip()
            )
            no_prc_cnt = sum(
                1
                for x in warn_list
                if float(fa_to_en_digits(x.get("regular_price") or "0") or 0) <= 1000
            )
            warning_alert_banner.visible = True
            warning_alert_banner.content = ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Text(
                        f"⚠️ هشدار: {no_img_cnt} بدون عکس | {no_prc_cnt} بدون قیمت",
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color="#B45309",
                    ),
                    ft.ElevatedButton(
                        "مشاهده و اصلاح",
                        bgcolor="#D97706",
                        color="white",
                        height=26,
                        on_click=lambda e: switch_stock_tab("warnings"),
                    ),
                ],
            )
        else:
            warning_alert_banner.visible = False

        t_mode = current_stock_tab[0]

        def style_top_tab(
            container_ctrl, title_str, count_n, key_name, active_bg, active_fg
        ):
            is_act = t_mode == key_name
            container_ctrl.bgcolor = active_bg if is_act else "#F8FAFC"
            container_ctrl.border = ft.border.all(
                1.5 if is_act else 1, active_fg if is_act else "#E2E8F0"
            )
            container_ctrl.on_click = lambda e, k=key_name: switch_stock_tab(k)
            container_ctrl.content = ft.Column(
                spacing=1,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text(
                        title_str,
                        size=10,
                        weight=ft.FontWeight.BOLD,
                        color=active_fg if is_act else "#475569",
                    ),
                    ft.Text(
                        f"({count_n})",
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=active_fg if is_act else "#64748B",
                    ),
                ],
            )

        style_top_tab(
            tab_btn_oos, "🚨 ناموجودها", len(oos_list), "oos", "#FEE2E2", "#DC2626"
        )
        style_top_tab(
            tab_btn_nis, "🚫 موجود نیست", len(nis_list), "nis", "#E2E8F0", "#1E293B"
        )
        style_top_tab(
            tab_btn_low, "⚠️ رو به اتمام", len(low_list), "low", "#FEF3C7", "#B45309"
        )
        style_top_tab(
            tab_btn_in, "✅ موجودها", len(in_list), "instock", "#DCFCE7", "#15803D"
        )

        if t_mode == "oos":
            base_items = list(oos_list)
        elif t_mode == "nis":
            base_items = list(nis_list)
        elif t_mode == "low":
            base_items = list(low_list)
        elif t_mode == "warnings":
            base_items = list(warn_list)
        else:
            base_items = list(in_list)

        cats = backend.get_categories()
        capsule_cats_row.controls.clear()
        sel_c = current_cat_id[0]

        def make_capsule(c_key: str, c_title: str, c_cnt: int):
            act = sel_c == c_key
            return ft.Container(
                padding=ft.padding.symmetric(horizontal=10, vertical=4),
                border_radius=20,
                bgcolor="#0F766E" if act else "#F1F5F9",
                border=ft.border.all(1, "#0F766E" if act else "#CBD5E1"),
                on_click=lambda e, ck=c_key: select_capsule_cat(ck),
                content=ft.Text(
                    f"{c_title} ({c_cnt})",
                    size=11,
                    weight=ft.FontWeight.BOLD,
                    color="white" if act else "#334155",
                ),
            )

        capsule_cats_row.controls.append(
            make_capsule("all", "همه دسته‌ها", len(base_items))
        )
        for c in cats:
            cid_s = str(c["id"])
            cnt_in_cat = sum(
                1
                for x in base_items
                if any(
                    str(cat_o.get("id")) == cid_s for cat_o in x.get("categories", [])
                )
            )
            if cnt_in_cat > 0 or sel_c == cid_s:
                capsule_cats_row.controls.append(
                    make_capsule(cid_s, c["name"], cnt_in_cat)
                )

        if sel_c != "all":
            base_items = [
                p
                for p in base_items
                if any(str(c.get("id")) == sel_c for c in p.get("categories", []))
            ]

        q_str = (search_tf.value or "").strip().lower()
        if q_str:
            base_items = [
                p
                for p in base_items
                if q_str in p.get("name", "").lower()
                or q_str in str(p.get("sku", "")).lower()
            ]

        s_mode = sort_dd.value or "newest"
        if s_mode == "newest":
            base_items.sort(key=lambda x: x.get("date_modified", ""), reverse=True)
        elif s_mode == "oldest":
            base_items.sort(key=lambda x: x.get("date_modified", ""))
        elif s_mode == "price_desc":
            base_items.sort(
                key=lambda x: float(
                    fa_to_en_digits(x.get("regular_price") or "0") or 0
                ),
                reverse=True,
            )
        elif s_mode == "price_asc":
            base_items.sort(
                key=lambda x: float(
                    fa_to_en_digits(x.get("regular_price") or "0") or 0
                )
            )

        current_filtered_ids.clear()
        for x in base_items:
            current_filtered_ids.append(x["id"])

        cards_list_col.controls.clear()
        img_controls_map = {}

        if not base_items:
            cards_list_col.controls.append(
                ft.Container(
                    padding=26,
                    border_radius=16,
                    bgcolor="#DCFCE7",
                    alignment=ft.alignment.center,
                    content=ft.Text(
                        "🎉 هیچ کالایی در این بخش نیست!",
                        color="#15803D",
                        weight=ft.FontWeight.BOLD,
                        size=13,
                    ),
                )
            )
            page.update()
            return

        for p in base_items:
            pid = p["id"]
            pname = p.get("name", "بدون نام")
            psku = p.get("sku", "-")
            qty = int(p.get("stock_quantity") or 0)
            st = p.get("stock_status", "outofstock")
            managed = bool(p.get("manage_stock", True))
            nis = bool(p.get("not_in_store", False))
            nis_r = p.get("not_in_store_reason", "")
            cat_title = (
                p.get("categories", [{}])[0].get("name", "عمومی")
                if p.get("categories")
                else "عمومی"
            )
            reg_num = float(fa_to_en_digits(p.get("regular_price") or "0") or 0)

            if nis:
                pill_txt = f"🚫 موجود نیست ({nis_r or 'بایگانی'})"
                pill_bg, pill_fg, b_col = "#E2E8F0", "#334155", "#94A3B8"
            elif st == "outofstock" or (managed and qty <= 0):
                pill_txt = "ناموجود (۰)"
                pill_bg, pill_fg, b_col = "#FEE2E2", "#DC2626", "#FCA5A5"
            elif managed and qty <= low_limit:
                pill_txt = f"رو به اتمام ({qty})"
                pill_bg, pill_fg, b_col = "#FEF3C7", "#B45309", "#FDE68A"
            else:
                pill_txt = f"موجود ({qty})" if managed else "موجود"
                pill_bg, pill_fg, b_col = "#DCFCE7", "#15803D", "#86EFAC"

            price_display = (
                "⚠️ بدون قیمت!"
                if reg_num <= 0
                else f"{format_price(p.get('regular_price', 0), is_rial)} ت"
            )

            cards_list_col.controls.append(
                ft.Container(
                    padding=9,
                    border_radius=16,
                    bgcolor="white",
                    border=ft.border.all(1, "#E2E8F0"),
                    shadow=ft.BoxShadow(
                        blur_radius=5, color="#0A000000", offset=ft.Offset(0, 2)
                    ),
                    content=ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            build_product_thumbnail_m1(p, b_col, img_controls_map),
                            ft.Column(
                                expand=True,
                                spacing=3,
                                controls=[
                                    ft.Text(
                                        pname,
                                        size=12,
                                        weight=ft.FontWeight.BOLD,
                                        color="#0F172A",
                                        max_lines=1,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    ft.Text(
                                        f"{cat_title} | کد: {psku}",
                                        size=10,
                                        color="#64748B",
                                    ),
                                    ft.Row(
                                        spacing=6,
                                        wrap=True,
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                        controls=[
                                            ft.Container(
                                                padding=ft.padding.symmetric(
                                                    horizontal=6, vertical=2
                                                ),
                                                border_radius=6,
                                                bgcolor=pill_bg,
                                                content=ft.Text(
                                                    pill_txt,
                                                    color=pill_fg,
                                                    size=10,
                                                    weight=ft.FontWeight.BOLD,
                                                ),
                                            ),
                                            ft.Text(
                                                price_display,
                                                size=12,
                                                weight=ft.FontWeight.BOLD,
                                                color="#DC2626"
                                                if reg_num <= 0
                                                else "#0F766E",
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            ft.Column(
                                spacing=4,
                                controls=[
                                    ft.ElevatedButton(
                                        "✏️ ویرایش",
                                        bgcolor="#0F766E",
                                        color="white",
                                        height=30,
                                        on_click=lambda e, prod_id=pid: open_fullscreen_editor(
                                            prod_id, from_nav_idx=0
                                        ),
                                    ),
                                    ft.OutlinedButton(
                                        "🔍 بررسی",
                                        height=28,
                                        on_click=lambda e, prod_obj=p: show_inspect_dialog(
                                            prod_obj
                                        ),
                                    ),
                                ],
                            ),
                        ],
                    ),
                )
            )

        page.update()
        preload_images_in_bg(base_items, img_controls_map)

    inventory_main_panel = ft.Column(
        spacing=7,
        expand=True,
        controls=[
            ft.Container(
                padding=5,
                border_radius=12,
                bgcolor="white",
                content=ft.Row(
                    spacing=5,
                    controls=[tab_btn_oos, tab_btn_nis, tab_btn_low, tab_btn_in],
                ),
            ),
            warning_alert_banner,
            ft.Container(
                padding=8,
                border_radius=12,
                bgcolor="white",
                content=ft.Column(
                    spacing=6,
                    controls=[
                        ft.Row(spacing=6, controls=[search_tf, sort_dd]),
                        capsule_cats_row,
                    ],
                ),
            ),
            cards_list_col,
        ],
    )

    # ==========================================================================
    # صفحه ۲: 👤 لاگ تخصصی ادمین‌ها (با تایید ۲ مرحله‌ای برای برگرداندن تغییر)
    # ==========================================================================
    admin_filter_dd = ft.Dropdown(
        label="فیلتر بر اساس نام ادمین",
        value="all",
        dense=True,
        text_size=12,
        expand=True,
    )
    logs_list_col = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)

    def build_admin_logs_view():
        opts = [ft.dropdown.Option("all", "همه ادمین‌ها")]
        for adm in backend.config.get("admins_list", []):
            opts.append(ft.dropdown.Option(adm, f"👤 {adm}"))
        admin_filter_dd.options = opts

        sel_adm = admin_filter_dd.value or "all"
        logs = list(backend.admin_logs)
        if sel_adm != "all":
            logs = [lg for lg in logs if lg.get("admin") == sel_adm]

        logs_list_col.controls.clear()
        if not logs:
            logs_list_col.controls.append(
                ft.Container(
                    padding=20,
                    border_radius=14,
                    bgcolor="white",
                    alignment=ft.alignment.center,
                    content=ft.Text(
                        "هنوز هیچ لاگی برای این ادمین ثبت نشده است.", size=12
                    ),
                )
            )
            page.update()
            return

        for lg in logs:
            note_str = f" | علت/یادداشت: {lg['note']}" if lg.get("note") else ""

            logs_list_col.controls.append(
                ft.Container(
                    padding=11,
                    border_radius=14,
                    bgcolor="white",
                    border=ft.border.all(1, "#CBD5E1"),
                    content=ft.Column(
                        spacing=5,
                        controls=[
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.Text(
                                        f"👤 {lg.get('admin')}",
                                        size=12,
                                        weight=ft.FontWeight.BOLD,
                                        color="#0F766E",
                                    ),
                                    ft.Text(
                                        f"🕒 {lg.get('jalali_time')}",
                                        size=10,
                                        color="#64748B",
                                    ),
                                ],
                            ),
                            ft.Text(
                                f"🛍️ کالا: {lg.get('product_name')} (#{lg.get('product_id')})",
                                size=12,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(
                                f"🛠️ عملیات: {lg.get('action_type')}{note_str}",
                                size=11,
                                color="#0284C7",
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Container(
                                padding=8,
                                border_radius=8,
                                bgcolor="#F8FAFC",
                                content=ft.Column(
                                    spacing=3,
                                    controls=[
                                        ft.Text(
                                            f"🔢 تغییر تعداد موجودی: از {lg.get('old_stock')} عدد ⬅️ به {lg.get('new_stock')} عدد",
                                            size=11,
                                            color="#1E293B",
                                        ),
                                        ft.Text(
                                            f"💰 تغییر قیمت عادی: از {format_price(lg.get('old_reg_price'))} ت ⬅️ به {format_price(lg.get('new_reg_price'))} ت",
                                            size=11,
                                            color="#15803D",
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                        ft.Text(
                                            f"🏷️ قیمت ویژه: از {format_price(lg.get('old_sale_price') or 0)} ⬅️ به {format_price(lg.get('new_sale_price') or 0)}",
                                            size=10,
                                            color="#64748B",
                                        ),
                                    ],
                                ),
                            ),
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.TextButton(
                                        "✏️ ویرایش مجدد کالا",
                                        on_click=lambda e, pid=lg["product_id"]: open_fullscreen_editor(
                                            pid, from_nav_idx=1
                                        ),
                                    ),
                                    ft.OutlinedButton(
                                        "↩️ برگرداندن به قبل (۲ مرحله‌ای)",
                                        height=30,
                                        on_click=lambda e, log_item=lg: ask_two_step_undo_confirmation(
                                            log_item
                                        ),
                                    ),
                                ],
                            ),
                        ],
                    ),
                )
            )
        page.update()

    admin_filter_dd.on_change = lambda e: build_admin_logs_view()

    admin_logs_panel = ft.Column(
        spacing=8,
        expand=True,
        controls=[
            ft.Container(
                padding=10,
                border_radius=12,
                bgcolor="white",
                content=ft.Row(
                    spacing=8,
                    controls=[
                        admin_filter_dd,
                        ft.OutlinedButton(
                            "📊 اکسل ناموجودها",
                            on_click=lambda e: show_snack(
                                f"ذخیره شد: {os.path.basename(backend.export_outofstock_to_csv())}"
                            ),
                        ),
                    ],
                ),
            ),
            logs_list_col,
        ],
    )

    # ==========================================================================
    # صفحه ۳: ⚙️ تنظیمات سایت حبیب، مدیریت ادمین‌ها و ساخت اتوماتیک APK
    # ==========================================================================
    new_admin_tf = ft.TextField(
        label="افزودن نام ادمین جدید (مثلاً: محمد - انباردار)",
        dense=True,
        text_size=12,
        expand=True,
    )
    site_url_tf = ft.TextField(
        label="آدرس سایت حبیب (https://...)",
        value=backend.config.get("site_url", ""),
        dense=True,
        text_size=12,
    )
    ck_tf = ft.TextField(
        label="Consumer Key (ck_...)",
        value=backend.config.get("consumer_key", ""),
        dense=True,
        text_size=12,
    )
    cs_tf = ft.TextField(
        label="Consumer Secret (cs_...)",
        value=backend.config.get("consumer_secret", ""),
        dense=True,
        text_size=12,
        password=True,
        can_reveal_password=True,
    )
    rial_chk = ft.Checkbox(
        label="واحد پول سایت من «ریال» است (تبدیل خودکار به تومان)",
        value=backend.config.get("is_rial", False),
    )
    gh_token_tf = ft.TextField(
        label="توکن کلاسیک گیت‌هاب برای ساخت APK (ghp_...)",
        value=backend.config.get("github_token", ""),
        dense=True,
        text_size=12,
        password=True,
        can_reveal_password=True,
    )

    def on_add_new_admin(e):
        name_a = new_admin_tf.value.strip()
        if not name_a:
            return
        adms = backend.config.setdefault("admins_list", [])
        if name_a not in adms:
            adms.append(name_a)
        backend.config["current_admin"] = name_a
        backend.save_config()
        new_admin_tf.value = ""
        refresh_header_admin_dd()
        show_snack(f"👤 ادمین «{name_a}» اضافه و فعال شد.")

    def save_settings_all(e=None):
        backend.config["site_url"] = site_url_tf.value.strip()
        backend.config["consumer_key"] = ck_tf.value.strip()
        backend.config["consumer_secret"] = cs_tf.value.strip()
        backend.config["is_rial"] = bool(rial_chk.value)
        backend.config["github_token"] = gh_token_tf.value.strip()
        backend.save_config()
        if e:
            show_snack("✔️ تنظیمات ذخیره شد.")

    def on_import_from_site(e):
        save_settings_all()

        def _task():
            ok, msg = backend.import_sample_products_from_habib_site(
                site_url_tf.value.strip()
            )
            show_snack(msg, "#0F766E" if ok else "#DC2626")
            if ok:
                switch_bottom_nav(0)

        run_in_bg(_task)

    def on_connect_live_wc(e):
        save_settings_all()

        def _task():
            ok, msg = backend.test_wc_connection()
            if ok:
                backend.config["mode"] = "live"
                backend.save_config()
                mobile_mode_switch.value = True
                backend.get_all_cached_or_live_products(force_network=True)
                show_snack("✔️ متصل شد! کالاها و عکس‌های سایت حبیب بارگذاری شدند.")
                switch_bottom_nav(0)
            else:
                show_snack(msg, "#DC2626")

        run_in_bg(_task)

    settings_panel = ft.Column(
        spacing=8,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        controls=[
            ft.Container(
                padding=12,
                border_radius=14,
                bgcolor="white",
                content=ft.Column(
                    spacing=6,
                    controls=[
                        ft.Text(
                            "👤 مدیریت ادمین‌های فروشگاه",
                            size=13,
                            weight=ft.FontWeight.BOLD,
                            color="#0F766E",
                        ),
                        ft.Row(
                            spacing=6,
                            controls=[
                                new_admin_tf,
                                ft.ElevatedButton(
                                    "➕ افزودن ادمین",
                                    bgcolor="#0F766E",
                                    color="white",
                                    on_click=on_add_new_admin,
                                ),
                            ],
                        ),
                    ],
                ),
            ),
            ft.Container(
                padding=12,
                border_radius=14,
                bgcolor="white",
                border=ft.border.all(1.5, "#0F766E"),
                content=ft.Column(
                    spacing=8,
                    controls=[
                        ft.Text(
                            "🌐 اتصال به سایت حبیب و دریافت عکس‌ها و کالاها",
                            size=13,
                            weight=ft.FontWeight.BOLD,
                            color="#0F766E",
                        ),
                        site_url_tf,
                        ft.Container(
                            width=float("inf"),
                            content=ft.ElevatedButton(
                                "📸 استخراج فوری کالاها و عکس‌ها از سایت حبیب",
                                bgcolor="#0284C7",
                                color="white",
                                height=38,
                                on_click=on_import_from_site,
                            ),
                        ),
                        ck_tf,
                        cs_tf,
                        rial_chk,
                        ft.Container(
                            width=float("inf"),
                            content=ft.ElevatedButton(
                                "🔌 ذخیره کلیدها و اتصال زنده دوطرفه به سایت",
                                bgcolor="#0F766E",
                                color="white",
                                height=38,
                                on_click=on_connect_live_wc,
                            ),
                        ),
                    ],
                ),
            ),
            ft.Container(
                padding=12,
                border_radius=14,
                bgcolor="white",
                content=ft.Column(
                    spacing=6,
                    controls=[
                        ft.Text(
                            "🤖 ساخت اتوماتیک فایل اندروید (APK)",
                            size=13,
                            weight=ft.FontWeight.BOLD,
                        ),
                        gh_token_tf,
                        ft.Container(
                            width=float("inf"),
                            content=ft.ElevatedButton(
                                "🚀 شروع ساخت اتوماتیک APK با گیت‌هاب",
                                bgcolor="#7C3AED",
                                color="white",
                                height=38,
                                on_click=lambda e: (
                                    save_settings_all(),
                                    subprocess.Popen(
                                        [
                                            "cmd",
                                            "/c",
                                            "start",
                                            "cmd",
                                            "/k",
                                            sys.executable,
                                            "apk_builder.py",
                                        ]
                                    )
                                    if os.name == "nt"
                                    else subprocess.Popen(
                                        [sys.executable, "apk_builder.py"]
                                    ),
                                ),
                            ),
                        ),
                    ],
                ),
            ),
        ],
    )

    # ==========================================================================
    # هدر گوشی، انتخابگر ادمین، قفل امنیت، منوی پایین و لایه SafeArea اندروید
    # ==========================================================================
    header_admin_dd = ft.Dropdown(
        value=backend.config.get("current_admin", "حبیب (مدیر کل)"),
        width=130,
        dense=True,
        text_size=11,
        bgcolor="white",
    )

    def refresh_header_admin_dd():
        header_admin_dd.options = [
            ft.dropdown.Option(a, f"👤 {a}")
            for a in backend.config.get("admins_list", ["حبیب (مدیر کل)"])
        ]
        header_admin_dd.value = backend.config.get("current_admin", "حبیب (مدیر کل)")
        page.update()

    def on_admin_change(e):
        backend.config["current_admin"] = header_admin_dd.value
        backend.save_config()
        log_to_terminal(f"👤 ادمین فعال تغییر کرد به: {header_admin_dd.value}")
        show_snack(f"👤 ادمین فعال: {header_admin_dd.value}")

    header_admin_dd.on_change = on_admin_change
    refresh_header_admin_dd()

    lock_btn = ft.Container(
        padding=ft.padding.symmetric(horizontal=8, vertical=4),
        border_radius=8,
        bgcolor="#FEE2E2" if backend.config.get("edit_locked") else "#DCFCE7",
        content=ft.Text(
            "🔒 قفل" if backend.config.get("edit_locked") else "🔓 باز",
            size=10,
            weight=ft.FontWeight.BOLD,
            color="#DC2626" if backend.config.get("edit_locked") else "#15803D",
        ),
    )

    def toggle_edit_lock(e):
        cur_l = not bool(backend.config.get("edit_locked"))
        backend.config["edit_locked"] = cur_l
        backend.save_config()
        lock_btn.bgcolor = "#FEE2E2" if cur_l else "#DCFCE7"
        lock_btn.content.value = "🔒 قفل" if cur_l else "🔓 باز"
        lock_btn.content.color = "#DC2626" if cur_l else "#15803D"
        show_snack(
            "🔒 قفل امنیت ویرایش فعال شد" if cur_l else "🔓 قفل ویرایش باز شد."
        )
        page.update()

    lock_btn.on_click = toggle_edit_lock

    def on_toggle_mode(e):
        backend.config["mode"] = "live" if e.control.value else "sandbox"
        backend.save_config()
        if backend.is_live():
            run_in_bg(
                lambda: (
                    backend.get_all_cached_or_live_products(force_network=True),
                    rebuild_inventory_screen(),
                )
            )
        else:
            rebuild_inventory_screen()

    mobile_mode_switch = ft.Switch(
        value=backend.is_live(),
        active_color="#14B8A6",
        scale=0.75,
        on_change=on_toggle_mode,
    )

    mobile_body_holder = ft.Container(
        expand=True, padding=8, bgcolor="#F1F5F9", content=inventory_main_panel
    )
    nav_buttons_row = ft.Row(alignment=ft.MainAxisAlignment.SPACE_AROUND)

    def build_bottom_nav():
        idx = current_bottom_nav[0]
        nav_items = [
            (0, "📦", "موجودی و کالاها"),
            (1, "👤", f"لاگ ادمین‌ها ({len(backend.admin_logs)})"),
            (2, "⚙️", "اتصال سایت و APK"),
        ]
        nav_buttons_row.controls.clear()
        for n_idx, ic, lbl in nav_items:
            act = idx == n_idx
            nav_buttons_row.controls.append(
                ft.Container(
                    padding=ft.padding.symmetric(horizontal=12, vertical=5),
                    border_radius=12,
                    bgcolor="#CCFBF1" if act else "transparent",
                    on_click=lambda e, t=n_idx: switch_bottom_nav(t),
                    content=ft.Column(
                        spacing=1,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(ic, size=15),
                            ft.Text(
                                lbl,
                                size=11,
                                weight=ft.FontWeight.BOLD
                                if act
                                else ft.FontWeight.NORMAL,
                                color="#0F766E" if act else "#64748B",
                            ),
                        ],
                    ),
                )
            )

    def switch_bottom_nav(idx: int):
        is_in_fullscreen_editor[0] = False
        a35_bottom_bar.visible = True
        current_bottom_nav[0] = idx
        build_bottom_nav()
        if idx == 0:
            rebuild_inventory_screen()
            mobile_body_holder.content = inventory_main_panel
        elif idx == 1:
            build_admin_logs_view()
            mobile_body_holder.content = admin_logs_panel
        elif idx == 2:
            mobile_body_holder.content = settings_panel
        page.update()

    a35_status_bar = ft.Container(
        visible=not is_real_mobile,
        padding=ft.padding.symmetric(horizontal=18, vertical=6),
        bgcolor="#0F766E",
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Text("۱۲:۴۵", color="white", size=11, weight=ft.FontWeight.BOLD),
                ft.Container(
                    width=15,
                    height=15,
                    border_radius=8,
                    bgcolor="#020617",
                    border=ft.border.all(1.5, "#334155"),
                ),
                ft.Text(
                    "5G 📶 98% 🔋", color="white", size=11, weight=ft.FontWeight.BOLD
                ),
            ],
        ),
    )

    a35_app_header = ft.Container(
        padding=ft.padding.symmetric(horizontal=10, vertical=8),
        bgcolor="#0F766E",
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Row(
                    spacing=6,
                    controls=[
                        ft.Text(
                            "🛒 موجودی‌های سایت حبیب",
                            color="white",
                            size=14,
                            weight=ft.FontWeight.BOLD,
                        ),
                        lock_btn,
                    ],
                ),
                ft.Row(
                    spacing=4,
                    controls=[header_admin_dd, mobile_mode_switch],
                ),
            ],
        ),
    )

    a35_bottom_bar = ft.Container(
        bgcolor="white",
        padding=ft.padding.only(top=5, bottom=7, left=6, right=6),
        border=ft.border.only(top=ft.BorderSide(1, "#E2E8F0")),
        content=ft.Column(
            spacing=5,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                nav_buttons_row,
                ft.Container(
                    visible=not is_real_mobile,
                    width=115,
                    height=4,
                    border_radius=2,
                    bgcolor="#94A3B8",
                ),
            ],
        ),
    )

    core_mobile_column = ft.Column(
        spacing=0,
        expand=True,
        controls=[
            a35_status_bar,
            a35_app_header,
            loading_bar,
            mobile_body_holder,
            a35_bottom_bar,
        ],
    )

    a35_phone_frame = ft.Container(
        width=None if is_real_mobile else 460,
        height=None if is_real_mobile else 855,
        expand=True if is_real_mobile else False,
        border_radius=0 if is_real_mobile else 38,
        bgcolor="#0F172A",
        border=None
        if is_real_mobile
        else ft.border.all(9, backend.config.get("a35_color", "#1E293B")),
        shadow=None
        if is_real_mobile
        else ft.BoxShadow(blur_radius=25, color="#90000000", offset=ft.Offset(0, 8)),
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        content=ft.SafeArea(content=core_mobile_column, expand=True)
        if is_real_mobile
        else core_mobile_column,
    )

    def set_frame_mode(mode_name: str):
        if mode_name == "a35":
            a35_phone_frame.width = 460
            a35_phone_frame.border_radius = 38
            a35_phone_frame.expand = False
        else:
            a35_phone_frame.width = None
            a35_phone_frame.border_radius = 16
            a35_phone_frame.expand = True
        page.update()

    quick_site_input = ft.TextField(
        label="آدرس سایت حبیب برای دریافت فوری کالا و عکس (https://...)",
        value=backend.config.get("site_url", "https://habibshop.ir"),
        dense=True,
        text_size=12,
        bgcolor="white",
        expand=True,
    )

    dev_control_panel = ft.Container(
        visible=not is_real_mobile,
        expand=True,
        height=855,
        padding=14,
        border_radius=18,
        bgcolor="#1E293B",
        border=ft.border.all(1, "#334155"),
        content=ft.Column(
            spacing=10,
            expand=True,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text(
                            "📱 موجودی‌های سایت حبیب | شبیه‌ساز Samsung Galaxy A35",
                            color="white",
                            size=14,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Container(
                            padding=ft.padding.symmetric(horizontal=10, vertical=4),
                            border_radius=8,
                            bgcolor="#0F766E",
                            content=ft.Text(
                                "نسخه نهایی (Undo دو مرحله‌ای + تاریخچه کامل)",
                                color="white",
                                size=11,
                            ),
                        ),
                    ],
                ),
                ft.Container(
                    padding=10,
                    border_radius=12,
                    bgcolor="#0F172A",
                    border=ft.border.all(1, "#0284C7"),
                    content=ft.Column(
                        spacing=6,
                        controls=[
                            ft.Text(
                                "📸 مشاهده فوری محصولات و عکس‌های واقعی سایت حبیب:",
                                color="#38BDF8",
                                size=12,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Row(
                                spacing=6,
                                controls=[
                                    quick_site_input,
                                    ft.ElevatedButton(
                                        "🌐 استخراج از سایت",
                                        bgcolor="#0284C7",
                                        color="white",
                                        height=36,
                                        on_click=lambda e: (
                                            setattr(
                                                site_url_tf,
                                                "value",
                                                quick_site_input.value.strip(),
                                            ),
                                            on_import_from_site(None),
                                        ),
                                    ),
                                ],
                            ),
                        ],
                    ),
                ),
                ft.Row(
                    spacing=8,
                    wrap=True,
                    controls=[
                        ft.ElevatedButton(
                            "📱 نمای گوشی Galaxy A35",
                            bgcolor="#0F766E",
                            color="white",
                            on_click=lambda e: set_frame_mode("a35"),
                        ),
                        ft.ElevatedButton(
                            "🖥️ نمای تمام‌صفحه",
                            bgcolor="#334155",
                            color="white",
                            on_click=lambda e: set_frame_mode("desktop"),
                        ),
                        ft.OutlinedButton(
                            "🔄 بازنشانی داده‌های آزمایشی",
                            style=ft.ButtonStyle(color="#38BDF8"),
                            on_click=lambda e: (
                                backend.reset_sandbox(),
                                rebuild_inventory_screen(),
                            ),
                        ),
                    ],
                ),
                ft.Divider(color="#334155", height=6),
                ft.Text(
                    "💻 ترمینال زنده فارسی و ثبت لحظه‌ای لاگ ادمین‌ها:",
                    color="#38BDF8",
                    size=12,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Container(
                    expand=True,
                    padding=10,
                    border_radius=12,
                    bgcolor="#020617",
                    content=terminal_list,
                ),
            ],
        ),
    )

    if is_real_mobile:
        page.add(a35_phone_frame)
    else:
        page.add(
            ft.Row(
                expand=True,
                spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[a35_phone_frame, dev_control_panel],
            )
        )

    log_to_terminal("🚀 نسخه نهایی «🛒 موجودی‌های سایت حبیب» با موفقیت راه‌اندازی شد!")
    switch_bottom_nav(0)


if __name__ == "__main__":
    ft.app(target=main)
