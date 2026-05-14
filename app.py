"""
RAPIDEX IA — AI Video Translation
Pipeline: Demucs → WhisperX → GoogleTranslate → Fish Speech/XTTS → MuseTalk/Wav2Lip
"""

import os, sys, subprocess, tempfile, shutil, time, traceback
os.environ["COQUI_TOS_AGREED"] = "1"

# ── FIX PyTorch 2.6+: weights_only padrão virou True, quebra checkpoints antigos ──
import torch
_orig_load = torch.load
def _safe_load(*a, **kw):
    kw.setdefault("weights_only", False)
    return _orig_load(*a, **kw)
torch.load = _safe_load

import gradio as gr
from deep_translator import GoogleTranslator

# ── Detecta ambiente ──────────────────────────────────────────────────────────
USE_GPU   = torch.cuda.is_available()
DEVICE    = "cuda" if USE_GPU else "cpu"
GPU_NAME  = torch.cuda.get_device_name(0) if USE_GPU else "CPU (sem GPU)"

# Paths dos modelos — funcionam tanto no RunPod (/workspace) quanto no Colab
BASE      = os.environ.get("RAPIDEX_BASE", "/workspace")
WAV2LIP   = os.path.join(BASE, "Wav2Lip")
MUSETALK  = os.path.join(BASE, "MuseTalk")

LANGUAGES = {
    "Detectar automaticamente": "auto",
    "Português": "pt",  "Inglês": "en",    "Espanhol": "es",
    "Francês": "fr",    "Alemão": "de",    "Italiano": "it",
    "Japonês": "ja",    "Coreano": "ko",   "Chinês": "zh",
    "Árabe": "ar",      "Russo": "ru",     "Hindi": "hi",
}

# ── Estado de sessão (substituir por gr.State em versão futura) ───────────────
_S: dict = {}


# ═══════════════════════════════════════════════════════════════════════════════
#  PIPELINE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def extract_audio(video_path: str, out_dir: str) -> str:
    """Extrai áudio WAV mono 16kHz do vídeo."""
    raw = os.path.join(out_dir, "raw_audio.wav")
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", video_path,
         "-vn", "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", raw],
        capture_output=True, text=True
    )
    if not os.path.exists(raw):
        raise RuntimeError(f"ffmpeg extract failed:\n{r.stderr[-500:]}")
    return raw


def run_demucs(raw_audio: str, out_dir: str):
    """Separa voz do fundo musical usando Demucs htdemucs."""
    demucs_out = os.path.join(out_dir, "demucs")
    subprocess.run(
        ["python", "-m", "demucs", "--two-stems=vocals", "-o", demucs_out, raw_audio],
        capture_output=True
    )
    # Procura vocals.wav na saída
    for root, _, files in os.walk(demucs_out):
        if "vocals.wav" in files:
            vocals  = os.path.join(root, "vocals.wav")
            bgmusic = os.path.join(root, "no_vocals.wav")
            return vocals, bgmusic if os.path.exists(bgmusic) else None
    # Fallback: demucs falhou, usa áudio original
    return raw_audio, None


def run_whisperx(vocals_path: str, lang_code: str) -> str:
    """Transcreve com WhisperX large-v3. Retorna texto original."""
    import whisperx
    compute = "float16" if USE_GPU else "int8"
    lang    = lang_code if lang_code != "auto" else None
    model   = whisperx.load_model("large-v3", DEVICE, compute_type=compute, language=lang)
    audio   = whisperx.load_audio(vocals_path)
    result  = model.transcribe(audio, batch_size=16)
    # Alinhamento de palavras (opcional — silencioso se falhar)
    try:
        lc = result.get("language", lang_code if lang_code != "auto" else "en")
        am, meta = whisperx.load_align_model(language_code=lc, device=DEVICE)
        result   = whisperx.align(result["segments"], am, meta, audio, DEVICE)
    except Exception:
        pass
    text = " ".join(s["text"].strip() for s in result.get("segments", []))
    del model
    if USE_GPU:
        torch.cuda.empty_cache()
    return text


