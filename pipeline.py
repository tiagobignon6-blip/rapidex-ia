"""
RAPIDEX IA - pipeline.py v3.0
Toda a logica de processamento. Modelos carregados UMA VEZ e reutilizados.
"""

import os, subprocess, shutil, time, logging, threading, gc, tempfile
from pathlib import Path
from functools import wraps

import torch
import torchaudio

log = logging.getLogger("rapidex")

# ── CONFIG ────────────────────────────────────────────────────────────────────
DEVICE       = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE      = "float16" if DEVICE == "cuda" else "int8"
SR           = 16_000
WORKSPACE    = Path(os.environ.get("WORKSPACE", "/workspace"))
OUTPUT_DIR   = WORKSPACE / "outputs"
MODEL_DIR    = WORKSPACE / "models"
MUSETALK     = WORKSPACE / "MuseTalk"
WAV2LIP      = WORKSPACE / "Wav2Lip"
WAV2LIP_CK   = WAV2LIP / "checkpoints" / "wav2lip_gan.pth"
WHISPER_SIZE = "large-v3"
DEMUCS_MODEL = "htdemucs"
MAX_CHARS    = 4_500

for d in (OUTPUT_DIR, MODEL_DIR):
    d.mkdir(parents=True, exist_ok=True)

log.info(f"RAPIDEX pipeline - device={DEVICE} compute={COMPUTE}")

LANGUAGES = {
    "Detectar automaticamente": "auto",
    "Portugues": "pt", "Ingles": "en", "Espanhol": "es",
    "Frances": "fr",  "Alemao": "de",  "Italiano": "it",
    "Japones":  "ja", "Coreano": "ko", "Chines":   "zh",
    "Arabe":    "ar", "Russo":   "ru", "Hindi":    "hi",
    "Turco":    "tr", "Holandes": "nl", "Polones": "pl",
}

# ── MODEL MANAGER ──────────────────────────────────────────────────────────────

class ModelManager:
    """Singleton. WhisperX carregado UMA VEZ no startup em background thread."""
    _lock    = threading.Lock()
    _whisper = None
    _status  = "loading"

    @classmethod
    def preload(cls):
        try:
            import whisperx
            log.info(f"Carregando WhisperX {WHISPER_SIZE}...")
            model = whisperx.load_model(
                WHISPER_SIZE, DEVICE,
                compute_type=COMPUTE,
                download_root=str(MODEL_DIR),
            )
            with cls._lock:
                cls._whisper = model
                cls._status  = "ready"
            log.info("WhisperX pronto")
        except Exception as e:
            with cls._lock:
                cls._status = "failed"
            log.error(f"WhisperX falhou: {e}")

    @classmethod
    def whisper(cls):
        with cls._lock: return cls._whisper

    @classmethod
    def status(cls):
        with cls._lock: return cls._status

    @classmethod
    def clear_gpu(cls):
        if DEVICE == "cuda":
            torch.cuda.empty_cache()
            gc.collect()

# ── RETRY ─────────────────────────────────────────────────────────────────────

def retry(times=3, delay=2):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            for i in range(1, times + 1):
                try:
                    return fn(*a, **kw)
                except Exception as e:
                    log.warning(f"[retry] {fn.__name__} {i}/{times}: {e}")
                    if i < times:
                        time.sleep(delay)
                    else:
                        raise
        return wrapper
    return decorator

# ── AUDIO EXTRACTION ───────────────────────────────────────────────────────────

def extract_audio(video_path, out_dir):
    out = os.path.join(out_dir, "raw_audio.wav")
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", video_path,
         "-vn", "-ac", "1", "-ar", str(SR), "-sample_fmt", "s16", out],
        capture_output=True, text=True, timeout=300,
    )
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError(f"FFmpeg extract_audio falhou:\n{r.stderr[-300:]}")
    return out

# ── VOCAL SEPARATION (DEMUCS) ──────────────────────────────────────────────────

