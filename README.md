# Ollama 7B Code Llama Python Project

## Table of Contents

- [Features](#features)
- [Setup](#setup)
- [How to Run](#how-to-run)
- [Interactive CLI](#interactive-cli)
- [Running the Server and Health Check](#running-the-server-and-health-check)
- [Usage](#usage)
- [HTTP API Usage](#http-api-usage)
  - [Submit Code as Text](#submit-code-as-text)
  - [Submit Code as a File](#submit-code-as-a-file)
  - [Example Response](#example-response)
- [Scala and Other Languages](#scala-and-other-languages)
- [Contributing](#contributing)
- [License](#license)
- [Usage Examples](#usage-examples)
- [Tips & Best Practices](#tips-and-best-practices)

## Features

| Feature | Description |
|---------|-------------|
| **Local LLM API** | Run and interact with the 7B Code Llama model locally via Ollama |
| **Modern CLI** | Interactive CLI with rich UI, arrow-key navigation, and spinners |
| **Audit Scope Selection** | Choose to audit all files, changed files (PR), README only, or test strategy only |
| **Parallel Analysis & Caching** | LLM file analysis runs in parallel with progress bar and session caching |
| **File Filtering** | Filter files by pattern or manual selection before audit |
| **Configurable Output Directory** | Choose where reports and updated READMEs are saved |
| **API Integration** | Upload generated reports to a remote API endpoint |
| **Automated CLI Tests** | Run a full audit workflow on a public repo for validation |
| **Improved Output Parsing** | LLM output is parsed into structured sections for actionable insights |
| **Persistent Logging** | Rotating log file with detailed logs |
| **Environment Variables** | Used for secrets (API key, GitHub token, log file path) |
| **Graceful Error Handling** | User-friendly error messages and robust validation |

## Setup
1. **Install [Ollama](https://ollama.com/download)** and ensure the 7B Code Llama model is available:
   ```sh
   ollama pull codellama:7b
   ollama serve
   ```
2. **Install Python dependencies:**
   ```sh
   pip install -r requirements.txt
   ```
   This will install all required packages, including [python-dotenv](https://pypi.org/project/python-dotenv/) for .env support.

3. **Configure secrets and environment variables:**
   - Copy `.env.example` to `.env` and fill in your secrets (e.g., `GITHUB_TOKEN`, `OLLAMA_API_KEY`).
   - You can also set these variables directly in your shell or in `config.yaml` (see below for loading order).

## Configuration and Secrets Loading Order

Secrets and config values (like `GITHUB_TOKEN`, `OLLAMA_API_KEY`, etc.) are loaded in this order:

1. **Environment variables** (set in your shell or by your process manager)
2. **.env file** (if present, loaded automatically by python-dotenv)
3. **config.yaml** (as a fallback for non-secret values)

**Best practice:** Use environment variables or a `.env` file for secrets. Only use `config.yaml` for non-sensitive defaults.

Example `.env`:
```
GITHUB_TOKEN=ghp_yourgithubapitoken
OLLAMA_API_KEY=changeme
OLLAMA_LOG_FILE=ollama_server.log
```

> **Important:**
> This project requires **marshmallow 3.x**. Marshmallow 4.x is not supported and will cause runtime errors (e.g., `TypeError: ... got an unexpected keyword argument 'data_key'`).
> If you see this error, run:
> ```sh
> pip install 'marshmallow<4'
> ```

## How to Run

You can start the server in several ways, choosing between development and production modes:

- **Recommended:**
  - Run the interactive CLI:
    ```sh
    python cli.py
    ```
    - Select **Start server** from the menu.
    - Choose **Production (Gunicorn)** for production/multi-user, or **Development (Flask app.run)** for local development/testing.

- **Shell script (production):**
  ```sh
  ./run_server.sh
  ```

- **Makefile (production):**
  ```sh
  make run-server
  ```

- **Manual (production):**
  ```sh
  gunicorn -w 2 --threads 4 -b 0.0.0.0:5000 http_api:app
  ```

- **Manual (development):**
  ```sh
  python http_api.py
  ```

Once running, access the API at [http://localhost:5000](http://localhost:5000). Use `/help` for API documentation.

## Interactive CLI

The project includes a beautiful, interactive CLI powered by [rich](https://github.com/Textualize/rich) and [questionary](https://github.com/tmbo/questionary):

- Arrow-key navigation for all menus
- Colorful, modern UI with section headings and spinners
- Set run parameters (host, model, port) interactively
- Test all API endpoints (health, text, file, github-pr) from the CLI
- View and edit config.yaml
- View recent logs in a styled panel
- Run the example script
- [NEW] **Start server**: Launch the API server with Gunicorn from the menu
- **Audit Scope Selection**: Choose to audit all files, changed files (PR), README only, or test strategy only
- **Parallel Analysis & Caching**: LLM file analysis runs in parallel with progress bar and session caching for speed
- **File Filtering**: Filter files by pattern or manual selection before audit
- **Configurable Output Directory**: Choose where reports and updated READMEs are saved
- **API Integration**: Upload generated reports to a remote API endpoint
- **Automated CLI Tests**: Run a full audit workflow on a public repo for validation
- **Improved Output Parsing**: LLM output is parsed into structured sections for actionable insights

### CLI Main Menu Options
- Show server status
- Start server
- Set run parameters
- Test endpoints
- Run example.py
- Generate GitHub Report
- View config.yaml
- View recent logs
- Help
- Exit
- **Run automated test** (runs a full audit on a public repo and checks for all key sections)
- **Upload report to API** (send a generated report to a remote API endpoint)

### Audit Workflow Enhancements
- **Audit Scope Selection**: After selecting a repo/branch/PR, choose what to audit.
- **Parallel Analysis & Caching**: File analyses are parallelized and cached for speed. Reruns use cached results.
- **File Filtering**: Filter files by glob pattern or manual selection before analysis.
- **Configurable Output Directory**: Choose where reports and updated READMEs are saved.
- **Preview and Edit**: Preview the report in the CLI and open in your editor before saving.
- **Save Only Updated README**: Optionally save the updated README as a separate file.
- **Re-run Only a Section**: Re-run just the README or test strategy analysis without repeating the whole audit.
- **Improved Output Parsing**: LLM output is parsed into summary, bugs/issues, suggestions, code examples, code smells, security/performance, and test coverage.
- **API Integration**: Upload reports to a remote API endpoint with custom headers.
- **Automated CLI Tests**: Validate the workflow on a public repo with a single command.

### Example CLI session
```
================ Ollama Code Llama CLI ================
? Main Menu:
  ▸ Generate GitHub Report
    Run automated test
    Upload report to API
    ...
```

## Running the Server and Health Check

1. **Start the Flask API server:**
   ```sh
   python http_api.py
   ```
   This will start the API at http://localhost:5000

2. **Check if the LLM is running:**
   ```sh
   curl http://localhost:5000/health
   ```
   You should see a JSON response like:
   ```json
   { "status": "ok", "llm_reply": "pong" }
   ```
   (or whatever the LLM replies to "ping").

## Usage
See `example.py` for a basic usage example:
```sh
python example.py
```

## HTTP API Usage

You can interact with the LLM via HTTP endpoints for both text and file-based code analysis.

### Submit Code as Text

POST to `/generate/text` with a JSON body:

```sh
curl -X POST http://localhost:5000/generate/text \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Analyze the following code for bugs and suggest improvements:\n\ndef add(a, b):\n    return a + b"}'
```

### Submit Code as a File

POST to `/generate/file` with form-data:

```sh
curl -X POST http://localhost:5000/generate/file \
  -F "file=@my_code.py"
```

### Example Response
```json
{
  "response": "The function add is correct for adding two numbers. For improvement, consider adding type hints and input validation."
}
```

## Scala and Other Languages

The Code Llama 7B model supports multiple programming languages, including Scala. You can submit Scala code for analysis using the same HTTP endpoints. For best results, make your prompt explicit, for example:

```
Analyze the following Scala code for bugs and suggest improvements:

def add(a: Int, b: Int): Int = a + b
```

**Note:** The model's proficiency in Scala is generally good for common patterns, but may be less accurate for advanced or niche features. Always review the LLM's suggestions before applying them in production.

## Contributing
Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

## License
MIT 

## Usage Examples

### 1. Generate a GitHub Audit Report (Full Workflow)

```
$ python cli.py
? Main Menu: Generate GitHub Report
? GitHub token: <your_token>
? GitHub repo (e.g. user/repo): psf/requests
? Branch (leave blank for default): master
? PR number (leave blank if not analyzing a PR):
? What do you want to audit?: All code files
? Would you like to filter which files to include in the audit?: Yes
? Filter files by: Pattern (glob/regex)
? Enter glob pattern (e.g. *.py, src/*.js): *.py
? Output directory for reports and README? (default: reports): my_audits
? Open full report in your editor before saving?: No
? Save the updated README as a separate file?: Yes
```
- The audit runs in parallel, showing a progress bar.
- The report and updated README are saved in `my_audits/`.

### 2. Audit Only Changed Files in a PR
```
? Main Menu: Generate GitHub Report
? ...
? PR number (leave blank if not analyzing a PR): 123
? What do you want to audit?: Only changed files (for PR)
```
- Only files changed in PR #123 are analyzed.

### 3. Audit README Only
```
? Main Menu: Generate GitHub Report
? ...
? What do you want to audit?: README only
```
- Only the README is analyzed and improved.

### 4. Run Automated CLI Test
```
? Main Menu: Run automated test
```
- Runs a full audit on a public repo and checks for all key report sections.

### 5. Upload a Report to an API
```
? Main Menu: Upload report to API
? Directory containing report? (default: reports): my_audits
? Select report to upload: github_audit_psf_requests_master.md
? API endpoint URL: https://my-api.example.com/upload
? Add custom headers (e.g., API key)?: Yes
? Header key (leave blank to finish): X-API-KEY
? Value for X-API-KEY: myapikey123
? Send as: JSON (report as string)
```
- The report is POSTed to the specified API endpoint with custom headers.

### 6. Use Parallel Analysis & Caching
- On first run, all files are analyzed in parallel (progress bar shown).
- On rerun, cached results are used for unchanged files, speeding up the audit.

### 7. Filter Files Before Audit
- When prompted, choose to filter files by pattern (e.g., `*.py`) or manual selection.
- Only selected files are included in the audit and report.

### 8. Set Output Directory
- When prompted, enter a directory name (e.g., `my_audits`).
- All reports and updated READMEs will be saved there.

## Tips & Best Practices
- **Use a valid GitHub token** with appropriate scopes for private repos and higher rate limits.
- **Use file filtering** to focus audits on relevant code (e.g., skip vendor or test files).
- **Leverage caching** by rerunning audits after small changes—only changed files are re-analyzed.
- **Preview and edit reports** before saving for maximum control.
- **Automate validation** with the built-in CLI test runner.
- **Upload reports** to your own API or dashboard for team review. 