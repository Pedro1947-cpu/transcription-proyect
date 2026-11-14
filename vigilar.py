#!/usr/bin/env python3
"""Vigila las carpetas «Grabaciones» de Drive y transcribe cada audio nuevo.

Pensado para la app grabadora: los audios se suben a Drive en
«Medicina 1º/<Asignatura>/Grabaciones». Con Google Drive para escritorio,
esa carpeta aparece en el Mac, y este script:

  1. busca audios nuevos de la app (sin .txt ni Google Doc al lado) en las
     asignaturas de «Medicina 1º» y en «Grabaciones de clase»,
  2. avisa con una notificación del Mac,
  3. los transcribe en local (mlx-whisper, sin gastar tokens),
  4. guarda el .txt junto al audio (Drive lo sube solo) y vuelve a avisar.

Lo lanza macOS cada 5 minutos (ver instalar-vigilante.sh). También se puede
ejecutar a mano:  python vigilar.py  [carpetas...]   (sin carpetas: las busca solo)
  python vigilar.py --ver            (solo enseña qué carpetas vigila)
"""

import ctypes
import json
import os
import re
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
# Nombre que pone la app: «Bioquímica Básica 2026-11-16 (lunes) 09h00.m4a».
# Así los audios antiguos subidos a mano se quedan como están.
NOMBRE_APP = re.compile(r"\d{4}-\d{2}-\d{2} \(\w+\) \d{2}h\d{2}")
ESTADO = Path.home() / ".transcriptor-fallidos.json"


def buscar_carpetas() -> list[Path]:
    """Todas las «Medicina 1º» y «Grabaciones de clase» de Google Drive para escritorio.

    Mira todas las cuentas conectadas y también las carpetas compartidas contigo
    que tengan un acceso directo en «Mi unidad».
    """
    nube = Path.home() / "Library" / "CloudStorage"
    encontradas = []
    patrones = [f"GoogleDrive-*/*/{n}*" for n in (CARPETA_RAIZ, CARPETA_SUELTAS)]
    # Carpetas «Compartido conmigo» con acceso directo: Drive las guarda aquí.
    patrones += [f"GoogleDrive-*/.shortcut-targets-by-id/*/{n}*" for n in (CARPETA_RAIZ, CARPETA_SUELTAS)]
    for patron in patrones:
        try:
            encontradas += [p for p in nube.glob(patron) if p.is_dir()]
        except OSError as e:
            print("  Aviso:", e, file=sys.stderr)
    return sorted(set(encontradas))


def avisar(titulo: str, texto: str) -> None:
    """Notificación del Mac (no falla si no se puede mostrar)."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{esc(texto)}" with title "{esc(titulo)}" sound name "Glass"'
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def es_pendiente(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in EXTENSIONES and not p.name.startswith(".") \
        and not p.with_suffix(".txt").exists() and not p.with_suffix(".gdoc").exists()


def pendientes(carpetas: list[Path]) -> list[Path]:
    audios = set()
    for raiz in carpetas:
        # os.walk se salta (en vez de abortar) una carpeta que Drive aún no deja leer.
        for dirpath, _, nombres in os.walk(raiz, onerror=lambda e: print("  Aviso:", e, file=sys.stderr)):
            for nombre in nombres:
                p = Path(dirpath) / nombre
                try:
                    if not es_pendiente(p):
                        continue
                except OSError:
                    continue
                # En «Grabaciones de clase» o en una carpeta «Grabaciones», todo es nuevo;
                # en el resto de «Medicina 1º», solo lo que tenga el nombre de la app.
                if raiz.name.startswith(CARPETA_SUELTAS) or p.parent.name == SUBCARPETA \
                        or NOMBRE_APP.search(p.stem):
                    audios.add(p)
    return sorted(audios, key=lambda p: p.stat().st_mtime)


def permitir_descargas_de_drive() -> None:
    """Deja que este proceso (y ffmpeg, que hereda la política) baje audios «solo en la nube».

    Sin esto, un proceso lanzado por launchd que abre un archivo de Drive no
    descargado recibe «Resource deadlock avoided».
    """
    try:
        # setiopolicy_np(IOPOL_TYPE_VFS_MATERIALIZE_DATALESS_FILES, IOPOL_SCOPE_PROCESS, ON)
        ctypes.CDLL(None).setiopolicy_np(3, 0, 2)
    except (OSError, AttributeError):
        pass


def descargar(audio: Path) -> None:
    """Lee el archivo entero para que Drive lo baje antes de pasárselo a ffmpeg."""
    with open(audio, "rb") as f:
        while f.read(1 << 20):
            pass


def subida_completa(audio: Path) -> bool:
    """True si el tamaño no cambia en 10 s (Drive ya terminó de copiarlo)."""
    try:
        antes = audio.stat().st_size
        time.sleep(10)
        return antes > 0 and audio.stat().st_size == antes
    except FileNotFoundError:
        return False


def main() -> int:
    permitir_descargas_de_drive()  # antes de recorrer Drive: también hace falta para listar carpetas nuevas
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
        asignatura = (audio.parent.parent if audio.parent.name == SUBCARPETA else audio.parent).name.strip()
        print(time.strftime("%Y-%m-%d %H:%M"), "Nuevo audio:", audio, flush=True)
        avisar(f"Nueva grabación · {asignatura}", f"Transcribiendo {audio.stem}…")
        inicio = time.time()
        try:
            descargar(audio)
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
