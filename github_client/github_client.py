"""
github/github_client.py
----------------------
Async and sync GitHub API client and data models for repository, PR, file, comment, and commit metadata.
Handles efficient, type-safe, and rate-limited GitHub data access for code analysis workflows.
"""

import asyncio
import time
import httpx
from pydantic import BaseModel, Field, ValidationError
from typing import List, Optional, Dict, Any
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn
from loguru import logger
import base64
from github import Github

MODULE = "GITHUB_CLIENT"
def log_info(function, action, details):
    logger.info(f"[{MODULE}] [{function}] [{action}] {details}")
def log_warning(function, action, details):
    logger.warning(f"[{MODULE}] [{function}] [{action}] {details}")
def log_error(function, action, details):
    logger.error(f"[{MODULE}] [{function}] [{action}] {details}")
def log_exception(function, action, details):
    logger.exception(f"[{MODULE}] [{function}] [{action}] {details}")

class GitHubRepo(BaseModel):
    """
    Pydantic model representing a GitHub repository.
    """
    name: str
    owner: str
    description: Optional[str] = None
    private: bool
    url: str

async def fetch_repo_data_async(owner: str, repo: str, token: str) -> GitHubRepo:
    """
    Fetch repository data from GitHub asynchronously using httpx.
    Args:
        owner (str): Repository owner.
        repo (str): Repository name.
        token (str): GitHub API token.
    Returns:
        GitHubRepo: Pydantic model with repository details.
    """
    headers = {"Authorization": f"token {token}"}
    url = f"https://api.github.com/repos/{owner}/{repo}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return GitHubRepo(
            name=data["name"],
            owner=data["owner"]["login"],
            description=data.get("description"),
            private=data["private"],
            url=data["html_url"]
        )

class GitHubPullRequestInfo(BaseModel):
    """
    Pydantic model representing pull request metadata.
    """
    title: str
    body: str
    user: str
    created_at: str
    state: str
    merged: bool
    base_branch: str
    head_branch: str
    url: str

class GitHubFile(BaseModel):
    """
    Pydantic model representing a file in a GitHub repository or PR.
    """
    filename: str
    status: Optional[str] = None
    patch: Optional[str] = None
    content: Optional[str] = None

class GitHubComment(BaseModel):
    """
    Pydantic model representing a comment on a GitHub issue or PR.
    """
    user: str
    body: str
    created_at: str
    path: Optional[str] = None
    position: Optional[int] = None

class GitHubCommit(BaseModel):
    """
    Pydantic model representing a commit in a GitHub repository.
    """
    sha: str
    message: str
    author: str
    date: str

class AsyncGitHubClient:
    """
    Asynchronous GitHub API client using httpx for non-blocking requests.
    Handles rate limiting and retries.
    """
    def __init__(self, token: str):
        self.token = token
        self.headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
        self.base_url = "https://api.github.com"
        self.client = httpx.AsyncClient(headers=self.headers, timeout=30)

    async def get(self, endpoint: str, params: dict = None, retries: int = 3) -> dict:
        """
        Perform an async GET request to the GitHub API with retries and rate limit handling.
        Args:
            endpoint (str): API endpoint (e.g., /repos/owner/repo).
            params (dict, optional): Query parameters.
            retries (int): Number of retries on failure.
        Returns:
            dict: JSON response from the API.
        """
        url = f"{self.base_url}{endpoint}"
        for attempt in range(retries):
            try:
                response = await self.client.get(url, params=params)
                # Handle rate limiting
                if response.status_code == 403 and 'X-RateLimit-Remaining' in response.headers and response.headers['X-RateLimit-Remaining'] == '0':
                    reset = int(response.headers.get('X-RateLimit-Reset', '0'))
                    wait = max(reset - int(time.time()), 1)
                    logger.warning(f"GitHub API rate limit hit. Waiting {wait} seconds...")
                    await asyncio.sleep(wait)
                    continue
                response.raise_for_status()
                return response.json()
            except Exception as error:
                logger.error(f"GitHub API GET {endpoint} failed (attempt {attempt+1}): {error}")
                await asyncio.sleep(2 ** attempt)
        raise RuntimeError(f"GitHub API GET {endpoint} failed after {retries} attempts.")

    async def close(self):
        """
        Close the underlying httpx.AsyncClient session.
        """
        await self.client.aclose()

