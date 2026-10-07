#!/usr/bin/env python3
"""Transcribe audios largos (MP3, M4A, WAV...) a .txt, localmente en Apple Silicon.

Usa mlx-whisper con whisper-large-v3-turbo. Acepta uno o varios archivos,
o carpetas completas, y guarda un .txt junto a cada audio (o en --salida).

Ejemplos:
    python transcribir.py clase1.mp3
    python transcribir.py ~/Clases/ --timestamps
    python transcribir.py clase.m4a -l es --salida ~/Transcripciones
"""

import argparse
import shutil
import sys
import time
from pathlib import Path

EXTENSIONES = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac", ".mp4", ".mov", ".mkv", ".webm"}

# Versión de openai/whisper-large-v3-turbo ya convertida al formato MLX.
# (El repo original de openai está en formato PyTorch y mlx-whisper no lo carga directo.)
MODELO_POR_DEFECTO = "mlx-community/whisper-large-v3-turbo"

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


def main() -> int:
    ap = argparse.ArgumentParser(description="Transcribe audio a .txt con mlx-whisper (Apple Silicon).")
    ap.add_argument("entradas", nargs="+", help="Archivos de audio y/o carpetas")
    ap.add_argument("-l", "--idioma", default="es", help="Código de idioma (default: es). Usa 'auto' para detectar")
    ap.add_argument("-m", "--modelo", default=MODELO_POR_DEFECTO, help=f"Modelo HF (default: {MODELO_POR_DEFECTO})")
    ap.add_argument("-s", "--salida", help="Carpeta donde guardar los .txt (default: junto al audio)")
    ap.add_argument("-t", "--timestamps", action="store_true", help="Una línea por segmento con marca de tiempo")
    ap.add_argument("--prompt", default=PROMPT_MEDICINA, help="Texto de contexto/vocabulario (usa '' para desactivar)")
    ap.add_argument("--sobrescribir", action="store_true", help="Rehacer aunque el .txt ya exista")
    args = ap.parse_args()

    if shutil.which("ffmpeg") is None:
        print("Error: no se encontró ffmpeg. Instálalo con: brew install ffmpeg", file=sys.stderr)
        return 1

    try:
        import mlx_whisper
    except ImportError:
        print("Error: falta mlx-whisper. Instálalo con: pip install mlx-whisper", file=sys.stderr)
        return 1

    audios = recopilar_audios(args.entradas)
    if not audios:
        print("No se encontraron archivos de audio.", file=sys.stderr)
        return 1

    carpeta_salida = Path(args.salida).expanduser() if args.salida else None
    if carpeta_salida:
        carpeta_salida.mkdir(parents=True, exist_ok=True)

    fallidos = 0
    for i, audio in enumerate(audios, 1):
        destino = (carpeta_salida or audio.parent) / f"{audio.stem}.txt"
        print(f"\n[{i}/{len(audios)}] {audio.name}")
        if destino.exists() and not args.sobrescribir:
            print(f"  Ya existe {destino.name}, se omite (usa --sobrescribir para rehacer).")
            continue

        inicio = time.time()
        try:
            resultado = mlx_whisper.transcribe(
                str(audio),
                path_or_hf_repo=args.modelo,
                language=None if args.idioma == "auto" else args.idioma,
                initial_prompt=args.prompt or None,
                # Evita que un error se "contagie" y repita frases en audios largos.
                condition_on_previous_text=False,
                verbose=False,
            )
        except Exception as e:  # noqa: BLE001 - seguimos con el siguiente archivo
            print(f"  Error transcribiendo: {e}", file=sys.stderr)
            fallidos += 1
            continue

        destino.write_text(construir_texto(resultado, audio, args.timestamps), encoding="utf-8")
        print(f"  Guardado: {destino}  ({formatear_tiempo(time.time() - inicio)})")

    return 1 if fallidos else 0


if __name__ == "__main__":
    sys.exit(main())
