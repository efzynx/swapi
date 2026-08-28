import os
import stat
import re
from core.utils import run, find_cmd, parse_size_to_mib, SUDO
from core.info import get_priority_for, get_swaps_from_proc
from core.ui import inputbox, yesno, show_menu, loading_animation, print_success, print_error, print_info, print_warning

def _prepare_swapfile(path: str, size_str: str, mib: int) -> bool:
    dir_path = os.path.dirname(os.path.abspath(path))
    code, out, _ = run(f"stat -f -c %T '{dir_path}'")
    if code == 0 and out.strip().lower() == 'btrfs':
        print_info("Mendeteksi sistem file BTRFS. Menyiapkan atribut NoCoW...")
        run(f"{SUDO} touch '{path}'")
        run(f"{SUDO} truncate -s 0 '{path}'")
        run(f"{SUDO} chattr +C '{path}'")

    with loading_animation(f"Membuat file swap {size_str} (mohon tunggu)..."):
        code, _, _ = run(f"{SUDO} fallocate -l {size_str} '{path}'")
        if code != 0:
            print_warning("fallocate gagal, fallback ke dd ...")
            code, _, err = run(f"{SUDO} dd if=/dev/zero of='{path}' bs=1M count={mib}")
            if code != 0:
                print_error(f"Gagal membuat swapfile: {err}")
                return False
    return True

def add_swap():
    path = inputbox("Tambah Swap", "Path swap (file/partisi):", "/swapfile")
    if path is None:
        return
    path = path.strip() or "/swapfile"
    
    is_block = False
    try:
        mode = os.stat(path).st_mode
        is_block = stat.S_ISBLK(mode)
    except FileNotFoundError:
        pass

    if is_block:
        if yesno("Konfirmasi partisi", f"[{path}] terdeteksi sebagai partisi. Jalankan mkswap?\n(Peringatan: Akan menghapus data di partisi tsb!)"):
            with loading_animation(f"Menyiapkan partisi {path}..."):
                run(f"{SUDO} mkswap '{path}'")
        else:
            print_info("Melewati mkswap, mengasumsikan partisi sudah berformat swap.")
    else:
        size_str = inputbox("Ukuran Swap", "Masukkan ukuran (contoh: 8G atau 4096M):", "8G")
        if not size_str:
            return
        size_str = size_str.strip()
        mib = parse_size_to_mib(size_str)
        if not mib:
            print_error("Ukuran tidak valid. Contoh benar: 8G, 4096M")
            return

        print_info(f"Membuat {path} sebesar {size_str} ...")
        ok = _prepare_swapfile(path, size_str, mib)
        if not ok:
            return

        with loading_animation(f"Mengonfigurasi mkswap pada {path}..."):
            run(f"{SUDO} chmod 600 '{path}'")
            run(f"{SUDO} mkswap '{path}'")

    swapon = find_cmd("swapon")
    if swapon:
        with loading_animation(f"Mengaktifkan swap pada {path}..."):
            code, _, err = run(f"{SUDO} {swapon} '{path}'")
        if code != 0:
            print_error(f"Gagal mengaktifkan swapfile: {err}")
            return
        print_success("Swapfile diaktifkan.")
    else:
        print_warning("'swapon' tidak ditemukan. Swap akan aktif setelah reboot jika ditambahkan ke fstab.")

    if yesno("Persisten", "Tambahkan ke /etc/fstab agar permanen?"):
        pri = inputbox("Prioritas Swap", "Set priority (mis. -1, atau kosongkan):", "")
        if pri is None:
            pri = ""
        pri = pri.strip()
        opts = "defaults" + (f",pri={pri}" if pri else "")
        run(f"echo '{path} none swap {opts} 0 0' | {SUDO} tee -a /etc/fstab > /dev/null")
        print_success("Ditambahkan ke /etc/fstab.")


def remove_swap():
    path = inputbox("Nonaktifkan Swap", "Path swap (file/partisi) yang dihapus:", "/swapfile")
    if not path:
        return
    path = path.strip()
    
    is_block = False
    try:
        mode = os.stat(path).st_mode
        is_block = stat.S_ISBLK(mode)
    except FileNotFoundError:
        pass

    print_info(f"Menonaktifkan {path} ...")
    with loading_animation(f"Menonaktifkan swap pada {path}..."):
        swapoff = find_cmd("swapoff")
        if swapoff:
            run(f"{SUDO} {swapoff} {path}")
        else:
            run(f"{SUDO} swapoff {path}")  # best effort

        run(f"{SUDO} sed -i '#{path}#d' /etc/fstab")
        
        if not is_block:
            run(f"{SUDO} rm -f {path}")

    if not is_block:
        print_success("Swapfile dihapus & fstab dibersihkan.")
    else:
        print_success("Partisi swap dinonaktifkan & fstab dibersihkan (partisi tidak dihapus).")


