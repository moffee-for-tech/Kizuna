import os
import re
from pathlib import Path
from typing import Optional, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = PROJECT_ROOT / "ponytail" / "skills"

def _strip_frontmatter(text: str) -> str:
    return re.sub(r"^---[\s\S]*?---\s*", "", text or "", count=1)

def _parse_frontmatter(text: str) -> Dict[str, str]:
    meta = {}
    match = re.match(r"^---([\s\S]*?)---", text)
    if match:
        yaml_content = match.group(1)
        for line in yaml_content.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, val = line.split(":", 1)
            # Basic YAML string parsing (strip quotes, trim whitespace)
            val = val.strip().strip("'\"")
            # Handle multi-line strings indicator
            if val == ">" or val == "|":
                continue
            meta[key.strip()] = val
    return meta

def _filter_skill_body_for_mode(body: str, mode: str) -> str:
    effective = mode.strip().lower()
    if effective not in {"lite", "full", "ultra"}:
        effective = "full"
        
    lines = []
    for line in body.splitlines():
        # Check table row filters (e.g. | **lite** | What change |)
        table_label = re.match(r"^\|\s*\*\*(.+?)\*\*\s*\|", line)
        if table_label:
            label_mode = table_label.group(1).strip().lower()
            if label_mode in {"lite", "full", "ultra"} and label_mode != effective:
                continue

        # Check list item filters (e.g. - lite: ...)
        example_label = re.match(r"^-\s*([^:]+):\s*", line)
        if example_label:
            label_mode = example_label.group(1).strip().lower()
            if label_mode in {"lite", "full", "ultra"} and label_mode != effective:
                continue

        lines.append(line)
    return "\n".join(lines)

def list_skills() -> List[Dict[str, str]]:
    """Scan the ponytail/skills directory and return a list of available skills with metadata."""
    skills = []
    if not SKILLS_DIR.exists():
        return skills
        
    for entry in sorted(SKILLS_DIR.iterdir()):
        if entry.is_dir():
            skill_md = entry / "SKILL.md"
            if skill_md.exists():
                try:
                    content = skill_md.read_text(encoding="utf-8")
                    meta = _parse_frontmatter(content)
                    
                    skill_id = entry.name
                    # If description key has no value because it used multiline indicator,
                    # we can fallback or extract it.
                    desc = meta.get("description", "")
                    if not desc:
                        # Extract description block
                        match = re.search(r"description:\s*[>|]\s*\n([\s\S]*?)(?=\n\w+:|---)", content)
                        if match:
                            desc = re.sub(r"\s+", " ", match.group(1).strip())
                            
                    skills.append({
                        "id": skill_id,
                        "name": meta.get("name", skill_id),
                        "description": desc or f"Custom skill {skill_id}"
                    })
                except Exception as e:
                    # Ignore malformed files, proceed with others
                    continue
    return skills

def load_skill_instructions(skill_id: str, lazy_senior_mode: str = "full") -> str:
    """Load and return the raw instruction text for a skill, filtering if it is the core lazy-senior skill."""
    skill_file = SKILLS_DIR / skill_id / "SKILL.md"
    if not skill_file.exists():
        return ""
        
    try:
        content = skill_file.read_text(encoding="utf-8")
        body = _strip_frontmatter(content)
        
        if skill_id == "lazy-senior":
            return f"LAZY SENIOR MODE ACTIVE — level: {lazy_senior_mode}\n\n" + _filter_skill_body_for_mode(body, lazy_senior_mode)
        
        return f"ACTIVE SKILL: {skill_id.upper()}\n\n" + body
    except Exception:
        return ""
