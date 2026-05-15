"""
RAPIDEX IA - pipeline.py v3.2
Logica central. Modelos carregados UMA VEZ. Fallbacks em tudo.
Auto-healing: retry, CPU fallback, NaN protection, OOM recovery.
"""

import os, sys, subprocess, shutil, time, logging, threading, gc
from pathlib import Path
from functools import wraps

import torch
import torchaudio

log = logging.getLogger("rapidex")

# ── CONFIG ────────────────────────────────────────────────────────────────────
DEVICE       = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE      = "float16" if DEVICE == "cuda" else "int8"
SR           = 16_000
DEMUCS_SR    = 44_100


def _pick_workspace():
    """Escolhe um workspace gravavel. Prefere /workspace (runpod), depois RAPIDEX_BASE (colab), depois /tmp."""
    candidates = [
        os.environ.get("WORKSPACE"),
        os.environ.get("RAPIDEX_BASE"),
        "/workspace",
        "/content",
        os.path.expanduser("~/rapidex"),
        "/tmp/rapidex",
    ]
    for c in candidates:
        if not c:
            continue
        p = Path(c)
        try:
            p.mkdir(parents=True, exist_ok=True)
            # Testa escrita real
            probe = p / ".rapidex_probe"
            probe.write_text("ok")
            probe.unlink()
            return p
        except Exception:
            continue
    return Path("/tmp")


WORKSPACE    = _pick_workspace()
OUTPUT_DIR   = WORKSPACE / "outputs"
MODEL_DIR    = WORKSPACE / "models"
MUSETALK     = WORKSPACE / "MuseTalk"
WAV2LIP      = WORKSPACE / "Wav2Lip"
WAV2LIP_CK   = WAV2LIP / "checkpoints" / "wav2lip_gan.pth"
WHISPER_SIZE = os.environ.get("WHISPER_SIZE", "large-v3")
DEMUCS_MODEL = os.environ.get("DEMUCS_MODEL", "htdemucs")
MAX_CHARS    = 4_500
PYBIN        = sys.executable or "python3"

# Coqui XTTS exige aceite automatico para nao travar
os.environ.setdefault("COQUI_TOS_AGREED", "1")

for d in (OUTPUT_DIR, MODEL_DIR):
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception as _e:
        log.warning(f"Nao foi possivel criar {d}: {_e}")

log.info(f"RAPIDEX pipeline - device={DEVICE} compute={COMPUTE} python={PYBIN}")

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
    _lock    = threading.Lock()
    _whisper = None
    _status  = "idle"

    @classmethod
    def preload(cls):
        with cls._lock:
            if cls._whisper is not None:
                return
            cls._status = "loading"
        try:
            import whisperx
            log.info(f"Carregando WhisperX {WHISPER_SIZE} em {DEVICE}/{COMPUTE}...")
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
                cls._status = f"failed: {e}"
            log.error(f"WhisperX falhou: {e}")

    @classmethod
    def whisper(cls):
        with cls._lock:
            return cls._whisper

    @classmethod
    def status(cls):
        with cls._lock:
            return cls._status

    @classmethod
    def ensure_whisper(cls, timeout=600):
        """Garante que o whisper esteja carregado. Bloqueia até estar pronto."""
        m = cls.whisper()
        if m is not None:
            return m
        # Se ainda nao carregou, carrega agora (sincronamente)
        if cls.status() != "loading":
            cls.preload()
        else:
            # Espera o background terminar
            start = time.time()
            while cls.status() == "loading" and time.time() - start < timeout:
                time.sleep(1)
        m = cls.whisper()
        if m is None:
            raise RuntimeError(f"WhisperX indisponivel: {cls.status()}")
        return m

    @classmethod
    def clear_gpu(cls):
        if DEVICE == "cuda":
            try:
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            except Exception:
                pass
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
    """Extrai audio mono 16kHz para WhisperX. Tambem cria versao stereo 44.1kHz para Demucs."""
    out_16k = os.path.join(out_dir, "raw_audio.wav")
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", video_path,
         "-vn", "-ac", "1", "-ar", str(SR), "-sample_fmt", "s16", out_16k],
        capture_output=True, text=True, timeout=300,
    )
    if r.returncode != 0 or not os.path.exists(out_16k):
        raise RuntimeError(f"FFmpeg extract_audio falhou:\n{r.stderr[-300:]}")

    # Versao para Demucs (stereo 44.1kHz - qualidade necessaria para boa separacao)
    out_demucs = os.path.join(out_dir, "demucs_input.wav")
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path,
         "-vn", "-ac", "2", "-ar", str(DEMUCS_SR), "-sample_fmt", "s16", out_demucs],
        capture_output=True, text=True, timeout=300,
    )
    if not os.path.exists(out_demucs):
        # Se falhar, usa o de 16k mesmo (demucs aceita resample interno)
        out_demucs = out_16k

    log.info(f"Audio extraido: 16k={out_16k} demucs={out_demucs}")
    return out_16k, out_demucs

