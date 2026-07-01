"""
Automatización de la UI de Veo3 (Google Labs / Flow) con Playwright.

IMPORTANTE: los selectores de abajo (marcados con # TODO) son placeholders.
Tenés que inspeccionar la página real con devtools y reemplazarlos por los
data-testid / aria-label / texto reales de los botones y campos.

Para conseguirlos:
  1. Corré con HEADLESS=false (default) para ver el navegador.
  2. Abrí devtools (F12) sobre la página de Veo3 mientras corre el script,
     o simplemente inspeccioná manualmente antes.
  3. Reemplazá cada selector marcado abajo.

Se usa un perfil persistente de Chromium (launch_persistent_context) para
que la sesión logueada en tu cuenta de Google se mantenga entre corridas,
sin tener que loguearte cada vez.
"""

import asyncio
import re
import time
from pathlib import Path
from playwright.async_api import async_playwright, Page, BrowserContext
from ..config import CHROME_USER_DATA_DIR, CHROME_CHANNEL, VEO3_URL, HEADLESS, GENERATION_TIMEOUT_MS, MEDIA_DIR

_playwright = None
_context: BrowserContext | None = None


async def get_context() -> BrowserContext:
    """Devuelve un contexto persistente único (reutilizado entre llamadas).

    Usa el canal "chrome" (tu Chrome real instalado) en vez del Chromium de
    Playwright, y saca las banderas que delatan automatización, para reducir
    la chance de que Google bloquee el login como "navegador inseguro".
    """
    global _playwright, _context
    if _context is None:
        _playwright = await async_playwright().start()
        _context = await _playwright.chromium.launch_persistent_context(
            user_data_dir=CHROME_USER_DATA_DIR,
            channel=CHROME_CHANNEL,
            headless=HEADLESS,
            viewport={"width": 1400, "height": 900},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-features=Translate,TranslateUI",
            ],
            ignore_default_args=["--enable-automation"],
        )
    return _context


async def close_context():
    global _context, _playwright
    if _context:
        await _context.close()
        _context = None
    if _playwright:
        await _playwright.stop()
        _playwright = None


async def _open_veo3_page(context: BrowserContext) -> Page:
    page = await context.new_page()
    await page.goto(VEO3_URL, wait_until="networkidle")
    return page


async def _enter_flow_app(page: Page):
    """La URL de Flow a veces cae en la landing de marketing en vez de la
    app. Si aparece el botón 'Create with Google Flow', hay que clickearlo
    para entrar."""
    btn = page.get_by_role("button", name=re.compile("Create with Google Flow"))
    if await btn.count() > 0 and await btn.first.is_visible():
        await btn.first.click()
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1000)


async def _ensure_new_project(page: Page):
    """Si estamos en la pantalla inicial (sin proyecto abierto), crea uno."""
    btn = page.get_by_role("button", name=re.compile("Nuevo proyecto"))
    if await btn.count() > 0 and await btn.first.is_visible():
        await btn.first.click()
        await page.wait_for_timeout(1000)


async def _ensure_agent_mode(page: Page):
    """Espera a que aparezca el toolbar de creación (con el pill 'Agente').
    Si el pill del modelo ('Nano Banana...') todavía no está visible, hace
    clic en 'Agente' para revelarlo."""
    agente = page.get_by_text("Agente", exact=True)
    await agente.first.wait_for(state="visible", timeout=15000)

    model_pill = page.get_by_role("button", name=re.compile("Nano Banana"))
    model_visible = await model_pill.count() > 0 and await model_pill.first.is_visible()

    if not model_visible:
        await agente.first.click()
        await page.wait_for_timeout(500)

        # Si por lentitud de la UI todavía no apareció, reintentamos una vez.
        model_visible = await model_pill.count() > 0 and await model_pill.first.is_visible()
        if not model_visible:
            await page.wait_for_timeout(1000)
            model_visible = await model_pill.count() > 0 and await model_pill.first.is_visible()
            if not model_visible:
                await agente.first.click()
                await page.wait_for_timeout(500)


