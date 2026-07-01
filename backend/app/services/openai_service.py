import json
from openai import OpenAI
from ..config import OPENAI_API_KEY, OPENAI_MODEL
from ..models import ScenePromptPair

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("Falta OPENAI_API_KEY en el .env")
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


SYSTEM_PROMPT = """Sos un guionista visual experto en generar prompts para IA de \
imagen y video (estilo Veo3 / modelos de difusión). Dado un tema, devolvés \
ÚNICAMENTE un JSON válido (sin texto adicional, sin markdown) con esta forma exacta:

{
  "scenes": [
    {"image_prompt": "...", "video_prompt": "..."},
    ...
  ]
}

Reglas:
- image_prompt: descripción visual detallada de una sola imagen fija (estilo, \
  composición, iluminación, personajes, encuadre). En inglés, apto para \
  generadores de imagen.
- video_prompt: describe el MOVIMIENTO/animación que debe aplicarse a esa \
  imagen de referencia (cámara, acción, transición). También en inglés. No \
  repitas la descripción estática de la imagen, enfocate en el movimiento.
- Las escenas deben tener continuidad narrativa entre sí (son parte de un \
  mismo video corto vertical).
- Formato pensado para video vertical 9:16.
"""


def generate_scenes_from_topic(topic: str, num_scenes: int = 5) -> list[ScenePromptPair]:
    client = get_client()
    user_prompt = (
        f"Tema: {topic}\n"
        f"Generá exactamente {num_scenes} escenas siguiendo el formato indicado."
    )

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.8,
    )

    raw = response.choices[0].message.content
    data = json.loads(raw)
    scenes = data.get("scenes", [])

    if not scenes:
        raise ValueError("El modelo no devolvió escenas válidas")

    return [ScenePromptPair(**s) for s in scenes]
