import gradio as gr
import os
import subprocess
import tempfile
import shutil
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("rapidex")

# ─────────────────────────────────────────
# PIPELINE FUNCTIONS
# ─────────────────────────────────────────

def extract_audio(video_path, out_dir):
    raw_audio = os.path.join(out_dir, "raw_audio.wav")
    result = subprocess.run([
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", raw_audio
    ], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg (extract_audio) falhou:\n{result.stderr}")
    return raw_audio


def run_demucs(raw_audio, out_dir):
    demucs_out = os.path.join(out_dir, "demucs")
    result = subprocess.run([
        "python", "-m", "demucs", "--two-stems=vocals", "-o", demucs_out, raw_audio
    ], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Demucs falhou:\n{result.stderr}")

    stem_dir = None
    for root, dirs, files in os.walk(demucs_out):
        if "vocals.wav" in files:
            stem_dir = root
            break
    if stem_dir is None:
        raise RuntimeError("Demucs nao gerou vocals.wav")
    return os.path.join(stem_dir, "vocals.wav"), os.path.join(stem_dir, "no_vocals.wav")


def run_whisperx(vocals_path, lang_code):
    try:
        import whisperx
        import torch
    except ImportError as e:
        raise RuntimeError(f"Dependencia ausente: {e}. Instale whisperx e torch.")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute = "float16" if device == "cuda" else "int8"

    model = whisperx.load_model(
        "large-v3", device, compute_type=compute,
        language=lang_code if lang_code != "auto" else None
    )
    audio = whisperx.load_audio(vocals_path)
    result = model.transcribe(audio, batch_size=16)

    detected_lang = result.get("language", lang_code if lang_code != "auto" else "pt")
    try:
        align_model, meta = whisperx.load_align_model(language_code=detected_lang, device=device)
        result = whisperx.align(result["segments"], align_model, meta, audio, device)
    except Exception as e:
        log.warning(f"Alinhamento WhisperX falhou (usando segmentos brutos): {e}")

    segments = result.get("segments", [])
    text = " ".join(s["text"].strip() for s in segments if s.get("text"))
    return text, detected_lang


def translate_text(text, source_code, target_code):
    from deep_translator import GoogleTranslator

    src = source_code if source_code else "auto"
    tgt = target_code if target_code else "pt"

    if src != "auto" and src == tgt:
        return text

    MAX_CHARS = 4500
    if len(text) <= MAX_CHARS:
        return GoogleTranslator(source=src, target=tgt).translate(text) or text

    chunks = []
    current = ""
    for sentence in text.split(". "):
        if len(current) + len(sentence) + 2 <= MAX_CHARS:
            current += sentence + ". "
        else:
            if current:
                chunks.append(current.strip())
            current = sentence + ". "
    if current:
        chunks.append(current.strip())

    translated_chunks = [
        GoogleTranslator(source=src, target=tgt).translate(c) or c
        for c in chunks
    ]
    return " ".join(translated_chunks)


def run_fish_speech(text, ref_wav, out_dir):
    dubbed = os.path.join(out_dir, "dubbed_voice.wav")

    r = subprocess.run([
        "fish_speech", "infer",
        "--text", text,
        "--reference-audio", ref_wav,
        "--output", dubbed,
    ], capture_output=True, text=True)

    if r.returncode == 0 and os.path.exists(dubbed):
        return dubbed

    r2 = subprocess.run([
        "python", "-m", "fish_speech.inference",
        "--text", text,
        "--reference-audio", ref_wav,
        "--output", dubbed,
        "--device", "cuda"
    ], capture_output=True, text=True)

    if r2.returncode == 0 and os.path.exists(dubbed):
        return dubbed

    log.warning("Fish Speech indisponivel. Usando gTTS como fallback.")
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang="pt")
        mp3_path = os.path.join(out_dir, "dubbed_gtts.mp3")
        tts.save(mp3_path)
        conv = subprocess.run([
            "ffmpeg", "-y", "-i", mp3_path,
            "-ar", "16000", "-ac", "1", dubbed
        ], capture_output=True, text=True)
        if conv.returncode != 0 or not os.path.exists(dubbed):
            raise RuntimeError("Conversao gTTS mp3->wav falhou")
        return dubbed
    except ImportError:
        raise RuntimeError(
            f"Fish Speech falhou e gTTS nao esta instalado.\n"
            f"Erro Fish Speech: {r2.stderr}"
        )


def mix_audio(dubbed, bgmusic, out_dir):
    mixed = os.path.join(out_dir, "mixed_audio.wav")

    if not os.path.exists(bgmusic) or os.path.getsize(bgmusic) == 0:
        log.warning("Musica de fundo ausente ou vazia - usando apenas voz dublada.")
        shutil.copy(dubbed, mixed)
        return mixed

    result = subprocess.run([
        "ffmpeg", "-y", "-i", dubbed, "-i", bgmusic,
        "-filter_complex",
        "[0:a]volume=1.0[v];[1:a]volume=0.35[b];[v][b]amix=inputs=2:duration=longest[out]",
        "-map", "[out]", mixed
    ], capture_output=True, text=True)

    if result.returncode != 0 or not os.path.exists(mixed):
        log.warning(f"Mix de audio falhou: {result.stderr} - usando apenas voz dublada.")
        shutil.copy(dubbed, mixed)

    return mixed


def run_lipsync(video, audio, out_dir):
    output = os.path.join(out_dir, "rapidex_output.mp4")
    musetalk = "/workspace/MuseTalk"

    if os.path.isdir(musetalk):
        r = subprocess.run([
            "python", f"{musetalk}/scripts/inference.py",
            "--video_path", video, "--audio_path", audio,
            "--output_path", output, "--bbox_shift", "0"
        ], capture_output=True, text=True, cwd=musetalk)
        if r.returncode == 0 and os.path.exists(output):
            return output
        log.warning(f"MuseTalk falhou: {r.stderr}")

    wav2lip = "/workspace/Wav2Lip"
    checkpoint = f"{wav2lip}/checkpoints/wav2lip_gan.pth"
    if os.path.isdir(wav2lip) and os.path.exists(checkpoint):
        r2 = subprocess.run([
            "python", f"{wav2lip}/inference.py",
            "--checkpoint_path", checkpoint,
            "--face", video, "--audio", audio,
            "--outfile", output,
            "--pads", "0", "10", "0", "0", "--resize_factor", "1"
        ], capture_output=True, text=True, cwd=wav2lip)
        if r2.returncode == 0 and os.path.exists(output):
            return output
        log.warning(f"Wav2Lip falhou: {r2.stderr}")

    log.warning("Lip-sync indisponivel - substituindo apenas o audio.")
    r3 = subprocess.run([
        "ffmpeg", "-y", "-i", video, "-i", audio,
        "-c:v", "copy", "-map", "0:v:0", "-map", "1:a:0", "-shortest", output
    ], capture_output=True, text=True)
    if r3.returncode != 0 or not os.path.exists(output):
        raise RuntimeError(f"Fallback FFmpeg falhou:\n{r3.stderr}")
    return output


def cleanup_tmp(tmp_dir):
    try:
        if tmp_dir and os.path.isdir(tmp_dir):
            shutil.rmtree(tmp_dir)
            log.info(f"Temp removido: {tmp_dir}")
    except Exception as e:
        log.warning(f"Falha ao remover temp {tmp_dir}: {e}")


# ─────────────────────────────────────────
# STEP FUNCTIONS (com gr.State - thread-safe)
# ─────────────────────────────────────────

def step_transcribe(video, source_lang, target_lang, session_state, progress=gr.Progress(track_tqdm=True)):
    if video is None:
        raise gr.Error("Envie um video.")

    src = LANGUAGES.get(source_lang, "auto")
    tgt = LANGUAGES.get(target_lang, "pt")

    if session_state and session_state.get("tmp"):
        cleanup_tmp(session_state["tmp"])

    tmp = tempfile.mkdtemp(prefix="rapidex_")
    new_state = {"tmp": tmp, "video": video, "src": src, "tgt": tgt}

    try:
        progress(0.10, desc="Extraindo audio...")
        raw = extract_audio(video, tmp)

        progress(0.25, desc="Separando voz e musica...")
        vocals, bg = run_demucs(raw, tmp)
        new_state["vocals"] = vocals
        new_state["bg"] = bg

        progress(0.55, desc="Transcrevendo com WhisperX...")
        original, detected_lang = run_whisperx(vocals, src)
        new_state["detected_lang"] = detected_lang

        progress(0.80, desc="Traduzindo...")
        actual_src = detected_lang if src == "auto" else src
        translated = translate_text(original, actual_src, tgt)

        progress(1.00, desc="Pronto!")
        return original, translated, "Transcricao concluida - edite o texto se quiser e clique em Dublar", new_state

    except Exception as e:
        cleanup_tmp(tmp)
        raise gr.Error(str(e))


def step_dub(translated_text, use_lipsync, ref_audio, session_state, progress=gr.Progress(track_tqdm=True)):
    if not translated_text or not translated_text.strip():
        raise gr.Error("Texto de traducao vazio.")
    if not session_state or "tmp" not in session_state:
        raise gr.Error("Faca a transcricao primeiro.")

    tmp = session_state["tmp"]
    video = session_state["video"]
    vocals = session_state["vocals"]
    bg = session_state["bg"]

    try:
        progress(0.15, desc="Gerando voz dublada...")
        ref = ref_audio if ref_audio else vocals
        dubbed = run_fish_speech(translated_text, ref, tmp)

        progress(0.40, desc="Mixando audio...")
        mixed = mix_audio(dubbed, bg, tmp)

        if use_lipsync:
            progress(0.65, desc="Sincronizando labios...")
            out = run_lipsync(video, mixed, tmp)
        else:
            progress(0.65, desc="Exportando video...")
            out = os.path.join(tmp, "rapidex_output.mp4")
            result = subprocess.run([
                "ffmpeg", "-y", "-i", video, "-i", mixed,
                "-c:v", "copy", "-map", "0:v:0", "-map", "1:a:0", "-shortest", out
            ], capture_output=True, text=True)
            if result.returncode != 0 or not os.path.exists(out):
                raise RuntimeError(f"FFmpeg falhou ao exportar:\n{result.stderr}")

        progress(0.95, desc="Finalizando...")
        final = f"/workspace/output_{int(time.time())}.mp4"
        shutil.copy(out, final)
        cleanup_tmp(tmp)
        session_state["tmp"] = None
        return out, "Dublagem concluida!"

    except Exception as e:
        raise gr.Error(str(e))


# ─────────────────────────────────────────
# IDIOMAS
# ─────────────────────────────────────────

LANGUAGES = {
    "Detectar automaticamente": "auto",
    "Portugues": "pt", "Ingles": "en", "Espanhol": "es",
    "Frances": "fr", "Alemao": "de", "Italiano": "it",
    "Japones": "ja", "Coreano": "ko", "Chines": "zh",
    "Arabe": "ar", "Russo": "ru", "Hindi": "hi",
    "Turco": "tr", "Holandes": "nl", "Polones": "pl",
}

# ─────────────────────────────────────────
# CSS
# ─────────────────────────────────────────

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');
:root {
  --bg: #020409; --surface: #0b0f1a; --border: #1a2035;
  --accent: #6366f1; --accent2: #a855f7; --accent3: #ec4899;
  --text: #e2e8f0; --muted: #64748b; --success: #10b981; --radius: 12px;
}
* { box-sizing: border-box; }
body, .gradio-container { background: var(--bg) !important; font-family: 'Syne', sans-serif !important; color: var(--text) !important; }
.rapidex-header { padding: 2rem 0 1.5rem; text-align: center; border-bottom: 1px solid var(--border); margin-bottom: 2rem; background: linear-gradient(180deg, #0d1025 0%, transparent 100%); }
.rapidex-logo { font-size: 2.4rem; font-weight: 800; letter-spacing: -0.02em; background: linear-gradient(135deg, var(--accent), var(--accent2), var(--accent3)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.rapidex-tagline { font-size: 0.85rem; color: var(--muted); font-family: 'JetBrains Mono', monospace; letter-spacing: 0.08em; margin-top: 4px; }
.gpu-badge { display: inline-block; font-size: 0.7rem; font-family: 'JetBrains Mono', monospace; background: rgba(99,102,241,0.12); color: var(--accent); border: 1px solid rgba(99,102,241,0.3); padding: 3px 10px; border-radius: 20px; margin: 0 4px; }
.pipeline-bar { display: flex; align-items: center; justify-content: center; gap: 0; margin-bottom: 2rem; padding: 0 1rem; }
.step { display: flex; align-items: center; gap: 8px; font-size: 0.72rem; font-family: 'JetBrains Mono', monospace; color: var(--muted); padding: 8px 14px; border: 1px solid var(--border); background: var(--surface); border-radius: 8px; white-space: nowrap; }
.step-num { font-size: 0.65rem; background: var(--border); color: var(--muted); width: 18px; height: 18px; border-radius: 50%; display: flex; align-items: center; justify-content: center; }
.step-arrow { width: 28px; height: 1px; background: var(--border); }
.card-title { font-size: 0.7rem; font-family: 'JetBrains Mono', monospace; color: var(--muted); letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 1rem; padding-bottom: 0.75rem; border-bottom: 1px solid var(--border); }
button.primary { background: linear-gradient(135deg, var(--accent), var(--accent2)) !important; border: none !important; border-radius: 8px !important; font-family: 'Syne', sans-serif !important; font-weight: 600 !important; font-size: 0.95rem !important; padding: 0.75rem 2rem !important; }
button.secondary { background: var(--surface) !important; border: 1px solid var(--border) !important; color: var(--text) !important; border-radius: 8px !important; font-family: 'Syne', sans-serif !important; }
label { color: var(--muted) !important; font-size: 0.78rem !important; font-family: 'JetBrains Mono', monospace !important; letter-spacing: 0.05em !important; text-transform: uppercase !important; }
input, select, textarea { background: var(--bg) !important; border: 1px solid var(--border) !important; color: var(--text) !important; border-radius: 8px !important; font-family: 'Syne', sans-serif !important; }
input:focus, select:focus, textarea:focus { border-color: var(--accent) !important; box-shadow: 0 0 0 2px rgba(99,102,241,0.15) !important; outline: none !important; }
.gr-panel, .gr-block, .gr-box { background: transparent !important; border: none !important; }
::-webkit-scrollbar { width: 4px; } ::-webkit-scrollbar-track { background: var(--bg); } ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
"""

HEADER = """
<div class="rapidex-header">
  <div class="rapidex-logo">RAPIDEX IA</div>
  <div class="rapidex-tagline">Traduza videos. Conecte o mundo.</div>
  <div style="margin-top:12px;">
    <span class="gpu-badge">RUNPOD GPU</span>
    <span class="gpu-badge">CUDA</span>
    <span class="gpu-badge">v2.1</span>
  </div>
</div>
<div class="pipeline-bar">
  <div class="step"><span class="step-num">1</span>Video</div>
  <div class="step-arrow"></div>
  <div class="step"><span class="step-num">2</span>Audio</div>
  <div class="step-arrow"></div>
  <div class="step"><span class="step-num">3</span>Traducao</div>
  <div class="step-arrow"></div>
  <div class="step"><span class="step-num">4</span>Voz</div>
  <div class="step-arrow"></div>
  <div class="step"><span class="step-num">5</span>Lipsync</div>
</div>
"""

# ─────────────────────────────────────────
# INTERFACE
# ─────────────────────────────────────────

with gr.Blocks(title="RAPIDEX IA", css=CSS) as app:

    gr.HTML(HEADER)
    session_state = gr.State({})

    with gr.Row(equal_height=False):

        with gr.Column(scale=1):
            gr.HTML('<div class="card-title">01 - Video e Idiomas</div>')
            video_input = gr.Video(label="Video de entrada", sources=["upload"], height=240)
            source_lang = gr.Dropdown(choices=list(LANGUAGES.keys()), value="Detectar automaticamente", label="Idioma original")
            target_lang = gr.Dropdown(choices=[k for k in LANGUAGES if k != "Detectar automaticamente"], value="Portugues", label="Idioma de destino")
            transcribe_btn = gr.Button("TRANSCREVER E TRADUZIR", variant="secondary", size="lg")

        with gr.Column(scale=1):
            gr.HTML('<div class="card-title">02 - Revisar e Editar Texto</div>')
            original_out = gr.Textbox(label="Transcricao original", lines=5, interactive=False, placeholder="Texto original aparece aqui apos transcricao...")
            translated_out = gr.Textbox(label="Traducao - edite antes de dublar", lines=5, interactive=True, placeholder="Traducao aparece aqui. Edite a vontade antes de dublar...")
            status_out = gr.Textbox(label="Status", interactive=False, lines=1)

        with gr.Column(scale=1):
            gr.HTML('<div class="card-title">03 - Voz e Resultado</div>')
            ref_audio = gr.Audio(label="Audio de referencia para clonagem (opcional)", sources=["upload"], type="filepath")
            gr.HTML('<p style="font-size:0.78rem;color:var(--muted);margin:6px 0 14px;">Sem referencia: usa a voz original do video.</p>')
            use_lipsync = gr.Checkbox(label="Sincronizar labios (MuseTalk)", value=True)
            dub_btn = gr.Button("DUBLAR VIDEO", variant="primary", size="lg")
            video_out = gr.Video(label="Video dublado", height=230)

    transcribe_btn.click(fn=step_transcribe, inputs=[video_input, source_lang, target_lang, session_state], outputs=[original_out, translated_out, status_out, session_state], show_progress=True)
    dub_btn.click(fn=step_dub, inputs=[translated_out, use_lipsync, ref_audio, session_state], outputs=[video_out, status_out], show_progress=True)

# ─────────────────────────────────────────
# LAUNCH
# ─────────────────────────────────────────

if __name__ == "__main__":
    app.launch(server_name="0.0.0.0", server_port=7860, share=True, show_error=True)