def set_swap_priority():
    swaps = get_swaps_from_proc()
    if not swaps:
        print_error("Tidak ada swap aktif.")
        return

    options = []
    for i, s in enumerate(swaps, 1):
        size_gib = s['size_kib'] / 1024 / 1024
        used_gib = s['used_kib'] / 1024 / 1024
        label = f"{s['name']} ({s['type']}) size={size_gib:.1f}G used={used_gib:.1f}G pri={s['prio']}"
        options.append((str(i), label))

    sel = show_menu("Ubah Prioritas", "Pilih swap target:", options)
    if not sel or not sel.isdigit() or not (1 <= int(sel) <= len(swaps)):
        print_error("Dibatalkan / Pilihan tidak valid.")
        return

    target_swap = swaps[int(sel) - 1]
    target = target_swap['name']
    used_gib = target_swap['used_kib'] / 1024 / 1024
    
    new_pri = inputbox("Prioritas Baru", f"Prioritas baru untuk {target} (mis. -1..100):")
    if not new_pri:
        return
    new_pri = new_pri.strip()

    swapoff = find_cmd("swapoff")
    swapon = find_cmd("swapon")

    if swapon and swapoff:
        if used_gib > 0:
            print_warning(f"Swap {target} sedang terpakai sebesar {used_gib:.1f}G.\n⚠ Proses mematikan swap (swapoff) mungkin membutuhkan waktu lama karena sistem harus memindahkan data kembali ke RAM. Harap bersabar...")
            
        with loading_animation(f"Menerapkan prioritas baru {new_pri} pada {target}..."):
            run(f"{SUDO} {swapoff} {target}")
            code, _, err = run(f"{SUDO} {swapon} --priority {new_pri} {target}")
            if code != 0:
                code2, _, err2 = run(f"{SUDO} {swapon} -p {new_pri} {target}")
                if code2 != 0:
                    print_error(f"Gagal mengaktifkan dengan prioritas baru: {err or err2}")
                    return
        print_success("Prioritas runtime diubah.")
    else:
        print_warning("'swapon/swapoff' tidak ditemukan. Akan memperbarui konfigurasi permanen saja.")

    if "/zram" in target:
        print_info("ZRAM tidak dikonfigurasi via /etc/fstab. Untuk persist, atur di zram-generator (override.conf).")
    else:
        run(f"{SUDO} sed -i '#{re.escape(target)}#d' /etc/fstab")
        run(f"echo '{target} none swap defaults,pri={new_pri} 0 0' | {SUDO} tee -a /etc/fstab > /dev/null")
        print_success("/etc/fstab diperbarui.")


def resize_swapfile():
    path = inputbox("Resize Swapfile", "Path swapfile yang ingin di-resize:", "/swapfile")
    if not path:
        return
    path = path.strip()
    if not os.path.exists(path):
        print_error("Swapfile tidak ditemukan.")
        return

    mode = os.stat(path).st_mode
    if stat.S_ISBLK(mode):
        print_error("Peringatan: Resize partisi swap tidak didukung secara otomatis. Mohon gunakan gparted/fdisk.")
        return

    new_size = inputbox("Ukuran Baru", f"Ukuran baru untuk {path} (contoh 16G):", "16G")
    if not new_size:
        return
    new_size = new_size.strip()
    mib = parse_size_to_mib(new_size)
    if not mib:
        print_error("Ukuran tidak valid.")
        return

    old_pri = get_priority_for(path)

    print_info(f"Melakukan Resize {path} -> {new_size}")
    with loading_animation(f"Memproses resize pada {path}..."):
        swapoff = find_cmd("swapoff")
        if swapoff:
            run(f"{SUDO} {swapoff} '{path}'")
        else:
            run(f"{SUDO} swapoff '{path}'")

    ok = _prepare_swapfile(path, new_size, mib)
    if not ok:
        return

    with loading_animation("Mengonfigurasi mkswap dan swapon..."):
        run(f"{SUDO} chmod 600 '{path}'")
        run(f"{SUDO} mkswap '{path}'")

        swapon = find_cmd("swapon")
        if swapon:
            if old_pri is not None:
                code, _, err = run(f"{SUDO} {swapon} --priority {old_pri} '{path}'")
                if code != 0:
                    code2, _, err2 = run(f"{SUDO} {swapon} -p {old_pri} '{path}'")
                    if code2 != 0:
                        print_error(f"Gagal mengaktifkan kembali swapfile: {err2}")
                        return
            else:
                code, _, err = run(f"{SUDO} {swapon} '{path}'")
                if code != 0:
                    print_error(f"Gagal mengaktifkan kembali swapfile: {err}")
                    return
            print_success("Resize selesai & swapfile aktif kembali.")
        else:
            print_warning("'swapon' tidak ditemukan. Swap akan aktif setelah reboot.")

        run(f"{SUDO} sed -i '#{re.escape(path)}#d' /etc/fstab")
        opts = "defaults" + (f",pri={old_pri}" if old_pri is not None else "")
        run(f"echo '{path} none swap {opts} 0 0' | {SUDO} tee -a /etc/fstab > /dev/null")
        print_success("/etc/fstab diperbarui.")