def list_code_files(contents, get_contents_func, ref, is_async=False):
    """
    Recursively traverse and return a flat list of code file objects from a GitHub repo.
    Args:
        contents (list): Initial list of content objects (from GitHub API).
        get_contents_func (callable): Function to get contents of a directory.
        ref (str): Branch or ref name.
        is_async (bool): Whether to use await for get_contents_func.
    Returns:
        list: List of file content objects (files only, filtered by extension).
    """
    stack = contents[:]
    files = []
    while stack:
        file_content = stack.pop()
        if file_content['type'] == "dir":
            if is_async:
                # For async, get_contents_func returns a coroutine
                import asyncio
                subdir = asyncio.get_event_loop().run_until_complete(get_contents_func(file_content['path'], ref))
            else:
                subdir = get_contents_func(file_content['path'], ref)
            stack.extend(subdir)
        else:
            if file_content['name'].endswith((
                '.py', '.js', '.ts', '.java', '.go', '.rb', '.cpp', '.c', '.cs', '.php', '.scala', '.rs', '.sh', '.pl', '.swift', '.kt', '.m', '.h', '.hpp', '.html', '.css', '.json', '.yml', '.yaml', '.xml', '.md')):
                files.append(file_content)
    return files

async def async_fetch_repo_data(
    repo_full_name: str,
    branch: Optional[str],
    pr_number: Optional[int],
    token: str
) -> dict:
    """
    Fetch code files, comments, commits, and README from a GitHub repo asynchronously.
    Returns a dict with lists of Pydantic models for files, comments, commits, readme, and pr_info.
    Args:
        repo_full_name (str): Full repo name (e.g., owner/repo).
        branch (str or None): Branch name.
        pr_number (int or None): PR number.
        token (str): GitHub API token.
    Returns:
        dict: Dictionary with files, comments, commits, readme, and pr_info.
    """
    client = AsyncGitHubClient(token)
    owner, repo = repo_full_name.split('/')
    files: list = []
    comments: list = []
    commits: list = []
    readme: str = ""
    pr_info: Optional[GitHubPullRequestInfo] = None
    try:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), TimeElapsedColumn(), TimeRemainingColumn(), transient=True) as progress:
            if pr_number:
                # Fetch PR info and changed files
                pr_task = progress.add_task("Fetching PR info...", total=1)
                pr = await client.get(f"/repos/{owner}/{repo}/pulls/{pr_number}")
                pr_info = GitHubPullRequestInfo(
                    title=pr['title'],
                    body=pr['body'],
                    user=pr['user']['login'],
                    created_at=pr['created_at'],
                    state=pr['state'],
                    merged=pr.get('merged', False),
                    base_branch=pr['base']['ref'],
                    head_branch=pr['head']['ref'],
                    url=pr['html_url']
                )
                progress.update(pr_task, advance=1)
                files_task = progress.add_task("Fetching changed files...", total=1)
                pr_files = await client.get(f"/repos/{owner}/{repo}/pulls/{pr_number}/files")
                file_tasks = [client.get(f"/repos/{owner}/{repo}/contents/{file['filename']}", params={"ref": pr['head']['ref']}) for file in pr_files]
                file_results = await asyncio.gather(*file_tasks, return_exceptions=True)
                for file, content in zip(pr_files, file_results):
                    file_content = None
                    if isinstance(content, dict) and 'content' in content:
                        try:
                            file_content = base64.b64decode(content['content']).decode('utf-8')
                        except Exception:
                            file_content = None
                    files.append(GitHubFile(
                        filename=file['filename'],
                        status=file['status'],
                        patch=file.get('patch'),
                        content=file_content
                    ))
                progress.update(files_task, advance=1)
                # Fetch PR comments
                comments_task = progress.add_task("Fetching PR comments...", total=1)
                pr_comments = await client.get(f"/repos/{owner}/{repo}/issues/{pr_number}/comments")
                for comment in pr_comments:
                    comments.append(GitHubComment(
                        user=comment['user']['login'],
                        body=comment['body'],
                        created_at=comment['created_at']
                    ))
                review_comments = await client.get(f"/repos/{owner}/{repo}/pulls/{pr_number}/comments")
                for comment in review_comments:
                    comments.append(GitHubComment(
                        user=comment['user']['login'],
                        body=comment['body'],
                        path=comment['path'],
                        position=comment.get('position'),
                        created_at=comment['created_at']
                    ))
                progress.update(comments_task, advance=1)
                # Fetch PR commits
                commits_task = progress.add_task("Fetching PR commits...", total=1)
                pr_commits = await client.get(f"/repos/{owner}/{repo}/pulls/{pr_number}/commits")
                for commit in pr_commits:
                    commits.append(GitHubCommit(
                        sha=commit['sha'],
                        message=commit['commit']['message'],
                        author=commit['commit']['author']['name'],
                        date=commit['commit']['author']['date']
                    ))
                progress.update(commits_task, advance=1)
                # Fetch README from base branch
                readme_task = progress.add_task("Fetching README...", total=1)
                try:
                    readme_obj = await client.get(f"/repos/{owner}/{repo}/readme", params={"ref": pr['base']['ref']})
                    readme = base64.b64decode(readme_obj['content']).decode('utf-8')
                except Exception:
                    readme = ""
                progress.update(readme_task, advance=1)
            else:
                # Fetch all files, comments, commits, and README for a branch
                ref = branch or (await client.get(f"/repos/{owner}/{repo}")).get('default_branch', 'main')
                contents_task = progress.add_task("Fetching repo files...", total=1)
                contents = await client.get(f"/repos/{owner}/{repo}/contents", params={"ref": ref})
                stack = contents[:]
                file_tasks = []
                while stack:
                    file_content = stack.pop()
                    if file_content['type'] == "dir":
                        subdir = await client.get(f"/repos/{owner}/{repo}/contents/{file_content['path']}", params={"ref": ref})
                        stack.extend(subdir)
                    else:
                        # Only include code files (basic filter)
                        if file_content['name'].endswith((
                            '.py', '.js', '.ts', '.java', '.go', '.rb', '.cpp', '.c', '.cs', '.php', '.scala', '.rs', '.sh', '.pl', '.swift', '.kt', '.m', '.h', '.hpp', '.html', '.css', '.json', '.yml', '.yaml', '.xml', '.md')):
                            file_tasks.append(client.get(f"/repos/{owner}/{repo}/contents/{file_content['path']}", params={"ref": ref}))
                file_results = await asyncio.gather(*file_tasks, return_exceptions=True)
                for content in file_results:
                    if isinstance(content, dict) and 'content' in content:
                        try:
                            file_content = base64.b64decode(content['content']).decode('utf-8')
                        except Exception:
                            file_content = None
                        files.append(GitHubFile(
                            filename=content['path'],
                            content=file_content
                        ))
                progress.update(contents_task, advance=1)
                # Fetch branch commits
                commits_task = progress.add_task("Fetching branch commits...", total=1)
                branch_commits = await client.get(f"/repos/{owner}/{repo}/commits", params={"sha": ref})
                for commit in branch_commits:
                    commits.append(GitHubCommit(
                        sha=commit['sha'],
                        message=commit['commit']['message'],
                        author=commit['commit']['author']['name'],
                        date=commit['commit']['author']['date']
                    ))
                progress.update(commits_task, advance=1)
                # Fetch issue comments
                comments_task = progress.add_task("Fetching issue comments...", total=1)
                issues = await client.get(f"/repos/{owner}/{repo}/issues", params={"state": "all"})
                for issue in issues:
                    issue_comments = await client.get(f"/repos/{owner}/{repo}/issues/{issue['number']}/comments")
                    for comment in issue_comments:
                        comments.append(GitHubComment(
                            user=comment['user']['login'],
                            body=comment['body'],
                            created_at=comment['created_at']
                        ))
                progress.update(comments_task, advance=1)
                # Fetch README
                readme_task = progress.add_task("Fetching README...", total=1)
                try:
                    readme_obj = await client.get(f"/repos/{owner}/{repo}/readme", params={"ref": ref})
                    readme = base64.b64decode(readme_obj['content']).decode('utf-8')
                except Exception:
                    readme = ""
                progress.update(readme_task, advance=1)
    finally:
        await client.close()
    return {
        'files': [file.dict() for file in files],
        'comments': [comment.dict() for comment in comments],
        'commits': [commit.dict() for commit in commits],
        'readme': readme,
        'pr_info': pr_info.dict() if pr_info else None
    }

