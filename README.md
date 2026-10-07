# Transcriptor de clases (Mac M1)

Script en Python que transcribe audios largos (MP3, M4A, WAV…) a texto, **100 % local** en Apple Silicon, usando [`mlx-whisper`](https://github.com/ml-explore/mlx-examples/tree/main/whisper) con el modelo Whisper large-v3-turbo.

- Acepta uno o varios archivos, o carpetas enteras.
- Guarda un `.txt` por audio, ordenado en párrafos (o con marcas de tiempo).
- Omite audios ya transcritos y sigue con el siguiente si uno falla.
- Incluye un prompt con vocabulario médico para mejorar los términos técnicos.

## Instalación (una sola vez)

Abre la app **Terminal** en tu Mac y ejecuta, en orden:

### 1. Herramientas de línea de comandos de Apple
```bash
xcode-select --install
```
Si ya las tienes, te lo dirá; continúa.

### 2. Homebrew
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
Al terminar, Homebrew muestra una sección **"Next steps"** con dos comandos (`echo ... >> ~/.zprofile` y `eval "$(/opt/homebrew/bin/brew shellenv)"`). **Cópialos y ejecútalos**; si no, `brew` no se reconocerá. Comprueba con:
```bash
brew --version
```

### 3. ffmpeg y Python
```bash
brew install ffmpeg python@3.12
```

### 4. Descargar este proyecto
```bash
git clone https://github.com/pedro1947-cpu/transcription-proyect.git
cd transcription-proyect
git checkout claude/github-repository-access-kt44wb   # solo si aún no está fusionado a main
```

### 5. Entorno virtual e instalación de mlx-whisper
```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> Cada vez que abras una Terminal nueva, entra a la carpeta y activa el entorno antes de usar el script:
> `cd transcription-proyect && source .venv/bin/activate`

## Uso

```bash
# Un archivo
python transcribir.py ~/Downloads/clase_fisiologia.mp3

# Varios archivos
python transcribir.py clase1.m4a clase2.m4a

# Una carpeta completa (busca audios dentro, incluidas subcarpetas)
python transcribir.py ~/Clases/

# Guardar los .txt en otra carpeta
python transcribir.py ~/Clases/ --salida ~/Transcripciones

# Con marcas de tiempo [HH:MM:SS] en cada línea
python transcribir.py clase.mp3 --timestamps
```

La **primera ejecución descarga el modelo (~1.6 GB)**; después funciona sin internet.

### Opciones

| Opción | Descripción |
|---|---|
| `-l`, `--idioma` | Idioma del audio (por defecto `es`). `auto` para detectarlo; `en` para inglés. |
| `-s`, `--salida` | Carpeta donde guardar los `.txt` (por defecto, junto al audio). |
| `-t`, `--timestamps` | Una línea por segmento con marca de tiempo. |
| `--prompt "texto"` | Vocabulario/contexto para mejorar términos. `--prompt ""` lo desactiva. Por defecto trae términos médicos; cámbialo según la materia. |
| `--sobrescribir` | Rehacer transcripciones aunque el `.txt` ya exista. |
| `-m`, `--modelo` | Otro modelo de Hugging Face en formato MLX. |

## Versión para la nube / Linux (en paralelo)

`transcribir_nube.py` hace lo mismo pero con [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper), que corre en cualquier Linux (CPU o GPU NVIDIA) y transcribe **varios archivos a la vez**.

```bash
sudo apt install ffmpeg
pip install -r requirements-nube.txt
python transcribir_nube.py clases/ --trabajos 4 --salida out/
python transcribir_nube.py clases/ --dispositivo cuda --tipo float16   # con GPU
```

Acepta las mismas opciones que la versión local (`-l`, `-s`, `-t`, `--prompt`, `--sobrescribir`) más:

| Opción | Descripción |
|---|---|
| `-j`, `--trabajos` | Archivos en paralelo (por defecto, la mitad de los núcleos). Cada proceso carga su copia del modelo y recibe `núcleos / trabajos` hilos. |
| `--dispositivo` | `cpu` (por defecto) o `cuda`. |
| `--tipo` | Precisión: `int8` en CPU, `float16` en GPU por defecto. |

`transcribir.py` (Mac, mlx-whisper) y `transcribir_nube.py` comparten las funciones de `comun.py`; ambos deben estar en la misma carpeta.

## Notas

- **Modelo:** se usa `mlx-community/whisper-large-v3-turbo`, que es `openai/whisper-large-v3-turbo` ya convertido al formato MLX. El repositorio original de OpenAI está en formato PyTorch y `mlx-whisper` no lo carga directamente.
- **Rendimiento:** en un M1 una clase de 1 hora suele tardar unos pocos minutos; depende de la RAM y de lo que tengas abierto. Se recomiendan 8 GB de RAM o más.
- **Formatos:** cualquier formato que ffmpeg lea (mp3, m4a, wav, flac, mp4…).
- **Errores frecuentes:**
  - `no se encontró ffmpeg` → `brew install ffmpeg` y abre una Terminal nueva.
  - `falta mlx-whisper` → no activaste el entorno: `source .venv/bin/activate`.
  - `command not found: brew` → faltó ejecutar los "Next steps" de Homebrew (paso 2).
  - Frases repetidas en el texto → ya se mitiga con `condition_on_previous_text=False`; si persiste, prueba con `--prompt ""`.
