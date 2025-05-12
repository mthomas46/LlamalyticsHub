import os
from github import Github
from rich.console import Console
from rich.panel import Panel

console = Console()

def test_github_connect():
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        console.print(Panel('[red]GITHUB_TOKEN not set in environment.[/red]', style='red'))
        return False
    try:
        g = Github(token)
        user = g.get_user()
        console.print(Panel(f'[green]GitHub connection successful![/green]\nAuthenticated as: [bold]{user.login}[/bold]', style='green'))
        return True
    except Exception as e:
        console.print(Panel(f'[red]GitHub connection failed: {e}[/red]', style='red'))
        return False

if __name__ == '__main__':
    test_github_connect() 