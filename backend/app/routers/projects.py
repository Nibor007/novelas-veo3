from fastapi import APIRouter, HTTPException
from ..models import (
    Project, Scene, ProjectStatus,
    CreateProjectFromTopic, CreateProjectFromJson,
)
from .. import storage
from ..services.openai_service import generate_scenes_from_topic

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=Project)
def create_from_topic(payload: CreateProjectFromTopic):
    """Genera el listado de escenas (prompts de imagen + video) a partir de
    un tema, usando OpenAI."""
    pairs = generate_scenes_from_topic(payload.topic, payload.num_scenes)

    project = Project(
        topic=payload.topic,
        status=ProjectStatus.DRAFT,
        scenes=[
            Scene(order=i, image_prompt=p.image_prompt, video_prompt=p.video_prompt)
            for i, p in enumerate(pairs)
        ],
    )
    storage.save_project(project)
    return project


@router.post("/from-json", response_model=Project)
def create_from_json(payload: CreateProjectFromJson):
    """Crea un proyecto a partir de un JSON de escenas ya generado
    externamente (subido por el usuario)."""
    project = Project(
        topic=payload.topic,
        status=ProjectStatus.DRAFT,
        scenes=[
            Scene(order=i, image_prompt=s.image_prompt, video_prompt=s.video_prompt)
            for i, s in enumerate(payload.scenes)
        ],
    )
    storage.save_project(project)
    return project


@router.get("", response_model=list[Project])
def list_all():
    return storage.list_projects()


@router.get("/{project_id}", response_model=Project)
def get_project(project_id: str):
    try:
        return storage.load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(404, "Proyecto no encontrado")


@router.delete("/{project_id}")
def delete_project(project_id: str):
    storage.delete_project(project_id)
    return {"ok": True}