async def _open_generation_settings(page: Page):
    """Click en el botón resumen (el que muestra '🍌 Nano Banana 2 ... x4')
    que abre el popover de configuración."""
    settings_btn = page.get_by_role(
        "button", name=re.compile("Nano Banana 2")
    ).first
    await settings_btn.click()
    await page.wait_for_timeout(300)


async def _select_image_mode(page: Page):
    # El id real es random, pero el sufijo "trigger-IMAGE" es estable
    # (viene del value="IMAGE" pasado al Tabs.Trigger de Radix).
    tab = page.locator('button[role="tab"][id$="trigger-IMAGE"]')
    await tab.click()


async def _select_aspect_ratio_9_16(page: Page):
    # El ícono usa la ligadura de material symbols "crop_9_16" como texto.
    # OJO: la pill colapsada (fuera del popover) también muestra este mismo
    # ícono como resumen del aspect ratio actual, así que hay que excluir
    # ese botón (el que dice "Nano Banana") para no volver a clickearlo y
    # cerrar el popover sin querer.
    icons = page.locator('i:has-text("crop_9_16")')
    count = await icons.count()
    target_btn = None
    for i in range(count):
        btn = icons.nth(i).locator("xpath=ancestor::button[1]")
        text = await btn.inner_text()
        if "Nano Banana" not in text:
            target_btn = btn
            break
    if target_btn is None:
        target_btn = icons.last.locator("xpath=ancestor::button[1]")
    await target_btn.click()


async def _select_quantity_1x(page: Page):
    tab = page.get_by_role("tab", name="1x", exact=True)
    await tab.click()


async def _select_model_nano_banana_2(page: Page):
    """Abre el dropdown de modelo (dentro del popover de settings) y
    selecciona 'Nano Banana 2' si el modelo activo es otro (por ejemplo
    'Nano Banana 2 Lite', que suele ser el default)."""
    # El botón de modelo tiene aria-haspopup="menu" y una flechita
    # "arrow_drop_down". Filtramos por eso para no confundirlo con la pill
    # colapsada de afuera del popover (que no tiene esa flecha).
    model_btn = page.locator('button[aria-haspopup="menu"]').filter(
        has_text="Nano Banana"
    ).filter(has=page.locator('i:has-text("arrow_drop_down")'))

    if await model_btn.count() == 0:
        return  # no encontramos el selector de modelo, seguimos igual

    btn = model_btn.last
    current_text = await btn.inner_text()
    if "Nano Banana 2" in current_text and "Lite" not in current_text:
        return  # ya está en "Nano Banana 2" (no Lite)

    await btn.click()
    await page.wait_for_timeout(300)

    # La opción exacta en el menú incluye el emoji: "🍌 Nano Banana 2"
    # (sin esto, "Nano Banana 2" a secas nunca matchea porque el texto real
    # del <span> trae el emoji adelante). exact=True evita que matchee
    # "🍌 Nano Banana 2 Lite".
    option = page.get_by_text("🍌 Nano Banana 2", exact=True)
    if await option.count() == 0:
        # fallback por si el emoji no se está renderizando como texto plano
        option = page.get_by_role("menuitem", name=re.compile(r"^Nano Banana 2$"))
    await option.first.click()
    await page.wait_for_timeout(300)


async def _fill_prompt(page: Page, prompt: str):
    # El popover de settings puede seguir abierto (con su overlay tapando
    # el editor de prompt) después de elegir modo/ratio/cantidad/modelo.
    # Escape lo cierra sin afectar nada más.
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(300)

    editor = page.locator('[data-slate-editor="true"]')
    await editor.click()
    # Por si quedó texto de un intento anterior
    await page.keyboard.press("Control+A")
    await page.keyboard.press("Backspace")
    await page.keyboard.type(prompt, delay=15)


async def _submit_generation(page: Page):
    # El texto accesible "Crear" también matchea otro botón distinto
    # (uno con ícono "add_2"). El que dispara la generación tiene el
    # ícono "arrow_forward", así que filtramos por eso.
    btn = page.get_by_role("button", name="Crear").filter(
        has=page.locator('i:has-text("arrow_forward")')
    )
    await btn.click()


async def _count_generated_images(page: Page) -> int:
    return await page.locator('img[alt="Imagen generada"]').count()


