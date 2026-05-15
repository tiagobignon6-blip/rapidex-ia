"""
RAPIDEX IA - app.py v3.2
Interface Gradio. Toda a logica vive em pipeline.py.
"""

import os
import sys
import tempfile
import shutil
import time
import logging
import threading
import subprocess

import gradio as gr

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("rapidex")

# ─────────────────────────────────────────
# IMPORTA PIPELINE (resiliente em qualquer CWD - colab, runpod, local)
# ─────────────────────────────────────────

def _add_pipeline_path():
    candidates = []
    if "__file__" in globals():
        candidates.append(os.path.dirname(os.path.abspath(__file__)))
    candidates.extend([
        os.getcwd(),
        os.path.join(os.getcwd(), "rapidex-ia"),
        "/workspace",
        "/workspace/rapidex-ia",
        "/content/rapidex-ia",
    ])
    for c in candidates:
        if c and os.path.isfile(os.path.join(c, "pipeline.py")):
            if c not in sys.path:
                sys.path.insert(0, c)
            return c
    return None

_add_pipeline_path()

from pipeline import (  # noqa: E402
    LANGUAGES,
    ModelManager,
    extract_audio,
    run_demucs,
    run_whisperx,
    translate_text,
    run_tts,
    mix_audio,
    run_lipsync,
    cleanup as cleanup_tmp,
    OUTPUT_DIR,
    DEVICE,
    WHISPER_SIZE,
)

# Apelidos para compatibilidade com notebook de teste
run_fish_speech = run_tts

# Pre-carrega WhisperX em background (nao bloqueia o boot da UI)
threading.Thread(target=ModelManager.preload, daemon=True).start()


def health_html():
    """Renderiza badge de status do modelo (HTML pequeno, atualizado periodicamente)."""
    status = ModelManager.status()
    if status == "ready":
        color, label = "#10b981", f"WHISPERX {WHISPER_SIZE} READY"
    elif status == "loading":
        color, label = "#f59e0b", f"WHISPERX {WHISPER_SIZE} CARREGANDO..."
    elif status == "idle":
        color, label = "#64748b", "WHISPERX OCIOSO"
    else:
        color, label = "#ef4444", f"WHISPERX FALHOU"
    device_label = "GPU" if DEVICE == "cuda" else "CPU"
    return (
        f'<div style="display:flex;gap:8px;justify-content:center;align-items:center;'
        f'font-family:JetBrains Mono,monospace;font-size:0.7rem;margin:8px 0;flex-wrap:wrap;">'
        f'<span style="padding:3px 10px;border-radius:20px;'
        f'background:rgba(99,102,241,0.12);color:#6366f1;'
        f'border:1px solid rgba(99,102,241,0.3);">{device_label}</span>'
        f'<span style="padding:3px 10px;border-radius:20px;'
        f'background:{color}22;color:{color};border:1px solid {color}55;">{label}</span>'
        f'</div>'
    )

# ─────────────────────────────────────────
# STEP FUNCTIONS (com gr.State - thread-safe)
# ─────────────────────────────────────────

def step_transcribe(video, source_lang, target_lang, session_state, progress=gr.Progress(track_tqdm=True)):
    if not video:
        raise gr.Error("Envie um video.")

    src = LANGUAGES.get(source_lang, "auto")
    tgt = LANGUAGES.get(target_lang, "pt")

    # Limpa qualquer sessao anterior antes de comecar
    if session_state and session_state.get("tmp"):
        cleanup_tmp(session_state["tmp"])

    tmp = tempfile.mkdtemp(prefix="rapidex_")
    new_state = {"tmp": tmp, "video": video, "src": src, "tgt": tgt}

    try:
        progress(0.10, desc="Extraindo audio...")
        raw_16k, demucs_in = extract_audio(video, tmp)

        progress(0.25, desc="Separando voz e musica...")
        vocals, bg = run_demucs(raw_16k, tmp, demucs_input=demucs_in)
        new_state["vocals"] = vocals
        new_state["bg"] = bg

        progress(0.55, desc="Transcrevendo com WhisperX...")
        original, detected_lang = run_whisperx(vocals, src)
        new_state["detected_lang"] = detected_lang

        progress(0.80, desc="Traduzindo...")
        actual_src = detected_lang if src == "auto" else src
        translated = translate_text(original, actual_src, tgt)

        progress(1.00, desc="Pronto!")
        return original, translated, f"Transcricao OK ({detected_lang} -> {tgt}). Edite e clique em Dublar.", new_state

    except gr.Error:
        cleanup_tmp(tmp)
        raise
    except Exception as e:
        cleanup_tmp(tmp)
        log.exception("step_transcribe falhou")
        raise gr.Error(f"Falha na transcricao: {e}")


