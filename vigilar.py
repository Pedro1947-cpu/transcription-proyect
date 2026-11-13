#!/usr/bin/env python3
"""Vigila las carpetas «Grabaciones» de Drive y transcribe cada audio nuevo.

Pensado para la app grabadora: los audios se suben a Drive en
«Medicina 1º/<Asignatura>/Grabaciones». Con Google Drive para escritorio,
esa carpeta aparece en el Mac, y este script:

  1. busca audios sin .txt en cualquier carpeta «Grabaciones» y en
     «Grabaciones de clase» (donde caen las grabaciones sin asignatura),
  2. avisa con una notificación del Mac,
  3. los transcribe en local (mlx-whisper, sin gastar tokens),
  4. guarda el .txt junto al audio (Drive lo sube solo) y vuelve a avisar.

Lo lanza macOS cada 5 minutos (ver instalar-vigilante.sh). También se puede
ejecutar a mano:  python vigilar.py  [carpetas...]   (sin carpetas: las busca solo)
  python vigilar.py --ver            (solo enseña qué carpetas vigila)
"""

import json
import subprocess
import sys
import time
from pathlib import Path

from transcribir import EXTENSIONES, MODELO_POR_DEFECTO, PROMPT_MEDICINA, construir_texto

CARPETA_RAIZ = "Medicina 1º"
SUBCARPETA = "Grabaciones"
# Donde la app deja las grabaciones que no encajan con ninguna asignatura (raíz del Drive).
CARPETA_SUELTAS = "Grabaciones de clase"
# Un audio que falla se reintenta como mucho estas veces (para no atascarse).
MAX_INTENTOS = 3
ESTADO = Path.home() / ".transcriptor-fallidos.json"


def buscar_carpetas() -> list[Path]:
    """Todas las «Medicina 1º» y «Grabaciones de clase» de Google Drive para escritorio.

    Mira todas las cuentas conectadas y también las carpetas compartidas contigo
    que tengan un acceso directo en «Mi unidad».
    """
    nube = Path.home() / "Library" / "CloudStorage"
    encontradas = []
    for nombre in (CARPETA_RAIZ, CARPETA_SUELTAS):
        encontradas += [p for p in nube.glob(f"GoogleDrive-*/*/{nombre}*") if p.is_dir()]
        # Carpetas «Compartido conmigo» con acceso directo: Drive las guarda aquí.
        encontradas += [p for p in nube.glob(f"GoogleDrive-*/.shortcut-targets-by-id/*/{nombre}*")
                        if p.is_dir()]
    return sorted(set(encontradas))


def avisar(titulo: str, texto: str) -> None:
    """Notificación del Mac (no falla si no se puede mostrar)."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{esc(texto)}" with title "{esc(titulo)}" sound name "Glass"'
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def es_pendiente(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in EXTENSIONES and not p.name.startswith(".") \
        and not p.with_suffix(".txt").exists()


def pendientes(carpetas: list[Path]) -> list[Path]:
    audios = set()
    for raiz in carpetas:
        if raiz.name.startswith(CARPETA_SUELTAS):
            audios.update(p for p in raiz.rglob("*") if es_pendiente(p))
        else:
            for carpeta in raiz.rglob(SUBCARPETA):
                if carpeta.is_dir():
                    audios.update(p for p in carpeta.iterdir() if es_pendiente(p))
    return sorted(audios, key=lambda p: p.stat().st_mtime)


def subida_completa(audio: Path) -> bool:
    """True si el tamaño no cambia en 10 s (Drive ya terminó de copiarlo)."""
    try:
        antes = audio.stat().st_size
        time.sleep(10)
        return antes > 0 and audio.stat().st_size == antes
    except FileNotFoundError:
        return False


def main() -> int:
    if sys.argv[1:] == ["--ver"]:
        for c in buscar_carpetas():
            print(c)
        return 0
    carpetas = [Path(a).expanduser() for a in sys.argv[1:]] or buscar_carpetas()
    carpetas = [c for c in carpetas if c.is_dir()]
    if not carpetas:
        print(f"No encuentro la carpeta «{CARPETA_RAIZ}» en Google Drive. "
              "¿Está abierto Google Drive para escritorio?", file=sys.stderr)
        return 1

    try:
        fallidos = json.loads(ESTADO.read_text())
    except (FileNotFoundError, ValueError):
        fallidos = {}

    cola = [a for a in pendientes(carpetas) if fallidos.get(str(a), 0) < MAX_INTENTOS]
    if not cola:
        return 0

    import mlx_whisper  # se importa solo si hay trabajo: así cada revisión es instantánea

    for audio in cola:
        if not subida_completa(audio):
            continue
        asignatura = audio.parent.parent.name if audio.parent.name == SUBCARPETA else audio.parent.name
        print(time.strftime("%Y-%m-%d %H:%M"), "Nuevo audio:", audio, flush=True)
        avisar(f"Nueva grabación · {asignatura}", f"Transcribiendo {audio.stem}…")
        inicio = time.time()
        try:
            resultado = mlx_whisper.transcribe(
                str(audio),
                path_or_hf_repo=MODELO_POR_DEFECTO,
                language="es",
                initial_prompt=PROMPT_MEDICINA,
                condition_on_previous_text=False,
                verbose=False,
            )
        except Exception as e:  # noqa: BLE001 - se reintenta en la próxima revisión
            fallidos[str(audio)] = fallidos.get(str(audio), 0) + 1
            ESTADO.write_text(json.dumps(fallidos, ensure_ascii=False, indent=1))
            print("  Error:", e, file=sys.stderr, flush=True)
            avisar("Error al transcribir", f"{audio.stem}: {e}")
            continue
        audio.with_suffix(".txt").write_text(
            construir_texto(resultado, audio, timestamps=False), encoding="utf-8")
        minutos = round((time.time() - inicio) / 60)
        print(f"  Listo en {minutos} min", flush=True)
        avisar(f"Transcripción lista · {asignatura}", f"{audio.stem} ({minutos} min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