async def _wait_for_new_image(page: Page, previous_count: int):
    """Espera a que la cantidad de imágenes en la galería aumente respecto
    a 'previous_count'. Es necesario porque, al pedir 'la última imagen'
    justo después de enviar un prompt, la imagen anterior ya está visible
    en esa posición — sin este chequeo, el código no esperaría realmente a
    que la nueva termine de generarse."""
    deadline = time.monotonic() + (GENERATION_TIMEOUT_MS / 1000)
    while True:
        count = await _count_generated_images(page)
        if count > previous_count:
            return
        if time.monotonic() > deadline:
            raise TimeoutError(
                "La imagen nueva no apareció en la galería dentro del tiempo esperado"
            )
        await page.wait_for_timeout(1000)


async def _latest_generated_media(page: Page):
    """Devuelve la imagen más reciente de la galería (posición .first,
    ya que Flow prepende los resultados nuevos). Se asume que ya se esperó
    la aparición real con _wait_for_new_image antes de llamar a esto."""
    images = page.locator('img[alt="Imagen generada"]')
    await images.first.wait_for(state="visible", timeout=15000)
    return images.first


async def _find_closest_more_button(page: Page, image):
    """El ícono 'more_vert' aparece más de una vez en la página (también en
    el header, ej. el botón 'Más' de arriba a la derecha). En vez de medir
    posiciones en pantalla (lo cual fuerza un scroll que rompe el estado
    :hover de la miniatura), subimos por los ancestros del DOM desde la
    imagen hasta encontrar su propio botón de 3 puntos — así nunca se puede
    confundir con el del header, que vive en otra rama del árbol."""
    handle = await image.element_handle()
    marker = "data-pw-more-btn"

    found = await page.evaluate(
        """([img, marker]) => {
            let node = img;
            for (let depth = 0; depth < 10 && node; depth++) {
                const icons = node.querySelectorAll('i');
                for (const icon of icons) {
                    if (icon.textContent && icon.textContent.includes('more_vert')) {
                        const btn = icon.closest('button');
                        if (btn) {
                            btn.setAttribute(marker, 'true');
                            return true;
                        }
                    }
                }
                node = node.parentElement;
            }
            return false;
        }""",
        [handle, marker],
    )

    if not found:
        raise RuntimeError("No se encontró el botón de 3 puntos cerca de la imagen")

    return page.locator(f'[{marker}="true"]')


async def _download_generated_image(page: Page, quality: str = "2K", image=None) -> "Download":
    if image is None:
        image = await _latest_generated_media(page)
    await image.scroll_into_view_if_needed()

    quality_btn = page.locator(
        f'[role="menuitem"]:has(span:text-is("{quality}"))'
    )

    last_error: Exception | None = None

    for attempt in range(3):
        try:
            # El menú aparece al pasar el mouse sobre la miniatura, que
            # revela una mini-toolbar (❤ / ↻ / ⋮).
            await image.hover()
            await page.wait_for_timeout(300)

            more_btn = await _find_closest_more_button(page, image)
            await more_btn.click()

            download_item = page.get_by_role("menuitem").filter(has_text="Descargar")
            await download_item.wait_for(state="visible", timeout=5000)

            # Estrategia 1: hover (como haría un usuario real)
            await download_item.hover()
            await page.wait_for_timeout(400)

            # Estrategia 2: si el hover no alcanzó, un click directo
            if await quality_btn.count() == 0 or not await quality_btn.first.is_visible():
                await download_item.click()
                await page.wait_for_timeout(400)

            # Estrategia 3: navegación por teclado (Radix abre submenús con
            # ArrowRight cuando el trigger tiene foco)
            if await quality_btn.count() == 0 or not await quality_btn.first.is_visible():
                await download_item.hover()
                await page.keyboard.press("ArrowRight")
                await page.wait_for_timeout(400)

            await quality_btn.first.wait_for(state="visible", timeout=5000)

            async with page.expect_download() as download_info:
                await quality_btn.first.click()
            return await download_info.value

        except Exception as e:
            last_error = e
            # Reseteamos cualquier menú que haya quedado abierto a medias
            # antes de reintentar desde cero.
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)

    raise RuntimeError(
        f"No se pudo completar la descarga tras 3 intentos: {last_error}"
    )


