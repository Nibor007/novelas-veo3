from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import MEDIA_DIR
from .routers import projects, scenes

app = FastAPI(title="Veo3 Video Generator API")

# Frontend (Next.js) corriendo en localhost:3000 por defecto
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sirve las imágenes/videos descargados para que el frontend los muestre
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")

app.include_router(projects.router)
app.include_router(scenes.router)
app.include_router(scenes.merge_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.on_event("shutdown")
async def shutdown_event():
    from .services.veo_automation import close_context
    await close_context()