def run_demucs(raw_audio, out_dir):
    demucs_dir = os.path.join(out_dir, "demucs")
    os.makedirs(demucs_dir, exist_ok=True)

    # Tentativa 1: API Python
    try:
        from demucs.apply     import apply_model
        from demucs.pretrained import get_model
        model = get_model(DEMUCS_MODEL)
        model.eval()
        if DEVICE == "cuda": model.cuda()
        wav, sr_orig = torchaudio.load(raw_audio)
        if wav.shape[0] == 1: wav = wav.repeat(2, 1)
        wav = torchaudio.functional.resample(wav, sr_orig, model.samplerate)
        wav = wav.unsqueeze(0).to(DEVICE)
        with torch.no_grad():
            sources = apply_model(model, wav, device=DEVICE, progress=False)
        names      = model.sources
        v_idx      = names.index("vocals")
        vocals_wav = sources[0, v_idx].cpu()
        bg_wav     = sum(sources[0, i].cpu() for i, n in enumerate(names) if n != "vocals")
        voc_raw  = os.path.join(demucs_dir, "vocals_raw.wav")
        bg_path  = os.path.join(demucs_dir, "no_vocals.wav")
        torchaudio.save(voc_raw, vocals_wav, model.samplerate)
        torchaudio.save(bg_path, bg_wav,     model.samplerate)
        voc_16k = os.path.join(demucs_dir, "vocals.wav")
        subprocess.run(["ffmpeg", "-y", "-i", voc_raw, "-ar", str(SR), "-ac", "1", voc_16k],
                       capture_output=True)
        ModelManager.clear_gpu()
        log.info("Demucs API OK")
        return voc_16k, bg_path
    except Exception as e:
        log.warning(f"Demucs API falhou ({e}), tentando subprocess")
        ModelManager.clear_gpu()

    # Tentativa 2: subprocess
    r = subprocess.run(
        ["python", "-m", "demucs", f"--name={DEMUCS_MODEL}",
         "--two-stems=vocals", "-o", demucs_dir, raw_audio],
        capture_output=True, text=True, timeout=600,
    )
    vocals_path = bg_path = None
    for root, _, files in os.walk(demucs_dir):
        if "vocals.wav" in files:
            vocals_path = os.path.join(root, "vocals.wav")
            bg_path     = os.path.join(root, "no_vocals.wav")
            break
    if not vocals_path:
        log.warning("Demucs falhou - usando audio bruto como vocals")
        return raw_audio, None
    voc_16k = os.path.join(demucs_dir, "vocals.wav")
    subprocess.run(["ffmpeg", "-y", "-i", vocals_path, "-ar", str(SR), "-ac", "1", voc_16k],
                   capture_output=True)
    log.info("Demucs subprocess OK")
    return voc_16k, bg_path

# ── TRANSCRIPTION (WHISPERX) ───────────────────────────────────────────────────

def run_whisperx(vocals_path, lang_code):
    import whisperx
    model = ModelManager.whisper()
    if model is None:
        raise RuntimeError(f"WhisperX nao esta pronto. Status: {ModelManager.status()}")
    audio  = whisperx.load_audio(vocals_path)
    bs     = 16 if DEVICE == "cuda" else 4
    result = model.transcribe(audio, batch_size=bs,
                              language=None if lang_code == "auto" else lang_code)
    detected = result.get("language", "pt" if lang_code == "auto" else lang_code)
    try:
        am, meta = whisperx.load_align_model(language_code=detected, device=DEVICE)
        result   = whisperx.align(result["segments"], am, meta, audio, DEVICE,
                                  return_char_alignments=False)
        del am
        ModelManager.clear_gpu()
    except Exception as e:
        log.warning(f"Alinhamento WhisperX ignorado: {e}")
    text = " ".join(s["text"].strip() for s in result.get("segments", [])
                    if s.get("text", "").strip())
    log.info(f"Transcricao OK ({detected}): {text[:60]}...")
    return text.strip(), detected

# ── TRANSLATION ────────────────────────────────────────────────────────────────

@retry(times=4, delay=3)
def translate_text(text, src, tgt):
    from deep_translator import GoogleTranslator
    if not text or (src != "auto" and src == tgt):
        return text
    if len(text) <= MAX_CHARS:
        out = GoogleTranslator(source=src, target=tgt).translate(text)
        return out or text
    sentences = text.replace(". ", ".|").split("|")
    chunks, cur = [], ""
    for s in sentences:
        if len(cur) + len(s) + 2 <= MAX_CHARS:
            cur += s + " "
        else:
            if cur: chunks.append(cur.strip())
            cur = s + " "
    if cur: chunks.append(cur.strip())
    parts = []
    for chunk in chunks:
        t = GoogleTranslator(source=src, target=tgt).translate(chunk)
        parts.append(t or chunk)
        time.sleep(0.4)
    return " ".join(parts)

# ── TTS (VOICE SYNTHESIS) ──────────────────────────────────────────────────────