async def _setup_project_page(context: BrowserContext) -> Page:
    """Abre una pestaña nueva, entra a la app de Flow, crea un proyecto
    nuevo (si hace falta) y deja listo el toolbar de creación (Agente +
    pill de modelo visibles). Se llama UNA sola vez por proyecto/lote."""
    page = await _open_veo3_page(context)
    await _enter_flow_app(page)
    await _ensure_new_project(page)
    await _ensure_agent_mode(page)
    return page


async def _generate_image_on_page(page: Page, prompt: str, output_name: str) -> str:
    """Genera una imagen dentro de un proyecto/página YA ABIERTA (no crea
    proyecto nuevo ni abre pestaña). Usar esto para generar varias
    imágenes seguidas dentro del mismo proyecto de Flow."""
    await _open_generation_settings(page)
    await _select_image_mode(page)
    await _select_aspect_ratio_9_16(page)
    await _select_quantity_1x(page)
    await _select_model_nano_banana_2(page)
    await _fill_prompt(page, prompt)

    previous_count = await _count_generated_images(page)
    await _submit_generation(page)
    await _wait_for_new_image(page, previous_count)

    download = await _download_generated_image(page, quality="2K")

    dest_path = MEDIA_DIR / f"{output_name}.png"
    await download.save_as(str(dest_path))
    return str(dest_path)


async def generate_image(prompt: str, output_name: str) -> str:
    """Genera una única imagen en un proyecto nuevo. Útil para pruebas
    puntuales; para varias imágenes en el MISMO proyecto usar
    generate_images_batch."""
    context = await get_context()
    page = await _setup_project_page(context)
    try:
        return await _generate_image_on_page(page, prompt, output_name)
    finally:
        await page.close()


async def generate_images_batch(
    prompts: list[str],
    output_prefix: str,
    delay_seconds: float = 5.0,
) -> list[dict]:
    """Genera una lista de imágenes EN ORDEN, todas dentro de UN MISMO
    proyecto de Flow (se crea el proyecto una sola vez, al principio), con
    una pausa entre cada generación para no saturar la app.

    No corta el lote si una imagen falla: sigue con la siguiente y deja
    registrado el error para esa entrada, así un fallo puntual no te hace
    perder el resto.

    Los archivos se nombran con padding de ceros (prefix_000, prefix_001,
    ...) para que ordenar por nombre de archivo respete el orden original.

    Devuelve una lista de resultados EN EL MISMO ORDEN que 'prompts':
        [{"index": 0, "prompt": "...", "status": "ok", "path": "...", "error": None}, ...]
    """
    context = await get_context()
    page = await _setup_project_page(context)

    results: list[dict] = []
    total = len(prompts)

    try:
        for i, prompt in enumerate(prompts):
            output_name = f"{output_prefix}_{i:03d}"
            print(f"[{i + 1}/{total}] Generando: {prompt[:70]}...")

            try:
                path = await _generate_image_on_page(page, prompt, output_name)
                results.append(
                    {"index": i, "prompt": prompt, "status": "ok", "path": path, "error": None}
                )
                print(f"[{i + 1}/{total}] OK -> {path}")
            except Exception as e:
                results.append(
                    {"index": i, "prompt": prompt, "status": "error", "path": None, "error": str(e)}
                )
                print(f"[{i + 1}/{total}] ERROR -> {e}")
                # Si algo quedó abierto (menú, popover) tras el error,
                # intentamos resetear el estado antes de seguir con la
                # siguiente imagen.
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(500)

            if i < total - 1:
                await asyncio.sleep(delay_seconds)
    finally:
        await page.close()

    ok_count = sum(1 for r in results if r["status"] == "ok")
    print(f"\nListo: {ok_count}/{total} imágenes generadas correctamente en el mismo proyecto.")
    return results


# Patrón de stagger para el pipeline: 2s, 5s, 7s, 2s, 5s, 7s, ...
# Deja tiempo suficiente para que Flow encole sin confundirse, pero sin
# esperar a que termine la generación de cada una.
_STAGGER_PATTERN = [2, 5, 7]


