import os
import stat
import re
from core.utils import run, find_cmd, parse_size_to_mib, SUDO
from core.info import get_priority_for, get_swaps_from_proc
from core.ui import inputbox, yesno, show_menu, loading_animation, print_success, print_error, print_info, print_warning

def get_partition_uuid(path: str) -> str:
    """Mendapatkan UUID dari partisi swap menggunakan blkid atau lsblk."""
    code, out, _ = run(f"blkid -s UUID -o value '{path}'")
    if code == 0 and out.strip():
        return out.strip()
    code, out, _ = run(f"lsblk -no UUID '{path}'")
    if code == 0 and out.strip():
        return out.strip()
    return ""

def check_grub_resume(uuid: str):
    """Memeriksa apakah ada konfigurasi resume kernel di GRUB yang mengarah ke UUID lama/berbeda."""
    grub_file = "/etc/default/grub"
    if os.path.exists(grub_file):
        try:
            with open(grub_file, "r") as f:
                content = f.read()
            if "resume=" in content:
                print_warning(
                    f"⚠️  PERINGATAN: Parameter 'resume=' terdeteksi di {grub_file}!\n"
                    f"Jika partisi swap ini digunakan untuk hibernasi (resume), pastikan UUID dikonfigurasi ke:\n"
                    f"  resume=UUID={uuid}\n"
                    f"Lalu jalankan 'sudo update-grub' / 'sudo grub-mkconfig -o /boot/grub/grub.cfg' agar booting tidak freeze."
                )
        except Exception:
            pass

def backup_fstab() -> bool:
    """Membuat backup otomatis /etc/fstab dengan timestamp."""
    code, _, err = run(f"{SUDO} cp /etc/fstab /etc/fstab.bak.$(date +%s)")
    if code != 0:
        print_warning(f"Gagal membuat backup /etc/fstab: {err}")
        return False
    return True

def remove_from_fstab(target: str, uuid: str = ""):
    """Menghapus entri lama di /etc/fstab berdasarkan path atau UUID untuk mencegah duplikasi."""
    backup_fstab()
    escaped_target = re.escape(target)
    # Hapus berdasarkan path
    run(f"{SUDO} sed -i '\\#{escaped_target}[[:space:]]#d; \\#{escaped_target}$#d' /etc/fstab")
    if uuid:
        escaped_uuid = re.escape(uuid)
        # Hapus berdasarkan UUID
        run(f"{SUDO} sed -i '\\#UUID={escaped_uuid}[[:space:]]#d; \\#UUID={escaped_uuid}$#d' /etc/fstab")

def add_to_fstab(target: str, pri: str = "", is_block: bool = False):
    """Menambahkan entri swap ke /etc/fstab dengan sanitasi pencegahan duplikasi."""
    uuid = get_partition_uuid(target) if is_block else ""
    remove_from_fstab(target, uuid)
    
    opts = "defaults" + (f",pri={pri}" if pri else "")
    entry = f"UUID={uuid}" if (is_block and uuid) else target
    code, _, err = run(f"echo '{entry} none swap {opts} 0 0' | {SUDO} tee -a /etc/fstab > /dev/null")
    if code == 0:
        print_success(f"Ditambahkan ke /etc/fstab ({entry}).")
    else:
        print_error(f"Gagal menambahkan entri ke /etc/fstab: {err}")

