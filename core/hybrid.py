import os
from core.utils import run, SUDO, pick_from_list
from core.info import classify_existing_swaps
from core.zram import resize_zram, create_zram_permanent
from core.file_part import remove_swapfile_by_path, resize_swapfile_path, create_swapfile
from core.ui import show_menu, inputbox, loading_animation, print_success, print_error, print_info, print_warning

def setup_hybrid():
    print_info("=== Setup Hybrid (ZRAM + Swapfile) — dengan pre-check anti double ===")

    existing = classify_existing_swaps()
    has_zr = bool(existing['zram'])
    has_sf = bool(existing['files'])

    if has_zr or has_sf:
        print_info("Ditemukan swap aktif:")
        if has_zr:
            print_info(f"- ZRAM : {', '.join(existing['zram'])}")
        if has_sf:
            print_info(f"- Files: {', '.join(existing['files'])}")

        opts = [
            ("1", "Buat baru (double) — tetap pertahankan yang lama"),
            ("2", "Hapus yang lama, lalu buat baru"),
            ("3", "Edit/Resize yang ada"),
            ("4", "Batal")
        ]
        choice = show_menu("Ditemukan Swap Aktif", "Apa yang ingin kamu lakukan?", opts)

        if not choice or choice == "4":
            return

        if choice == "3":
            opts = []
            if has_zr: opts.append("zram")
            if has_sf: opts.append("swapfile")
            
            sel = show_menu("Target Resize", "Pilih target resize:", [(str(i), o) for i, o in enumerate(opts, 1)])
            if not sel:
                return
            target = opts[int(sel) - 1]

            if target == "zram":
                dev = pick_from_list("Pilih device ZRAM:", existing['zram'])
                if dev:
                    resize_zram(dev)
            else:
                path = pick_from_list("Pilih swapfile:", existing['files'])
                if path:
                    new_size = inputbox("Resize Swapfile", f"Ukuran baru untuk {path} (mis. 12G):", "12G")
                    if new_size:
                        resize_swapfile_path(path, new_size.strip())
            return

        if choice == "2":
            with loading_animation("Menghapus ZRAM dan Swapfile lama..."):
                if has_zr:
                    for dev in existing['zram']:
                        run(f"{SUDO} swapoff {dev}")
                        run(f"{SUDO} modprobe -r zram || true")
                    run(f"{SUDO} systemctl disable --now zram.service || true")
                    run(f"{SUDO} rm -f /etc/systemd/system/zram.service /usr/local/bin/zram-start.sh || true")

                if has_sf:
                    for path in existing['files']:
                        remove_swapfile_by_path(path)

            print_success("Swap/ZRAM lama dibersihkan. Lanjut buat hybrid baru...")

    print_info("== Konfigurasi Hybrid ==")
    zr_size = inputbox("ZRAM", "Ukuran ZRAM (kosongkan untuk skip ZRAM):", "4G")
    if zr_size is None:
        return
    zr_size = zr_size.strip()
    
    sf_path_default = "/swapfile2" if os.path.exists("/swapfile") else "/swapfile"
    sf_path = inputbox("Swapfile Path", "Path swapfile:", sf_path_default)
    if not sf_path:
        return
    sf_path = sf_path.strip()
    
    sf_size = inputbox("Swapfile Size", "Ukuran swapfile:", "16G")
    if not sf_size:
        return
    sf_size = sf_size.strip()
    
    pri_zr = inputbox("ZRAM Priority", "Prioritas ZRAM:", "100") or "100"
    pri_sf = inputbox("Swapfile Priority", "Prioritas swapfile:", "-1") or "-1"

    if zr_size:
        create_zram_permanent(zr_size, pri_zr.strip())
    else:
        print_info("Lewatkan ZRAM.")

    ok = create_swapfile(sf_path, sf_size, pri_sf.strip(), add_to_fstab=True)
    if not ok:
        print_error("Gagal membuat swapfile. Batalkan.")
        return

    print_success("✨ Hybrid selesai. ZRAM (jika dibuat) dan swapfile sudah aktif dan persist sesuai konfigurasi.")

