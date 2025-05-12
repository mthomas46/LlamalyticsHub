import requests
import json
from loguru import logger
from rich.console import Console

# Configure logging
console = Console()

class OllamaCodeLlama:
    def __init__(self, model="codellama:7b", host="http://localhost:11434"):
        """
        Initialize the Code Llama interface.
        """
        self.model = model
        self.host = host
        logger.info(f"OllamaCodeLlama initialized with model={model} and host={host}")

    def generate(self, prompt, options=None):
        """
        Generate code or text using the LLM.

        Args:
            prompt (str): The prompt to send to the model.
            options (dict, optional): Additional options for the model.

        Returns:
            str: The generated response from the LLM.
        """
        logger.info(f"Generating response for prompt: {prompt[:50]}...")
        url = f"{self.host}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
        }
        if options:
            payload["options"] = options
        try:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            lines = response.text.strip().splitlines()
            responses = []
            for line in lines:
                try:
                    obj = json.loads(line)
                    if "response" in obj and obj["response"]:
                        responses.append(obj["response"])
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error for line: {line} | Error: {e}")
            full_response = "".join(responses)
            logger.info("Generation complete.")
            if not full_response:
                logger.warning("LLM returned an empty response.")
            return full_response
        except requests.RequestException as e:
            logger.error(f"Request to LLM failed: {e}")
            console.print_exception()
            raise RuntimeError(f"Request to LLM failed: {e}")
        except Exception as e:
            logger.exception("Unexpected error in generate")
            console.print_exception()
            raise 