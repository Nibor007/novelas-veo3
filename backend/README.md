# Backend — Veo3 Video Generator

## Instalación

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

Necesitás además `ffmpeg` instalado en el sistema (para el merge final):
- Mac: `brew install ffmpeg`
- Ubuntu: `sudo apt install ffmpeg`
- Windows: descargar de https://ffmpeg.org y agregar al PATH

Copiá `.env.example` a `.env` y completá tu `OPENAI_API_KEY`.

## Correr

```bash
uvicorn app.main:app --reload --port 8000
```

La primera vez que se ejecute `generate_image` o `generate_video`, se va a
abrir un Chromium visible (porque `HEADLESS=false`) apuntando a Veo3. Si no
estás logueado en tu cuenta de Google, logueate manualmente esa primera vez:
la sesión queda guardada en `chrome_profile/` y no vas a tener que volver a
loguearte en corridas futuras.

## ⚠️ Pendiente antes de que esto funcione

El archivo `app/services/veo_automation.py` tiene selectores **placeholder**
(marcados con `# TODO`). Hay que:

1. Abrir Veo3 manualmente en Chrome con devtools.
2. Inspeccionar el campo de prompt, los selectores de formato/cantidad/modelo,
   el botón de generar y el de descargar.
3. Reemplazar cada selector placeholder por el real
   (`data-testid`, `aria-label`, texto visible, etc.)

## Flujo de endpoints (orden típico)

1. `POST /projects` — con `{"topic": "...", "num_scenes": 5}` → genera los
   prompts con OpenAI
   - o `POST /projects/from-json` si subís tu propio JSON de escenas
2. Por cada escena: `POST /projects/{id}/scenes/{sid}/generate-image`
3. Frontend consulta `GET /projects/{id}` (polling) hasta ver `image_status:
   "generated"`, muestra la imagen (`/media/...`) para aprobar
4. `POST /projects/{id}/scenes/{sid}/approve-image` (o `reject-image` para
   regenerar)
5. Cuando la imagen está aprobada: `POST
   /projects/{id}/scenes/{sid}/generate-video`
6. Igual que con imágenes: aprobar con `approve-video` / regenerar con
   `reject-video`
7. Cuando todos los videos están aprobados: `POST /projects/{id}/merge`
8. El resultado queda en `project.final_video_path`, servido en `/media/...`
