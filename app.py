import gradio as gr
import os
import subprocess
import tempfile
import shutil
import time

from pipeline.runtime import OUTPUTS_DIR
from pipeline.audio import extract_audio, mix_audio
from pipeline.separator import run_demucs
from pipeline.transcribe import run_whisperx
from pipeline.translate import translate_text
from pipeline.tts import run_fish_speech
from pipeline.lipsync import run_lipsync

# Sessão entre etapas
_S = {}

def step_transcribe(video, source_lang, target_lang, progress=gr.Progress(track_tqdm=True)):
    if video is None:
        raise gr.Error("Envie um vídeo.")
    src = LANGUAGES.get(source_lang, "auto")
    tgt = LANGUAGES.get(target_lang, "pt")
    tmp = tempfile.mkdtemp(prefix="rapidex_")
    _S.update({"tmp": tmp, "video": video, "src": src, "tgt": tgt})
    try:
        progress(0.10, desc="Extraindo áudio...")
        raw = extract_audio(video, tmp)
        progress(0.25, desc="Processando áudio...")
        vocals, bg = run_demucs(raw, tmp)
        _S["vocals"] = vocals
        _S["bg"]     = bg
        progress(0.55, desc="Transcrevendo...")
        original = run_whisperx(vocals, src)
        progress(0.80, desc="Traduzindo...")
        translated = translate_text(original, src, tgt)
        progress(1.00, desc="Pronto!")
        return original, translated, "✅ Transcrição concluída — edite o texto se quiser e clique em Dublar"
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        raise gr.Error(str(e))


def step_dub(translated_text, use_lipsync, ref_audio, progress=gr.Progress(track_tqdm=True)):
    if not translated_text or not translated_text.strip():
        raise gr.Error("Texto de tradução vazio.")
    if "tmp" not in _S:
        raise gr.Error("Faça a transcrição primeiro.")
    tmp, video, vocals, bg = _S["tmp"], _S["video"], _S["vocals"], _S["bg"]
    try:
        progress(0.15, desc="Gerando voz dublada...")
        ref = ref_audio if ref_audio else vocals
        dubbed = run_fish_speech(translated_text, ref, tmp)
        progress(0.40, desc="Mixando áudio...")
        mixed = mix_audio(dubbed, bg, tmp)
        if use_lipsync:
            progress(0.65, desc="Sincronizando lábios...")
            out = run_lipsync(video, mixed, tmp)
        else:
            progress(0.65, desc="Exportando vídeo...")
            out = os.path.join(tmp, "rapidex_output.mp4")
            subprocess.run([
                "ffmpeg", "-y", "-i", video, "-i", mixed,
                "-c:v", "copy", "-map", "0:v:0", "-map", "1:a:0", "-shortest", out
            ], check=True, capture_output=True)
        progress(0.95, desc="Finalizando...")
        final = os.path.join(OUTPUTS_DIR, f"output_{int(time.time())}.mp4")
        shutil.copy(out, final)
        return out, "✅ Dublagem concluída!"
    except Exception as e:
        raise gr.Error(str(e))


# ─────────────────────────────────────────
#  IDIOMAS
# ─────────────────────────────────────────

LANGUAGES = {
    "Detectar automaticamente": "auto",
    "Português": "pt", "Inglês": "en", "Espanhol": "es",
    "Francês": "fr", "Alemão": "de", "Italiano": "it",
    "Japonês": "ja", "Coreano": "ko", "Chinês": "zh",
    "Árabe": "ar", "Russo": "ru", "Hindi": "hi",
    "Turco": "tr", "Holandês": "nl", "Polonês": "pl",
}

# ─────────────────────────────────────────
#  CSS
# ─────────────────────────────────────────

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --bg:      #020409;
  --surface: #0b0f1a;
  --border:  #1a2035;
  --accent:  #6366f1;
  --accent2: #a855f7;
  --accent3: #ec4899;
  --text:    #e2e8f0;
  --muted:   #64748b;
  --success: #10b981;
  --radius:  12px;
}

* { box-sizing: border-box; }

body, .gradio-container {
  background: var(--bg) !important;
  font-family: 'Syne', sans-serif !important;
  color: var(--text) !important;
}

.rapidex-header {
  padding: 2rem 0 1.5rem;
  text-align: center;
  border-bottom: 1px solid var(--border);
  margin-bottom: 2rem;
  background: linear-gradient(180deg, #0d1025 0%, transparent 100%);
}
.rapidex-logo {
  font-size: 2.4rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  background: linear-gradient(135deg, var(--accent), var(--accent2), var(--accent3));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.rapidex-tagline {
  font-size: 0.85rem;
  color: var(--muted);
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.08em;
  margin-top: 4px;
}
.gpu-badge {
  display: inline-block;
  font-size: 0.7rem;
  font-family: 'JetBrains Mono', monospace;
  background: rgba(99,102,241,0.12);
  color: var(--accent);
  border: 1px solid rgba(99,102,241,0.3);
  padding: 3px 10px;
  border-radius: 20px;
  margin: 0 4px;
}

.pipeline-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  margin-bottom: 2rem;
  padding: 0 1rem;
}
.step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.72rem;
  font-family: 'JetBrains Mono', monospace;
  color: var(--muted);
  padding: 8px 14px;
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 8px;
  white-space: nowrap;
}
.step-num {
  font-size: 0.65rem;
  background: var(--border);
  color: var(--muted);
  width: 18px; height: 18px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
}
.step-arrow { width: 28px; height: 1px; background: var(--border); }