def translate_text(text: str, src: str, tgt: str) -> str:
    """Traduz com Google Translate. Divide textos longos em chunks."""
    if src == tgt:
        return text
    MAX = 4500
    if len(text) <= MAX:
        return GoogleTranslator(source="auto", target=tgt).translate(text)
    words, chunks, chunk, size = text.split(), [], [], 0
    for w in words:
        if size + len(w) + 1 > MAX:
            chunks.append(" ".join(chunk)); chunk, size = [w], len(w)
        else:
            chunk.append(w); size += len(w) + 1
    if chunk: chunks.append(" ".join(chunk))
    return " ".join(GoogleTranslator(source="auto", target=tgt).translate(c) for c in chunks)


def run_fish_speech(text: str, ref_wav: str, out_dir: str) -> str:
    """
    Clona voz com Fish Speech V1.5.
    Fallback automático para XTTS v2 se Fish Speech não estiver disponível.
    """
    out = os.path.join(out_dir, "dubbed_voice.wav")
    fish_dir = os.path.join(BASE, "fish-speech")

    # Tenta Fish Speech
    if os.path.isdir(fish_dir):
        try:
            r = subprocess.run(
                ["python", "tools/run_fish_e2e.py",
                 "--text", text,
                 "--reference-audio", ref_wav,
                 "--output", out,
                 "--checkpoint-path", "checkpoints/fish-speech-1.5"],
                cwd=fish_dir, capture_output=True, text=True, timeout=300
            )
            if os.path.exists(out): return out
        except Exception:
            pass

    # Fallback: XTTS v2 (Coqui)
    try:
        from TTS.api import TTS
        tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=USE_GPU)
        tts.tts_to_file(text=text, file_path=out, speaker_wav=ref_wav, language="pt")
        if os.path.exists(out): return out
    except Exception as e_xtts:
        pass

    # Último fallback: gTTS (sem clonagem, só para não quebrar)
    try:
        from gtts import gTTS
        gTTS(text=text, lang="pt").save(out)
        return out
    except Exception:
        raise RuntimeError("Todos os motores TTS falharam (Fish Speech, XTTS, gTTS).")


def mix_audio(dubbed: str, bgmusic: str | None, out_dir: str) -> str:
    """Mistura voz dublada com música de fundo a 35% de volume."""
    if not bgmusic or not os.path.exists(bgmusic):
        return dubbed
    mixed = os.path.join(out_dir, "mixed_audio.wav")
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", dubbed, "-i", bgmusic,
         "-filter_complex",
         "[0:a]volume=1.0[v];[1:a]volume=0.35[b];[v][b]amix=inputs=2:duration=longest[out]",
         "-map", "[out]", mixed],
        capture_output=True
    )
    return mixed if r.returncode == 0 else dubbed


def run_lipsync(video: str, audio: str, out_dir: str) -> str:
    """
    Lipsync com MuseTalk como primário, Wav2Lip como fallback.
    Se nenhum disponível, só substitui o áudio.
    """
    output = os.path.join(out_dir, "rapidex_output.mp4")

    # Tenta MuseTalk
    if os.path.isdir(MUSETALK):
        musetalk_script = os.path.join(MUSETALK, "scripts", "inference.py")
        if not os.path.exists(musetalk_script):
            musetalk_script = os.path.join(MUSETALK, "inference.py")
        if os.path.exists(musetalk_script):
            r = subprocess.run(
                ["python", musetalk_script,
                 "--video_path", video,
                 "--audio_path", audio,
                 "--output_path", output,
                 "--bbox_shift", "0"],
                capture_output=True, text=True, cwd=MUSETALK
            )
            if os.path.exists(output): return output

    # Tenta Wav2Lip
    wav2lip_inf = os.path.join(WAV2LIP, "inference.py")
    wav2lip_ckpt = os.path.join(WAV2LIP, "checkpoints", "wav2lip_gan.pth")
    if os.path.exists(wav2lip_inf) and os.path.exists(wav2lip_ckpt):
        r = subprocess.run(
            ["python", wav2lip_inf,
             "--checkpoint_path", wav2lip_ckpt,
             "--face", video, "--audio", audio,
             "--outfile", output,
             "--pads", "0", "10", "0", "0", "--resize_factor", "1"],
            capture_output=True, text=True, cwd=WAV2LIP
        )
        if os.path.exists(output): return output

    # Sem lipsync disponível — só troca o áudio
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", video, "-i", audio,
         "-c:v", "copy", "-map", "0:v:0", "-map", "1:a:0", "-shortest", output],
        capture_output=True
    )
    if not os.path.exists(output):
        raise RuntimeError("Nenhuma ferramenta de lipsync disponível e ffmpeg merge falhou.")
    return output


