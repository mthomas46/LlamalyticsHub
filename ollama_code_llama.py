import requests
import json
from loguru import logger
from rich.console import Console
import httpx
import asyncio

# Configure logging
console = Console()

# Add standardized logging helpers
MODULE = "OLLAMA_CODE_LLAMA"
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

class OllamaCodeLlama:
    def __init__(self, model="codellama:7b", host="http://localhost:11434"):
        """
        Initialize the Code Llama interface.
        """
        self.model = model
        self.host = host
        log_info("__init__", "init", f"OllamaCodeLlama initialized with model={model} and host={host}", feature=MODULE)

    def generate(self, prompt, options=None):
        """
        Generate code or text using the LLM.

        Args:
            prompt (str): The prompt to send to the model.
            options (dict, optional): Additional options for the model.

        Returns:
            str: The generated response from the LLM.
        """
        log_info("generate", "start", f"Generating response for prompt: {prompt[:50]}...", feature=MODULE)
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
                    log_error("generate", "json_decode", f"JSON decode error for line: {line} | Error: {e}", feature=MODULE)
            full_response = "".join(responses)
            log_info("generate", "complete", "Generation complete.", feature=MODULE)
            if not full_response:
                log_warning("generate", "empty_response", "LLM returned an empty response.", feature=MODULE)
            return full_response
        except requests.RequestException as e:
            log_error("generate", "request", f"Request to LLM failed: {e}", feature=MODULE)
            console.print_exception()
            raise RuntimeError(f"Request to LLM failed: {e}")
        except Exception as e:
            log_exception("generate", "unexpected", "Unexpected error in generate", feature=MODULE)
            console.print_exception()
            raise

    async def async_generate(self, prompt, options=None):
        """
        Asynchronously generate code or text using the LLM.
        """
        log_info("async_generate", "start", f"[async] Generating response for prompt: {prompt[:50]}...", feature=MODULE)
        url = f"{self.host}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
        }
        if options:
            payload["options"] = options
        async with httpx.AsyncClient(timeout=60) as client:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                lines = response.text.strip().splitlines()
                responses = []
                for line in lines:
                    try:
                        obj = json.loads(line)
                        if "response" in obj and obj["response"]:
                            responses.append(obj["response"])
                    except json.JSONDecodeError as e:
                        log_error("async_generate", "json_decode", f"JSON decode error for line: {line} | Error: {e}", feature=MODULE)
                full_response = "".join(responses)
                log_info("async_generate", "complete", "[async] Generation complete.", feature=MODULE)
                if not full_response:
                    log_warning("async_generate", "empty_response", "LLM returned an empty response.", feature=MODULE)
                return full_response
            except httpx.RequestError as e:
                log_error("async_generate", "request", f"[async] Request to LLM failed: {e}", feature=MODULE)
                console.print_exception()
                raise RuntimeError(f"Request to LLM failed: {e}")
            except Exception as e:
                log_exception("async_generate", "unexpected", "Unexpected error in async_generate", feature=MODULE)
                console.print_exception()
                raise

    async def batch_async_generate(self, prompts, options=None):
        """
        Asynchronously generate responses for a batch of prompts.
        Returns a list of responses in the same order as prompts.
        """
        log_info("batch_async_generate", "start", f"[async] Batch generating {len(prompts)} prompts...", feature=MODULE)
        url = f"{self.host}/api/generate"
        async with httpx.AsyncClient(timeout=60) as client:
            tasks = []
            for prompt in prompts:
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                }
                if options:
                    payload["options"] = options
                tasks.append(client.post(url, json=payload))
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            results = []
            for resp in responses:
                if isinstance(resp, Exception):
                    log_error("batch_async_generate", "batch_llm_call", f"Batch LLM call failed: {resp}", feature=MODULE)
                    results.append("")
                    continue
                try:
                    lines = resp.text.strip().splitlines()
                    out = []
                    for line in lines:
                        try:
                            obj = json.loads(line)
                            if "response" in obj and obj["response"]:
                                out.append(obj["response"])
                        except json.JSONDecodeError as e:
                            log_error("batch_async_generate", "json_decode", f"JSON decode error for line: {line} | Error: {e}", feature=MODULE)
                    results.append("".join(out))
                except Exception as e:
                    log_error("batch_async_generate", "parse_batch_response", f"Error parsing batch LLM response: {e}", feature=MODULE)
                    results.append("")
            log_info("batch_async_generate", "complete", "[async] Batch generation complete.", feature=MODULE)
            return results 