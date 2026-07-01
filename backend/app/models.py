from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class ImageStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    GENERATED = "generated"
    APPROVED = "approved"
    FAILED = "failed"


class VideoStatus(str, Enum):
    PENDING = "pending"          # esperando que la imagen se apruebe
    GENERATING = "generating"
    GENERATED = "generated"
    APPROVED = "approved"
    FAILED = "failed"


class ProjectStatus(str, Enum):
    DRAFT = "draft"
    GENERATING_IMAGES = "generating_images"
    REVIEWING_IMAGES = "reviewing_images"
    GENERATING_VIDEOS = "generating_videos"
    REVIEWING_VIDEOS = "reviewing_videos"
    MERGING = "merging"
    COMPLETED = "completed"


class Scene(BaseModel):
    scene_id: str = Field(default_factory=lambda: new_id("scene"))
    order: int
    image_prompt: str
    video_prompt: str

    image_status: ImageStatus = ImageStatus.PENDING
    image_path: Optional[str] = None       # ruta local del último archivo descargado
    image_attempts: int = 0

    video_status: VideoStatus = VideoStatus.PENDING
    video_path: Optional[str] = None
    video_attempts: int = 0

    error: Optional[str] = None


class Project(BaseModel):
    project_id: str = Field(default_factory=lambda: new_id("proj"))
    topic: str
    status: ProjectStatus = ProjectStatus.DRAFT
    scenes: list[Scene] = Field(default_factory=list)
    final_video_path: Optional[str] = None

    def get_scene(self, scene_id: str) -> Scene:
        for s in self.scenes:
            if s.scene_id == scene_id:
                return s
        raise ValueError(f"Scene {scene_id} no encontrada")

    def all_images_approved(self) -> bool:
        return all(s.image_status == ImageStatus.APPROVED for s in self.scenes)

    def all_videos_approved(self) -> bool:
        return all(s.video_status == VideoStatus.APPROVED for s in self.scenes)


# --- Payloads de entrada ---

class CreateProjectFromTopic(BaseModel):
    topic: str
    num_scenes: int = 5


class ScenePromptPair(BaseModel):
    image_prompt: str
    video_prompt: str


class CreateProjectFromJson(BaseModel):
    topic: str
    scenes: list[ScenePromptPair]
