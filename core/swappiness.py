from core.utils import run, SUDO
from core.ui import inputbox, loading_animation, print_success, print_error, print_info

def set_swappiness(percent):
    """Set vm.swappiness secara runtime dan permanent."""
    try:
        percent = int(percent)
        if not (0 <= percent <= 100):
            print_error("Nilai swappiness harus antara 0 dan 100.")
            return
        
        with loading_animation(f"Menerapkan swappiness {percent}%..."):
            run(f"{SUDO} sysctl -w vm.swappiness={percent} > /dev/null")
            run(f"echo 'vm.swappiness={percent}' | {SUDO} tee /etc/sysctl.d/99-swap-tuning.conf > /dev/null")
        
        print_success(f"Swap akan mulai digunakan setelah RAM terpakai ±{percent}% (vm.swappiness={percent})")
    except ValueError:
        print_error("Masukkan angka valid.")

def setup_swappiness_prompt():
    """Prompt user untuk set swappiness."""
    swap_percent = inputbox("Swappiness", "Gunakan swap setelah RAM terpakai berapa persen?\n(0-100):", "60")
    if not swap_percent:
        return
    set_swappiness(swap_percent.strip())

