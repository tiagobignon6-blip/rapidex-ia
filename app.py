"""
RAPIDEX IA - app.py v3.3
Interface Gradio com fluxo SEQUENCIAL e APROVACAO MANUAL.

Etapas:
  1. Upload video
  2. Transcrever + traduzir
  3. Editar texto manualmente
  4. Gerar audio (preview)
  5. Ouvir preview
  6. Aprovar manualmente -> lipsync + render final
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

run_fish_speech = run_tts  # alias para compatibilidade com notebook

# Pre-carrega WhisperX em background (nao bloqueia o boot da UI)
threading.Thread(target=ModelManager.preload, daemon=True).start()


def health_html():
    """Badge de status do modelo (atualizado a cada 4s pelo Timer)."""
    status = ModelManager.status()
    if status == "ready":
        color, label = "#10b981", f"WHISPERX {WHISPER_SIZE} READY"
    elif status == "loading":
        color, label = "#f59e0b", f"WHISPERX {WHISPER_SIZE} CARREGANDO..."
    elif status == "idle":
        color, label = "#64748b", "WHISPERX OCIOSO"
    else:
        color, label = "#ef4444", "WHISPERX FALHOU"
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


def _get_audio_duration(path):
    """Retorna duracao em segundos. Tenta varias estrategias do ffprobe."""
    queries = [
        # 1. Container format duration
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        # 2. Primeiro stream de audio
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        # 3. Primeiro stream de video
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
    ]
    for cmd in queries:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                raw = r.stdout.strip()
                if raw and raw.lower() != "n/a":
                    try:
                        d = float(raw)
                        if d > 0:
                            return d
                    except ValueError:
                        pass
        except Exception:
            continue
    return 0.0


def _validate_audio(path, min_size=2_000, min_duration=0.5):
    """Audio: existe + tamanho + duracao. Duracao e estrita pra audio."""
    if not path or not os.path.exists(path):
        return False, "arquivo nao existe"
    size = os.path.getsize(path)
    if size < min_size:
        return False, f"arquivo muito pequeno ({size} bytes)"
    duration = _get_audio_duration(path)
    if duration < min_duration:
        return False, f"duracao invalida ({duration:.2f}s)"
    return True, f"{duration:.1f}s"


def _validate_video(path, min_size=5_000, min_duration=0.5):
    """Video: existe + tamanho. Duracao e best-effort - se ffprobe nao detectar,
    aceita mesmo assim (alguns formatos so revelam duracao apos demuxing completo).
    Se for arquivo realmente quebrado, extract_audio vai falhar com mensagem clara.
    """
    if not path or not os.path.exists(path):
        return False, "arquivo nao existe"
    size = os.path.getsize(path)
    if size < min_size:
        return False, f"arquivo muito pequeno ({size} bytes)"
    duration = _get_audio_duration(path)
    if duration <= 0:
        log.warning(f"ffprobe nao conseguiu detectar duracao de {path} (size={size}) - prosseguindo, extract_audio validara")
        return True, f"{size//1024}KB"
    if duration < min_duration:
        return False, f"duracao muito curta ({duration:.2f}s)"
    return True, f"{duration:.1f}s"




# ─────────────────────────────────────────
# ETAPA 1+2+3 - TRANSCREVER E TRADUZIR
# ─────────────────────────────────────────

def step_transcribe(video, source_lang, target_lang, session_state, progress=gr.Progress(track_tqdm=True)):
    if not video:
        raise gr.Error("Envie um video.")

    ok, msg = _validate_video(video)
    if not ok:
        raise gr.Error(f"Video invalido: {msg}")

    src = LANGUAGES.get(source_lang, "auto")
    tgt = LANGUAGES.get(target_lang, "pt")

    # Limpa qualquer sessao anterior
    if session_state and session_state.get("tmp"):
        cleanup_tmp(session_state["tmp"])

    tmp = tempfile.mkdtemp(prefix="rapidex_")
    new_state = {
        "tmp": tmp,
        "video": video,
        "src": src,
        "tgt": tgt,
        "approved": False,
        "audio_preview": None,
    }

    try:
        progress(0.10, desc="Extraindo audio...")
        raw_16k, demucs_in = extract_audio(video, tmp)

        progress(0.25, desc="Separando voz e musica...")
        vocals, bg = run_demucs(raw_16k, tmp, demucs_input=demucs_in)
        new_state["vocals"] = vocals
        new_state["bg"] = bg

        # Valida que demucs gerou audio aproveitavel
        ok, msg = _validate_audio(vocals, min_size=1_000, min_duration=0.3)
        if not ok:
            raise gr.Error(f"Falha ao isolar voz: {msg}")

        progress(0.55, desc="Transcrevendo com WhisperX...")
        original, detected_lang = run_whisperx(vocals, src)
        new_state["detected_lang"] = detected_lang

        progress(0.80, desc="Traduzindo...")
        actual_src = detected_lang if src == "auto" else src
        translated = translate_text(original, actual_src, tgt)

        progress(1.00, desc="Pronto!")
        return (
            original,
            translated,
            f"Transcricao OK ({detected_lang} -> {tgt}). Edite o texto e gere o audio.",
            new_state,
        )

    except gr.Error:
        cleanup_tmp(tmp)
        raise
    except Exception as e:
        cleanup_tmp(tmp)
        log.exception("step_transcribe falhou")
        raise gr.Error(f"Falha na transcricao: {e}")


# ─────────────────────────────────────────
# ETAPA 4+5 - GERAR AUDIO (PREVIEW)
# ─────────────────────────────────────────

def step_generate_audio(translated_text, ref_audio, session_state, progress=gr.Progress(track_tqdm=True)):
    if not translated_text or not translated_text.strip():
        raise gr.Error("Texto vazio. Faca a transcricao primeiro ou digite o texto.")
    if not session_state or not session_state.get("tmp"):
        raise gr.Error("Faca a transcricao primeiro (etapa 1).")

    tmp = session_state["tmp"]
    vocals = session_state.get("vocals")
    bg = session_state.get("bg")
    tgt = session_state.get("tgt", "pt")

    if not vocals or not os.path.exists(vocals):
        raise gr.Error("Audio da transcricao perdido. Refaca a etapa 1.")

    try:
        progress(0.20, desc="Gerando voz dublada...")
        ref = ref_audio if (ref_audio and os.path.exists(ref_audio)) else vocals
        dubbed = run_tts(translated_text, ref, tmp, tgt_lang=tgt)

        progress(0.60, desc="Mixando com fundo musical...")
        mixed = mix_audio(dubbed, bg, tmp)

        # Validacoes
        ok, info = _validate_audio(mixed)
        if not ok:
            raise RuntimeError(f"Audio gerado invalido: {info}")

        progress(1.00, desc="Audio pronto - escute o preview")

        # Persiste o preview pra etapa de aprovacao
        session_state["audio_preview"] = mixed
        session_state["dubbed_voice"] = dubbed
        session_state["approved"] = False
        session_state["translated_text"] = translated_text  # preserva texto editado

        return (
            mixed,
            f"Audio gerado ({info}). Ouca o preview e clique em DUBLAR VIDEO.",
            session_state,
        )

    except gr.Error:
        raise
    except Exception as e:
        log.exception("step_generate_audio falhou")
        raise gr.Error(f"Falha ao gerar audio: {e}")


# ─────────────────────────────────────────
# ETAPA 6 - APROVAR
# ─────────────────────────────────────────

def step_approve(session_state):
    """Marca aprovacao manual. Habilita o botao de lipsync."""
    if not session_state or not session_state.get("audio_preview"):
        raise gr.Error("Gere o audio primeiro (etapa 2).")
    ok, info = _validate_audio(session_state["audio_preview"])
    if not ok:
        raise gr.Error(f"Audio invalido para aprovar: {info}")

    session_state["approved"] = True
    return (
        session_state,
        "Audio APROVADO. Agora clique em DUBLAR VIDEO para gerar o video final com lipsync.",
        gr.update(interactive=True),  # habilita botao de render
    )


# ─────────────────────────────────────────
# ETAPA 7+8+9 - LIPSYNC + RENDER FINAL
# ─────────────────────────────────────────

def step_render(use_lipsync, session_state, progress=gr.Progress(track_tqdm=True)):
    """Renderiza o video final. Requer audio gerado em step_generate_audio.
    Aprovacao manual: implicita ao clicar em DUBLAR VIDEO (UX simplificada)."""
    if not session_state or not session_state.get("audio_preview"):
        raise gr.Error("Gere o audio primeiro (clique em GERAR AUDIO).")

    tmp = session_state["tmp"]
    video = session_state["video"]
    mixed = session_state.get("audio_preview")

    if not mixed or not os.path.exists(mixed):
        raise gr.Error("Audio aprovado nao encontrado. Refaca a etapa 2.")
    if not video or not os.path.exists(video):
        raise gr.Error("Video original nao encontrado. Refaca a etapa 1.")

    try:
        if use_lipsync:
            progress(0.30, desc="Sincronizando labios... (pode demorar varios minutos)")
            out = run_lipsync(video, mixed, tmp)
        else:
            progress(0.30, desc="Exportando video sem lipsync...")
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

        # Valida resultado final
        ok, info = _validate_video(out)
        if not ok:
            raise RuntimeError(f"Video final invalido: {info}")

        progress(0.95, desc="Finalizando...")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        final = str(OUTPUT_DIR / f"rapidex_{int(time.time())}.mp4")
        shutil.copy(out, final)

        # Preserva o video gerado, limpa apenas o tmp
        cleanup_tmp(tmp)
        session_state["tmp"] = None

        return final, f"Render final OK ({info})!"

    except gr.Error:
        raise
    except Exception as e:
        log.exception("step_render falhou")
        raise gr.Error(f"Falha no render final: {e}")


# Compatibilidade com versoes antigas que chamavam step_dub
def step_dub(translated_text, use_lipsync, ref_audio, session_state, progress=gr.Progress(track_tqdm=True)):
    """Compat: faz generate_audio + approve + render numa unica chamada."""
    audio, _, session_state = step_generate_audio(translated_text, ref_audio, session_state, progress)
    session_state["approved"] = True
    final, status = step_render(use_lipsync, session_state, progress)
    return final, status


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
button.success { background: linear-gradient(135deg, #10b981, #059669) !important; border: none !important; color: white !important; }
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
    <span class="gpu-badge">v3.3</span>
  </div>
</div>
<div class="pipeline-bar">
  <div class="step"><span class="step-num">1</span>Upload</div>
  <div class="step-arrow"></div>
  <div class="step"><span class="step-num">2</span>Transcrever</div>
  <div class="step-arrow"></div>
  <div class="step"><span class="step-num">3</span>Editar</div>
  <div class="step-arrow"></div>
  <div class="step"><span class="step-num">4</span>Gerar Audio</div>
  <div class="step-arrow"></div>
  <div class="step"><span class="step-num">5</span>Aprovar</div>
  <div class="step-arrow"></div>
  <div class="step"><span class="step-num">6</span>Render</div>
</div>
"""

