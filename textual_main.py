"""
Textual TUI main application for LlamalyticsHub.
Provides a rich terminal user interface for the application.
"""

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Button
import cli


def log_info(function, action, details, feature=None, file=None, 
             prompt_hash=None):
    """Log info messages with context."""
    context = (
        f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | "
        if feature or file or prompt_hash else ""
    )
    print(f"[INFO] [{function}] [{action}] {context}{details}")


def log_warning(function, action, details, feature=None, file=None, 
                prompt_hash=None):
    """Log warning messages with context."""
    context = (
        f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | "
        if feature or file or prompt_hash else ""
    )
    print(f"[WARNING] [{function}] [{action}] {context}{details}")


def log_error(function, action, details, feature=None, file=None, 
              prompt_hash=None):
    """Log error messages with context."""
    context = (
        f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | "
        if feature or file or prompt_hash else ""
    )
    print(f"[ERROR] [{function}] [{action}] {context}{details}")


def log_exception(function, action, details, feature=None, file=None, 
                  prompt_hash=None):
    """Log exception messages with context."""
    context = (
        f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | "
        if feature or file or prompt_hash else ""
    )
    print(f"[EXCEPTION] [{function}] [{action}] {context}{details}")


def import_cli_functions():
    """Import CLI functions for use in the TUI."""
    return cli.server_menu, cli.reports_menu, cli.config_menu, cli.logs_help_menu


class MainMenu(Vertical):
    """Main menu container for the TUI."""

    def compose(self) -> ComposeResult:
        """Compose the main menu layout."""
        yield Button("Server Management", id="server")
        yield Button("Reports", id="reports")
        yield Button("Configuration", id="config")
        yield Button("Logs & Help", id="logs")
        yield Button("Exit", id="exit")


class OllamaApp(App):
    """Main Textual application for Ollama Code Llama."""

    CSS_PATH = "app.css"

    def __init__(self):
        super().__init__()
        self.server_menu, self.reports_menu, self.config_menu, self.logs_help_menu = import_cli_functions()

    def compose(self) -> ComposeResult:
        """Compose the application layout."""
        yield MainMenu()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "server":
            self.server_menu({})
        elif event.button.id == "reports":
            self.reports_menu({})
        elif event.button.id == "config":
            self.config_menu()
        elif event.button.id == "logs":
            self.logs_help_menu()
        elif event.button.id == "exit":
            self.exit()


if __name__ == "__main__":
    app = OllamaApp()
    app.run() 