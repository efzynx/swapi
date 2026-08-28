import re
from core.utils import run, find_cmd

def get_swaps_from_proc():
    swaps = []
    try:
        with open("/proc/swaps") as f:
            lines = f.read().strip().splitlines()
        for i, line in enumerate(lines):
            if i == 0:
                continue
            parts = line.split()
            if len(parts) >= 5:
                swaps.append({
                    "name": parts[0],
                    "type": parts[1],
                    "size_kib": int(parts[2]),
                    "used_kib": int(parts[3]),
                    "prio": int(parts[4]),
                })
    except Exception:
        pass
    return swaps

def get_priority_for(path: str):
    for s in get_swaps_from_proc():
        if s['name'] == path:
            return s['prio']
    try:
        with open('/etc/fstab') as f:
            for line in f:
                if line.strip().startswith('#'):
                    continue
                if path in line:
                    m = re.search(r'pri=(-?\d+)', line)
                    if m:
                        return int(m.group(1))
    except Exception:
        pass
    return None

def classify_existing_swaps():
    zram, files, parts = [], [], []
    for s in get_swaps_from_proc():
        name = s['name']
        typ = s['type'].lower()
        if 'zram' in name:
            zram.append(name)
        elif typ == 'file':
            files.append(name)
        else:
            parts.append(name)
    return {'zram': zram, 'files': files, 'parts': parts}

def check_swap():
    from core.ui import get_console, print_info, print_warning
    from rich.table import Table

    console = get_console()
    swapon = find_cmd("swapon")
    if swapon:
        code, out, err = run(f"{swapon} --show")
        if out:
            print_info("Info Swap (swapon)")
            console.print(out)
        else:
            print_info("Tidak ada swap aktif (swapon).")
    else:
        print_warning("'swapon' tidak ditemukan, fallback ke 'free -h':")
        _, out, _ = run("free -h")
        console.print(out)

    swaps = get_swaps_from_proc()
    if swaps:
        table = Table(title="Detail /proc/swaps", title_style="bold magenta", border_style="cyan")
        table.add_column("Filename", style="bold white")
        table.add_column("Type", style="green")
        table.add_column("Size (MiB)", justify="right", style="yellow")
        table.add_column("Used (MiB)", justify="right", style="red")
        table.add_column("Priority", justify="right", style="cyan")

        for s in swaps:
            table.add_row(
                s['name'],
                s['type'],
                str(int(s['size_kib']/1024)),
                str(int(s['used_kib']/1024)),
                str(s['prio'])
            )
        console.print(table)
    else:
        print_info("Tidak ada data di /proc/swaps.")
