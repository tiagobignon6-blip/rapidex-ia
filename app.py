import gradio as gr
import os
import subprocess
import tempfile
import shutil
import time

# ─────────────────────────────────────────
#  PIPELINE FUNCTIONS
# ─────────────────────────────────────────

def extract_audio(video_path, out_dir):
    raw_audio = os.path.join(out_dir, "raw_audio.wav")
    subprocess.run([
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", raw_audio
    ], check=True, capture_output=True)
    return raw_audio


def run_demucs(raw_audio, out_dir):
    demucs_out = os.path.join(out_dir, "demucs")
    subprocess.run([
        "python", "-m", "demucs", "--two-stems=vocals", "-o", demucs_out, raw_audio
    ], check=True, capture_output=True)
    stem_dir = None
    for root, dirs, files in os.walk(demucs_out):
        if "vocals.wav" in files:
            stem_dir = root
            break
    if stem_dir is None:
        raise RuntimeError("Demucs não gerou vocals.wav")
    return os.path.join(stem_dir, "vocals.wav"), os.path.join(stem_dir, "no_vocals.wav")


def run_whisperx(vocals_path, lang_code):
    """Retorna (texto, lang_detectado)."""
    import whisperx, torch
    device  = "cuda" if torch.cuda.is_available() else "cpu"
    compute = "float16" if device == "cuda" else "int8"
    model   = whisperx.load_model(
        "large-v3", device, compute_type=compute,
        language=lang_code if lang_code != "auto" else None
    )
    audio  = whisperx.load_audio(vocals_path)
    result = model.transcribe(audio, batch_size=16)
    detected = result.get("language", lang_code if lang_code != "auto" else "en")
    try:
        am, meta = whisperx.load_align_model(language_code=detected, device=device)
        result   = whisperx.align(result["segments"], am, meta, audio, device)
    except Exception:
        pass
    text = " ".join(s["text"].strip() for s in result["segments"])
    return text, detected


def translate_text(text, source_code, target_code):
    from deep_translator import GoogleTranslator
    src = source_code if source_code and source_code != "auto" else "auto"
    return GoogleTranslator(source=src, target=target_code).translate(text)


FISH_SPEECH_DIR = "/workspace/fish-speech"
FISH_SPEECH_CKPT = "/workspace/fish-speech/checkpoints/fish-speech-1.5"
FISH_SPEECH_VQGAN = "/workspace/fish-speech/checkpoints/firefly-gan-vq-fsq-8x1024-21hz-generator.pth"


def _ref_text_from_audio(ref_wav):
    """Transcreve o áudio de referência (curto) para passar como prompt-text ao Fish Speech."""
    try:
        import whisperx, torch
        device  = "cuda" if torch.cuda.is_available() else "cpu"
        compute = "float16" if device == "cuda" else "int8"
        model   = whisperx.load_model("large-v3", device, compute_type=compute)
        audio   = whisperx.load_audio(ref_wav)
        result  = model.transcribe(audio, batch_size=16)
        return " ".join(s["text"].strip() for s in result["segments"])[:300]
    except Exception:
        return ""


def run_fish_speech(text, ref_wav, out_dir):
    """Pipeline Fish Speech V1.5:
       1) tools.vqgan.inference -> codebook do áudio de referência
       2) tools.llama.generate  -> tokens semânticos do texto alvo
       3) tools.vqgan.inference -> wav final
    """
    dubbed = os.path.join(out_dir, "dubbed_voice.wav")
    ref_codes = os.path.join(out_dir, "ref.npy")
    out_codes = os.path.join(out_dir, "codes_0.npy")

    # Etapa 1: extrai código VQ do áudio de referência
    r1 = subprocess.run([
        "python", "tools/vqgan/inference.py",
        "-i", ref_wav,
        "-o", ref_codes,
        "--checkpoint-path", FISH_SPEECH_VQGAN,
    ], capture_output=True, text=True, cwd=FISH_SPEECH_DIR)
    if r1.returncode != 0 or not os.path.exists(ref_codes):
        raise RuntimeError(
            "Fish Speech (VQGAN encode) falhou.\n"
            f"STDOUT: {r1.stdout[-500:]}\nSTDERR: {r1.stderr[-1000:]}"
        )

    # Etapa 2: gera tokens semânticos a partir do texto alvo
    prompt_text = _ref_text_from_audio(ref_wav)
    cmd_llama = [
        "python", "tools/llama/generate.py",
        "--text", text,
        "--prompt-tokens", ref_codes,
        "--checkpoint-path", FISH_SPEECH_CKPT,
        "--num-samples", "1",
        "--compile",
    ]
    if prompt_text:
        cmd_llama += ["--prompt-text", prompt_text]
    r2 = subprocess.run(cmd_llama, capture_output=True, text=True, cwd=FISH_SPEECH_DIR)
    # generate.py escreve em ./codes_0.npy no cwd
    generated_codes = os.path.join(FISH_SPEECH_DIR, "codes_0.npy")
    if r2.returncode != 0 or not os.path.exists(generated_codes):
        raise RuntimeError(
            "Fish Speech (LLaMA generate) falhou.\n"
            f"STDOUT: {r2.stdout[-500:]}\nSTDERR: {r2.stderr[-1000:]}"
        )
    shutil.move(generated_codes, out_codes)

    # Etapa 3: decodifica tokens em wav
    r3 = subprocess.run([
        "python", "tools/vqgan/inference.py",
        "-i", out_codes,
        "-o", dubbed,
        "--checkpoint-path", FISH_SPEECH_VQGAN,
    ], capture_output=True, text=True, cwd=FISH_SPEECH_DIR)
    if r3.returncode != 0 or not os.path.exists(dubbed):
        raise RuntimeError(
            "Fish Speech (VQGAN decode) falhou.\n"
            f"STDOUT: {r3.stdout[-500:]}\nSTDERR: {r3.stderr[-1000:]}"
        )
    return dubbed