def fetch_repo_data(
    repo_full_name: str,
    branch: Optional[str],
    pr_number: Optional[int],
    token: str
) -> dict:
    """
    Fetch code files, changed files (if PR), code comments, commit messages, and README from a GitHub repo (synchronous).
    Returns a dict with lists of Pydantic models for files, comments, commits, and PR info.
    Args:
        repo_full_name (str): Full repo name (e.g., owner/repo).
        branch (str or None): Branch name.
        pr_number (int or None): PR number.
        token (str): GitHub API token.
    Returns:
        dict: Dictionary with files, comments, commits, readme, and pr_info.
    """
    github_client = Github(token)
    repository = github_client.get_repo(repo_full_name)
    files = []
    comments = []
    commits = []
    readme = ""
    pr_info = None
    try:
        if pr_number:
            # Fetch PR info and changed files
            pull_request = repository.get_pull(pr_number)
            pr_info = GitHubPullRequestInfo(
                title=pull_request.title,
                body=pull_request.body,
                user=pull_request.user.login,
                created_at=pull_request.created_at.isoformat(),
                state=pull_request.state,
                merged=pull_request.is_merged(),
                base_branch=pull_request.base.ref,
                head_branch=pull_request.head.ref,
                url=pull_request.html_url
            )
            for file in pull_request.get_files():
                try:
                    file_content = repository.get_contents(file.filename, ref=pull_request.head.ref).decoded_content.decode('utf-8')
                except Exception:
                    file_content = None
                files.append(GitHubFile(
                    filename=file.filename,
                    status=file.status,
                    patch=getattr(file, 'patch', None),
                    content=file_content
                ))
            for comment in pull_request.get_issue_comments():
                comments.append(GitHubComment(
                    user=comment.user.login,
                    body=comment.body,
                    created_at=comment.created_at.isoformat()
                ))
            for comment in pull_request.get_review_comments():
                comments.append(GitHubComment(
                    user=comment.user.login,
                    body=comment.body,
                    path=comment.path,
                    position=comment.position,
                    created_at=comment.created_at.isoformat()
                ))
            for commit in pull_request.get_commits():
                commits.append(GitHubCommit(
                    sha=commit.sha,
                    message=commit.commit.message,
                    author=commit.commit.author.name,
                    date=commit.commit.author.date.isoformat()
                ))
            try:
                readme = repository.get_readme(ref=pull_request.base.ref).decoded_content.decode('utf-8')
            except Exception:
                readme = ""
        else:
            # Fetch all files, comments, commits, and README for a branch
            ref = branch or repository.default_branch
            contents = repository.get_contents("", ref=ref)
            stack = contents[:]
            while stack:
                file_content = stack.pop()
                if file_content.type == "dir":
                    stack.extend(repository.get_contents(file_content.path, ref=ref))
                else:
                    # Only include code files (basic filter)
                    if file_content.name.endswith((
                        '.py', '.js', '.ts', '.java', '.go', '.rb', '.cpp', '.c', '.cs', '.php', '.scala', '.rs', '.sh', '.pl', '.swift', '.kt', '.m', '.h', '.hpp', '.html', '.css', '.json', '.yml', '.yaml', '.xml', '.md')):
                        files.append(GitHubFile(
                            filename=file_content.path,
                            content=file_content.decoded_content.decode('utf-8')
                        ))
            for commit in repository.get_commits(sha=ref):
                commits.append(GitHubCommit(
                    sha=commit.sha,
                    message=commit.commit.message,
                    author=commit.commit.author.name,
                    date=commit.commit.author.date.isoformat()
                ))
            for issue in repository.get_issues(state='all'):
                for comment in issue.get_comments():
                    comments.append(GitHubComment(
                        user=comment.user.login,
                        body=comment.body,
                        created_at=comment.created_at.isoformat()
                    ))
            try:
                readme = repository.get_readme(ref=ref).decoded_content.decode('utf-8')
            except Exception:
                readme = ""
    except Exception as error:
        logger.exception("Error in fetch_repo_data")
    return {
        'files': [file.dict() for file in files],
        'comments': [comment.dict() for comment in comments],
        'commits': [commit.dict() for commit in commits],
        'readme': readme,
        'pr_info': pr_info.dict() if pr_info else None
    }

# More functions and models can be added here as you modularize further. 