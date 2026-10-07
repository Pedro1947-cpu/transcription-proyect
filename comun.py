"""Funciones compartidas por transcribir.py (local, Mac) y transcribir_nube.py (nube, Linux)."""

import sys
import time
from pathlib import Path

EXTENSIONES = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac", ".mp4", ".mov", ".mkv", ".webm"}

# Un prompt con vocabulario ayuda a que Whisper acierte términos técnicos.
PROMPT_MEDICINA = (
    "Clase de medicina. Terminología médica: fisiopatología, farmacocinética, "
    "anatomía, histología, semiología, diagnóstico diferencial, etiología."
)


def formatear_tiempo(segundos: float) -> str:
    s = int(segundos)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def recopilar_audios(entradas: list[str]) -> list[Path]:
    audios: list[Path] = []
    for entrada in entradas:
        ruta = Path(entrada).expanduser()
        if ruta.is_dir():
            audios += sorted(p for p in ruta.rglob("*") if p.suffix.lower() in EXTENSIONES)
        elif ruta.is_file():
            audios.append(ruta)
        else:
            print(f"[aviso] No existe: {ruta}", file=sys.stderr)
    return audios


def a_parrafos(segmentos: list[dict], pausa: float = 1.5, max_chars: int = 600) -> list[str]:
    """Agrupa segmentos en párrafos: nuevo párrafo tras una pausa larga o texto muy largo."""
    parrafos, actual, fin_previo = [], "", None
    for seg in segmentos:
        texto = seg["text"].strip()
        if not texto:
            continue
        if actual and (
            (fin_previo is not None and seg["start"] - fin_previo >= pausa)
            or (len(actual) >= max_chars and actual.endswith((".", "?", "!")))
        ):
            parrafos.append(actual)
            actual = ""
        actual = f"{actual} {texto}".strip()
        fin_previo = seg["end"]
    if actual:
        parrafos.append(actual)
    return parrafos


def construir_texto(resultado: dict, audio: Path, timestamps: bool) -> str:
    cabecera = [
        f"Transcripción de: {audio.name}",
        f"Idioma detectado: {resultado.get('language', '?')}",
        f"Fecha: {time.strftime('%Y-%m-%d %H:%M')}",
        "=" * 60,
        "",
    ]
    segmentos = resultado.get("segments", [])
    if timestamps:
        cuerpo = [f"[{formatear_tiempo(s['start'])}] {s['text'].strip()}" for s in segmentos]
        separador = "\n"
    else:
        cuerpo = a_parrafos(segmentos) or [resultado.get("text", "").strip()]
        separador = "\n\n"
    return "\n".join(cabecera) + separador.join(cuerpo) + "\n"


def ruta_destino(audio: Path, carpeta_salida: Path | None) -> Path:
    return (carpeta_salida or audio.parent) / f"{audio.stem}.txt"