# ── VOCAL SEPARATION (DEMUCS) ──────────────────────────────────────────────────

def _demucs_normalize(wav):
    """Normaliza wav para demucs. Protege contra silencio (std=0)."""
    ref = wav.mean(0)
    mean = ref.mean().item()
    std = ref.std().item()
    if std < 1e-6:
        std = 1.0  # audio silencioso/constante
    return (wav - mean) / std, mean, std


def _demucs_apply(model, wav_in, device):
    from demucs.apply import apply_model
    with torch.no_grad():
        return apply_model(
            model, wav_in,
            device=device,
            progress=False,
            shifts=0,        # mais rapido, evita OOM
            split=True,      # divide audio longo automaticamente
            overlap=0.25,
        )


def run_demucs(raw_audio, out_dir, demucs_input=None):
    """Separa voz do fundo. Retorna (vocals_path_16k, bg_path) ou (raw_audio, None)."""
    demucs_dir = os.path.join(out_dir, "demucs")
    os.makedirs(demucs_dir, exist_ok=True)
    src_audio = demucs_input or raw_audio

    # Tentativa 1: API Python (mais precisa e rapida)
    try:
        from demucs.pretrained import get_model

        model = get_model(DEMUCS_MODEL)
        model.eval()
        model.to(DEVICE)

        wav, sr_orig = torchaudio.load(src_audio)
        if wav.shape[0] == 1:
            wav = wav.repeat(2, 1)
        if sr_orig != model.samplerate:
            wav = torchaudio.functional.resample(wav, sr_orig, model.samplerate)

        wav_norm, ref_mean, ref_std = _demucs_normalize(wav)
        wav_in = wav_norm.unsqueeze(0)  # (1, channels, time)

        # Tenta no DEVICE configurado, com fallback para CPU em caso de OOM
        try:
            sources = _demucs_apply(model, wav_in, DEVICE)
        except torch.cuda.OutOfMemoryError as oom:
            log.warning(f"Demucs CUDA OOM ({oom}), tentando em CPU")
            ModelManager.clear_gpu()
            model.to("cpu")
            sources = _demucs_apply(model, wav_in, "cpu")
        except RuntimeError as re:
            msg = str(re).lower()
            if "out of memory" in msg or "cuda" in msg:
                log.warning(f"Demucs RuntimeError CUDA ({re}), tentando em CPU")
                ModelManager.clear_gpu()
                model.to("cpu")
                sources = _demucs_apply(model, wav_in, "cpu")
            else:
                raise

        # Des-normalizar
        sources = sources * ref_std + ref_mean

        names   = list(model.sources)          # ex.: ['drums','bass','other','vocals']
        if "vocals" not in names:
            raise RuntimeError(f"Demucs sem stem 'vocals' em {names}")
        v_idx   = names.index("vocals")
        voc_wav = sources[0, v_idx].cpu()
        bg_wav  = sum(
            sources[0, i].cpu()
            for i, n in enumerate(names) if n != "vocals"
        )

        # Limpa NaN/Inf que podem vir de audio silencioso
        voc_wav = torch.nan_to_num(voc_wav, nan=0.0, posinf=1.0, neginf=-1.0)
        bg_wav  = torch.nan_to_num(bg_wav,  nan=0.0, posinf=1.0, neginf=-1.0)

        voc_raw  = os.path.join(demucs_dir, "vocals_raw.wav")
        bg_path  = os.path.join(demucs_dir, "no_vocals.wav")
        torchaudio.save(voc_raw, voc_wav, model.samplerate)
        torchaudio.save(bg_path, bg_wav,  model.samplerate)

        # libera modelo da memoria
        del model, sources, wav, wav_in, wav_norm
        ModelManager.clear_gpu()

        # Converte vocals para 16k mono (formato do WhisperX/TTS)
        voc_16k = os.path.join(demucs_dir, "vocals.wav")
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", voc_raw, "-ar", str(SR), "-ac", "1", voc_16k],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0 or not os.path.exists(voc_16k):
            log.warning(f"FFmpeg vocals 16k falhou: {r.stderr[-200:]}")
            voc_16k = voc_raw

        log.info("Demucs API OK")
        return voc_16k, bg_path

    except Exception as e:
        log.warning(f"Demucs API falhou ({type(e).__name__}: {e}), tentando subprocess")
        ModelManager.clear_gpu()

    # Tentativa 2: subprocess (CLI)
    cmd_device = "cuda" if DEVICE == "cuda" else "cpu"
    r = subprocess.run(
        [PYBIN, "-m", "demucs",
         f"--name={DEMUCS_MODEL}",
         "--two-stems=vocals",
         "-d", cmd_device,
         "-o", demucs_dir, src_audio],
        capture_output=True, text=True, timeout=900,
    )
    if r.returncode != 0:
        log.warning(f"Demucs CLI ({cmd_device}) falhou: {r.stderr[-300:]}")
        if cmd_device == "cuda":
            log.warning("Reexecutando Demucs CLI em CPU")
            r = subprocess.run(
                [PYBIN, "-m", "demucs",
                 f"--name={DEMUCS_MODEL}",
                 "--two-stems=vocals",
                 "-d", "cpu",
                 "-o", demucs_dir, src_audio],
                capture_output=True, text=True, timeout=1800,
            )

    vocals_path = bg_path = None
    for root, _, files in os.walk(demucs_dir):
        if "vocals.wav" in files:
            vocals_path = os.path.join(root, "vocals.wav")
            bg_candidate = os.path.join(root, "no_vocals.wav")
            bg_path = bg_candidate if os.path.exists(bg_candidate) else None
            break

    if not vocals_path:
        log.warning("Demucs falhou completamente - usando audio bruto sem separacao")
        return raw_audio, None

    voc_16k = os.path.join(demucs_dir, "vocals_16k.wav")
    conv = subprocess.run(
        ["ffmpeg", "-y", "-i", vocals_path, "-ar", str(SR), "-ac", "1", voc_16k],
        capture_output=True, text=True, timeout=120,
    )
    if conv.returncode != 0 or not os.path.exists(voc_16k):
        voc_16k = vocals_path
    log.info("Demucs subprocess OK")
    return voc_16k, bg_path

