from typing import Dict, Any
import os
import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator
from rich.console import Console
from rich.table import Table
import questionary
from loguru import logger

MODULE = "CONFIG_MANAGER"
def log_info(function, action, details, feature=None, file=None, prompt_hash=None):
    context = f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | " if feature or file or prompt_hash else ""
    logger.info(f"[{MODULE}] [{function}] [{action}] {context}{details}")
def log_warning(function, action, details, feature=None, file=None, prompt_hash=None):
    context = f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | " if feature or file or prompt_hash else ""
    logger.warning(f"[{MODULE}] [{function}] [{action}] {context}{details}")
def log_error(function, action, details, feature=None, file=None, prompt_hash=None):
    context = f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | " if feature or file or prompt_hash else ""
    logger.error(f"[{MODULE}] [{function}] [{action}] {context}{details}")
def log_exception(function, action, details, feature=None, file=None, prompt_hash=None):
    context = f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | " if feature or file or prompt_hash else ""
    logger.exception(f"[{MODULE}] [{function}] [{action}] {context}{details}")

console = Console()

class ConfigEditModel(BaseModel):
    section: str
    key: str
    value: str
    @field_validator('section', 'key')
    def validate_section_key(cls, v):
        """
        Ensure the section and key are not empty strings.
        """
        if not v.strip():
            raise ValueError('Cannot be empty')
        return v

def load_config() -> Dict[str, Any]:
    """
    Load the configuration from config.yaml if present.
    Returns:
        dict: The loaded configuration dictionary, or an empty dict if not found.
    """
    CONFIG_PATH = 'config.yaml'
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH) as file:
                config = yaml.safe_load(file)
                log_info("load_config", "load", f"Loaded config from {CONFIG_PATH}", feature="config_manager", file=CONFIG_PATH)
                return config
        log_warning("load_config", "load", f"Config file {CONFIG_PATH} not found. Returning empty config.", feature="config_manager", file=CONFIG_PATH)
        return {}
    except Exception as e:
        log_exception("load_config", "load", f"Error loading config: {e}", feature="config_manager", file=CONFIG_PATH)
        return {}

def print_config():
    """
    Display the current config.yaml in a rich table and allow editing interactively.
    Prompts the user to edit the config if desired.
    """
    try:
        config = load_config()
        table = Table(title="Current config.yaml", show_header=True, header_style="bold blue")
        table.add_column("Section", style="cyan", no_wrap=True)
        table.add_column("Key", style="green")
        table.add_column("Value", style="yellow")
        for section, values in config.items():
            if isinstance(values, dict):
                for key, value in values.items():
                    table.add_row(str(section), str(key), str(value))
            else:
                table.add_row(str(section), "-", str(values))
        console.print(table)
        log_info("print_config", "display", "Config table printed.", feature="config_manager")
        if questionary.confirm("Edit config?").ask():
            args = collect_config_edit_args(config)
            if not args:
                log_info("print_config", "edit", "User aborted config edit.", feature="config_manager")
                return
            section, key, value = args['section'], args['key'], args['value']
            if section in config and isinstance(config[section], dict):
                config[section][key] = value
            else:
                config[section] = {key: value}
            with open('config.yaml', 'w') as file:
                yaml.safe_dump(config, file)
            console.print("[green]Config updated.[/green]")
            log_info("print_config", "edit", f"Config updated: {section}.{key} = {value}", feature="config_manager")
    except Exception as e:
        log_exception("print_config", "display/edit", f"Error: {e}", feature="config_manager")
        console.print(f"[red]Error displaying or editing config: {e}[/red]")

def collect_config_edit_args(config: dict) -> dict:
    """
    Collect and validate config edit arguments interactively using the ConfigEditModel.
    Args:
        config (dict): The current configuration dictionary.
    Returns:
        dict: Validated arguments for editing the config.
    """
    sections = list(config.keys())
    while True:
        try:
            section = questionary.select("Select section:", choices=sections + ['Back']).ask()
            if section == 'Back':
                log_info("collect_config_edit_args", "select_section", "User selected Back.", feature="config_manager")
                return None
            keys = list(config[section].keys()) if isinstance(config[section], dict) else []
            key = questionary.text("Key to edit:").ask() if not keys else questionary.select("Select key:", choices=keys + ['Back']).ask()
            if key == 'Back':
                log_info("collect_config_edit_args", "select_key", "User selected Back.", feature="config_manager")
                return None
            value = questionary.text("New value:").ask()
            args_dict = {'section': section, 'key': key, 'value': value}
            try:
                validated = ConfigEditModel(**args_dict)
                log_info("collect_config_edit_args", "validate", f"Validated args: {args_dict}", feature="config_manager")
                return validated.dict()
            except ValidationError as ve:
                log_warning("collect_config_edit_args", "validate", f"Input error: {ve.errors()}", feature="config_manager")
                console.print(f"[red]Input error: {ve.errors()}[/red]")
                continue
        except Exception as e:
            log_exception("collect_config_edit_args", "input", f"Error: {e}", feature="config_manager")
            console.print(f"[red]Error collecting config edit args: {e}[/red]")
            continue 