# ─────────────────────────────────────────
# INTERFACE
# ─────────────────────────────────────────

# Gradio 4.x aceita css no Blocks; 6.x exige no launch.
# Passamos nos dois, compativel com ambas as versoes.
try:
    _BLOCKS_KWARGS = {"title": "RAPIDEX IA", "css": CSS}
    _probe = gr.Blocks(**_BLOCKS_KWARGS)
    del _probe
except TypeError:
    _BLOCKS_KWARGS = {"title": "RAPIDEX IA"}

with gr.Blocks(**_BLOCKS_KWARGS) as app:

    gr.HTML(HEADER)
    health_badge = gr.HTML(health_html())
    session_state = gr.State({})

    # Atualizacao do badge a cada 4s (gr.Timer existe a partir do gradio 4.36+)
    try:
        _timer = gr.Timer(value=4)
        _timer.tick(fn=health_html, outputs=[health_badge])
    except (AttributeError, TypeError):
        pass

    # ── ETAPA 1: Upload + Transcricao ─────────────────────────────────────────
    with gr.Row(equal_height=False):

        with gr.Column(scale=1):
            gr.HTML('<div class="card-title">01 - Video e Idiomas</div>')
            video_input = gr.Video(label="Video de entrada", sources=["upload"], height=240)
            source_lang = gr.Dropdown(
                choices=list(LANGUAGES.keys()),
                value="Detectar automaticamente",
                label="Idioma original",
            )
            target_lang = gr.Dropdown(
                choices=[k for k in LANGUAGES if k != "Detectar automaticamente"],
                value="Portugues",
                label="Idioma de destino",
            )
            transcribe_btn = gr.Button("TRANSCREVER E TRADUZIR", variant="secondary", size="lg")

        # ── ETAPA 2+3: Editar Texto ───────────────────────────────────────────
        with gr.Column(scale=1):
            gr.HTML('<div class="card-title">02 - Revisar e Editar Texto</div>')
            original_out = gr.Textbox(
                label="Transcricao original",
                lines=5,
                interactive=False,
                placeholder="Texto original aparece aqui apos transcricao...",
            )
            translated_out = gr.Textbox(
                label="Traducao - edite a vontade",
                lines=5,
                interactive=True,
                placeholder="Traducao aparece aqui. Edite antes de gerar o audio...",
            )
            transcribe_status = gr.Textbox(label="Status da transcricao", interactive=False, lines=1)

        # ── ETAPA 4+5: Gerar e Ouvir Audio ────────────────────────────────────
        with gr.Column(scale=1):
            gr.HTML('<div class="card-title">03 - Gerar e Ouvir Audio</div>')
            ref_audio = gr.Audio(
                label="Audio de referencia para clonagem (opcional)",
                sources=["upload"],
                type="filepath",
            )
            gr.HTML('<p style="font-size:0.72rem;color:var(--muted);margin:4px 0 12px;">Sem referencia: usa a voz original do video.</p>')
            generate_btn = gr.Button("GERAR AUDIO (PREVIEW)", variant="secondary", size="lg")
            audio_preview = gr.Audio(
                label="Preview do audio dublado",
                type="filepath",
                interactive=False,
            )
            generate_status = gr.Textbox(label="Status do audio", interactive=False, lines=1)

    # ── ETAPA 5: Render Final ─────────────────────────────────────────────────
    with gr.Row():
        with gr.Column(scale=2):
            gr.HTML('<div class="card-title">04 - Renderizar Video Final</div>')
            with gr.Row():
                use_lipsync = gr.Checkbox(label="Sincronizar labios (LatentSync/Wav2Lip)", value=True)
                render_btn = gr.Button("DUBLAR VIDEO", variant="primary", size="lg")
            render_status = gr.Textbox(label="Status do render", interactive=False, lines=1)
            video_out = gr.Video(label="Video final dublado", height=320)

    # ── WIRING ────────────────────────────────────────────────────────────────

    transcribe_btn.click(
        fn=step_transcribe,
        inputs=[video_input, source_lang, target_lang, session_state],
        outputs=[original_out, translated_out, transcribe_status, session_state],
        show_progress=True,
    )

    generate_btn.click(
        fn=step_generate_audio,
        inputs=[translated_out, ref_audio, session_state],
        outputs=[audio_preview, generate_status, session_state],
        show_progress=True,
    )

    render_btn.click(
        fn=step_render,
        inputs=[use_lipsync, session_state],
        outputs=[video_out, render_status],
        show_progress=True,
    )

# ─────────────────────────────────────────
# LAUNCH
# ─────────────────────────────────────────

if __name__ == "__main__":
    launch_kwargs = dict(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("GRADIO_PORT", 7860)),
        share=True,
        show_error=True,
    )
    # Em Gradio 6+, css/title vao no launch()
    import inspect
    sig = inspect.signature(app.launch)
    if "css" in sig.parameters:
        launch_kwargs["css"] = CSS
    if "title" in sig.parameters:
        launch_kwargs["title"] = "RAPIDEX IA"
    app.queue(default_concurrency_limit=1).launch(**launch_kwargs)
