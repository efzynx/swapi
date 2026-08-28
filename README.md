# 🛠️ SWAPI — ZRAM & Swapfile Utility for Linux

**SWAPI** adalah utilitas interaktif berbasis **Python** dengan antarmuka terminal (TUI) modern yang cantik (memanfaatkan library `rich` dan `questionary`) untuk mengelola swap di Linux. SWAPI mendukung:

* Pembuatan **swapfile** dan **partisi swap** dengan ukuran dan prioritas custom
* Pembuatan **ZRAM** permanen (via systemd service & zram-generator)
* **Hybrid mode** (ZRAM + Swapfile) dengan *pre-check* anti-duplikat
* Pengaturan **Swappiness** (batas penggunaan RAM sebelum beralih ke swap)
* Resize, ubah prioritas, dan hapus swap dengan mudah & aman (memiliki sistem peringatan otomatis)

Script ini sangat cocok untuk pengguna yang ingin mengoptimalkan memori virtual di sistemnya, baik untuk server maupun desktop Linux.

---

## ✨ Fitur Utama

* **Cek Status Swap (Berwarna & Tabel Rapi)**: Menampilkan status dari `swapon` & `/proc/swaps`
* **Tambah Swap (File/Partisi)**: Mendukung pembuatan file swap dengan alokasi cepat (fallocate/dd)
* **Hapus Swap**: Menonaktifkan dan membersihkan `/etc/fstab` secara otomatis
* **Ubah Prioritas Swap**: Mengatur prioritas runtime maupun permanen
* **Resize Swapfile**: Ubah ukuran file swap tanpa perlu menghapus manual
* **Setup Hybrid Mode (Otomatis)**: Membuat ZRAM + Swapfile secara instan
* **Ubah Swappiness**: Optimasi penggunaan memori virtual (mis. mengaktifkan swap hanya setelah RAM terpakai 60%)
* **Animasi Loading & Notifikasi Interaktif**: Mencegah kebingungan saat sistem sedang memproses *swapoff* atau pembuatan disk (I/O lambat).

---

## 📦 Instalasi

Clone repository ini dan install dependensinya (sebaiknya di dalam virtual environment):

```bash
# Clone repo
git clone https://github.com/efzynx/swapi.git
cd swapi

# (Opsional) Buat virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependensi TUI (questionary, rich)
pip install -r requirements.txt
```

---

## 🚀 Cara Menjalankan

Jalankan script menggunakan Python (dibutuhkan akses `sudo` otomatis untuk eksekusi kernel/disk):

```bash
python swap_manager.py
```

Atau jika file sudah dijadikan *executable*:

```bash
./swap_manager.py
```

Menu TUI modern akan muncul:

```text
✦ SWAPI
  Pilih menu navigasi (Gunakan Panah dan Enter): 
 » ○ Cek Status Swap Aktif
   ○ Tambah Swap (File/Partisi)
   ○ Hapus/Nonaktifkan Swap
   ○ Ubah Prioritas Swap
   ○ Resize Swapfile
   ○ Setup Hybrid (ZRAM + Swapfile)
   ○ Ubah Swappiness (Penggunaan RAM)
   ○ Keluar
```

---

## 📖 Contoh Penggunaan

### 1. Setup Hybrid Mode (ZRAM + Swapfile)
Cocok untuk desktop/server dengan RAM terbatas. ZRAM (RAM yang dikompresi) akan menjadi swap prioritas tinggi, sedangkan Swapfile menjadi fallback.
1. Pilih menu `Setup Hybrid`.
2. SWAPI akan mengecek apakah ada swap aktif. Anda bisa menghapusnya terlebih dahulu otomatis dari menu.
3. Masukkan ukuran ZRAM (misal `4G`).
4. Masukkan ukuran Swapfile (misal `16G`).
5. SWAPI akan membangun semuanya dan memperbarui `/etc/fstab` serta membuat service `zram`.

### 2. Ubah Swappiness
Mengubah seberapa sering kernel Linux melakukan "swapping".
1. Pilih menu `Ubah Swappiness`.
2. Masukkan persentase, misalnya `60` (Swap akan digunakan ketika RAM fisik sudah terpakai sekitar 60%).
3. SWAPI menerapkan runtime lewat `sysctl` dan menyimpannya permanen di `/etc/sysctl.d/99-swap-tuning.conf`.

### 3. Resize Swapfile
1. Pilih menu `Resize Swapfile`.
2. Pilih path (misal `/swapfile`).
3. Masukkan ukuran baru (misal `8G`). SWAPI otomatis menonaktifkan, mengubah, dan menyalakan kembali swap tersebut. *(Terdapat peringatan otomatis jika mematikan swap yang sedang penuh memakan waktu lama)*.

---

## ⚙️ Catatan Teknis

* **ZRAM** dibuat permanen via `/etc/systemd/system/zram.service` atau `zram-generator` (jika terdeteksi).
* **Swapfile & Partisi Swap** dibuat permanen via entri di `/etc/fstab`.
* **File System Khusus**: SWAPI mendeteksi partisi BTRFS dan otomatis mengatur atribut NoCoW (`chattr +C`) untuk mencegah degradasi performa swap.
* **Tested di**:
  * Debian 12+
  * Arch Linux / EndeavourOS
  * Ubuntu 22.04+

---

## 📜 Lisensi

GNU GPL-3.0 License.

---

## 👨‍💻 Kontribusi

Pull request & issue sangat terbuka!
Jika ada bug, masalah kompatibilitas, atau ide fitur baru, silakan ajukan di tab **Issues**.