.card-title {
  font-size: 0.7rem;
  font-family: 'JetBrains Mono', monospace;
  color: var(--muted);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  margin-bottom: 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--border);
}

button.primary { 
  background: linear-gradient(135deg, var(--accent), var(--accent2)) !important;
  border: none !important; border-radius: 8px !important;
  font-family: 'Syne', sans-serif !important;
  font-weight: 600 !important; font-size: 0.95rem !important;
  padding: 0.75rem 2rem !important;
}
button.secondary {
  background: var(--surface) !important;
  border: 1px solid var(--border) !important;
  color: var(--text) !important; border-radius: 8px !important;
  font-family: 'Syne', sans-serif !important;
}

label {
  color: var(--muted) !important;
  font-size: 0.78rem !important;
  font-family: 'JetBrains Mono', monospace !important;
  letter-spacing: 0.05em !important;
  text-transform: uppercase !important;
}

input, select, textarea {
  background: var(--bg) !important;
  border: 1px solid var(--border) !important;
  color: var(--text) !important;
  border-radius: 8px !important;
  font-family: 'Syne', sans-serif !important;
}
input:focus, select:focus, textarea:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 2px rgba(99,102,241,0.15) !important;
  outline: none !important;
}

.gr-panel, .gr-block, .gr-box { background: transparent !important; border: none !important; }

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
"""

HEADER = """
<div class="rapidex-header">
  <div class="rapidex-logo">⚡ RAPIDEX IA</div>
  <div class="rapidex-tagline">Traduza vídeos. Conecte o mundo.</div>
  <div style="margin-top:12px;">
    <span class="gpu-badge">RUNPOD GPU</span>
    <span class="gpu-badge">CUDA</span>
    <span class="gpu-badge">v2.0</span>
  </div>
</div>
<div class="pipeline-bar">
  <div class="step"><span class="step-num">1</span>Vídeo</div>
  <div class="step-arrow"></div>
  <div class="step"><span class="step-num">2</span>Áudio</div>
  <div class="step-arrow"></div>
  <div class="step"><span class="step-num">3</span>Tradução</div>
  <div class="step-arrow"></div>
  <div class="step"><span class="step-num">4</span>Voz</div>
  <div class="step-arrow"></div>
  <div class="step"><span class="step-num">5</span>Lipsync</div>
</div>
"""

# ─────────────────────────────────────────
#  INTERFACE
# ─────────────────────────────────────────

with gr.Blocks(title="RAPIDEX IA") as app:
    gr.HTML(HEADER)

    with gr.Row(equal_height=False):

        # ── Coluna 1: Vídeo & Idiomas
        with gr.Column(scale=1):
            gr.HTML('<div class="card-title">01 — Vídeo & Idiomas</div>')
            video_input = gr.Video(label="Vídeo de entrada", sources=["upload"], height=240)
            source_lang = gr.Dropdown(
                choices=list(LANGUAGES.keys()),
                value="Detectar automaticamente",
                label="Idioma original"
            )
            target_lang = gr.Dropdown(
                choices=[k for k in LANGUAGES if k != "Detectar automaticamente"],
                value="Português",
                label="Idioma de destino"
            )
            transcribe_btn = gr.Button("🔍  TRANSCREVER & TRADUZIR", variant="secondary", size="lg")

        # ── Coluna 2: Editar texto
        with gr.Column(scale=1):
            gr.HTML('<div class="card-title">02 — Revisar & Editar Texto</div>')
            original_out = gr.Textbox(
                label="Transcrição original",
                lines=5, interactive=False,
                placeholder="Texto original aparece aqui após transcrição..."
            )
            translated_out = gr.Textbox(
                label="Tradução — edite antes de dublar",
                lines=5, interactive=True,
                placeholder="Tradução aparece aqui. Edite à vontade antes de dublar..."
            )
            status_out = gr.Textbox(label="Status", interactive=False, lines=1)

        # ── Coluna 3: Voz + Resultado
        with gr.Column(scale=1):
            gr.HTML('<div class="card-title">03 — Voz & Resultado</div>')
            ref_audio = gr.Audio(
                label="Áudio de referência para clonagem (opcional)",
                sources=["upload"], type="filepath"
            )
            gr.HTML('<p style="font-size:0.78rem;color:var(--muted);margin:6px 0 14px;">Sem referência: usa a voz original do vídeo.</p>')
            use_lipsync = gr.Checkbox(label="Sincronizar lábios (MuseTalk)", value=True)
            dub_btn     = gr.Button("▶  DUBLAR VÍDEO", variant="primary", size="lg")
            video_out   = gr.Video(label="Vídeo dublado", height=230)

    transcribe_btn.click(
        fn=step_transcribe,
        inputs=[video_input, source_lang, target_lang],
        outputs=[original_out, translated_out, status_out],
        show_progress=True
    )
    dub_btn.click(
        fn=step_dub,
        inputs=[translated_out, use_lipsync, ref_audio],
        outputs=[video_out, status_out],
        show_progress=True
    )

# ─────────────────────────────────────────
#  LAUNCH
# ─────────────────────────────────────────
if __name__ == "__main__":
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=True,
        show_error=True,
        css=CSS
    )
