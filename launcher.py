import os
import subprocess
import sys
import time
import webbrowser
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

console = Console()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
VENV_STREAMLIT = os.path.join(BASE_DIR, "venv", "Scripts", "streamlit.exe")
MT5_PATH = r"C:\Program Files\Admirals Group MT5 Terminal\terminal64.exe"

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def show_welcome():
    welcome_text = """
    [bold cyan]🚀 ARAFURA - TRADING BOT[/bold cyan]
    [bold blue]SISTEMA DE TRADING AUTÓNOMO CON IA[/bold blue]
    
    [dim]Innovation Architect 2026 - Premium Interface[/dim]
    """
    console.print(Panel(welcome_text, border_style="bright_blue", expand=False))

def start_mt5():
    if os.path.exists(MT5_PATH):
        console.print("[yellow]Opening MetaTrader 5...[/yellow]")
        subprocess.Popen([MT5_PATH], shell=True)
        return True
    else:
        console.print("[red]❌ Error: MetaTrader 5 not found at expected path.[/red]")
        return False

def start_dashboard():
    console.print("[yellow]Starting Dashboard...[/yellow]")
    # Abrir el navegador después de un momento
    def open_browser():
        time.sleep(5)
        webbrowser.open("http://localhost:8501")
    
    import threading
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Iniciar streamlit en un proceso separado (en segundo plano si estamos en modo ALL)
    return subprocess.Popen([VENV_STREAMLIT, "run", "ui/dashboard.py", "--server.headless", "true"], 
                            cwd=BASE_DIR, 
                            creationflags=subprocess.CREATE_NEW_CONSOLE)

def start_bot():
    console.print("[bold green]Starting Trading Bot...[/bold green]")
    # El bot se ejecuta en el proceso actual para ver los logs
    subprocess.call([VENV_PYTHON, "run.py"], cwd=BASE_DIR)

def main_menu():
    while True:
        clear_screen()
        show_welcome()
        
        table = Table(show_header=False, box=None)
        table.add_row("[bold cyan][1][/bold cyan]", "✨ [bold white]INICIAR TODO[/bold white] (MT5 + Dashboard + Bot)")
        table.add_row("[bold cyan][2][/bold cyan]", "📊 Solo [bold blue]Dashboard[/bold blue]")
        table.add_row("[bold cyan][3][/bold cyan]", "🤖 Solo [bold green]Bot[/bold green] (requiere MT5)")
        table.add_row("[bold cyan][4][/bold cyan]", "❌ Salir")
        
        console.print(Panel(table, title="[bold white]MENÚ PRINCIPAL[/bold white]", border_style="cyan", expand=False))
        
        choice = Prompt.ask("Selecciona una opción", choices=["1", "2", "3", "4"], default="1")
        
        if choice == "1":
            clear_screen()
            show_welcome()
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                progress.add_task(description="Iniciando MT5...", total=None)
                start_mt5()
                time.sleep(2)
                
                progress.add_task(description="Lanzando Dashboard...", total=None)
                start_dashboard()
                time.sleep(2)
                
                progress.add_task(description="Preparando motor de trading...", total=None)
                time.sleep(1)
            
            console.print("\n[bold green]✅ Todo listo. Iniciando orquestador...[/bold green]\n")
            start_bot()
            input("\nPresiona Enter para volver al menú...")
            
        elif choice == "2":
            clear_screen()
            show_welcome()
            console.print("\n[bold blue]Iniciando solo Dashboard...[/bold blue]\n")
            start_dashboard().wait() # Esperar a que termine (aunque streamlit no termina solo)
            
        elif choice == "3":
            clear_screen()
            show_welcome()
            console.print("\n[bold yellow]⚠️ Asegúrate de que MT5 esté abierto.[/bold yellow]")
            if Prompt.ask("¿Continuar?", choices=["y", "n"], default="y") == "y":
                console.print("\n[bold green]Iniciando solo el Bot...[/bold green]\n")
                start_bot()
                input("\nPresiona Enter para volver al menú...")
                
        elif choice == "4":
            console.print("\n[bold cyan]¡Hasta pronto![/bold cyan] 👋")
            time.sleep(1)
            break

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        console.print("\n[bold red]Interrumpido.[/bold red]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[bold red]Error fatal: {e}[/bold red]")
        sys.exit(1)
