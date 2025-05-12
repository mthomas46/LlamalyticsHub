from ollama_code_llama import OllamaCodeLlama

if __name__ == "__main__":
    llama = OllamaCodeLlama()
    prompt = "Write a Python function that returns the Fibonacci sequence up to n."
    result = llama.generate(prompt)
    print("Generated code:\n", result) 