from textual.app import App, ComposeResult
from textual.widgets import Button, Header, Footer, Static
from textual.containers import Vertical
import sys
import importlib

# Import the original CLI submenus from cli.py
def import_cli_functions():
    cli = importlib.import_module('cli')
    return cli.server_menu, cli.reports_menu, cli.config_menu, cli.logs_help_menu

class MainMenu(Vertical):
    def compose(self) -> ComposeResult:
        yield Static("Ollama Code Llama CLI", classes="banner")
        yield Button("🖥️  Server", id="server")
        yield Button("📄  Reports & Audits", id="reports")
        yield Button("⚙️  Configuration", id="config")
        yield Button("📝  Logs & Help", id="logs")
        yield Button("🚪  Exit", id="exit")

class OllamaApp(App):
    CSS_PATH = None  # You can add a CSS file for styling if desired

    def __init__(self, params):
        super().__init__()
        self.params = params
        self.server_menu, self.reports_menu, self.config_menu, self.logs_help_menu = import_cli_functions()

    def compose(self) -> ComposeResult:
        yield Header()
        yield MainMenu()
        yield Footer()

    def on_button_pressed(self, event):
        button_id = event.button.id
        if button_id == "server":
            self.exit("server")
        elif button_id == "reports":
            self.exit("reports")
        elif button_id == "config":
            self.exit("config")
        elif button_id == "logs":
            self.exit("logs")
        elif button_id == "exit":
            self.exit()

if __name__ == "__main__":
    # Load params as in cli.py
    import cli
    config = cli.load_config()
    params = {
        'host': config.get('ollama', {}).get('host', 'http://localhost:11434'),
        'model': config.get('ollama', {}).get('model', 'codellama:7b'),
        'port': config.get('server', {}).get('port', 5000),
    }
    app = OllamaApp(params)
    result = app.run()
    # After exiting the TUI, call the appropriate submenu
    if result == "server":
        cli.server_menu(params)
    elif result == "reports":
        cli.reports_menu(params)
    elif result == "config":
        cli.config_menu()
    elif result == "logs":
        cli.logs_help_menu() 