def _prepare_swapfile(path: str, size_str: str, mib: int) -> bool:
    """Menyiapkan swapfile dengan deteksi Btrfs khusus atau filesystem standar."""
    dir_path = os.path.dirname(os.path.abspath(path))
    
    # Deteksi filesystem tempat file dibuat
    code, out, _ = run(f"df -T '{dir_path}' | tail -n 1 | awk '{{print $2}}'")
    fs_type = out.strip().lower() if code == 0 else ""
    if not fs_type:
        code, out, _ = run(f"stat -f -c %T '{dir_path}'")
        fs_type = out.strip().lower() if code == 0 else ""

    if fs_type == 'btrfs':
        print_info("Mendeteksi sistem berkas Btrfs.")
        btrfs_cmd = find_cmd("btrfs")
        # 1. Coba btrfs filesystem mkswapfile bawaan
        if btrfs_cmd:
            with loading_animation(f"Membuat swapfile Btrfs {size_str} dengan 'btrfs filesystem mkswapfile'..."):
                code, _, err = run(f"{SUDO} {btrfs_cmd} filesystem mkswapfile --size {size_str} '{path}'")
                if code == 0:
                    print_success("Swapfile Btrfs berhasil dibuat.")
                    return True
                else:
                    print_warning(f"'btrfs filesystem mkswapfile' tidak berhasil ({err}). Menggunakan fallback manual...")

        # 2. Fallback manual untuk Btrfs
        with loading_animation(f"Membuat swapfile Btrfs manual {size_str} (NoCoW & uncompressed)..."):
            run(f"{SUDO} touch '{path}'")
            run(f"{SUDO} truncate -s 0 '{path}'")
            run(f"{SUDO} chattr +C '{path}'")
            if btrfs_cmd:
                run(f"{SUDO} {btrfs_cmd} property set '{path}' compression none")
            code, _, err = run(f"{SUDO} dd if=/dev/zero of='{path}' bs=1M count={mib} status=progress")
            if code != 0:
                print_error(f"Gagal mengalokasikan file swap: {err}")
                return False
            run(f"{SUDO} chmod 600 '{path}'")
            code, _, err = run(f"{SUDO} mkswap '{path}'")
            if code != 0:
                print_error(f"mkswap gagal pada {path}: {err}")
                return False
            return True

    # Filesystem Standar (ext4, xfs, dll.)
    with loading_animation(f"Membuat file swap {size_str} (mohon tunggu)..."):
        fallocate = find_cmd("fallocate")
        allocated = False
        if fallocate:
            code, _, _ = run(f"{SUDO} {fallocate} -l {size_str} '{path}'")
            if code == 0:
                allocated = True
        
        if not allocated:
            print_warning("fallocate gagal atau tidak tersedia, fallback ke dd ...")
            code, _, err = run(f"{SUDO} dd if=/dev/zero of='{path}' bs=1M count={mib} status=progress")
            if code != 0:
                print_error(f"Gagal membuat swapfile: {err}")
                return False
        
        run(f"{SUDO} chmod 600 '{path}'")
        code, _, err = run(f"{SUDO} mkswap '{path}'")
        if code != 0:
            print_error(f"mkswap gagal pada {path}: {err}")
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
        if yesno("Konfirmasi partisi", f"[{path}] terdeteksi sebagai partisi. Jalankan mkswap?\n(Peringatan: Akan memformat data di partisi tsb!)"):
            with loading_animation(f"Menyiapkan partisi {path}..."):
                old_uuid = get_partition_uuid(path)
                if old_uuid:
                    print_info(f"Mempertahankan UUID partisi yang ada: {old_uuid}")
                    code, _, err = run(f"{SUDO} mkswap -U '{old_uuid}' '{path}'")
                else:
                    code, _, err = run(f"{SUDO} mkswap '{path}'")
                
                if code != 0:
                    print_error(f"Gagal menjalankan mkswap: {err}")
                    return

                new_uuid = get_partition_uuid(path)
                if not old_uuid and new_uuid:
                    check_grub_resume(new_uuid)
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

    swapon = find_cmd("swapon")
    if swapon:
        with loading_animation(f"Mengaktifkan swap pada {path}..."):
            code, _, err = run(f"{SUDO} {swapon} '{path}'")
        if code != 0:
            print_error(f"Gagal mengaktifkan swap: {err}")
            return
        print_success("Swap diaktifkan.")
    else:
        print_warning("'swapon' tidak ditemukan. Swap akan aktif setelah reboot jika ditambahkan ke fstab.")

    if yesno("Persisten", "Tambahkan ke /etc/fstab agar permanen?"):
        pri = inputbox("Prioritas Swap", "Set priority (mis. -1, atau kosongkan):", "")
        if pri is None:
            pri = ""
        pri = pri.strip()
        add_to_fstab(path, pri=pri, is_block=is_block)

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
            run(f"{SUDO} {swapoff} '{path}'")
        else:
            run(f"{SUDO} swapoff '{path}'")

        uuid = get_partition_uuid(path) if is_block else ""
        remove_from_fstab(path, uuid)
        
        if not is_block:
            run(f"{SUDO} rm -f '{path}'")

    if not is_block:
        print_success("Swapfile dihapus & fstab dibersihkan.")
    else:
        print_success("Partisi swap dinonaktifkan & fstab dibersihkan (partisi fisik tidak dihapus).")

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
            run(f"{SUDO} {swapoff} '{target}'")
            code, _, err = run(f"{SUDO} {swapon} --priority {new_pri} '{target}'")
            if code != 0:
                code2, _, err2 = run(f"{SUDO} {swapon} -p {new_pri} '{target}'")
                if code2 != 0:
                    print_error(f"Gagal mengaktifkan dengan prioritas baru: {err or err2}")
                    return
        print_success("Prioritas runtime diubah.")
    else:
        print_warning("'swapon/swapoff' tidak ditemukan. Akan memperbarui konfigurasi permanen saja.")

    if "/zram" in target:
        print_info("ZRAM tidak dikonfigurasi via /etc/fstab. Untuk persist, atur di zram-generator (override.conf).")
    else:
        is_block = False
        try:
            is_block = stat.S_ISBLK(os.stat(target).st_mode)
        except Exception:
            pass
        add_to_fstab(target, pri=new_pri, is_block=is_block)
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

    with loading_animation("Mengaktifkan kembali swap..."):
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

        add_to_fstab(path, pri=str(old_pri) if old_pri is not None else "", is_block=False)

def create_swapfile(path: str, size_str: str, pri: str = "-1", add_to_fstab_flag: bool = True):
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
    else:
        print_info(f"Menggunakan partisi swap {path} ...")
        with loading_animation(f"Menyiapkan mkswap pada {path}..."):
            old_uuid = get_partition_uuid(path)
            if old_uuid:
                print_info(f"Mempertahankan UUID partisi: {old_uuid}")
                code, _, err = run(f"{SUDO} mkswap -U '{old_uuid}' '{path}'")
            else:
                code, _, err = run(f"{SUDO} mkswap '{path}'")
            
            if code != 0:
                print_error(f"Gagal mkswap: {err}")
                return False

            new_uuid = get_partition_uuid(path)
            if not old_uuid and new_uuid:
                check_grub_resume(new_uuid)

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

    if add_to_fstab_flag:
        add_to_fstab(path, pri=pri, is_block=is_block)

    print_success(f"Swap {path} siap (pri={pri}).")
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
        run(f"{SUDO} {swapoff} '{path}'")
        uuid = get_partition_uuid(path) if is_block else ""
        remove_from_fstab(path, uuid)
        if not is_block:
            run(f"{SUDO} rm -f '{path}'")
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

    with loading_animation(f"Mengaktifkan kembali {path}..."):
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

        add_to_fstab(path, pri=str(old_pri) if old_pri is not None else "", is_block=False)
    return True
