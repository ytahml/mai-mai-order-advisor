"""Dependency-free, offline project checks; never prints matched secret values."""

import ast
import hashlib
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent.parent
DECLARATION_SHA256 = "cd28101bcb29cc8fb24b372fe91ce6b42c4a1487a54e01f7ade0c8c6a84241b7"
REQUIRED = ("README.md", "SKILL.md", "MCP_INTEGRATION.md", "CONTEST_DECLARATION.md",
            "mcp-config.example.json", "docs/design.md", "references/contracts.md", "fixtures/demo.json")
SKIP = {".git", "__pycache__", ".venv", ".local"}
TEXT_SUFFIXES = {".py", ".md", ".json", ".toml", ".txt"}
# Heuristic checks, not a guarantee that arbitrary personal information is absent.
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\b(?:ghp_|github_pat_|sk-)[A-Za-z0-9_]{20,}\b"),
    re.compile(r"Bearer\s+(?!\$\{MCD_MCP_TOKEN\})[A-Za-z0-9._-]{16,}"),
]


def main():
    errors = []
    count = 0
    for name in REQUIRED:
        if not (ROOT / name).is_file():
            errors.append(f"missing required file: {name}")
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if any(part in SKIP for part in relative.parts) or not path.is_file():
            continue
        if path.name == ".env" or path.name.startswith(".env."):
            errors.append(f"environment file in project: {relative}")
        if path.suffix not in TEXT_SUFFIXES and path.name != ".gitignore":
            continue
        count += 1
        text = path.read_text(encoding="utf-8")
        for index, line in enumerate(text.splitlines(), 1):
            if line.rstrip() != line or "\t" in line:
                errors.append(f"whitespace: {relative}:{index}")
            if path.suffix == ".py" and len(line) > 110:
                errors.append(f"Python line longer than 110: {relative}:{index}")
        if not text.endswith("\n"):
            errors.append(f"missing final newline: {relative}")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"possible secret (value withheld): {relative}")
        if path.suffix == ".py":
            tree = ast.parse(text, filename=str(relative))
            if relative.parts[0] == "copilot":
                for node in ast.walk(tree):
                    names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                             else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                    if any(name.split(".")[0] in {"socket", "urllib", "http", "requests",
                                                  "subprocess"} for name in names):
                        errors.append(f"unexpected transport/process import: {relative}")
        if path.suffix == ".json":
            json.loads(text)
        if path.suffix == ".md":
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
                if "://" not in target and not target.startswith("#"):
                    link = target.split("#", 1)[0]
                    if not (path.parent / link).is_file():
                        errors.append(f"broken local link: {relative} -> {link}")
    declaration = ROOT / "CONTEST_DECLARATION.md"
    if declaration.is_file() and hashlib.sha256(declaration.read_bytes()).hexdigest() != DECLARATION_SHA256:
        errors.append("official declaration local snapshot changed; verify upstream original")
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    if not skill.startswith("---\nname: mai-mai-order-advisor\ndescription: ") or "\n---\n" not in skill[4:]:
        errors.append("invalid Skill frontmatter")
    example = json.loads((ROOT / "mcp-config.example.json").read_text(encoding="utf-8"))
    if example["mcpServers"]["mcd-mcp"]["headers"]["Authorization"] != "Bearer ${MCD_MCP_TOKEN}":
        errors.append("configuration must use environment placeholder")
    fixture = json.loads((ROOT / "fixtures/demo.json").read_text(encoding="utf-8"))
    if "SYNTHETIC FIXTURE" not in fixture["notice"]:
        errors.append("fixture must clearly declare synthetic origin")

    def check_sources(value):
        if isinstance(value, dict):
            if "source" in value and value["source"] != "fixture":
                errors.append("non-fixture source in demonstration data")
            for child in value.values():
                check_sources(child)
        elif isinstance(value, list):
            for child in value:
                check_sources(child)

    check_sources(fixture)
    if errors:
        print("\n".join(errors))
        return 1
    print(f"PASS: {count} text files; syntax, basic format, local links, contest files,")
    print("Skill frontmatter, declaration snapshot and heuristic secret scan.")
    print("Offline only; does not validate live MCP schemas or prove absence of all personal data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