# ── TRANSCRIPTION (WHISPERX) ───────────────────────────────────────────────────

def run_whisperx(vocals_path, lang_code):
    import whisperx

    model = ModelManager.ensure_whisper()

    audio   = whisperx.load_audio(vocals_path)
    bs      = 16 if DEVICE == "cuda" else 4
    result  = model.transcribe(
        audio, batch_size=bs,
        language=None if lang_code == "auto" else lang_code,
    )
    detected = result.get("language", "pt" if lang_code == "auto" else lang_code)

    try:
        am, meta = whisperx.load_align_model(
            language_code=detected, device=DEVICE
        )
        result = whisperx.align(
            result["segments"], am, meta, audio, DEVICE,
            return_char_alignments=False,
        )
        del am
        ModelManager.clear_gpu()
    except Exception as e:
        log.warning(f"Alinhamento WhisperX ignorado ({detected}): {e}")

    text = " ".join(
        s["text"].strip()
        for s in result.get("segments", [])
        if s.get("text", "").strip()
    )
    if not text.strip():
        raise RuntimeError("Transcricao vazia - audio sem fala detectavel")
    log.info(f"Transcricao OK ({detected}): {text[:60]}...")
    return text.strip(), detected

# ── TRANSLATION ────────────────────────────────────────────────────────────────

