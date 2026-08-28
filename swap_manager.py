#!/usr/bin/env python3
import os
import sys

from core.info import check_swap
from core.file_part import add_swap, remove_swap, set_swap_priority, resize_swapfile
from core.hybrid import setup_hybrid
from core.swappiness import setup_swappiness_prompt
from core.ui import check_ui_dependencies, show_menu, msgbox, clear_console, get_console, print_error

def main():
    if not check_ui_dependencies():
        print("❌ 'questionary' atau 'rich' tidak ditemukan. Silakan jalankan: pip install -r requirements.txt")
        sys.exit(1)

    console = get_console()

    while True:
        options = [
            ("1", "Cek Status Swap Aktif"),
            ("2", "Tambah Swap (File/Partisi)"),
            ("3", "Hapus/Nonaktifkan Swap"),
            ("4", "Ubah Prioritas Swap"),
            ("5", "Resize Swapfile"),
            ("6", "Setup Hybrid (ZRAM + Swapfile)"),
            ("7", "Ubah Swappiness (Penggunaan RAM)"),
            ("8", "Keluar")
        ]
        
        choice = show_menu(
            title="SWAPI",
            text="Pilih menu navigasi (Gunakan Panah dan Enter):",
            options=options
        )

        if choice is None or choice == "8":
            break
            
        # Bersihkan layar dengan rich console
        clear_console()

        if choice == "1":
            check_swap()
            console.input("\n[bold cyan]\\[Tekan Enter untuk kembali ke menu][/bold cyan]")
        elif choice == "2":
            add_swap()
            console.input("\n[bold cyan]\\[Tekan Enter untuk kembali ke menu][/bold cyan]")
        elif choice == "3":
            remove_swap()
            console.input("\n[bold cyan]\\[Tekan Enter untuk kembali ke menu][/bold cyan]")
        elif choice == "4":
            set_swap_priority()
            console.input("\n[bold cyan]\\[Tekan Enter untuk kembali ke menu][/bold cyan]")
        elif choice == "5":
            resize_swapfile()
            console.input("\n[bold cyan]\\[Tekan Enter untuk kembali ke menu][/bold cyan]")
        elif choice == "6":
            setup_hybrid()
            console.input("\n[bold cyan]\\[Tekan Enter untuk kembali ke menu][/bold cyan]")
        elif choice == "7":
            setup_swappiness_prompt()
            console.input("\n[bold cyan]\\[Tekan Enter untuk kembali ke menu][/bold cyan]")

if __name__ == "__main__":
    main()

