from fastapi import APIRouter, HTTPException, BackgroundTasks
from ..models import ImageStatus, VideoStatus, ProjectStatus
from .. import storage
from ..services import veo_automation, video_merge

router = APIRouter(prefix="/projects/{project_id}/scenes", tags=["scenes"])


# ---------- IMÁGENES ----------

@router.post("/{scene_id}/generate-image")
async def generate_image(project_id: str, scene_id: str, background_tasks: BackgroundTasks):
    project = storage.load_project(project_id)
    scene = project.get_scene(scene_id)

    scene.image_status = ImageStatus.GENERATING
    scene.error = None
    project.status = ProjectStatus.GENERATING_IMAGES
    storage.save_project(project)

    background_tasks.add_task(_run_generate_image, project_id, scene_id)
    return {"status": "generating"}


async def _run_generate_image(project_id: str, scene_id: str):
    project = storage.load_project(project_id)
    scene = project.get_scene(scene_id)
    scene.image_attempts += 1
    try:
        output_name = f"{project_id}_{scene_id}_img_{scene.image_attempts}"
        path = await veo_automation.generate_image(scene.image_prompt, output_name)
        scene.image_path = path
        scene.image_status = ImageStatus.GENERATED
    except Exception as e:
        scene.image_status = ImageStatus.FAILED
        scene.error = str(e)
    storage.save_project(project)


@router.post("/{scene_id}/approve-image")
def approve_image(project_id: str, scene_id: str):
    project = storage.load_project(project_id)
    scene = project.get_scene(scene_id)
    if scene.image_status != ImageStatus.GENERATED:
        raise HTTPException(400, "La imagen todavía no fue generada")
    scene.image_status = ImageStatus.APPROVED

    if project.all_images_approved():
        project.status = ProjectStatus.REVIEWING_IMAGES

    storage.save_project(project)
    return {"status": "approved"}


@router.post("/{scene_id}/reject-image")
def reject_image(project_id: str, scene_id: str):
    """Marca la imagen como pendiente de nuevo para poder regenerarla."""
    project = storage.load_project(project_id)
    scene = project.get_scene(scene_id)
    scene.image_status = ImageStatus.PENDING
    storage.save_project(project)
    return {"status": "pending"}


# ---------- VIDEOS ----------

@router.post("/{scene_id}/generate-video")
async def generate_video(project_id: str, scene_id: str, background_tasks: BackgroundTasks):
    project = storage.load_project(project_id)
    scene = project.get_scene(scene_id)

    if scene.image_status != ImageStatus.APPROVED:
        raise HTTPException(400, "La imagen de referencia todavía no fue aprobada")

    scene.video_status = VideoStatus.GENERATING
    scene.error = None
    project.status = ProjectStatus.GENERATING_VIDEOS
    storage.save_project(project)

    background_tasks.add_task(_run_generate_video, project_id, scene_id)
    return {"status": "generating"}


async def _run_generate_video(project_id: str, scene_id: str):
    project = storage.load_project(project_id)
    scene = project.get_scene(scene_id)
    scene.video_attempts += 1
    try:
        output_name = f"{project_id}_{scene_id}_vid_{scene.video_attempts}"
        path = await veo_automation.generate_video(
            scene.video_prompt, scene.image_path, output_name
        )
        scene.video_path = path
        scene.video_status = VideoStatus.GENERATED
    except Exception as e:
        scene.video_status = VideoStatus.FAILED
        scene.error = str(e)
    storage.save_project(project)


@router.post("/{scene_id}/approve-video")
def approve_video(project_id: str, scene_id: str):
    project = storage.load_project(project_id)
    scene = project.get_scene(scene_id)
    if scene.video_status != VideoStatus.GENERATED:
        raise HTTPException(400, "El video todavía no fue generado")
    scene.video_status = VideoStatus.APPROVED

    if project.all_videos_approved():
        project.status = ProjectStatus.REVIEWING_VIDEOS

    storage.save_project(project)
    return {"status": "approved"}


@router.post("/{scene_id}/reject-video")
def reject_video(project_id: str, scene_id: str):
    project = storage.load_project(project_id)
    scene = project.get_scene(scene_id)
    scene.video_status = VideoStatus.PENDING
    storage.save_project(project)
    return {"status": "pending"}


# ---------- MERGE FINAL ----------

merge_router = APIRouter(prefix="/projects/{project_id}", tags=["merge"])


@merge_router.post("/merge")
def merge_final_video(project_id: str, background_tasks: BackgroundTasks):
    project = storage.load_project(project_id)
    if not project.all_videos_approved():
        raise HTTPException(400, "Todavía hay videos sin aprobar")

    project.status = ProjectStatus.MERGING
    storage.save_project(project)

    background_tasks.add_task(_run_merge, project_id)
    return {"status": "merging"}


def _run_merge(project_id: str):
    project = storage.load_project(project_id)
    try:
        final_path = video_merge.merge_project_videos(project)
        project.final_video_path = final_path
        project.status = ProjectStatus.COMPLETED
    except Exception as e:
        project.status = ProjectStatus.REVIEWING_VIDEOS
        # podrías guardar el error en un campo aparte si querés mostrarlo
    storage.save_project(project)
