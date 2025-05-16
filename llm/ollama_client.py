import os
import requests
import asyncio
import psutil
import time
import traceback
import json
from typing import List, Optional, Any
from loguru import logger

# Ensure log file exists and Loguru is configured
LOG_PATH = os.environ.get('OLLAMA_LOG_PATH', 'ollama_server.log')
if not any([h for h in logger._core.handlers.values() if getattr(h, 'name', None) == LOG_PATH]):
    logger.add(LOG_PATH, rotation="10 MB", retention="10 days", enqueue=True, backtrace=True, diagnose=True)

MODULE = "LLM_CLIENT"
def log_info(function, action, details, feature=None, file=None, prompt_hash=None):
    context = f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | " if feature or file or prompt_hash else ""
    logger.info(f"[{MODULE}] [{function}] [{action}] {context}{details}")
def log_warning(function, action, details, feature=None, file=None, prompt_hash=None):
    context = f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | " if feature or file or prompt_hash else ""
    logger.warning(f"[{MODULE}] [{function}] [{action}] {context}{details}")
def log_error(function, action, details, feature=None, file=None, prompt_hash=None):
    context = f"Feature: {feature} | File: {file} | PromptHash: {prompt_hash} | " if feature or file or prompt_hash else ""
    logger.error(f"[{MODULE}] [{function}] [{action}] {context}{details}")
def log_exception(function, action, details):
    logger.exception(f"[{MODULE}] [{function}] [{action}] {details}")

class OllamaCodeLlama:
    """
    Client for interacting with the Ollama Code Llama LLM server.
    Supports synchronous, asynchronous, and batch generation.
    """
    def __init__(self, host: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize the OllamaCodeLlama client.
        Args:
            host (str, optional): The base URL of the Ollama server.
            model (str, optional): The model name to use.
        """
        self.host = host or os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
        self.model = model or os.environ.get('OLLAMA_MODEL', 'codellama:7b')
        self.api_url = f"{self.host}/api/generate"

    def generate(self, prompt: str, **kwargs) -> str:
        """
        Synchronous call to the LLM server.
        Args:
            prompt (str): The prompt to send to the LLM.
            **kwargs: Additional parameters for the API.
        Returns:
            str: The LLM's response or an error message.
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            **kwargs
        }
        try:
            response = requests.post(self.api_url, json=payload, timeout=60)
            response.raise_for_status()
            lines = response.text.strip().splitlines()
            responses = []
            for line in lines:
                # Log each raw LLM response line
                log_info("generate", "llm_raw_response", f"Raw LLM response: {line}", feature=MODULE, file=__file__, prompt_hash=hash(prompt))
                try:
                    obj = json.loads(line)
                    if "response" in obj and obj["response"]:
                        responses.append(obj["response"])
                except json.JSONDecodeError as e:
                    log_error("generate", "json_decode", f"JSON decode error for line: {line} | Error: {e}", feature=MODULE)
            log_info("generate", "call", f"Prompt: {prompt[:50]}... | Response: {str(responses)[:50]}...", feature=MODULE, file=__file__, prompt_hash=hash(prompt))
            return "".join(responses)
        except Exception as error:
            log_error("generate", "call", f"Ollama LLM error: {error}", feature=MODULE, file=__file__, prompt_hash=hash(prompt))
            return f"[LLM error: {error}]"

    async def async_generate(self, prompt: str, **kwargs) -> str:
        """
        Asynchronous call to the LLM server using httpx.
        Args:
            prompt (str): The prompt to send to the LLM.
            **kwargs: Additional parameters for the API.
        Returns:
            str: The LLM's response or an error message.
        """
        import httpx
        import json
        process = psutil.Process(os.getpid())
        start_mem = process.memory_info().rss / 1024 / 1024
        start_time = time.time()
        log_info("async_generate", "start", f"Memory: {start_mem:.2f} MB | Prompt: {prompt[:80]}...", feature=MODULE, file=__file__, prompt_hash=hash(prompt))
        payload = {
            "model": self.model,
            "prompt": prompt,
            **kwargs
        }
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    response = await client.post(self.api_url, json=payload)
                    response.raise_for_status()
                    lines = response.text.strip().splitlines()
                    responses = []
                    for line in lines:
                        # Log each raw LLM response line
                        log_info("async_generate", "llm_raw_response", f"Raw LLM response: {line}", feature=MODULE, file=__file__, prompt_hash=hash(prompt))
                        try:
                            obj = json.loads(line)
                            if "response" in obj and obj["response"]:
                                responses.append(obj["response"])
                        except json.JSONDecodeError as e:
                            log_error("async_generate", "json_decode", f"JSON decode error for line: {line} | Error: {e}", feature=MODULE)
                    if responses:
                        end_mem = process.memory_info().rss / 1024 / 1024
                        duration = time.time() - start_time
                        log_info("async_generate", "success_jsonl", f"Parsed as JSONL. Memory: {end_mem:.2f} MB | Duration: {duration:.2f}s", feature=MODULE, file=__file__, prompt_hash=hash(prompt))
                        return "".join(responses)
                    else:
                        log_error("async_generate", "jsonl_parse_fail", f"No valid JSONL lines. Parse errors: {responses}", feature=MODULE, file=__file__, prompt_hash=hash(prompt))
                        end_mem = process.memory_info().rss / 1024 / 1024
                        duration = time.time() - start_time
                        log_error("async_generate", "fail", f"No valid LLM response. Memory: {end_mem:.2f} MB | Duration: {duration:.2f}s", feature=MODULE, file=__file__, prompt_hash=hash(prompt))
                        return f"[LLM error: Could not parse response. Parse errors: {responses}]"
            except Exception as e:
                tb = traceback.format_exc()
                log_error("async_generate", "call", f"Ollama LLM async error: {e}\nTraceback:\n{tb}", feature=MODULE, file=__file__, prompt_hash=hash(prompt))
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                end_mem = process.memory_info().rss / 1024 / 1024
                duration = time.time() - start_time
                log_error("async_generate", "fail", f"Final failure. Memory: {end_mem:.2f} MB | Duration: {duration:.2f}s", feature=MODULE, file=__file__, prompt_hash=hash(prompt))
                return f"[LLM error: {e}]"

    def batch_generate(self, prompts: List[str], **kwargs) -> List[str]:
        """
        Synchronous batch generation for a list of prompts.
        Args:
            prompts (List[str]): List of prompts to send to the LLM.
            **kwargs: Additional parameters for the API.
        Returns:
            List[str]: List of LLM responses.
        """
        return [self.generate(prompt, **kwargs) for prompt in prompts]

    async def batch_async_generate(self, prompts: List[str], **kwargs) -> List[str]:
        """
        Asynchronous batch generation for a list of prompts.
        Args:
            prompts (List[str]): List of prompts to send to the LLM.
            **kwargs: Additional parameters for the API.
        Returns:
            List[str]: List of LLM responses.
        """
        tasks = [self.async_generate(prompt, **kwargs) for prompt in prompts]
        return await asyncio.gather(*tasks) 