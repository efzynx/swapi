import os
import subprocess
from core.utils import run, find_cmd, parse_size_to_bytes, SUDO
from core.info import get_priority_for
from core.ui import inputbox, loading_animation, print_success, print_error, print_info, print_warning

def resize_zram(dev="/dev/zram0", new_size_str=None):
    if new_size_str is None:
        new_size_str = inputbox("Resize ZRAM", f"Ukuran ZRAM baru untuk {dev} (mis. 4G):", "4G")
        if not new_size_str:
            return
        new_size_str = new_size_str.strip()
    bytes_ = parse_size_to_bytes(new_size_str)
    if not bytes_:
        print_error("Ukuran tidak valid.")
        return

    old_pri = get_priority_for(dev)

    with loading_animation(f"Mematikan swap ZRAM {dev}..."):
        swapoff = find_cmd("swapoff")
        if swapoff:
            run(f"{SUDO} {swapoff} {dev}")
        else:
            run(f"{SUDO} swapoff {dev}")

    with loading_animation(f"Menyesuaikan ukuran ZRAM {dev}..."):
        zramctl = find_cmd("zramctl")
        if zramctl:
            run(f"{SUDO} {zramctl} -r {dev}")
            code, out, err = run(f"{SUDO} {zramctl} --find --size {bytes_}")
            if code != 0:
                print_error(f"Gagal set size zram via zramctl: {err}")
                return
            new_dev = out.strip().splitlines()[-1] if out.strip() else dev
            dev = new_dev
        else:
            if not os.path.exists(f"/sys/block/{os.path.basename(dev)}/disksize"):
                print_error("Tidak menemukan sysfs zram. Kernel mungkin tidak mendukung.")
                return
            run(f"echo {bytes_} | {SUDO} tee /sys/block/{os.path.basename(dev)}/disksize > /dev/null")

        run(f"{SUDO} mkswap {dev}")

        swapon = find_cmd("swapon")
        if swapon:
            if old_pri is not None:
                code, _, err = run(f"{SUDO} {swapon} --priority {old_pri} {dev}")
                if code != 0:
                    run(f"{SUDO} {swapon} -p {old_pri} {dev}")
            else:
                run(f"{SUDO} {swapon} {dev}")
            print_success("ZRAM di-resize & aktif kembali.")
        else:
            print_warning("'swapon' tidak ditemukan. ZRAM akan aktif setelah reboot.")

    with loading_animation("Menyimpan konfigurasi persist zram-generator..."):
        zr_gen = find_cmd("zram-generator") or ("/usr/lib/systemd/zram-generator"
                                                if os.path.exists("/usr/lib/systemd/zram-generator") else None)
        if zr_gen:
            mib = int(bytes_ / 1024 / 1024)
            pri = old_pri if old_pri is not None else 100
            run(f"{SUDO} mkdir -p /etc/systemd/zram-generator.conf.d")
            conf = f"[{os.path.basename(dev)}]\nzram-size = {mib}\npriorities = {pri}\n"
            run(f"echo '{conf}' | {SUDO} tee /etc/systemd/zram-generator.conf.d/override.conf > /dev/null")
            run(f"{SUDO} systemctl daemon-reexec")
            print_success("Persist zram-generator diperbarui.")
        else:
            print_info("zram-generator tidak ada; perubahan ZRAM hanya runtime.")


def create_zram_permanent(size_gb, priority):
    with loading_animation(f"Membuat ZRAM permanent {size_gb}..."):
        subprocess.run(["modprobe", "zram"], check=False)
        size_gb_clean = size_gb.strip().upper().replace("G", "").replace("M", "")
        try:
            size_gb_int = int(size_gb_clean)
        except ValueError:
            print_error(f"Ukuran ZRAM '{size_gb}' tidak valid. Gunakan format seperti 1G atau 512M.")
            return

        bytes_size = size_gb_int * 1024 * 1024 * 1024
        device = subprocess.getoutput("zramctl --find").strip()
        if not device:
            print_error("Tidak ada device zram yang tersedia.")
            return

        subprocess.run(["zramctl", "--size", str(bytes_size), device], check=True)
        subprocess.run(["mkswap", device], check=True)
        subprocess.run(["swapon", "-p", str(priority), device], check=True)

        zram_service = f"""[Unit]
Description=ZRAM swap
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/sbin/modprobe zram
ExecStart=/sbin/zramctl --size {bytes_size} {device}
ExecStart=/sbin/mkswap {device}
ExecStart=/sbin/swapon -p {priority} {device}
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
"""
        with open("/etc/systemd/system/zram.service", "w") as f:
            f.write(zram_service)
        subprocess.run(["systemctl", "enable", "zram.service"], check=False)
    print_success(f"ZRAM permanent {size_gb} dibuat dengan prioritas {priority}")


def remove_zram_permanent():
    with loading_animation("Menghapus ZRAM permanent..."):
        run(f"{SUDO} systemctl disable --now zram.service")
        run(f"{SUDO} swapoff /dev/zram0")
        run(f"{SUDO} modprobe -r zram || true")
        run(f"{SUDO} rm -f /etc/systemd/system/zram.service /usr/local/bin/zram-start.sh")
        run(f"{SUDO} systemctl daemon-reload")
    print_success("ZRAM permanen berhasil dihapus (service & runtime).")
