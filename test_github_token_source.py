import os
import yaml
from rich.console import Console
from rich.panel import Panel
from dotenv import load_dotenv

console = Console()
load_dotenv()

CONFIG_PATH = 'config.yaml'
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
else:
    config = {}

github_token_env = os.environ.get('GITHUB_TOKEN')
github_token_config = config.get('github', {}).get('token')

if github_token_env:
    console.print(Panel(f'[green]GITHUB_TOKEN loaded from environment or .env:[/green] {github_token_env}', style='green'))
elif github_token_config:
    console.print(Panel(f'[yellow]GITHUB_TOKEN loaded from config.yaml:[/yellow] {github_token_config}', style='yellow'))
else:
    console.print(Panel('[red]GITHUB_TOKEN not set in environment, .env, or config.yaml[/red]', style='red')) 