@retry(times=4, delay=3)
def translate_text(text, src, tgt):
    from deep_translator import GoogleTranslator

    if not text:
        return text
    src = src or "auto"
    tgt = tgt or "pt"
    if src != "auto" and src == tgt:
        return text

    if len(text) <= MAX_CHARS:
        out = GoogleTranslator(source=src, target=tgt).translate(text)
        return out or text

    # Texto longo: dividir em chunks por sentenca
    sentences = text.replace(". ", ".|").split("|")
    chunks, cur = [], ""
    for s in sentences:
        if len(cur) + len(s) + 2 <= MAX_CHARS:
            cur += s + " "
        else:
            if cur:
                chunks.append(cur.strip())
            cur = s + " "
    if cur:
        chunks.append(cur.strip())

    parts = []
    for chunk in chunks:
        try:
            t = GoogleTranslator(source=src, target=tgt).translate(chunk)
            parts.append(t or chunk)
        except Exception as e:
            log.warning(f"Traducao chunk falhou: {e}")
            parts.append(chunk)
        time.sleep(0.4)
    return " ".join(parts)

# ── TTS ────────────────────────────────────────────────────────────────────────

def run_tts(text, ref_wav, out_dir, tgt_lang="pt"):
    """Ordem: Fish Speech -> Coqui XTTS v2 -> gTTS (sempre funciona)."""
    out = os.path.join(out_dir, "dubbed_voice.wav")
    tgt_lang = (tgt_lang or "pt").strip() or "pt"

    if not text or not text.strip():
        raise RuntimeError("Texto para TTS esta vazio")
    if not ref_wav or not os.path.exists(ref_wav):
        log.warning(f"Referencia de voz invalida ({ref_wav}) - pulando clonagem")
        ref_wav = None

    # 1. Fish Speech (clonagem de voz, melhor qualidade) - so se tiver ref
    if ref_wav:
        for cmd in [
            ["fish_speech", "infer",
             "--text", text, "--reference-audio", ref_wav, "--output", out],
            [PYBIN, "-m", "fish_speech.inference",
             "--text", text, "--reference-audio", ref_wav,
             "--output", out, "--device", DEVICE],
        ]:
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if r.returncode == 0 and _valid_wav(out):
                    log.info("Fish Speech OK")
                    return out
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
            except Exception as e:
                log.debug(f"Fish Speech erro: {e}")

    # 2. Coqui XTTS v2 (clonagem de voz, boa qualidade)
    if ref_wav:
        try:
            from TTS.api import TTS as CoquiTTS
            m = CoquiTTS(
                "tts_models/multilingual/multi-dataset/xtts_v2",
                gpu=(DEVICE == "cuda"),
            )
            lang_code = tgt_lang[:2]
            m.tts_to_file(
                text=text,
                speaker_wav=ref_wav,
                language=lang_code,
                file_path=out,
            )
            del m
            ModelManager.clear_gpu()
            if _valid_wav(out):
                log.info("Coqui XTTS OK")
                return out
        except Exception as e:
            log.warning(f"Coqui XTTS falhou: {e}")
            ModelManager.clear_gpu()

    # 3. gTTS (sem clonagem, mas SEMPRE funciona)
    log.warning("Usando gTTS (sem clonagem de voz)")
    from gtts import gTTS

    mp3 = os.path.join(out_dir, "gtts_tmp.mp3")
    try:
        gTTS(text=text, lang=_gtts_lang(tgt_lang), slow=False).save(mp3)
    except Exception as e:
        # gTTS pode falhar se lang nao suportado - cai pra portugues
        log.warning(f"gTTS lang {tgt_lang} falhou ({e}), tentando 'pt'")
        gTTS(text=text, lang="pt", slow=False).save(mp3)

    r = subprocess.run(
        ["ffmpeg", "-y", "-i", mp3,
         "-ar", str(SR), "-ac", "1", "-sample_fmt", "s16", out],
        capture_output=True, text=True, timeout=120,
    )
    if not _valid_wav(out):
        raise RuntimeError(f"gTTS->wav falhou: {r.stderr[-200:]}")
    log.info("gTTS OK")
    return out


