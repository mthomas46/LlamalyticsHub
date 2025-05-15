import requests
import json
from loguru import logger
from rich.console import Console
import httpx
import asyncio

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

    async def async_generate(self, prompt, options=None):
        """
        Asynchronously generate code or text using the LLM.
        """
        logger.info(f"[async] Generating response for prompt: {prompt[:50]}...")
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
                        logger.error(f"JSON decode error for line: {line} | Error: {e}")
                full_response = "".join(responses)
                logger.info("[async] Generation complete.")
                if not full_response:
                    logger.warning("LLM returned an empty response.")
                return full_response
            except httpx.RequestError as e:
                logger.error(f"[async] Request to LLM failed: {e}")
                console.print_exception()
                raise RuntimeError(f"Request to LLM failed: {e}")
            except Exception as e:
                logger.exception("Unexpected error in async_generate")
                console.print_exception()
                raise

    async def batch_async_generate(self, prompts, options=None):
        """
        Asynchronously generate responses for a batch of prompts.
        Returns a list of responses in the same order as prompts.
        """
        logger.info(f"[async] Batch generating {len(prompts)} prompts...")
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
                    logger.error(f"Batch LLM call failed: {resp}")
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
                            logger.error(f"JSON decode error for line: {line} | Error: {e}")
                    results.append("".join(out))
                except Exception as e:
                    logger.error(f"Error parsing batch LLM response: {e}")
                    results.append("")
            logger.info("[async] Batch generation complete.")
            return results 