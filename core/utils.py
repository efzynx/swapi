import os
import shutil
import subprocess
import re

SUDO = "" if os.geteuid() == 0 else "sudo "

def run(cmd):
    p = subprocess.run(cmd, shell=True, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

def find_cmd(name: str):
    path = shutil.which(name)
    if path:
        return path
    for d in ("/usr/sbin", "/sbin", "/usr/bin", "/bin"):
        cand = os.path.join(d, name)
        if os.path.exists(cand) and os.access(cand, os.X_OK):
            return cand
    return None

def parse_size_to_bytes(s: str):
    s = s.strip().lower()
    m = re.match(r'^(\d+(?:\.\d+)?)(g|gb|gi|m|mb|mi|k|kb|ki)?$', s)
    if not m:
        return None
    val = float(m.group(1))
    unit = (m.group(2) or 'm')[0]
    if unit == 'g':
        return int(val * 1024 * 1024 * 1024)
    elif unit == 'm':
        return int(val * 1024 * 1024)
    elif unit == 'k':
        return int(val * 1024)
    else:
        return None

def parse_size_to_mib(s: str):
    b = parse_size_to_bytes(s)
    return int(round(b / (1024 * 1024))) if b is not None else None

def pick_from_list(prompt_text, items):
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    
    from core.ui import show_menu
    options = [(str(i), val) for i, val in enumerate(items, 1)]
    choice = show_menu("Pilihan", prompt_text, options)
    
    if choice and choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(items):
            return items[idx]
    return None