def _valid_wav(p):
    return p and os.path.exists(p) and os.path.getsize(p) > 2_000


def _gtts_lang(code):
    m = {
        "zh": "zh-CN", "ko": "ko", "ja": "ja", "ar": "ar",
        "ru": "ru", "hi": "hi", "tr": "tr", "nl": "nl", "pl": "pl",
    }
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
         "[0:a]volume=1.0[v];[1:a]volume=0.28[b];"
         "[v][b]amix=inputs=2:duration=longest[out]",
         "-map", "[out]", "-ar", str(SR), out],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0 or not os.path.exists(out):
        log.warning(f"Mix falhou: {r.stderr[-200:]}")
        shutil.copy(voice, out)
    return out

# ── LIP SYNC ───────────────────────────────────────────────────────────────────

def _find_musetalk_script():
    """MuseTalk tem layouts diferentes entre versoes. Tenta os caminhos comuns."""
    candidates = [
        MUSETALK / "scripts" / "inference.py",
        MUSETALK / "inference.py",
        MUSETALK / "realtime_inference.py",
        MUSETALK / "scripts" / "realtime_inference.py",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def run_lipsync(video, audio, out_dir):
    """Ordem: MuseTalk -> Wav2Lip -> FFmpeg (troca so o audio, sempre funciona)."""
    out = os.path.join(out_dir, "lipsync.mp4")

    # MuseTalk (melhor qualidade)
    musetalk_script = _find_musetalk_script()
    if musetalk_script:
        r = subprocess.run(
            [PYBIN, str(musetalk_script),
             "--video_path", video,
             "--audio_path", audio,
             "--output_path", out,
             "--bbox_shift", "0"],
            capture_output=True, text=True,
            cwd=str(MUSETALK), timeout=1200,
        )
        if r.returncode == 0 and _valid_mp4(out):
            log.info("MuseTalk OK")
            return out
        log.warning(f"MuseTalk falhou: {r.stderr[-300:]}")

    # Wav2Lip (estavel, bem testado)
    if WAV2LIP.is_dir() and WAV2LIP_CK.exists():
        r = subprocess.run(
            [PYBIN, str(WAV2LIP / "inference.py"),
             "--checkpoint_path", str(WAV2LIP_CK),
             "--face", video,
             "--audio", audio,
             "--outfile", out,
             "--pads", "0", "15", "0", "0",
             "--resize_factor", "1",
             "--nosmooth"],
            capture_output=True, text=True,
            cwd=str(WAV2LIP), timeout=1200,
        )
        if r.returncode == 0 and _valid_mp4(out):
            log.info("Wav2Lip OK")
            return out
        log.warning(f"Wav2Lip falhou: {r.stderr[-300:]}")

    # Fallback: substituir audio sem mover labios
    log.warning("Lipsync indisponivel - substituindo apenas o audio")
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", video, "-i", audio,
         "-c:v", "copy",
         "-map", "0:v:0", "-map", "1:a:0",
         "-shortest", out],
        capture_output=True, text=True, timeout=300,
    )
    if r.returncode != 0 or not _valid_mp4(out):
        # Se o copy falhar (codec incompativel), re-encoda video
        r2 = subprocess.run(
            ["ffmpeg", "-y", "-i", video, "-i", audio,
             "-c:v", "libx264", "-preset", "fast", "-crf", "20",
             "-map", "0:v:0", "-map", "1:a:0",
             "-shortest", out],
            capture_output=True, text=True, timeout=600,
        )
        if r2.returncode != 0 or not _valid_mp4(out):
            raise RuntimeError(f"FFmpeg fallback final: {r2.stderr[-300:]}")
    return out


def _valid_mp4(p):
    return p and os.path.exists(p) and os.path.getsize(p) > 5_000

# ── CLEANUP ────────────────────────────────────────────────────────────────────

def cleanup(path):
    try:
        if path and os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            log.info(f"Temp removido: {path}")
    except Exception:
        pass
