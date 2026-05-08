import gradio as gr
import os
import subprocess
import tempfile
import shutil
import time
import json

# ─────────────────────────────────────────
#  PIPELINE FUNCTIONS
# ─────────────────────────────────────────

def extract_audio(video_path: str, out_dir: str) -> str:
    """Extrai áudio do vídeo em WAV 16kHz mono."""
    raw_audio = os.path.join(out_dir, "raw_audio.wav")
    subprocess.run([
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000",
        "-sample_fmt", "s16", raw_audio
    ], check=True, capture_output=True)
    return raw_audio


def run_demucs(raw_audio: str, out_dir: str):
    """
    Separa vocals e fundo com Demucs (htdemucs).
    Retorna (vocals_path, background_path).
    """
    demucs_out = os.path.join(out_dir, "demucs")
    subprocess.run([
        "python", "-m", "demucs",
        "--two-stems=vocals",
        "-o", demucs_out,
        raw_audio
    ], check=True, capture_output=True)

    # Demucs cria: demucs/htdemucs/<nome_arquivo>/vocals.wav e no_vocals.wav
    stem_dir = None
    for root, dirs, files in os.walk(demucs_out):
        if "vocals.wav" in files:
            stem_dir = root
            break

    if stem_dir is None:
        raise RuntimeError("Demucs não gerou vocals.wav")

    vocals  = os.path.join(stem_dir, "vocals.wav")
    bgmusic = os.path.join(stem_dir, "no_vocals.wav")
    return vocals, bgmusic


def run_whisperx(vocals_path: str, source_lang: str) -> dict:
    """
    Transcreve com WhisperX (large-v3 + VAD).
    Retorna dict com 'text' e 'segments'.
    """
    import whisperx
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute = "float16" if device == "cuda" else "int8"

    model = whisperx.load_model(
        "large-v3", device, compute_type=compute,
        language=source_lang if source_lang != "auto" else None
    )

    audio = whisperx.load_audio(vocals_path)
    result = model.transcribe(audio, batch_size=16)

    # Alinhamento de palavras
    try:
        lang_code = result.get("language", source_lang)
        align_model, metadata = whisperx.load_align_model(
            language_code=lang_code, device=device
        )
        result = whisperx.align(
            result["segments"], align_model, metadata, audio, device
        )
    except Exception:
        pass  # alinhamento é opcional

    full_text = " ".join(s["text"].strip() for s in result["segments"])
    return {"text": full_text, "segments": result["segments"]}


def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """Traduz com deep-translator (Google)."""
    from deep_translator import GoogleTranslator
    # Google usa códigos ISO 639-1
    translated = GoogleTranslator(
        source=source_lang if source_lang != "auto" else "auto",
        target=target_lang
    ).translate(text)
    return translated


