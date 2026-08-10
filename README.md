# 📢 Telegram Broadcast Bot

Bot Telegram untuk admin mengirim pesan broadcast ke grup-grup yang telah memberikan izin.

---

## Daftar Isi

1. [Cara Membuat Bot via BotFather](#1-cara-membuat-bot-via-botfather)
2. [Cara Mendapatkan BOT_TOKEN](#2-cara-mendapatkan-bot_token)
3. [Cara Mendapatkan ADMIN_ID](#3-cara-mendapatkan-admin_id)
4. [Install Dependency](#4-install-dependency)
5. [Konfigurasi .env](#5-konfigurasi-env)
6. [Menjalankan Bot](#6-menjalankan-bot)
7. [Menambahkan Bot ke Grup](#7-menambahkan-bot-ke-grup)
8. [Permission yang Diperlukan](#8-permission-yang-diperlukan)
9. [Contoh Penggunaan Command](#9-contoh-penggunaan-command)

---

## 1. Cara Membuat Bot via BotFather

1. Buka Telegram, cari **@BotFather**
2. Kirim `/newbot`
3. Masukkan **nama bot** (contoh: `My Broadcast Bot`)
4. Masukkan **username bot** — harus diakhiri `bot` (contoh: `mybroadcast_bot`)
5. BotFather akan memberikan **BOT_TOKEN**

---

## 2. Cara Mendapatkan BOT_TOKEN

Setelah membuat bot, BotFather akan mengirim pesan seperti:

```
Done! Congratulations on your new bot. You will find it at t.me/mybroadcast_bot.
Use this token to access the HTTP API:
1234567890:ABCDefGhIJKlmNoPQRsTUVwxyZ
```

Salin token tersebut — itulah `BOT_TOKEN` kamu.

---

## 3. Cara Mendapatkan ADMIN_ID

**Cara termudah:**

1. Buka Telegram, cari **@userinfobot**
2. Kirim `/start`
3. Bot akan membalas dengan **ID** kamu

Atau gunakan **@getmyid_bot**.

`ADMIN_ID` adalah angka seperti `123456789`.

---

## 4. Install Dependency

Pastikan Python 3.12+ sudah terinstall.

```cmd
cd telegram-broadcast

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt
```

---

## 5. Konfigurasi .env

Salin file contoh lalu isi nilainya:

```cmd
copy .env.example .env
```

Buka `.env` dengan teks editor dan isi:

```env
BOT_TOKEN=1234567890:ABCDefGhIJKlmNoPQRsTUVwxyZ
ADMIN_ID=123456789
DATABASE_PATH=data/broadcast.db
BROADCAST_DELAY=1.5
```

- `BOT_TOKEN` — token dari BotFather
- `ADMIN_ID` — Telegram user ID kamu
- `DATABASE_PATH` — lokasi file database SQLite (biarkan default)
- `BROADCAST_DELAY` — jeda antar pesan dalam detik (minimal 1.0 disarankan)

---

## 6. Menjalankan Bot

```cmd
venv\Scripts\activate
python bot.py
```

Bot akan berjalan dan menampilkan log di terminal. Tekan `Ctrl+C` untuk menghentikan.

---

## 7. Menambahkan Bot ke Grup

1. Buka grup Telegram yang ingin didaftarkan
2. Klik nama grup → **Edit** → **Administrators**
3. Klik **Add Administrator** → cari username bot kamu
4. Tambahkan bot sebagai admin

---

## 8. Permission yang Diperlukan

Bot memerlukan permission berikut di setiap grup:

| Permission | Keterangan |
|---|---|
| **Send Messages** | Wajib — untuk mengirim broadcast |
| **Send Media Messages** | Opsional — jika ingin broadcast gambar/video |

Tanpa permission **Send Messages**, grup akan otomatis ditandai **nonaktif** oleh bot.

---

## 9. Contoh Penggunaan Command

### `/start`
Menampilkan menu utama dengan tombol inline.

```
/start
```

---

### `/addgroup`
Mendaftarkan grup ke daftar broadcast.

```
/addgroup -1001234567890 Komunitas Python Indonesia
```

> Cara mendapatkan `chat_id` grup:
> 1. Tambahkan **@getidsbot** ke grup
> 2. Kirim `/id` — bot akan membalas dengan chat_id grup
> 3. Hapus @getidsbot setelah mendapat ID

---

### `/groups`
Menampilkan semua grup terdaftar beserta status aktif/nonaktif.

```
/groups
```

---

### `/removegroup`
Menghapus grup dari daftar broadcast.

```
/removegroup -1001234567890
```

---

### `/broadcast`
Mengirim pesan ke semua grup aktif.

```
/broadcast Halo semua! Ada pengumuman penting hari ini. Silakan cek website kami.
```

Bot akan menampilkan progress pengiriman secara real-time dan laporan akhir.

---

### `/pause`
Menghentikan broadcast yang sedang berjalan.

```
/pause
```

---

### `/stats`
Menampilkan statistik keseluruhan.

```
/stats
```

Output:
```
📊 Statistik Bot

👥 Grup Aktif     : 10
🚫 Grup Nonaktif  : 2
📢 Total Broadcast: 5
✅ Total Berhasil : 48
❌ Total Gagal    : 2
```

---

### `/logs`
Menampilkan 20 riwayat broadcast terakhir.

```
/logs
```

---

## Struktur Project

```
telegram-broadcast/
├── bot.py              # Entry point
├── config.py           # Konfigurasi dari .env
├── database.py         # Semua fungsi database
├── handlers/
│   ├── start.py        # /start dan menu inline
│   ├── groups.py       # /addgroup, /groups, /removegroup
│   ├── broadcast.py    # /broadcast, /pause
│   └── stats.py        # /stats, /logs
├── services/
│   └── broadcaster.py  # Logic pengiriman broadcast
├── data/
│   └── .gitkeep        # Database SQLite tersimpan di sini
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Catatan Penting

- Bot **tidak** akan mencoba join grup secara otomatis
- Bot **menghormati** Telegram flood limit dengan menunggu `retry_after`
- Grup yang menolak pesan (bot dikeluarkan/permission dicabut) otomatis ditandai **nonaktif**
- Semua token dan ID sensitif **hanya** dibaca dari file `.env`
- Jangan commit file `.env` ke repository