def create_swapfile(path: str, size_str: str, pri: str = "-1", add_to_fstab: bool = True):
    is_block = False
    try:
        mode = os.stat(path).st_mode
        is_block = stat.S_ISBLK(mode)
    except FileNotFoundError:
        pass

    if not is_block:
        mib = parse_size_to_mib(size_str)
        if mib is None:
            print_error("Ukuran tidak valid untuk swapfile.")
            return False

        print_info(f"Membuat swapfile {path} = {size_str} ...")
        ok = _prepare_swapfile(path, size_str, mib)
        if not ok:
            return False

        with loading_animation(f"Menyiapkan mkswap pada {path}..."):
            run(f"{SUDO} chmod 600 '{path}'")
            run(f"{SUDO} mkswap '{path}'")
    else:
        print_info(f"Menggunakan partisi swap {path} ...")
        with loading_animation(f"Menyiapkan mkswap pada {path}..."):
            run(f"{SUDO} mkswap '{path}'")

    swapon = find_cmd("swapon")
    if swapon:
        with loading_animation(f"Mengaktifkan swap pada {path}..."):
            code, _, err = run(f"{SUDO} {swapon} --priority {pri} '{path}'")
            if code != 0:
                code2, _, err2 = run(f"{SUDO} {swapon} -p {pri} '{path}'")
                if code2 != 0:
                    print_error(f"Gagal mengaktifkan swapfile: {err2}")
                    return False
    else:
        print_warning("'swapon' tidak ditemukan. Swapfile akan aktif setelah reboot jika ditambahkan ke fstab.")

    if add_to_fstab:
        run(f"{SUDO} sed -i '\\#{re.escape(path)}#d' /etc/fstab")
        run(f"echo '{path} none swap defaults,pri={pri} 0 0' | {SUDO} tee -a /etc/fstab > /dev/null")

    print_success(f"Swapfile {path} siap (pri={pri}).")
    return True


def remove_swapfile_by_path(path: str):
    print_info(f"Hapus/Nonaktifkan swap {path} ...")
    
    is_block = False
    try:
        mode = os.stat(path).st_mode
        is_block = stat.S_ISBLK(mode)
    except FileNotFoundError:
        pass

    swapoff = find_cmd("swapoff") or "swapoff"
    with loading_animation(f"Menonaktifkan {path}..."):
        run(f"{SUDO} {swapoff} {path}")
        run(f"{SUDO} sed -i '\\#{re.escape(path)}#d' /etc/fstab")
        if not is_block:
            run(f"{SUDO} rm -f {path}")
    print_success(f"{path} dinonaktifkan.")


def resize_swapfile_path(path: str, new_size_str: str):
    if not os.path.exists(path):
        print_error("Swapfile tidak ditemukan.")
        return False
    mib = parse_size_to_mib(new_size_str)
    if not mib:
        print_error("Ukuran tidak valid.")
        return False

    old_pri = get_priority_for(path)
    print_info(f"Resize {path} -> {new_size_str}")
    swapoff = find_cmd("swapoff") or "swapoff"
    with loading_animation(f"Menonaktifkan sementara {path}..."):
        run(f"{SUDO} {swapoff} '{path}'")

    ok = _prepare_swapfile(path, new_size_str, mib)
    if not ok:
        return False

    with loading_animation(f"Menyiapkan mkswap dan mengaktifkan {path}..."):
        run(f"{SUDO} chmod 600 '{path}'")
        run(f"{SUDO} mkswap '{path}'")

        swapon = find_cmd("swapon")
        if swapon:
            if old_pri is not None:
                code, _, err = run(f"{SUDO} {swapon} --priority {old_pri} '{path}'")
                if code != 0:
                    code2, _, err2 = run(f"{SUDO} {swapon} -p {old_pri} '{path}'")
                    if code2 != 0:
                        print_error(f"Gagal mengaktifkan kembali swapfile: {err2}")
                        return False
            else:
                code, _, err = run(f"{SUDO} {swapon} '{path}'")
                if code != 0:
                    print_error(f"Gagal mengaktifkan kembali swapfile: {err}")
                    return False
            print_success("Resize selesai & swapfile aktif kembali.")
        else:
            print_warning("'swapon' tidak ditemukan. Swap akan aktif setelah reboot.")

        run(f"{SUDO} sed -i '\\#{re.escape(path)}#d' /etc/fstab")
        opts = "defaults" + (f",pri={old_pri}" if old_pri is not None else "")
        run(f"echo '{path} none swap {opts} 0 0' | {SUDO} tee -a /etc/fstab > /dev/null")
        print_success("/etc/fstab diperbarui.")
    return True