def run_fish_speech(text: str, ref_wav: str, out_dir: str) -> str:
    """
    Gera voz com Fish Speech V1.5 clonando o ref_wav.
    Retorna caminho do dubbed_voice.wav gerado.
    """
    dubbed_path = os.path.join(out_dir, "dubbed_voice.wav")

    # Fish Speech CLI
    cmd = [
        "python", "-m", "fish_speech.inference",
        "--text", text,
        "--reference-audio", ref_wav,
        "--output", dubbed_path,
        "--device", "cuda"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if not os.path.exists(dubbed_path):
        raise RuntimeError(
            f"Fish Speech falhou.\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
    return dubbed_path


def mix_audio(dubbed_voice: str, bgmusic: str, out_dir: str) -> str:
    """
    Mistura voz dublada + música de fundo original.
    A voz fica em destaque (volume pleno), fundo levemente reduzido.
    """
    mixed_path = os.path.join(out_dir, "mixed_audio.wav")
    subprocess.run([
        "ffmpeg", "-y",
        "-i", dubbed_voice,
        "-i", bgmusic,
        "-filter_complex",
        "[0:a]volume=1.0[voice];[1:a]volume=0.35[bg];[voice][bg]amix=inputs=2:duration=longest[out]",
        "-map", "[out]",
        mixed_path
    ], check=True, capture_output=True)
    return mixed_path


def run_musetalk(video_path: str, audio_path: str, out_dir: str) -> str:
    """
    Roda MuseTalk para sincronizar os lábios com o áudio dublado.
    """
    output_video = os.path.join(out_dir, "rapidex_output.mp4")

    musetalk_dir = "/workspace/MuseTalk"
    cmd = [
        "python", f"{musetalk_dir}/scripts/inference.py",
        "--video_path", video_path,
        "--audio_path", audio_path,
        "--output_path", output_video,
        "--bbox_shift", "0"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=musetalk_dir)

    if not os.path.exists(output_video):
        # fallback para Wav2Lip se MuseTalk não estiver instalado
        output_video = run_wav2lip_fallback(video_path, audio_path, out_dir)

    return output_video


def run_wav2lip_fallback(video_path: str, audio_path: str, out_dir: str) -> str:
    """Fallback: Wav2Lip caso MuseTalk não esteja instalado."""
    output_video = os.path.join(out_dir, "rapidex_output.mp4")
    wav2lip_dir = "/workspace/Wav2Lip"
    checkpoint = f"{wav2lip_dir}/checkpoints/wav2lip_gan.pth"

    subprocess.run([
        "python", f"{wav2lip_dir}/inference.py",
        "--checkpoint_path", checkpoint,
        "--face", video_path,
        "--audio", audio_path,
        "--outfile", output_video,
        "--pads", "0", "10", "0", "0",
        "--resize_factor", "1"
    ], check=True, capture_output=True, cwd=wav2lip_dir)

    return output_video


def run_pipeline(
    video,
    source_lang,
    target_lang,
    use_lipsync,
    ref_audio,
    progress=gr.Progress(track_tqdm=True)
):
    if video is None:
        raise gr.Error("Envie um vídeo para continuar.")

    tmp = tempfile.mkdtemp(prefix="rapidex_")
    try:
        progress(0.05, desc="Extraindo áudio...")
        raw_audio = extract_audio(video, tmp)

        progress(0.15, desc="Processando áudio...")
        vocals, bgmusic = run_demucs(raw_audio, tmp)

        progress(0.30, desc="Transcrevendo...")
        transcription = run_whisperx(vocals, source_lang)
        original_text = transcription["text"]

        progress(0.45, desc="Traduzindo...")
        translated_text = translate_text(original_text, source_lang, target_lang)

        progress(0.60, desc="Gerando voz dublada...")
        ref_wav = ref_audio if ref_audio else vocals
        dubbed_voice = run_fish_speech(translated_text, ref_wav, tmp)

        progress(0.70, desc="Mixando áudio...")
        mixed_audio = mix_audio(dubbed_voice, bgmusic, tmp)

        if use_lipsync:
            progress(0.82, desc="Sincronizando lábios...")
            output_video = run_musetalk(video, mixed_audio, tmp)
        else:
            # Só troca o áudio sem lipsync
            progress(0.82, desc="Exportando vídeo...")
            output_video = os.path.join(tmp, "rapidex_output.mp4")
            subprocess.run([
                "ffmpeg", "-y",
                "-i", video,
                "-i", mixed_audio,
                "-c:v", "copy",
                "-map", "0:v:0", "-map", "1:a:0",
                "-shortest", output_video
            ], check=True, capture_output=True)

        progress(0.95, desc="Finalizando...")

        # Copia para local persistente
        final_path = f"/workspace/output_{int(time.time())}.mp4"
        shutil.copy(output_video, final_path)

        return output_video, original_text, translated_text, "✅ Concluído!"

    except Exception as e:
        raise gr.Error(f"Erro no pipeline: {str(e)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ─────────────────────────────────────────
#  INTERFACE
# ─────────────────────────────────────────

LANGUAGES = {
    "Detectar automaticamente": "auto",
    "Português": "pt",
    "Inglês": "en",
    "Espanhol": "es",
    "Francês": "fr",
    "Alemão": "de",
    "Italiano": "it",
    "Japonês": "ja",
    "Coreano": "ko",
    "Chinês": "zh",
    "Árabe": "ar",
    "Russo": "ru",
    "Hindi": "hi",
    "Turco": "tr",
    "Holandês": "nl",
    "Polonês": "pl",
}

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

/* Header */
.rapidex-header {
  padding: 2rem 0 1.5rem;
  text-align: center;
  border-bottom: 1px solid var(--border);
  margin-bottom: 2rem;
  background: linear-gradient(180deg, #0d1025 0%, transparent 100%);
}
.rapidex-logo {
  font-size: 2.2rem;
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

/* Pipeline steps */
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
.step-arrow {
  width: 28px;
  height: 1px;
  background: var(--border);
}

/* Cards */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.25rem;
}
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

/* Gradio overrides */
.gr-button-primary {
  background: linear-gradient(135deg, var(--accent), var(--accent2)) !important;
  border: none !important;
  border-radius: 8px !important;
  font-family: 'Syne', sans-serif !important;
  font-weight: 600 !important;
  font-size: 0.95rem !important;
  padding: 0.75rem 2rem !important;
  letter-spacing: 0.02em;
}
.gr-button-secondary {
  background: var(--surface) !important;
  border: 1px solid var(--border) !important;
  color: var(--text) !important;
  border-radius: 8px !important;
  font-family: 'Syne', sans-serif !important;
}

label, .gr-form > label {
  color: var(--muted) !important;
  font-size: 0.78rem !important;
  font-family: 'JetBrains Mono', monospace !important;
  letter-spacing: 0.05em !important;
  text-transform: uppercase !important;
}

input, select, textarea,
.gr-input, .gr-dropdown select,
.gr-box {
  background: var(--bg) !important;
  border: 1px solid var(--border) !important;
  color: var(--text) !important;
  border-radius: 8px !important;
  font-family: 'Syne', sans-serif !important;
}
input:focus, select:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 2px rgba(99,102,241,0.15) !important;
}

.gr-panel, .gr-block {
  background: transparent !important;
  border: none !important;
}

/* Progress & status */
.status-ok  { color: var(--success); font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; }
.status-err { color: var(--accent3); font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; }

/* Textboxes */
.gr-textbox textarea {
  background: var(--bg) !important;
  border: 1px solid var(--border) !important;
  color: var(--text) !important;
  border-radius: 8px !important;
  font-family: 'Syne', sans-serif !important;
  font-size: 0.9rem !important;
}

/* Upload zone */
.gr-file-drop {
  border: 1.5px dashed var(--border) !important;
  background: rgba(99,102,241,0.03) !important;
  border-radius: var(--radius) !important;
}
.gr-file-drop:hover {
  border-color: var(--accent) !important;
  background: rgba(99,102,241,0.06) !important;
}

/* Scrollbar */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
"""

HEADER = """
<div class="rapidex-header">
  <div class="rapidex-logo">⚡ RAPIDEX IA</div>
  <div class="rapidex-tagline">Traduza vídeos. Conecte o mundo.</div>
  <div style="margin-top: 12px;">
    <span class="gpu-badge">RUNPOD GPU</span>
    <span class="gpu-badge">CUDA</span>
    <span class="gpu-badge">v2.0</span>
  </div>
</div>

<div class="pipeline-bar">
  <div class="step"><span class="step-num">1</span> Vídeo</div>
  <div class="step-arrow"></div>
  <div class="step"><span class="step-num">2</span> Áudio</div>
  <div class="step-arrow"></div>
  <div class="step"><span class="step-num">3</span> Tradução</div>
  <div class="step-arrow"></div>
  <div class="step"><span class="step-num">4</span> Voz</div>
  <div class="step-arrow"></div>
  <div class="step"><span class="step-num">5</span> Lipsync</div>
</div>
"""

with gr.Blocks(css=CSS, title="RAPIDEX IA") as app:
    gr.HTML(HEADER)

    with gr.Row(equal_height=False):
        # ── Coluna 1: Vídeo & Idiomas
        with gr.Column(scale=1):
            gr.HTML('<div class="card-title">01 — Vídeo & Idiomas</div>')
            video_input = gr.Video(
                label="Vídeo de entrada",
                sources=["upload"],
                height=260
            )
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

        # ── Coluna 2: Voz
        with gr.Column(scale=1):
            gr.HTML('<div class="card-title">02 — Configurar Voz</div>')
            ref_audio = gr.Audio(
                label="Áudio de referência para clonagem (opcional)",
                sources=["upload"],
                type="filepath"
            )
            gr.HTML(
                '<p style="font-size:0.78rem; color:var(--muted); margin-top:6px;">'
                'Sem referência: usa a voz original do vídeo como base.'
                '</p>'
            )
            use_lipsync = gr.Checkbox(
                label="Sincronizar lábios (MuseTalk)",
                value=True
            )
            run_btn = gr.Button(
                "▶  DUBLAR VÍDEO",
                variant="primary",
                size="lg"
            )
            status_out = gr.Textbox(
                label="Status",
                interactive=False,
                lines=1
            )

        # ── Coluna 3: Resultado
        with gr.Column(scale=1):
            gr.HTML('<div class="card-title">03 — Resultado</div>')
            video_output = gr.Video(label="Vídeo dublado", height=260)
            with gr.Accordion("Textos gerados", open=False):
                original_text_out  = gr.Textbox(label="Transcrição original", lines=4)
                translated_text_out = gr.Textbox(label="Tradução",            lines=4)

    # ── Eventos
    run_btn.click(
        fn=run_pipeline,
        inputs=[
            video_input,
            source_lang,
            target_lang,
            use_lipsync,
            ref_audio,
        ],
        outputs=[video_output, original_text_out, translated_text_out, status_out],
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
        show_error=True
    )