async def _wait_for_nth_image(page: Page, target_count: int, timeout_s: float) -> bool:
    """Espera hasta que haya al menos `target_count` imágenes en la galería.
    Devuelve True si llegó a tiempo, False si hizo timeout."""
    deadline = time.monotonic() + timeout_s
    while True:
        count = await _count_generated_images(page)
        if count >= target_count:
            return True
        if time.monotonic() > deadline:
            return False
        await page.wait_for_timeout(1500)


async def generate_images_batch_pipeline(
    prompts: list[str],
    output_prefix: str,
    window_size: int = 3,
) -> list[dict]:
    """Pipeline de ventana deslizante: envía prompts con stagger (2 s, 5 s,
    7 s, 2 s, 5 s, …) sin esperar a que cada uno termine de generarse, y
    va descargando las imágenes completadas en segundo plano mientras ya
    se mandan las siguientes.

    Estrategia:
    - Se envían los prompts en grupos de `window_size` (default 3).
    - Después de cada envío se aplica el stagger del patrón cíclico.
    - Tras enviar un grupo completo, se espera a que las imágenes
      correspondientes estén listas y se descargan ANTES de enviar el
      grupo siguiente. Esto limita el daño en caso de fallo: si Flow
      pierde o reordena algo, el error queda acotado al grupo actual.

    Orden en la galería (FIFO inverso):
    - Flow prepende los resultados nuevos → la posición 0 siempre es
      la imagen más reciente. Por eso, una vez que un grupo de N
      imágenes está listo, ocupan las posiciones 0..N-1, donde la
      posición 0 corresponde al ÚLTIMO prompt del grupo y N-1 al primero.

    Devuelve resultados en el MISMO orden que 'prompts'.
    """
    context = await get_context()
    page = await _setup_project_page(context)

    total = len(prompts)
    results: list[dict | None] = [None] * total

    try:
        # --- Configuración única de modo/formato/modelo ---
        await _open_generation_settings(page)
        await _select_image_mode(page)
        await _select_aspect_ratio_9_16(page)
        await _select_quantity_1x(page)
        await _select_model_nano_banana_2(page)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)

        sent_count = 0          # prompts enviados hasta ahora
        downloaded_count = 0    # imágenes ya descargadas hasta ahora

        while sent_count < total:
            # Tamaño del grupo actual (puede ser menor en el último)
            group_size = min(window_size, total - sent_count)
            group_start = sent_count  # índice del primer prompt del grupo

            print(f"\n--- Enviando grupo {group_start + 1}–{group_start + group_size} de {total} ---")

            # 1) Enviar los prompts del grupo con stagger
            for j in range(group_size):
                i = group_start + j
                print(f"  Enviando [{i + 1}/{total}]: {prompts[i][:70]}...")
                await _fill_prompt(page, prompts[i])
                await _submit_generation(page)

                if j < group_size - 1:
                    wait_s = _STAGGER_PATTERN[j % len(_STAGGER_PATTERN)]
                    print(f"  Esperando {wait_s}s antes del siguiente envío...")
                    await asyncio.sleep(wait_s)

            sent_count += group_size

            # 2) Esperar a que las imágenes del grupo estén listas.
            #    La galería acumula TODAS las generadas, así que el número
            #    objetivo es el total de imágenes descargadas + las del grupo.
            target_gallery_count = downloaded_count + group_size
            timeout_per_image_s = GENERATION_TIMEOUT_MS / 1000
            group_timeout_s = timeout_per_image_s * group_size

            print(f"  Esperando a que lleguen {group_size} imagen(es) más en la galería...")
            reached = await _wait_for_nth_image(
                page,
                target_count=target_gallery_count,
                timeout_s=group_timeout_s,
            )

            current_gallery = await _count_generated_images(page)
            arrived = current_gallery - downloaded_count  # cuántas llegaron de este grupo

            if not reached:
                print(
                    f"  Timeout: solo llegaron {arrived}/{group_size} imagen(es) del grupo. "
                    "Las que llegaron se van a descargar igual."
                )

            # 3) Descargar las imágenes que llegaron del grupo.
            #    Las más recientes (posición 0..arrived-1 en la galería) son
            #    exactamente las del grupo actual, en orden inverso:
            #    posición 0 → último prompt del grupo, posición arrived-1 → primero.
            images = page.locator('img[alt="Imagen generada"]')

            for pos in range(arrived):
                # Posición en la galería (0 = más nueva)
                prompt_index = group_start + arrived - 1 - pos
                output_name = f"{output_prefix}_{prompt_index:03d}"

                try:
                    image = images.nth(pos)
                    download = await _download_generated_image(page, quality="2K", image=image)
                    dest_path = MEDIA_DIR / f"{output_name}.png"
                    await download.save_as(str(dest_path))
                    results[prompt_index] = {
                        "index": prompt_index,
                        "prompt": prompts[prompt_index],
                        "status": "ok",
                        "path": str(dest_path),
                        "error": None,
                    }
                    print(f"  [{prompt_index + 1}/{total}] OK -> {dest_path}")
                except Exception as e:
                    results[prompt_index] = {
                        "index": prompt_index,
                        "prompt": prompts[prompt_index],
                        "status": "error",
                        "path": None,
                        "error": str(e),
                    }
                    print(f"  [{prompt_index + 1}/{total}] ERROR -> {e}")

            downloaded_count = current_gallery

            # Marca como no generadas las imágenes del grupo que no llegaron
            for j in range(arrived, group_size):
                prompt_index = group_start + j
                if results[prompt_index] is None:
                    results[prompt_index] = {
                        "index": prompt_index,
                        "prompt": prompts[prompt_index],
                        "status": "error",
                        "path": None,
                        "error": "No se generó a tiempo (timeout de grupo)",
                    }

            # Breve pausa entre grupos para que la UI de Flow se estabilice
            if sent_count < total:
                await asyncio.sleep(2)

    finally:
        await page.close()

    ok_count = sum(1 for r in results if r and r["status"] == "ok")
    print(f"\nListo: {ok_count}/{total} imágenes generadas correctamente (pipeline).")
    return results


