from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def repo_root() -> Path:
    env = os.environ.get("ZOTERO_RSS_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "config.yaml").exists():
            return parent
    return Path.cwd()


def _expand(value: Any) -> Any:
    if isinstance(value, str) and value.startswith("~/"):
        return str(Path(value).expanduser())
    return value


def _expand_tree(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _expand_tree(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_tree(v) for v in obj]
    return _expand(obj)


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return _expand_tree(data)


def load_dotenv(root: Path | None = None) -> None:
    path = (root or repo_root()) / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


class AppConfig:
    def __init__(self, data: dict[str, Any], root: Path, profile: dict[str, Any]):
        self.data = data
        self.root = root
        self.profile = profile

    @property
    def zotero(self) -> dict[str, Any]:
        return self.data.get("zotero", {})

    @property
    def run(self) -> dict[str, Any]:
        return self.data.get("run", {})

    @property
    def llm(self) -> dict[str, Any]:
        return self.data.get("llm", {})

    @property
    def output(self) -> dict[str, Any]:
        return self.data.get("output", {})

    @property
    def data_dir(self) -> Path:
        return Path(self.zotero.get("data_dir", str(Path.home() / "Zotero"))).expanduser()

    @property
    def local_api_base(self) -> str:
        return str(self.zotero.get("local_api_base", "http://127.0.0.1:23119/api")).rstrip(
            "/"
        )

    @property
    def reports_dir(self) -> Path:
        return self.root / self.output.get("reports_dir", "reports")

    @property
    def findings_path(self) -> Path:
        return self.root / self.output.get("findings_file", "findings.md")

    @property
    def skipped_path(self) -> Path:
        return self.root / self.output.get("skipped_file", "reports/skipped.jsonl")

    @property
    def state_path(self) -> Path:
        return self.root / self.output.get("state_file", "data/state.json")

    def llm_settings(self) -> dict[str, Any]:
        block = self.llm
        api_key = os.environ.get(str(block.get("api_key_env", "OPENAI_API_KEY")), "")
        base_url = os.environ.get(
            str(block.get("base_url_env", "OPENAI_BASE_URL")),
            str(block.get("default_base_url", "https://api.openai.com/v1")),
        ).rstrip("/")
        model = os.environ.get(
            str(block.get("model_env", "OPENAI_MODEL")),
            str(block.get("default_model", "gpt-4o-mini")),
        )
        return {
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
            "temperature": float(block.get("temperature", 0.2)),
            "timeout_seconds": int(block.get("timeout_seconds", 90)),
            "max_tokens": int(block.get("max_tokens", 1200)),
            "enabled": bool(api_key),
        }


def load_app_config(config_dir: Path | None = None) -> AppConfig:
    root = repo_root() if config_dir is None else Path(config_dir).expanduser().resolve()
    if config_dir is not None and (root / "config.yaml").exists():
        cfg_path = root / "config.yaml"
        profile_path = root / "research_profile.yaml"
        project_root = root.parent if root.name == "config" else root
    else:
        cfg_path = root / "config" / "config.yaml"
        profile_path = root / "config" / "research_profile.yaml"
        project_root = root
    load_dotenv(project_root)
    return AppConfig(load_yaml(cfg_path), project_root, load_yaml(profile_path))
