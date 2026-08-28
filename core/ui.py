import sys
from contextlib import contextmanager

# Global console instance
_console = None

def get_console():
    global _console
    if _console is None:
        from rich.console import Console
        _console = Console()
    return _console

def print_success(text):
    console = get_console()
    if console:
        console.print(f"[bold green]✅ {text}[/bold green]")
    else:
        print(f"✅ {text}")

def print_error(text):
    console = get_console()
    if console:
        console.print(f"[bold red]❌ {text}[/bold red]")
    else:
        print(f"❌ {text}")

def print_info(text):
    console = get_console()
    if console:
        console.print(f"[bold cyan]ℹ {text}[/bold cyan]")
    else:
        print(f"ℹ {text}")

def print_warning(text):
    console = get_console()
    if console:
        console.print(f"[bold yellow]⚠ {text}[/bold yellow]")
    else:
        print(f"⚠ {text}")

@contextmanager
def loading_animation(text="Memproses..."):
    console = get_console()
    if console:
        with console.status(f"[bold cyan]{text}[/bold cyan]", spinner="dots"):
            yield
    else:
        print(f"{text} ", end="", flush=True)
        yield
        print("Selesai.")

def clear_console():
    console = get_console()
    if console:
        console.clear()
    else:
        import os
        os.system('clear')

def get_style():
    from questionary import Style
    return Style([
        ('qmark', 'fg:#00d7ff bold'),       # Token di depan pertanyaan (cyan)
        ('question', 'fg:#ffffff bold'),    # Teks pertanyaan (putih tebal)
        ('answer', 'fg:#00ff00 bold'),      # Jawaban yang disubmit (hijau tebal)
        ('pointer', 'fg:#ff5fd7 bold'),     # Pointer pilihan (pink)
        ('highlighted', 'fg:#ff5fd7 bold'), # Item yang disorot (pink)
        ('selected', 'fg:#00ff00'),         # Item terpilih 
        ('separator', 'fg:#8a8a8a'),        # Pemisah
        ('instruction', 'fg:#8a8a8a italic'),# Instruksi
        ('text', 'fg:#cccccc'),             # Teks biasa
        ('disabled', 'fg:#858585 italic')   # Pilihan yang dinonaktifkan
    ])

def check_ui_dependencies():
    try:
        import questionary
        import rich
        return True
    except ImportError:
        return False

def show_menu(title, text, options):
    """
    options: list of tuples (id, label)
    """
    import questionary
    
    choices = []
    for opt in options:
        choices.append(questionary.Choice(title=opt[1], value=opt[0]))
    
    print()
    choice = questionary.select(
        f"{title}\n  {text}",
        choices=choices,
        use_indicator=True,
        style=get_style(),
        qmark="✦"
    ).ask()
    return choice

def inputbox(title, text, default=""):
    import questionary
    print()
    ans = questionary.text(
        f"[{title}] {text}",
        default=str(default),
        style=get_style(),
        qmark="✎"
    ).ask()
    return ans

def yesno(title, text):
    import questionary
    print()
    ans = questionary.confirm(
        f"[{title}] {text}",
        default=False,
        style=get_style(),
        qmark="?"
    ).ask()
    return bool(ans)

def msgbox(title, text):
    console = get_console()
    if console:
        from rich.panel import Panel
        from rich.text import Text
        panel = Panel(
            Text(text, justify="center", style="bold green"),
            title=f"[bold cyan]{title}[/bold cyan]",
            border_style="cyan"
        )
        console.print(panel)
        console.print()
    else:
        print(f"\n--- {title} ---")
        print(text)
        print("-" * (8 + len(title)))