def mix_audio(dubbed, bgmusic, out_dir):
    mixed = os.path.join(out_dir, "mixed_audio.wav")
    subprocess.run([
        "ffmpeg", "-y", "-i", dubbed, "-i", bgmusic,
        "-filter_complex",
        "[0:a]volume=1.0[v];[1:a]volume=0.35[b];[v][b]amix=inputs=2:duration=longest[out]",
        "-map", "[out]", mixed
    ], check=True, capture_output=True)
    return mixed


def run_lipsync(video, audio, out_dir):
    """MuseTalk v1.5 com fallback para Wav2Lip.
    MuseTalk exige config YAML (não aceita flags --video_path/--audio_path direto).
    """
    output = os.path.join(out_dir, "rapidex_output.mp4")
    musetalk = "/workspace/MuseTalk"

    # Gera YAML temporário com a tarefa
    cfg_path = os.path.join(out_dir, "musetalk_cfg.yaml")
    result_dir = os.path.join(out_dir, "musetalk_results")
    os.makedirs(result_dir, exist_ok=True)
    with open(cfg_path, "w") as f:
        f.write(
            f"task_0:\n"
            f"  video_path: \"{video}\"\n"
            f"  audio_path: \"{audio}\"\n"
            f"  bbox_shift: 0\n"
        )

    r = subprocess.run([
        "python", "-m", "scripts.inference",
        "--inference_config", cfg_path,
        "--result_dir", result_dir,
        "--unet_model_path", f"{musetalk}/models/musetalk/pytorch_model.bin",
        "--unet_config", f"{musetalk}/models/musetalk/musetalk.json",
        "--version", "v15",
    ], capture_output=True, text=True, cwd=musetalk)

    # Procura o mp4 gerado em result_dir
    if r.returncode == 0:
        for root, _, files in os.walk(result_dir):
            for fn in files:
                if fn.endswith(".mp4"):
                    shutil.copy(os.path.join(root, fn), output)
                    return output

    print(f"[MuseTalk falhou, tentando Wav2Lip]\nSTDERR: {r.stderr[-800:]}")

    # Fallback Wav2Lip
    wav2lip = "/workspace/Wav2Lip"
    r2 = subprocess.run([
        "python", "inference.py",
        "--checkpoint_path", f"{wav2lip}/checkpoints/wav2lip_gan.pth",
        "--face", video, "--audio", audio,
        "--outfile", output,
        "--pads", "0", "10", "0", "0", "--resize_factor", "1"
    ], capture_output=True, text=True, cwd=wav2lip)
    if r2.returncode != 0 or not os.path.exists(output):
        raise RuntimeError(
            "MuseTalk e Wav2Lip falharam.\n"
            f"MuseTalk STDERR: {r.stderr[-500:]}\n"
            f"Wav2Lip STDERR: {r2.stderr[-500:]}"
        )
    return output


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
        original, detected = run_whisperx(vocals, src)
        _S["lang_detected"] = detected
        progress(0.80, desc="Traduzindo...")
        translated = translate_text(original, detected, tgt)
        progress(1.00, desc="Pronto!")
        return original, translated, f"✅ Transcrição concluída (detectado: {detected}) — edite e clique em Dublar"
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        _S.clear()
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
        final = f"/workspace/output_{int(time.time())}.mp4"
        shutil.copy(out, final)
        return final, "✅ Dublagem concluída!"
    except Exception as e:
        raise gr.Error(str(e))
    finally:
        # mantém os arquivos por enquanto; cleanup só após sessão fechar
        pass


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
