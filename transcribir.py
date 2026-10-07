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

from comun import PROMPT_MEDICINA, construir_texto, formatear_tiempo, recopilar_audios, ruta_destino

# Versión de openai/whisper-large-v3-turbo ya convertida al formato MLX.
# (El repo original de openai está en formato PyTorch y mlx-whisper no lo carga directo.)
MODELO_POR_DEFECTO = "mlx-community/whisper-large-v3-turbo"


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
        destino = ruta_destino(audio, carpeta_salida)
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