# ═══════════════════════════════════════════════════════════════════════════════
#  GRADIO HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

def step_transcribe(video, source_lang, target_lang, progress=gr.Progress(track_tqdm=True)):
    if video is None:
        return "", "", "❌ Envie um vídeo primeiro."
    src = LANGUAGES.get(source_lang, "auto")
    tgt = LANGUAGES.get(target_lang, "pt")
    tmp = tempfile.mkdtemp(prefix="rapidex_")
    _S.update({"tmp": tmp, "video": video, "src": src, "tgt": tgt})
    try:
        progress(0.10, desc="Extraindo áudio...")
        raw = extract_audio(video, tmp)

        progress(0.25, desc="Separando voz do fundo (Demucs)...")
        vocals, bg = run_demucs(raw, tmp)
        _S.update({"vocals": vocals, "bg": bg})

        progress(0.55, desc="Transcrevendo (WhisperX large-v3)...")
        original = run_whisperx(vocals, src)

        progress(0.80, desc="Traduzindo...")
        translated = translate_text(original, src, tgt)

        progress(1.00, desc="Pronto!")
        lang_det = src.upper() if src != "auto" else "AUTO"
        return original, translated, f"✅ {lang_det} → {tgt.upper()} | WhisperX large-v3"

    except Exception:
        tb = traceback.format_exc()
        shutil.rmtree(tmp, ignore_errors=True)
        return "", "", f"❌ Erro:\n{tb[-800:]}"


def step_dub(translated_text, use_lipsync, ref_audio, progress=gr.Progress(track_tqdm=True)):
    if not translated_text or not translated_text.strip():
        return None, None, "❌ Texto de tradução vazio — transcreva primeiro."
    if "tmp" not in _S:
        return None, None, "❌ Faça a transcrição primeiro."

    tmp   = _S["tmp"]
    video = _S["video"]
    vocals = _S.get("vocals", "")
    bg    = _S.get("bg")

    try:
        progress(0.15, desc="Clonando voz (Fish Speech / XTTS)...")
        ref    = ref_audio if ref_audio else vocals
        dubbed = run_fish_speech(translated_text, ref, tmp)

        # Preview de áudio ANTES do lipsync
        preview_audio = dubbed

        progress(0.40, desc="Mixando com fundo musical...")
        mixed = mix_audio(dubbed, bg, tmp)

        if use_lipsync:
            progress(0.65, desc="Sincronizando lábios (MuseTalk / Wav2Lip)...")
            out = run_lipsync(video, mixed, tmp)
        else:
            progress(0.65, desc="Substituindo áudio no vídeo...")
            out = os.path.join(tmp, "rapidex_audio_only.mp4")
            subprocess.run(
                ["ffmpeg", "-y", "-i", video, "-i", mixed,
                 "-c:v", "copy", "-map", "0:v:0", "-map", "1:a:0", "-shortest", out],
                capture_output=True, check=True
            )

        # Copia para output persistente
        final = os.path.join(BASE, f"rapidex_output_{int(time.time())}.mp4")
        shutil.copy(out, final)

        size_mb = os.path.getsize(final) / 1e6
        mode = "MuseTalk/Wav2Lip" if use_lipsync else "Só áudio"
        return preview_audio, final, f"✅ Concluído! {size_mb:.1f}MB — {mode}"

    except Exception:
        tb = traceback.format_exc()
        return None, None, f"❌ Erro:\n{tb[-800:]}"


# ═══════════════════════════════════════════════════════════════════════════════
#  INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --bg:       #020409;
  --surface:  #0b0f1a;
  --elevated: #111827;
  --border:   #1a2035;
  --accent:   #6366f1;
  --accent2:  #a855f7;
  --accent3:  #ec4899;
  --text:     #e2e8f0;
  --muted:    #64748b;
  --success:  #10b981;
  --radius:   12px;
}

