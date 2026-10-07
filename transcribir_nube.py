#!/usr/bin/env python3
"""Transcribe audios largos a .txt en la nube / Linux, en paralelo (CPU o GPU NVIDIA).

Usa faster-whisper (CTranslate2) con whisper-large-v3-turbo. Reparte los archivos
entre varios procesos; cada uno carga el modelo una sola vez y reparte los núcleos.

Ejemplos:
    python transcribir_nube.py clases/ --trabajos 4
    python transcribir_nube.py clase.mp3 -t --salida out/
    python transcribir_nube.py clases/ --dispositivo cuda --tipo float16
"""

import argparse
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from comun import PROMPT_MEDICINA, construir_texto, formatear_tiempo, recopilar_audios, ruta_destino

MODELO_POR_DEFECTO = "large-v3-turbo"

_modelo = None  # se carga una vez por proceso trabajador


def _iniciar_trabajador(nombre, dispositivo, tipo, hilos):
    global _modelo
    from faster_whisper import WhisperModel

    _modelo = WhisperModel(nombre, device=dispositivo, compute_type=tipo, cpu_threads=hilos)


def _transcribir(audio: str, idioma, prompt, timestamps: bool, destino: str) -> tuple[str, float]:
    inicio = time.time()
    segmentos, info = _modelo.transcribe(
        audio,
        language=idioma,
        initial_prompt=prompt,
        condition_on_previous_text=False,  # evita repeticiones en audios largos
        vad_filter=True,  # salta silencios, acelera clases largas
    )
    lista = [{"start": s.start, "end": s.end, "text": s.text} for s in segmentos]
    resultado = {"language": info.language, "segments": lista, "text": " ".join(s["text"].strip() for s in lista)}
    Path(destino).write_text(construir_texto(resultado, Path(audio), timestamps), encoding="utf-8")
    return destino, time.time() - inicio


def main() -> int:
    nucleos = os.cpu_count() or 1
    ap = argparse.ArgumentParser(description="Transcribe audio a .txt con faster-whisper, en paralelo.")
    ap.add_argument("entradas", nargs="+", help="Archivos de audio y/o carpetas")
    ap.add_argument("-l", "--idioma", default="es", help="Código de idioma (default: es). Usa 'auto' para detectar")
    ap.add_argument("-m", "--modelo", default=MODELO_POR_DEFECTO, help=f"Modelo faster-whisper (default: {MODELO_POR_DEFECTO})")
    ap.add_argument("-s", "--salida", help="Carpeta donde guardar los .txt (default: junto al audio)")
    ap.add_argument("-t", "--timestamps", action="store_true", help="Una línea por segmento con marca de tiempo")
    ap.add_argument("--prompt", default=PROMPT_MEDICINA, help="Texto de contexto/vocabulario (usa '' para desactivar)")
    ap.add_argument("--sobrescribir", action="store_true", help="Rehacer aunque el .txt ya exista")
    ap.add_argument("-j", "--trabajos", type=int, default=max(1, nucleos // 2),
                    help=f"Archivos a transcribir en paralelo (default: {max(1, nucleos // 2)}). Cada uno carga el modelo (~1-3 GB RAM)")
    ap.add_argument("--dispositivo", default="cpu", choices=["cpu", "cuda"], help="cpu (default) o cuda")
    ap.add_argument("--tipo", default=None, help="Precisión: int8 (default en cpu), float16 (default en cuda)...")
    args = ap.parse_args()

    if shutil.which("ffmpeg") is None:
        print("Error: no se encontró ffmpeg. Instálalo con: apt install ffmpeg", file=sys.stderr)
        return 1
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        print("Error: falta faster-whisper. Instálalo con: pip install -r requirements-nube.txt", file=sys.stderr)
        return 1

    audios = recopilar_audios(args.entradas)
    if not audios:
        print("No se encontraron archivos de audio.", file=sys.stderr)
        return 1

    carpeta_salida = Path(args.salida).expanduser() if args.salida else None
    if carpeta_salida:
        carpeta_salida.mkdir(parents=True, exist_ok=True)

    pendientes = []
    for audio in audios:
        destino = ruta_destino(audio, carpeta_salida)
        if destino.exists() and not args.sobrescribir:
            print(f"Ya existe {destino.name}, se omite (usa --sobrescribir para rehacer).")
        else:
            pendientes.append((audio, destino))
    if not pendientes:
        return 0

    trabajos = max(1, min(args.trabajos, len(pendientes)))
    hilos = max(1, nucleos // trabajos)
    tipo = args.tipo or ("float16" if args.dispositivo == "cuda" else "int8")
    idioma = None if args.idioma == "auto" else args.idioma
    print(f"{len(pendientes)} archivo(s), {trabajos} en paralelo, {hilos} hilo(s) c/u, modelo {args.modelo} ({tipo})")

    fallidos = 0
    # "spawn": seguro con CUDA y evita heredar estado del padre.
    import multiprocessing as mp

    with ProcessPoolExecutor(
        max_workers=trabajos,
        mp_context=mp.get_context("spawn"),
        initializer=_iniciar_trabajador,
        initargs=(args.modelo, args.dispositivo, tipo, hilos),
    ) as pool:
        futuros = {
            pool.submit(_transcribir, str(a), idioma, args.prompt or None, args.timestamps, str(d)): a
            for a, d in pendientes
        }
        for n, fut in enumerate(as_completed(futuros), 1):
            audio = futuros[fut]
            try:
                destino, seg = fut.result()
                print(f"[{n}/{len(pendientes)}] {audio.name} -> {destino} ({formatear_tiempo(seg)})", flush=True)
            except Exception as e:  # noqa: BLE001 - seguimos con los demás
                print(f"[{n}/{len(pendientes)}] {audio.name}: error: {e}", file=sys.stderr, flush=True)
                fallidos += 1
    return 1 if fallidos else 0


if __name__ == "__main__":
    sys.exit(main())
