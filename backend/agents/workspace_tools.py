import os
import re
import subprocess
import requests
import json
from pathlib import Path
from typing import Dict, Any, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Excluded folders to speed up operations and prevent scanning unnecessary files
EXCLUDE_DIRS = {
    ".git", "node_modules", "venv", ".next", "__pycache__", 
    ".pytest_cache", "data", "dist", "build", ".agents",
    ".openclaw", ".qoder", ".kiro", ".cursor", ".windsurf"
}

def is_excluded(path: Path) -> bool:
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return True
    return False

def workspace_list_files() -> str:
    """Lists all files in the project root recursively, excluding ignored directories."""
    files = []
    for root, dirs, filenames in os.walk(PROJECT_ROOT):
        # Filter directories in-place to prevent traversing them
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        
        for name in filenames:
            full_path = Path(root) / name
            rel_path = full_path.relative_to(PROJECT_ROOT)
            files.append(str(rel_path).replace("\\", "/"))
            
    if not files:
        return "No files found in workspace."
    return "\n".join(files)

def workspace_read_file(path: str) -> str:
    """Reads content of a file in the workspace, ensuring no directory traversal."""
    try:
        # Normalize path
        normalized_path = path.replace("\\", "/")
        full_path = (PROJECT_ROOT / normalized_path).resolve()
        
        # Security check: ensure path is within PROJECT_ROOT
        if not str(full_path).startswith(str(PROJECT_ROOT.resolve())):
            return f"Error: Access denied. Path '{path}' is outside project root."
            
        if not full_path.exists():
            return f"Error: File '{path}' does not exist."
        if not full_path.is_file():
            return f"Error: '{path}' is not a file."
            
        return full_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error reading file '{path}': {str(e)}"

def workspace_git_diff() -> str:
    """Runs git diff to get local changes."""
    try:
        # Run git diff command
        result = subprocess.run(
            ["git", "diff"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True
        )
        diff = result.stdout
        if not diff.strip():
            return "No local git changes (diff is empty)."
        return diff
    except subprocess.CalledProcessError as ce:
        return f"Error running git diff: {ce.stderr or str(ce)}"
    except Exception as e:
        return f"Error executing git diff: {str(e)}"

def workspace_grep(pattern: str) -> str:
    """Runs a grep search recursively in the workspace using pure Python."""
    results = []
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f"Error: Invalid regular expression pattern: {e}"

    for root, dirs, filenames in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for name in filenames:
            file_path = Path(root) / name
            rel_path = file_path.relative_to(PROJECT_ROOT)
            rel_str = str(rel_path).replace("\\", "/")
            
            try:
                # Read line by line
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    for line_num, line in enumerate(f, 1):
                        if rx.search(line):
                            results.append(f"{rel_str}:{line_num}: {line.strip()}")
            except Exception:
                # Skip files we cannot read
                continue
                
    if not results:
        return f"No matches found for pattern '{pattern}'."
    return "\n".join(results[:500]) # Cap output at 500 lines

def workspace_get_skills_registry() -> str:
    """Fetches the list of all available custom skills from the system registry."""
    try:
        from services.skills_service import list_skills
        skills = list_skills()
        if not skills:
            return "No custom skills found in the registry."
        lines = [
            "| Skill ID | Name | Description |",
            "|---|---|---|",
        ]
        for s in skills:
            lines.append(f"| {s['id']} | {s['name']} | {s['description']} |")
        return "\n".join(lines)
    except Exception as e:
        return f"Error loading skills registry: {str(e)}"

def web_search(query: str) -> str:
    """Searches the live web for the latest information using TinyFish Search API."""
    api_key = os.environ.get("TINYFISH_API_KEY", "")
    if not api_key:
        try:
            from config import settings
            api_key = getattr(settings, "TINYFISH_API_KEY", "")
        except Exception:
            pass
        
    if not api_key:
        return "Error: TINYFISH_API_KEY is not set."
        
    try:
        response = requests.get(
            "https://api.search.tinyfish.ai",
            params={"query": query},
            headers={"X-API-Key": api_key},
            timeout=10
        )
        if response.status_code != 200:
            return f"Error: TinyFish API returned status code {response.status_code}: {response.text}"
            
        data = response.json()
        if isinstance(data, dict):
            results = data.get("results", data)
        else:
            results = data
            
        if not results:
            return "No search results found."
            
        if isinstance(results, list):
            formatted = []
            for item in results[:8]:  # Limit to top 8 results to avoid token bloat
                title = item.get("title", "No Title")
                url = item.get("url", "No URL")
                snippet = item.get("snippet", item.get("content", ""))
                formatted.append(f"Title: {title}\nURL: {url}\nSnippet: {snippet}\n---")
            return "\n".join(formatted)
            
        return json.dumps(results, indent=2)
    except Exception as e:
        return f"Error during web search: {str(e)}"

# OpenAI Schema Definitions
WORKSPACE_TOOLS_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "workspace_list_files",
            "description": "Recursively lists all files in the current repository workspace, excluding standard build/version directories (.git, node_modules, venv, etc.).",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_read_file",
            "description": "Reads the contents of a specific file in the repository workspace. Paths should be relative to the repository root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path of the file to read (e.g. backend/main.py)."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_git_diff",
            "description": "Returns the git diff of modifications in the repository workspace.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_grep",
            "description": "Recursively searches for a regex pattern in files within the workspace, similar to running grep.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "The search pattern (e.g. 'lazy-senior:')."
                    }
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_get_skills_registry",
            "description": "Lists all available developer skills currently registered in the Kizuna system (e.g. lazy-senior, lazy-senior-review).",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Searches the live web for the latest information using the TinyFish search engine.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query (e.g. 'latest AI news July 2026')."
                    }
                },
                "required": ["query"]
            }
        }
    }
]

def execute_workspace_tool(name: str, arguments: Dict[str, Any]) -> str:
    """Routes and executes the workspace tools."""
    if name == "workspace_list_files":
        return workspace_list_files()
    elif name == "workspace_read_file":
        return workspace_read_file(arguments.get("path", ""))
    elif name == "workspace_git_diff":
        return workspace_git_diff()
    elif name == "workspace_grep":
        return workspace_grep(arguments.get("pattern", ""))
    elif name == "workspace_get_skills_registry":
        return workspace_get_skills_registry()
    elif name == "web_search":
        return web_search(arguments.get("query", ""))
    else:
        raise ValueError(f"Unknown workspace tool: {name}")
