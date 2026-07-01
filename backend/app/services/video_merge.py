import subprocess
import tempfile
from pathlib import Path
from ..config import MEDIA_DIR
from ..models import Project


def merge_project_videos(project: Project) -> str:
    """Concatena los videos aprobados de todas las escenas (en orden) en un
    único archivo mp4. Requiere ffmpeg instalado en el sistema.
    Devuelve la ruta del archivo final.
    """
    ordered_scenes = sorted(project.scenes, key=lambda s: s.order)
    video_paths = [s.video_path for s in ordered_scenes if s.video_path]

    if len(video_paths) != len(ordered_scenes):
        raise ValueError("Hay escenas sin video generado, no se puede unir todavía")

    # ffmpeg concat demuxer necesita un archivo de texto con la lista de inputs
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        for p in video_paths:
            # escapar comillas simples por las dudas
            safe_path = str(Path(p).resolve()).replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")
        list_file = f.name

    output_path = MEDIA_DIR / f"{project.project_id}_final.mp4"

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        # Fallback: si los videos tienen codecs/resoluciones distintas,
        # "-c copy" falla. Reintentamos re-codificando.
        cmd_reencode = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-c:v", "libx264",
            "-c:a", "aac",
            "-vsync", "vfr",
            str(output_path),
        ]
        result2 = subprocess.run(cmd_reencode, capture_output=True, text=True)
        if result2.returncode != 0:
            raise RuntimeError(f"ffmpeg falló: {result2.stderr[-2000:]}")

    return str(output_path)