def step_dub(translated_text, use_lipsync, ref_audio, session_state, progress=gr.Progress(track_tqdm=True)):
    if not translated_text or not translated_text.strip():
        raise gr.Error("Texto de traducao vazio.")
    if not session_state or "tmp" not in session_state or not session_state.get("tmp"):
        raise gr.Error("Faca a transcricao primeiro.")

    tmp = session_state["tmp"]
    video = session_state["video"]
    vocals = session_state.get("vocals")
    bg = session_state.get("bg")
    tgt = session_state.get("tgt", "pt")

    if not vocals or not os.path.exists(vocals):
        raise gr.Error("Audio da etapa de transcricao perdido. Refaca a transcricao.")

    try:
        progress(0.15, desc="Gerando voz dublada...")
        ref = ref_audio if (ref_audio and os.path.exists(ref_audio)) else vocals
        dubbed = run_tts(translated_text, ref, tmp, tgt_lang=tgt)

        progress(0.40, desc="Mixando audio...")
        mixed = mix_audio(dubbed, bg, tmp)

        if use_lipsync:
            progress(0.65, desc="Sincronizando labios...")
            out = run_lipsync(video, mixed, tmp)
        else:
            progress(0.65, desc="Exportando video...")
            out = os.path.join(tmp, "rapidex_output.mp4")
            r = subprocess.run(
                ["ffmpeg", "-y", "-i", video, "-i", mixed,
                 "-c:v", "copy", "-map", "0:v:0", "-map", "1:a:0", "-shortest", out],
                capture_output=True, text=True, timeout=300,
            )
            if r.returncode != 0 or not os.path.exists(out):
                # Fallback re-encoda se codec for incompativel
                r = subprocess.run(
                    ["ffmpeg", "-y", "-i", video, "-i", mixed,
                     "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                     "-map", "0:v:0", "-map", "1:a:0", "-shortest", out],
                    capture_output=True, text=True, timeout=600,
                )
                if r.returncode != 0 or not os.path.exists(out):
                    raise RuntimeError(f"FFmpeg export falhou:\n{r.stderr[-400:]}")

        progress(0.95, desc="Finalizando...")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        final = str(OUTPUT_DIR / f"rapidex_{int(time.time())}.mp4")
        shutil.copy(out, final)

        # Mantem video final, limpa o temp
        cleanup_tmp(tmp)
        session_state["tmp"] = None

        return final, "Dublagem concluida!"

    except gr.Error:
        raise
    except Exception as e:
        log.exception("step_dub falhou")
        raise gr.Error(f"Falha na dublagem: {e}")


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
.pipeline-bar { display: flex; align-items: center; justify-content: center; gap: 0; margin-bottom: 2rem; padding: 0 1rem; flex-wrap: wrap; }
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
    <span class="gpu-badge">v3.2</span>
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
    health_badge = gr.HTML(health_html())
    session_state = gr.State({})

    # Atualiza badge a cada 4s. gr.Timer existe a partir do gradio 4.36+
    try:
        _timer = gr.Timer(value=4)
        _timer.tick(fn=health_html, outputs=[health_badge])
    except (AttributeError, TypeError):
        pass  # Gradio antigo - badge nao atualiza dinamicamente

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

    transcribe_btn.click(
        fn=step_transcribe,
        inputs=[video_input, source_lang, target_lang, session_state],
        outputs=[original_out, translated_out, status_out, session_state],
        show_progress=True,
    )
    dub_btn.click(
        fn=step_dub,
        inputs=[translated_out, use_lipsync, ref_audio, session_state],
        outputs=[video_out, status_out],
        show_progress=True,
    )

# ─────────────────────────────────────────
# LAUNCH
# ─────────────────────────────────────────

if __name__ == "__main__":
    app.queue(default_concurrency_limit=1).launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("GRADIO_PORT", 7860)),
        share=True,
        show_error=True,
    )