async def generate_images_batch_parallel(
    prompts: list[str],
    output_prefix: str,
    stagger_seconds: float = 2.0,
) -> list[dict]:
    """Alias de compatibilidad → delega en generate_images_batch_pipeline.

    El parámetro stagger_seconds ya no se usa (el pipeline tiene su propio
    patrón cíclico), pero se mantiene para no romper código existente.
    """
    return await generate_images_batch_pipeline(prompts, output_prefix)


async def generate_video(prompt: str, reference_image_path: str, output_name: str) -> str:
    """Genera un video en Veo3 usando una imagen de referencia + prompt de
    movimiento, y devuelve la ruta local del archivo descargado.
    """
    context = await get_context()
    page = await _open_veo3_page(context)

    try:
        # TODO: ajustar selector para modo "generar video"
        await page.click('[data-testid="mode-video"]')

        # TODO: ajustar selector de upload de imagen de referencia
        async with page.expect_file_chooser() as fc_info:
            await page.click('[data-testid="reference-image-upload"]')
        file_chooser = await fc_info.value
        await file_chooser.set_files(reference_image_path)

        # Esperar a que la imagen se procese/suba
        # TODO: ajustar selector que indica que la imagen ya se cargó
        await page.wait_for_selector('[data-testid="reference-image-preview"]')

        # TODO: ajustar selector del campo de prompt de video
        await page.fill('[data-testid="video-prompt-input"]', prompt)

        # TODO: ajustar selector de formato 9:16 (si aplica también en video)
        await page.click('[data-testid="aspect-ratio-selector"]')
        await page.click('[data-testid="aspect-ratio-9-16"]')

        # TODO: ajustar selector del botón generar video
        await page.click('[data-testid="generate-video-button"]')

        # La generación de video suele tardar más que la de imagen
        # TODO: ajustar selector
        await page.wait_for_selector(
            '[data-testid="video-download-button"]', timeout=GENERATION_TIMEOUT_MS
        )

        dest_path = MEDIA_DIR / f"{output_name}.mp4"
        async with page.expect_download() as download_info:
            await page.click('[data-testid="video-download-button"]')
        download = await download_info.value
        await download.save_as(str(dest_path))

        return str(dest_path)

    finally:
        await page.close()
