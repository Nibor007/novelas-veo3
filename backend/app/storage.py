import json
from pathlib import Path
from .config import PROJECTS_DIR
from .models import Project


def _path(project_id: str) -> Path:
    return PROJECTS_DIR / f"{project_id}.json"


def save_project(project: Project) -> None:
    _path(project.project_id).write_text(
        project.model_dump_json(indent=2), encoding="utf-8"
    )


def load_project(project_id: str) -> Project:
    path = _path(project_id)
    if not path.exists():
        raise FileNotFoundError(f"Proyecto {project_id} no existe")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Project.model_validate(data)


def list_projects() -> list[Project]:
    projects = []
    for f in PROJECTS_DIR.glob("*.json"):
        try:
            projects.append(Project.model_validate(json.loads(f.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return projects


def delete_project(project_id: str) -> None:
    path = _path(project_id)
    if path.exists():
        path.unlink()
