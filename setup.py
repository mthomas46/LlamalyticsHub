from setuptools import setup, find_packages

setup(
    name="ollama-code-llama",
    version="0.1.0",
    description="Python interface for Ollama 7B Code Llama model",
    author="Your Name",
    license="MIT",
    packages=find_packages(),
    py_modules=["ollama_code_llama"],
    install_requires=[
        "requests>=2.31.0"
    ],
    python_requires=">=3.7",
    url="https://github.com/yourusername/ollama-code-llama",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    entry_points={
        "console_scripts": [
            "ollama-code-llama=cli:main",
        ],
    },
) 