def run_tts(text, ref_wav, out_dir, tgt_lang="pt"):
    """Fish Speech -> Coqui XTTS v2 -> gTTS (sempre funciona)"""
    out = os.path.join(out_dir, "dubbed_voice.wav")

    # 1. Fish Speech
    for cmd in [
        ["fish_speech", "infer", "--text", text,
         "--reference-audio", ref_wav, "--output", out],
        ["python", "-m", "fish_speech.inference", "--text", text,
         "--reference-audio", ref_wav, "--output", out, "--device", DEVICE],
    ]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if r.returncode == 0 and _valid_wav(out):
                log.info("Fish Speech OK")
                return out
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    # 2. Coqui XTTS v2
    try:
        from TTS.api import TTS as CoquiTTS
        m = CoquiTTS("tts_models/multilingual/multi-dataset/xtts_v2",
                     gpu=(DEVICE == "cuda"))
        m.tts_to_file(text=text, speaker_wav=ref_wav,
                      language=tgt_lang[:2], file_path=out)
        if _valid_wav(out):
            ModelManager.clear_gpu()
            log.info("Coqui XTTS OK")
            return out
    except Exception as e:
        log.warning(f"Coqui XTTS: {e}")

    # 3. gTTS (fallback garantido)
    log.warning("Usando gTTS (sem clonagem de voz)")
    from gtts import gTTS
    mp3 = os.path.join(out_dir, "gtts_tmp.mp3")
    gTTS(text=text, lang=_gtts_lang(tgt_lang), slow=False).save(mp3)
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", mp3, "-ar", str(SR), "-ac", "1", "-sample_fmt", "s16", out],
        capture_output=True, text=True,
    )
    if not _valid_wav(out):
        raise RuntimeError(f"gTTS falhou: {r.stderr[-200:]}")
    log.info("gTTS OK")
    return out


def _valid_wav(p):
    return os.path.exists(p) and os.path.getsize(p) > 2_000


def _gtts_lang(code):
    m = {"zh": "zh-CN", "ko": "ko", "ja": "ja", "ar": "ar",
         "ru": "ru", "hi": "hi", "tr": "tr", "nl": "nl", "pl": "pl"}
    return m.get(code, code[:2] if code else "pt")

# ── AUDIO MIX ──────────────────────────────────────────────────────────────────

def mix_audio(voice, bg, out_dir):
    out = os.path.join(out_dir, "mixed.wav")
    if not bg or not os.path.exists(bg) or os.path.getsize(bg) < 500:
        shutil.copy(voice, out)
        return out
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", voice, "-i", bg,
         "-filter_complex",
         "[0:a]volume=1.0[v];[1:a]volume=0.28[b];[v][b]amix=inputs=2:duration=longest[out]",
         "-map", "[out]", "-ar", str(SR), out],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0 or not os.path.exists(out):
        log.warning(f"Mix falhou: {r.stderr[-200:]}")
        shutil.copy(voice, out)
    return out

# ── LIP SYNC ───────────────────────────────────────────────────────────────────

def run_lipsync(video, audio, out_dir):
    """MuseTalk -> Wav2Lip -> FFmpeg fallback (sempre funciona)"""
    out = os.path.join(out_dir, "lipsync.mp4")

    # MuseTalk
    if MUSETALK.is_dir():
        r = subprocess.run(
            ["python", str(MUSETALK / "scripts/inference.py"),
             "--video_path", video, "--audio_path", audio,
             "--output_path", out, "--bbox_shift", "0"],
            capture_output=True, text=True, cwd=str(MUSETALK), timeout=900,
        )
        if r.returncode == 0 and _valid_mp4(out):
            log.info("MuseTalk OK")
            return out
        log.warning(f"MuseTalk falhou: {r.stderr[-200:]}")

    # Wav2Lip
    if WAV2LIP.is_dir() and WAV2LIP_CK.exists():
        r = subprocess.run(
            ["python", str(WAV2LIP / "inference.py"),
             "--checkpoint_path", str(WAV2LIP_CK),
             "--face", video, "--audio", audio,
             "--outfile", out,
             "--pads", "0", "15", "0", "0",
             "--resize_factor", "1", "--nosmooth"],
            capture_output=True, text=True, cwd=str(WAV2LIP), timeout=900,
        )
        if r.returncode == 0 and _valid_mp4(out):
            log.info("Wav2Lip OK")
            return out
        log.warning(f"Wav2Lip falhou: {r.stderr[-200:]}")

    # Fallback: troca de audio
    log.warning("Lipsync indisponivel - substituindo audio")
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", video, "-i", audio,
         "-c:v", "copy", "-map", "0:v:0", "-map", "1:a:0", "-shortest", out],
        capture_output=True, text=True, timeout=300,
    )
    if r.returncode != 0 or not _valid_mp4(out):
        raise RuntimeError(f"FFmpeg fallback: {r.stderr[-300:]}")
    return out


def _valid_mp4(p):
    return os.path.exists(p) and os.path.getsize(p) > 5_000

# ── CLEANUP ────────────────────────────────────────────────────────────────────

def cleanup(path):
    try:
        if path and os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            log.info(f"Temp removido: {path}")
    except Exception:
        pass