*, *::before, *::after { box-sizing: border-box; }

body, .gradio-container {
  background: var(--bg) !important;
  font-family: 'Syne', sans-serif !important;
  color: var(--text) !important;
  max-width: 100% !important;
}

/* ─── Header ─── */
.rx-header {
  padding: 2rem 0 1.5rem;
  text-align: center;
  border-bottom: 1px solid var(--border);
  margin-bottom: 1.5rem;
  background: linear-gradient(180deg, #0d1025 0%, transparent 100%);
}
.rx-logo {
  font-size: 2.2rem; font-weight: 800; letter-spacing: -0.02em;
  background: linear-gradient(135deg, var(--accent), var(--accent2), var(--accent3));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.rx-tagline {
  font-size: 0.8rem; color: var(--muted);
  font-family: 'JetBrains Mono', monospace; letter-spacing: 0.08em; margin-top: 4px;
}
.rx-badge {
  display: inline-block; font-size: 0.65rem;
  font-family: 'JetBrains Mono', monospace;
  background: rgba(99,102,241,0.1); color: var(--accent);
  border: 1px solid rgba(99,102,241,0.25);
  padding: 3px 10px; border-radius: 20px; margin: 0 3px;
}
.rx-badge.gpu {
  background: rgba(16,185,129,0.1); color: #10b981;
  border-color: rgba(16,185,129,0.3);
}

/* ─── Pipeline ─── */
.rx-pipeline {
  display: flex; align-items: center; justify-content: center;
  gap: 0; margin-bottom: 1.5rem; padding: 0 1rem; flex-wrap: wrap;
}
.rx-step {
  display: flex; align-items: center; gap: 7px;
  font-size: 0.68rem; font-family: 'JetBrains Mono', monospace;
  color: var(--muted); padding: 7px 13px;
  border: 1px solid var(--border); background: var(--surface);
  border-radius: 8px; white-space: nowrap;
}
.rx-step-num {
  font-size: 0.6rem; background: var(--border); color: var(--muted);
  width: 16px; height: 16px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
}
.rx-arrow { width: 24px; height: 1px; background: var(--border); }

/* ─── Cards ─── */
.rx-card-title {
  font-size: 0.65rem; font-family: 'JetBrains Mono', monospace;
  color: var(--muted); letter-spacing: 0.1em; text-transform: uppercase;
  margin-bottom: 1rem; padding-bottom: 0.75rem; border-bottom: 1px solid var(--border);
}

/* ─── Buttons ─── */
.gradio-container button.primary {
  background: linear-gradient(135deg, var(--accent), var(--accent2)) !important;
  border: none !important; border-radius: 8px !important;
  font-family: 'Syne', sans-serif !important; font-weight: 700 !important;
  transition: all 0.2s !important;
}
.gradio-container button.primary:hover {
  transform: translateY(-1px) !important;
  box-shadow: 0 6px 20px rgba(99,102,241,0.4) !important;
  filter: brightness(1.08) !important;
}
.gradio-container button.secondary {
  background: var(--surface) !important;
  border: 1px solid var(--border) !important;
  color: var(--text) !important; border-radius: 8px !important;
  font-family: 'Syne', sans-serif !important;
}
.gradio-container button.secondary:hover {
  border-color: var(--accent) !important;
  color: var(--accent) !important;
}

/* ─── Inputs ─── */
.gradio-container input, .gradio-container select,
.gradio-container textarea, .gradio-container .wrap {
  background: var(--bg) !important;
  border: 1px solid var(--border) !important;
  color: var(--text) !important; border-radius: 8px !important;
  font-family: 'Syne', sans-serif !important;
  transition: border-color 0.2s, box-shadow 0.2s !important;
}
.gradio-container input:focus, .gradio-container textarea:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 2px rgba(99,102,241,0.15) !important;
  outline: none !important;
}

/* ─── Labels ─── */
.gradio-container label span {
  color: var(--muted) !important; font-size: 0.72rem !important;
  font-family: 'JetBrains Mono', monospace !important;
  letter-spacing: 0.05em !important; text-transform: uppercase !important;
}

/* ─── Media ─── */
.gradio-container video, .gradio-container audio {
  border-radius: var(--radius) !important;
  border: 1px solid var(--border) !important;
}

/* ─── Scrollbar ─── */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

footer { display: none !important; }
"""

HEADER_HTML = f"""
<div class="rx-header">
  <div class="rx-logo">⚡ RAPIDEX IA</div>
  <div class="rx-tagline">Traduza vídeos. Conecte o mundo.</div>
  <div style="margin-top:12px;">
    <span class="rx-badge">WhisperX large-v3</span>
    <span class="rx-badge">Fish Speech</span>
    <span class="rx-badge">Demucs</span>
    <span class="rx-badge">MuseTalk</span>
    <span class="rx-badge gpu">{GPU_NAME}</span>
  </div>
</div>
<div class="rx-pipeline">
  <div class="rx-step"><span class="rx-step-num">1</span>Upload</div>
  <div class="rx-arrow"></div>
  <div class="rx-step"><span class="rx-step-num">2</span>Áudio</div>
  <div class="rx-arrow"></div>
  <div class="rx-step"><span class="rx-step-num">3</span>Transcrição</div>
  <div class="rx-arrow"></div>
  <div class="rx-step"><span class="rx-step-num">4</span>Tradução</div>
  <div class="rx-arrow"></div>
  <div class="rx-step"><span class="rx-step-num">5</span>Voz</div>
  <div class="rx-arrow"></div>
  <div class="rx-step"><span class="rx-step-num">6</span>Lipsync</div>
</div>
"""

with gr.Blocks(css=CSS, title="RAPIDEX IA") as app:
    gr.HTML(HEADER_HTML)

    with gr.Row(equal_height=False):

        # ── Coluna 1: Vídeo & Idiomas ─────────────────────────────────────────
        with gr.Column(scale=1, min_width=280):
            gr.HTML('<div class="rx-card-title">01 — Vídeo & Idiomas</div>')
            video_input = gr.Video(label="Vídeo de entrada", height=240)
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
            transcribe_btn = gr.Button("🔍 TRANSCREVER & TRADUZIR", variant="secondary", size="lg")

        # ── Coluna 2: Texto ───────────────────────────────────────────────────
        with gr.Column(scale=1, min_width=280):
            gr.HTML('<div class="rx-card-title">02 — Revisar & Editar</div>')
            original_out = gr.Textbox(
                label="Transcrição original",
                lines=5, interactive=False,
                placeholder="Texto original aparece aqui após transcrição..."
            )
            translated_out = gr.Textbox(
                label="Tradução — edite antes de dublar",
                lines=5, interactive=True,
                placeholder="Edite à vontade antes de clicar em Dublar..."
            )
            status_transcribe = gr.Textbox(label="Status", interactive=False, lines=2)

        # ── Coluna 3: Voz + Lipsync + Resultado ──────────────────────────────
        with gr.Column(scale=1, min_width=280):
            gr.HTML('<div class="rx-card-title">03 — Voz & Resultado</div>')
            ref_audio = gr.Audio(
                label="Áudio de referência para clonagem (opcional)",
                type="filepath"
            )
            gr.HTML('<p style="font-size:0.72rem;color:var(--muted);margin:4px 0 12px;">'
                    'Sem referência: usa a voz original do vídeo.</p>')
            use_lipsync = gr.Checkbox(label="Sincronizar lábios (MuseTalk → Wav2Lip)", value=True)
            dub_btn = gr.Button("▶ DUBLAR VÍDEO", variant="primary", size="lg")
            audio_preview = gr.Audio(label="Preview da voz clonada", type="filepath")
            video_out = gr.Video(label="Vídeo dublado", height=230)
            status_dub = gr.Textbox(label="Status", interactive=False, lines=2)

    # ── Bindings ──────────────────────────────────────────────────────────────
    transcribe_btn.click(
        fn=step_transcribe,
        inputs=[video_input, source_lang, target_lang],
        outputs=[original_out, translated_out, status_transcribe],
        show_progress=True
    )
    dub_btn.click(
        fn=step_dub,
        inputs=[translated_out, use_lipsync, ref_audio],
        outputs=[audio_preview, video_out, status_dub],
        show_progress=True
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  LAUNCH
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=True,
        show_error=True,
        allowed_paths=[BASE, "/tmp"]
    )
