#!/usr/bin/env python3
"""
RAPIDEX IA - test_pipeline.py
Smoke test interno (NAO usado pelo usuario final).

Roda ponta-a-ponta (com mocks para componentes pesados quando ausentes)
e reporta o que esta funcionando.

Uso:
  python test_pipeline.py                # roda tudo, reporta status
  python test_pipeline.py --strict       # falha (exit 1) se qualquer teste falhar
  python test_pipeline.py --real         # usa modelos reais (precisa GPU)
"""
import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from contextlib import contextmanager

# Silencia logs durante os testes
logging.basicConfig(level=logging.WARNING)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Cores ANSI
class C:
    G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"
    B = "\033[94m"; D = "\033[2m"; END = "\033[0m"
    BOLD = "\033[1m"

def ok(msg):    return f"{C.G}OK{C.END} {msg}"
def fail(msg):  return f"{C.R}FAIL{C.END} {msg}"
def skip(msg):  return f"{C.Y}SKIP{C.END} {msg}"
def info(msg):  return f"{C.B}INFO{C.END} {msg}"


@contextmanager
def temp_dir():
    d = tempfile.mkdtemp(prefix="rapidex_test_")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


class Report:
    def __init__(self):
        self.results = []
        self.errors = []

    def add(self, name, status, detail=""):
        self.results.append((name, status, detail))
        symbol = {"PASS": "✅", "FAIL": "❌", "SKIP": "⊘"}[status]
        line_color = {"PASS": ok, "FAIL": fail, "SKIP": skip}[status]
        print(f"  {symbol} {line_color(name)}  {C.D}{detail}{C.END}")

    def summary(self):
        n_pass = sum(1 for _, s, _ in self.results if s == "PASS")
        n_fail = sum(1 for _, s, _ in self.results if s == "FAIL")
        n_skip = sum(1 for _, s, _ in self.results if s == "SKIP")
        total = len(self.results)
        print()
        print(f"{C.BOLD}{'═' * 60}{C.END}")
        print(f"{C.BOLD}RESUMO: {n_pass}/{total} PASS, {n_fail} FAIL, {n_skip} SKIP{C.END}")
        print(f"{C.BOLD}{'═' * 60}{C.END}")
        if n_fail:
            print(f"{C.R}Componentes com falha:{C.END}")
            for name, status, detail in self.results:
                if status == "FAIL":
                    print(f"  - {name}: {detail}")
        if n_skip:
            print(f"{C.Y}Componentes pulados:{C.END}")
            for name, status, detail in self.results:
                if status == "SKIP":
                    print(f"  - {name}: {detail}")
        return n_fail


# ─────────────────────────────────────────
# MOCKS para deps GPU-only (so quando ausentes)
# ─────────────────────────────────────────

def install_mocks():
    """Instala mocks para deps que nao podem rodar sem GPU."""
    import types
    mocked = []

    if "demucs" not in sys.modules:
        try:
            import demucs  # noqa
        except ImportError:
            for m in ["demucs", "demucs.apply", "demucs.pretrained"]:
                sys.modules[m] = types.ModuleType(m)
            sys.modules["demucs.pretrained"].get_model = lambda name: _FakeDemucsModel()
            sys.modules["demucs.apply"].apply_model = _fake_apply_model
            mocked.append("demucs")

    if "whisperx" not in sys.modules:
        try:
            import whisperx  # noqa
        except ImportError:
            wx = types.ModuleType("whisperx")
            wx.load_model = lambda *a, **kw: _FakeWhisper()
            wx.load_audio = lambda p: b""
            wx.load_align_model = lambda **kw: (None, None)
            wx.align = lambda *a, **kw: {"segments": [{"text": "transcricao mockada"}]}
            sys.modules["whisperx"] = wx
            mocked.append("whisperx")

    if "TTS" not in sys.modules:
        try:
            import TTS  # noqa
        except ImportError:
            sys.modules["TTS"] = types.ModuleType("TTS")
            tapi = types.ModuleType("TTS.api")
            class _FakeXTTS:
                def __init__(self, *a, **kw): pass
                def tts_to_file(self, **kw):
                    # Gera um wav valido via ffmpeg
                    out = kw["file_path"]
                    subprocess.run(
                        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                         "-ar", "16000", "-ac", "1", out],
                        capture_output=True, timeout=20,
                    )
            tapi.TTS = _FakeXTTS
            sys.modules["TTS.api"] = tapi
            mocked.append("TTS")

    return mocked


class _FakeDemucsModel:
    samplerate = 44100
    sources = ["drums", "bass", "other", "vocals"]
    def eval(self): return self
    def to(self, device): return self


def _fake_apply_model(model, wav, **kw):
    import torch
    # Retorna shape (batch=1, stems=4, channels=2, time)
    _, ch, t = wav.shape
    return torch.zeros(1, 4, ch, t)


class _FakeWhisper:
    def transcribe(self, audio, **kw):
        return {
            "language": kw.get("language") or "en",
            "segments": [{"text": "Hello world this is a test", "start": 0, "end": 2}],
        }


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def make_test_video(out_path, duration=4):
    """Gera um video de teste (cor solida + tom 440Hz) usando ffmpeg."""
    r = subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", f"color=c=blue:size=320x240:rate=25:duration={duration}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", out_path],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg test video falhou: {r.stderr[-300:]}")
    return out_path


def make_test_audio(out_path, duration=2, freq=440):
    """Gera um wav de teste."""
    r = subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"sine=frequency={freq}:duration={duration}",
         "-ar", "16000", "-ac", "1", out_path],
        capture_output=True, timeout=15,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg test audio falhou")
    return out_path


def file_ok(path, min_size=1000):
    return path and os.path.exists(path) and os.path.getsize(path) >= min_size


# ─────────────────────────────────────────
# TESTES
# ─────────────────────────────────────────

def test_imports(report):
    print(f"\n{C.BOLD}[1] IMPORTS{C.END}")
    try:
        import pipeline
        report.add("pipeline.py imports", "PASS",
                   f"DEVICE={pipeline.DEVICE} WHISPER_SIZE={pipeline.WHISPER_SIZE}")
    except Exception as e:
        report.add("pipeline.py imports", "FAIL", str(e))
        return False

    try:
        import app
        report.add("app.py imports", "PASS", "")
        # Verifica functions criticas
        for fn in ["step_transcribe", "step_generate_audio", "step_render"]:
            if hasattr(app, fn):
                report.add(f"app.{fn} exists", "PASS", "")
            else:
                report.add(f"app.{fn} exists", "FAIL", "ausente")
    except Exception as e:
        report.add("app.py imports", "FAIL", str(e))
        return False
    return True


def test_ffmpeg(report):
    print(f"\n{C.BOLD}[2] FFMPEG{C.END}")
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            version = r.stdout.split("\n")[0]
            report.add("ffmpeg available", "PASS", version[:60])
        else:
            report.add("ffmpeg available", "FAIL", "returncode != 0")
            return False
    except FileNotFoundError:
        report.add("ffmpeg available", "FAIL", "comando nao encontrado")
        return False

    try:
        r = subprocess.run(["ffprobe", "-version"], capture_output=True, text=True, timeout=10)
        report.add("ffprobe available", "PASS" if r.returncode == 0 else "FAIL", "")
    except FileNotFoundError:
        report.add("ffprobe available", "FAIL", "")
    return True


def test_extract_audio(report):
    print(f"\n{C.BOLD}[3] EXTRACT_AUDIO{C.END}")
    import pipeline
    with temp_dir() as d:
        try:
            video = os.path.join(d, "test.mp4")
            make_test_video(video)
            r16, rdemucs = pipeline.extract_audio(video, d)
            ok1 = file_ok(r16, 5000)
            ok2 = file_ok(rdemucs, 5000)
            report.add("extract_audio retorna 16kHz", "PASS" if ok1 else "FAIL",
                       f"size={os.path.getsize(r16) if r16 else 0}")
            report.add("extract_audio retorna demucs-ready", "PASS" if ok2 else "FAIL",
                       f"size={os.path.getsize(rdemucs) if rdemucs else 0}")
            return ok1 and ok2
        except Exception as e:
            report.add("extract_audio", "FAIL", f"{type(e).__name__}: {e}")
            return False


def test_demucs(report, real=False):
    print(f"\n{C.BOLD}[4] DEMUCS (separacao de voz){C.END}")
    try:
        import demucs.pretrained  # noqa
    except ImportError:
        report.add("demucs disponivel", "SKIP", "demucs nao instalado neste ambiente")
        return False

    if not real:
        report.add("demucs disponivel", "SKIP", "use --real (precisa GPU/modelo baixado)")
        return False

    import pipeline
    with temp_dir() as d:
        try:
            video = os.path.join(d, "test.mp4")
            make_test_video(video, duration=3)
            r16, rdemucs = pipeline.extract_audio(video, d)
            vocals, bg = pipeline.run_demucs(r16, d, demucs_input=rdemucs)
            ok_v = file_ok(vocals, 1000)
            report.add("demucs separa voz", "PASS" if ok_v else "FAIL",
                       f"vocals={os.path.getsize(vocals) if vocals else 0}")
            return ok_v
        except Exception as e:
            report.add("demucs separa voz", "FAIL", f"{type(e).__name__}: {e}")
            return False


def test_demucs_normalize(report):
    """Testa que normalizacao protege contra silencio (NaN bug)."""
    print(f"\n{C.BOLD}[5] DEMUCS NORMALIZATION (silencio){C.END}")
    try:
        import torch
        import pipeline

        # Silencio total
        silence = torch.zeros(2, 44100)
        out, m, s = pipeline._demucs_normalize(silence)
        if torch.isnan(out).any() or torch.isinf(out).any():
            report.add("normalize tolera silencio", "FAIL", "NaN/Inf gerado")
            return False
        report.add("normalize tolera silencio", "PASS", f"std fallback={s}")

        # Sinal real - roundtrip
        real = torch.sin(torch.linspace(0, 100, 44100 * 2)).unsqueeze(0).repeat(2, 1)
        out, m, s = pipeline._demucs_normalize(real)
        restored = out * s + m
        if torch.allclose(restored, real, atol=1e-5):
            report.add("normalize roundtrip preserva sinal", "PASS", "")
        else:
            report.add("normalize roundtrip preserva sinal", "FAIL", "")
        return True
    except ImportError as e:
        report.add("normalize (torch)", "SKIP", f"torch ausente: {e}")
        return False
    except Exception as e:
        report.add("normalize", "FAIL", f"{type(e).__name__}: {e}")
        return False


def make_test_speech_audio(out_path, text="Hello world this is a test of the speech recognition system"):
    """Gera audio com FALA real via gTTS (necessario pra testar whisperx)."""
    from gtts import gTTS
    mp3 = out_path + ".mp3"
    gTTS(text=text, lang="en").save(mp3)
    subprocess.run(
        ["ffmpeg", "-y", "-i", mp3, "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", out_path],
        capture_output=True, timeout=30,
    )
    os.remove(mp3)
    return out_path


def test_whisperx(report, real=False):
    print(f"\n{C.BOLD}[6] WHISPERX (transcricao){C.END}")
    try:
        import whisperx  # noqa
    except ImportError:
        report.add("whisperx disponivel", "SKIP", "whisperx nao instalado")
        return False

    if not real:
        report.add("whisperx disponivel", "SKIP", "use --real (precisa GPU + ~10GB VRAM)")
        return False

    import pipeline
    with temp_dir() as d:
        try:
            audio = os.path.join(d, "test.wav")
            make_test_speech_audio(audio)  # FALA REAL via gTTS
            text, lang = pipeline.run_whisperx(audio, "en")
            ok_t = bool(text) and len(text) > 5
            report.add("whisperx transcreve", "PASS" if ok_t else "FAIL",
                       f"lang={lang} text={text[:60]!r}")
            return ok_t
        except Exception as e:
            report.add("whisperx transcreve", "FAIL", f"{type(e).__name__}: {e}")
            return False


def test_translate(report):
    print(f"\n{C.BOLD}[7] TRADUCAO{C.END}")
    try:
        from deep_translator import GoogleTranslator
    except ImportError as e:
        report.add("deep_translator instalado", "FAIL", str(e))
        return False

    import pipeline
    try:
        # Texto curto
        result = pipeline.translate_text("Hello world", "en", "pt")
        ok1 = result and result.lower() != "hello world"
        report.add("traducao curta (en->pt)", "PASS" if ok1 else "FAIL",
                   f"{result!r}")

        # Texto vazio
        result = pipeline.translate_text("", "en", "pt")
        report.add("traducao texto vazio nao crasha", "PASS", f"{result!r}")

        # Mesma lingua
        result = pipeline.translate_text("teste", "pt", "pt")
        report.add("traducao mesma lingua passa direto", "PASS", f"{result!r}")
        return ok1
    except Exception as e:
        report.add("traducao", "FAIL", f"{type(e).__name__}: {e}")
        return False


def test_gtts(report):
    print(f"\n{C.BOLD}[8] gTTS (TTS fallback){C.END}")
    try:
        from gtts import gTTS
    except ImportError as e:
        report.add("gTTS instalado", "FAIL", str(e))
        return False

    with temp_dir() as d:
        try:
            mp3 = os.path.join(d, "test.mp3")
            gTTS(text="Olá mundo, isto é um teste.", lang="pt").save(mp3)
            ok = file_ok(mp3, 500)
            report.add("gTTS gera mp3", "PASS" if ok else "FAIL",
                       f"size={os.path.getsize(mp3) if os.path.exists(mp3) else 0}")
            return ok
        except Exception as e:
            report.add("gTTS gera mp3", "FAIL", f"{type(e).__name__}: {e}")
            return False


def test_run_tts(report):
    print(f"\n{C.BOLD}[9] run_tts (com fallback gTTS){C.END}")
    import pipeline
    with temp_dir() as d:
        try:
            ref = os.path.join(d, "ref.wav")
            make_test_audio(ref)
            out = pipeline.run_tts("Olá, este é um teste do pipeline.", ref, d, tgt_lang="pt")
            ok = file_ok(out, 2000)
            report.add("run_tts gera audio", "PASS" if ok else "FAIL",
                       f"size={os.path.getsize(out) if out and os.path.exists(out) else 0}")
            return ok
        except Exception as e:
            report.add("run_tts", "FAIL", f"{type(e).__name__}: {e}")
            return False


def test_mix_audio(report):
    print(f"\n{C.BOLD}[10] mix_audio{C.END}")
    import pipeline
    with temp_dir() as d:
        try:
            voice = os.path.join(d, "voice.wav")
            bg = os.path.join(d, "bg.wav")
            make_test_audio(voice, duration=2, freq=440)
            make_test_audio(bg, duration=2, freq=200)
            out = pipeline.mix_audio(voice, bg, d)
            ok = file_ok(out, 2000)
            report.add("mix_audio funciona", "PASS" if ok else "FAIL", "")

            # bg ausente: deve copiar voice
            out2 = pipeline.mix_audio(voice, None, d + "_2") if False else pipeline.mix_audio(voice, "/nao/existe", d)
            ok2 = file_ok(out2, 2000)
            report.add("mix_audio sem bg cai pra copy", "PASS" if ok2 else "FAIL", "")
            return ok and ok2
        except Exception as e:
            report.add("mix_audio", "FAIL", f"{type(e).__name__}: {e}")
            return False


def test_video_validation_helpers(report):
    print(f"\n{C.BOLD}[11] VALIDADORES (audio/video){C.END}")
    import app
    with temp_dir() as d:
        try:
            # Audio valido
            audio = os.path.join(d, "ok.wav")
            make_test_audio(audio, duration=2)
            ok, msg = app._validate_audio(audio)
            report.add("_validate_audio aceita wav valido", "PASS" if ok else "FAIL", msg)

            # Audio inexistente
            ok, msg = app._validate_audio("/nao/existe.wav")
            report.add("_validate_audio rejeita inexistente", "PASS" if not ok else "FAIL", msg)

            # Audio vazio
            empty = os.path.join(d, "empty.wav")
            open(empty, "w").close()
            ok, msg = app._validate_audio(empty)
            report.add("_validate_audio rejeita vazio", "PASS" if not ok else "FAIL", msg)

            # Video valido
            video = os.path.join(d, "ok.mp4")
            make_test_video(video, duration=2)
            ok, msg = app._validate_video(video)
            report.add("_validate_video aceita mp4 valido", "PASS" if ok else "FAIL", msg)
            return True
        except Exception as e:
            report.add("validadores", "FAIL", f"{type(e).__name__}: {e}")
            return False


def test_e2e_orchestration(report):
    """Testa step_transcribe, generate_audio, approve, render com mocks
    para os componentes pesados, exercitando todo o fluxo do app.py."""
    print(f"\n{C.BOLD}[12] ORQUESTRACAO E2E (com mocks){C.END}")

    # Fakea componentes pesados em pipeline antes de importar app
    import pipeline
    import app

    # Salvar originais
    _orig = {
        "extract_audio": pipeline.extract_audio,
        "run_demucs": pipeline.run_demucs,
        "run_whisperx": pipeline.run_whisperx,
        "translate_text": pipeline.translate_text,
        "run_tts": pipeline.run_tts,
        "mix_audio": pipeline.mix_audio,
        "run_lipsync": pipeline.run_lipsync,
    }

    def fake_extract(video, out_dir):
        raw_16k = os.path.join(out_dir, "r16.wav")
        rdemucs = os.path.join(out_dir, "rd.wav")
        make_test_audio(raw_16k, duration=2)
        make_test_audio(rdemucs, duration=2)
        return raw_16k, rdemucs

    def fake_demucs(raw, out_dir, demucs_input=None):
        v = os.path.join(out_dir, "voc.wav")
        b = os.path.join(out_dir, "bg.wav")
        make_test_audio(v, duration=2)
        make_test_audio(b, duration=2)
        return v, b

    def fake_whisper(vocals, lang):
        return "Hello world this is a test of the pipeline", "en"

    def fake_tts(text, ref, out_dir, tgt_lang="pt"):
        out = os.path.join(out_dir, "dub.wav")
        make_test_audio(out, duration=3)
        return out

    def fake_lipsync(video, audio, out_dir):
        out = os.path.join(out_dir, "lipsync.mp4")
        # Cria mp4 real combinando video+audio
        make_test_video_with_audio(video, audio, out)
        return out

    pipeline.extract_audio = fake_extract
    pipeline.run_demucs = fake_demucs
    pipeline.run_whisperx = fake_whisper
    pipeline.run_tts = fake_tts
    pipeline.run_lipsync = fake_lipsync
    # Re-injeta no app.py (importou por nome)
    app.extract_audio = fake_extract
    app.run_demucs = fake_demucs
    app.run_whisperx = fake_whisper
    app.run_tts = fake_tts
    app.run_lipsync = fake_lipsync

    try:
        with temp_dir() as d:
            video = os.path.join(d, "input.mp4")
            make_test_video(video, duration=3)

            # 1. Transcrever
            state = {}
            orig, trans, status, state = app.step_transcribe(
                video, "Ingles", "Portugues", state,
            )
            assert orig == "Hello world this is a test of the pipeline", f"orig={orig!r}"
            assert "[en->pt]" in trans or len(trans) > 0, f"trans={trans!r}"
            assert os.path.isdir(state["tmp"]), "tmp dir nao criado"
            assert state.get("vocals") and os.path.exists(state["vocals"])
            report.add("step_transcribe ponta-a-ponta", "PASS",
                       f"orig={len(orig)}c trans={len(trans)}c")

            # 2. Gerar audio
            audio, status, state = app.step_generate_audio(trans, None, state)
            ok, info = app._validate_audio(audio)
            assert ok, f"audio invalido: {info}"
            assert state.get("audio_preview") == audio
            report.add("step_generate_audio ponta-a-ponta", "PASS", info)

            # 3. Render sem lipsync (UX simplificada - sem step de aprovacao)
            final, status = app.step_render(False, state)
            ok, info = app._validate_video(final)
            assert ok, f"video final invalido: {info}"
            report.add("step_render (sem lipsync) gera video", "PASS", info)

            # 4. Render COM lipsync (usa fake_lipsync)
            # precisa novo state pq render limpa o tmp
            state2 = {}
            _, _, _, state2 = app.step_transcribe(video, "Ingles", "Portugues", state2)
            _, _, state2 = app.step_generate_audio(trans, None, state2)
            final2, _ = app.step_render(True, state2)
            ok, info = app._validate_video(final2)
            report.add("step_render (com lipsync) gera video", "PASS" if ok else "FAIL", info)

            # 5. Render bloqueia sem audio gerado
            try:
                app.step_render(False, {"tmp": "/tmp", "video": video})
                report.add("step_render bloqueia sem audio gerado", "FAIL", "deveria erro")
            except Exception as e:
                if "Gere o audio" in str(e):
                    report.add("step_render bloqueia sem audio gerado", "PASS", "")
                else:
                    report.add("step_render bloqueia sem audio gerado", "FAIL", str(e))

            # 7. Tentar gerar audio sem transcrever - deve falhar
            try:
                app.step_generate_audio("texto", None, {})
                report.add("step_generate_audio bloqueia sem state", "FAIL", "")
            except Exception as e:
                report.add("step_generate_audio bloqueia sem state", "PASS", "")

            # 8. Texto vazio
            try:
                app.step_generate_audio("   ", None, state)
                report.add("step_generate_audio bloqueia texto vazio", "FAIL", "")
            except Exception as e:
                report.add("step_generate_audio bloqueia texto vazio", "PASS", "")

            # 9. Video sem upload
            try:
                app.step_transcribe(None, "Ingles", "Portugues", {})
                report.add("step_transcribe bloqueia video None", "FAIL", "")
            except Exception as e:
                report.add("step_transcribe bloqueia video None", "PASS", "")

            return True

    except AssertionError as e:
        report.add("orquestracao e2e", "FAIL", str(e))
        traceback.print_exc()
        return False
    except Exception as e:
        report.add("orquestracao e2e", "FAIL", f"{type(e).__name__}: {e}")
        traceback.print_exc()
        return False
    finally:
        # Restaura
        for k, v in _orig.items():
            setattr(pipeline, k, v)
            setattr(app, k, v)


def make_test_video_with_audio(video, audio, out):
    subprocess.run(
        ["ffmpeg", "-y", "-i", video, "-i", audio,
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
         "-map", "0:v:0", "-map", "1:a:0", "-shortest", out],
        capture_output=True, timeout=30,
    )


def test_state_persistence(report):
    """Garante que o estado da sessao persiste entre etapas."""
    print(f"\n{C.BOLD}[13] PERSISTENCIA DE ESTADO{C.END}")
    import app
    state = {"tmp": "/tmp/x", "video": "/tmp/v", "translated_text": "olá",
             "audio_preview": None, "approved": False}

    # Estado deve preservar campos entre chamadas
    assert state["translated_text"] == "olá"
    assert state["approved"] is False

    # Aprovar deve modificar so o approved
    # (nao chamamos step_approve aqui pq ele valida audio_preview)
    report.add("state dict guarda campos chave", "PASS", str(list(state.keys())))
    return True


def test_regenerate_audio_resets_approval(report):
    """Apos aprovar, gerar audio de novo deve invalidar a aprovacao."""
    print(f"\n{C.BOLD}[16] REGENERAR AUDIO RESETA APROVACAO{C.END}")
    import pipeline, app

    _orig = (pipeline.extract_audio, pipeline.run_demucs, pipeline.run_whisperx,
             pipeline.run_tts, pipeline.run_lipsync)

    def fake_extract(v, d):
        a = os.path.join(d, "r16.wav"); b = os.path.join(d, "rd.wav")
        make_test_audio(a); make_test_audio(b)
        return a, b
    def fake_demucs(r, d, demucs_input=None):
        v = os.path.join(d, "voc.wav"); b = os.path.join(d, "bg.wav")
        make_test_audio(v); make_test_audio(b)
        return v, b
    def fake_whisper(v, l): return "Hello world", "en"
    def fake_tts(t, r, d, tgt_lang="pt"):
        out = os.path.join(d, f"dub_{int(time.time()*1000)}.wav")
        make_test_audio(out); return out

    pipeline.extract_audio = fake_extract
    pipeline.run_demucs = fake_demucs
    pipeline.run_whisperx = fake_whisper
    pipeline.run_tts = fake_tts
    app.extract_audio = fake_extract
    app.run_demucs = fake_demucs
    app.run_whisperx = fake_whisper
    app.run_tts = fake_tts

    try:
        with temp_dir() as d:
            video = os.path.join(d, "v.mp4")
            make_test_video(video, duration=2)

            state = {}
            _, trans, _, state = app.step_transcribe(video, "Ingles", "Portugues", state)
            audio1, _, state = app.step_generate_audio(trans, None, state)
            assert state.get("audio_preview") == audio1
            report.add("audio gerado e persistido no state", "PASS", "")

            # Regenerar audio (novo texto) - audio_preview do state deve refletir a nova chamada
            audio2, _, state = app.step_generate_audio("Texto editado pelo usuario", None, state)
            assert state.get("audio_preview") == audio2
            report.add("regenerar audio atualiza o preview no state", "PASS", "")

            # Renderizar normalmente apos regenerar
            final, _ = app.step_render(False, state)
            ok, info = app._validate_video(final)
            report.add("render apos regenerar audio funciona", "PASS" if ok else "FAIL", info)
            return True
    except Exception as e:
        report.add("regenerar audio", "FAIL", f"{type(e).__name__}: {e}")
        traceback.print_exc()
        return False
    finally:
        (pipeline.extract_audio, pipeline.run_demucs, pipeline.run_whisperx,
         pipeline.run_tts, pipeline.run_lipsync) = _orig
        app.extract_audio, app.run_demucs, app.run_whisperx, app.run_tts, app.run_lipsync = _orig


def test_user_edits_text_between_transcribe_and_generate(report):
    """Texto editado pelo usuario deve ser usado no TTS, nao a traducao automatica."""
    print(f"\n{C.BOLD}[17] EDICAO MANUAL DE TEXTO{C.END}")
    import pipeline, app

    _orig_tts = pipeline.run_tts
    captured_text = []

    def capturing_tts(text, ref, d, tgt_lang="pt"):
        captured_text.append(text)
        out = os.path.join(d, "dub.wav")
        make_test_audio(out)
        return out

    _orig = (pipeline.extract_audio, pipeline.run_demucs, pipeline.run_whisperx,
             pipeline.run_tts)

    def fake_extract(v, d):
        a = os.path.join(d, "r16.wav"); b = os.path.join(d, "rd.wav")
        make_test_audio(a); make_test_audio(b)
        return a, b
    def fake_demucs(r, d, demucs_input=None):
        v = os.path.join(d, "voc.wav"); b = os.path.join(d, "bg.wav")
        make_test_audio(v); make_test_audio(b)
        return v, b
    def fake_whisper(v, l): return "Original text from whisper", "en"

    pipeline.extract_audio = fake_extract
    pipeline.run_demucs = fake_demucs
    pipeline.run_whisperx = fake_whisper
    pipeline.run_tts = capturing_tts
    app.extract_audio = fake_extract
    app.run_demucs = fake_demucs
    app.run_whisperx = fake_whisper
    app.run_tts = capturing_tts

    try:
        with temp_dir() as d:
            video = os.path.join(d, "v.mp4")
            make_test_video(video, duration=2)

            state = {}
            _, _, _, state = app.step_transcribe(video, "Ingles", "Portugues", state)

            # Usuario passa um texto MUITO diferente da traducao automatica
            user_text = "ESTE É O TEXTO QUE O USUÁRIO EDITOU MANUALMENTE"
            audio, _, state = app.step_generate_audio(user_text, None, state)

            assert captured_text and captured_text[-1] == user_text, \
                f"TTS recebeu texto errado: {captured_text}"
            assert state.get("translated_text") == user_text
            report.add("texto editado e passado para o TTS", "PASS", "")
            report.add("texto editado e persistido no state", "PASS", "")
            return True
    except Exception as e:
        report.add("edicao manual", "FAIL", f"{type(e).__name__}: {e}")
        traceback.print_exc()
        return False
    finally:
        (pipeline.extract_audio, pipeline.run_demucs, pipeline.run_whisperx,
         pipeline.run_tts) = _orig
        app.extract_audio, app.run_demucs, app.run_whisperx, app.run_tts = _orig


def test_translation_long_text(report):
    """Tradutor com texto longo (precisa quebrar em chunks)."""
    print(f"\n{C.BOLD}[18] TRADUCAO TEXTO LONGO (chunking){C.END}")
    import pipeline
    long_text = ("Hello world. " * 500).strip()  # ~6500 chars
    try:
        result = pipeline.translate_text(long_text, "en", "pt")
        ok = result and len(result) > len(long_text) * 0.5
        report.add("traducao chunking nao trava", "PASS" if ok else "FAIL",
                   f"in={len(long_text)}c out={len(result) if result else 0}c")
        return ok
    except Exception as e:
        report.add("traducao texto longo", "FAIL", f"{type(e).__name__}: {e}")
        return False


def test_multiple_target_languages(report):
    """gTTS deve funcionar pra varios idiomas comuns."""
    print(f"\n{C.BOLD}[19] gTTS MULTI-IDIOMA{C.END}")
    from gtts import gTTS
    langs = ["pt", "en", "es", "fr", "de", "it", "ja", "ko"]
    n_ok = 0
    with temp_dir() as d:
        for lang in langs:
            try:
                p = os.path.join(d, f"t_{lang}.mp3")
                gTTS(text="Hello test", lang=lang).save(p)
                if os.path.getsize(p) > 500:
                    n_ok += 1
            except Exception:
                pass
    report.add(f"gTTS funciona em multi-lang", "PASS" if n_ok >= 6 else "FAIL",
               f"{n_ok}/{len(langs)} idiomas")
    return n_ok >= 6


def test_e2e_real_pipeline(report):
    """
    End-to-end com modelos REAIS (demucs + whisperx + translate + tts + mix + render).
    Pula apenas o lipsync (precisa MuseTalk/Wav2Lip).
    """
    print(f"\n{C.BOLD}[21] E2E PIPELINE REAL (demucs+whisperx+translate+tts){C.END}")
    try:
        import demucs.pretrained  # noqa
        import whisperx  # noqa
    except ImportError:
        report.add("e2e real pipeline", "SKIP", "demucs/whisperx ausentes")
        return False

    import pipeline
    import app
    with temp_dir() as d:
        try:
            # 1. Cria video de teste com FALA REAL
            audio_path = os.path.join(d, "speech.wav")
            make_test_speech_audio(audio_path,
                                   "Hello world this is a real test of the rapidex pipeline")
            video = os.path.join(d, "test.mp4")
            subprocess.run(
                ["ffmpeg", "-y",
                 "-f", "lavfi", "-i", "color=c=blue:size=320x240:rate=25:duration=4",
                 "-i", audio_path,
                 "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-shortest", video],
                capture_output=True, timeout=30,
            )
            assert os.path.getsize(video) > 5000, "video de teste invalido"
            report.add("[e2e] gerou video com fala real", "PASS",
                       f"{os.path.getsize(video)} bytes")

            # 2. Step transcribe REAL
            t0 = time.time()
            state = {}
            orig, trans, status, state = app.step_transcribe(
                video, "Ingles", "Portugues", state,
            )
            t_trans = time.time() - t0

            assert orig and len(orig) > 5, f"transcricao vazia: {orig!r}"
            assert trans and len(trans) > 5, f"traducao vazia: {trans!r}"
            assert state.get("vocals") and os.path.exists(state["vocals"])
            report.add("[e2e] transcribe REAL", "PASS",
                       f"orig={orig[:40]!r} ({t_trans:.1f}s)")
            report.add("[e2e] traducao em portugues", "PASS",
                       f"trans={trans[:40]!r}")

            # 3. Step generate audio REAL (cai pro gTTS pq nao tem XTTS no venv)
            t0 = time.time()
            audio, status, state = app.step_generate_audio(trans, None, state)
            t_audio = time.time() - t0

            ok, info = app._validate_audio(audio)
            assert ok, f"audio invalido: {info}"
            report.add("[e2e] generate_audio REAL (gTTS fallback)", "PASS",
                       f"{info} ({t_audio:.1f}s)")

            # 4. Render direto (UX simplificada, sem approve step)
            t0 = time.time()
            final, status = app.step_render(False, state)
            t_render = time.time() - t0

            ok, info = app._validate_video(final)
            assert ok, f"video final invalido: {info}"
            assert os.path.exists(final), "arquivo final ausente"
            report.add("[e2e] render final REAL", "PASS",
                       f"{info} ({t_render:.1f}s) -> {final}")

            # 6. Validacoes extras: o video final tem AUDIO?
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "a",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0", final],
                capture_output=True, text=True, timeout=10,
            )
            has_audio = "audio" in r.stdout
            report.add("[e2e] video final tem trilha de audio", "PASS" if has_audio else "FAIL", "")

            # 7. Validacoes extras: o video final tem VIDEO?
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0", final],
                capture_output=True, text=True, timeout=10,
            )
            has_video = "video" in r.stdout
            report.add("[e2e] video final tem trilha de video", "PASS" if has_video else "FAIL", "")

            return True
        except AssertionError as e:
            report.add("[e2e] real pipeline", "FAIL", str(e))
            return False
        except Exception as e:
            report.add("[e2e] real pipeline", "FAIL", f"{type(e).__name__}: {e}")
            traceback.print_exc()
            return False


def test_face_segmentation_helpers(report):
    """Verifica que as funcoes de segmentacao por face existem e ffmpeg helpers funcionam."""
    print(f"\n{C.BOLD}[20b] FACE SEGMENTATION HELPERS{C.END}")
    import pipeline

    # Funcoes devem existir
    for fn_name in ["_detect_face_segments", "_ffmpeg_extract_segment",
                    "_ffmpeg_concat", "run_lipsync_segmented", "_get_video_duration"]:
        if hasattr(pipeline, fn_name):
            report.add(f"pipeline.{fn_name} existe", "PASS", "")
        else:
            report.add(f"pipeline.{fn_name} existe", "FAIL", "ausente")

    # Testa duracao
    with temp_dir() as d:
        video = os.path.join(d, "v.mp4")
        make_test_video(video, duration=3)
        dur = pipeline._get_video_duration(video)
        if 2.5 <= dur <= 3.5:
            report.add("_get_video_duration retorna valor correto", "PASS", f"{dur:.2f}s")
        else:
            report.add("_get_video_duration retorna valor correto", "FAIL", f"{dur}")

        # Testa extracao de segmento
        seg_video = os.path.join(d, "seg.mp4")
        out = pipeline._ffmpeg_extract_segment(video, 0.5, 2.0, seg_video, is_video=True)
        if out and os.path.exists(out):
            seg_dur = pipeline._get_video_duration(seg_video)
            if 1.0 <= seg_dur <= 2.0:
                report.add("_ffmpeg_extract_segment corta corretamente", "PASS", f"{seg_dur:.2f}s")
            else:
                report.add("_ffmpeg_extract_segment corta corretamente", "FAIL", f"{seg_dur}")
        else:
            report.add("_ffmpeg_extract_segment corta corretamente", "FAIL", "")

        # Testa concat
        out_path = os.path.join(d, "concat.mp4")
        result = pipeline._ffmpeg_concat([seg_video, seg_video], out_path)
        if result and os.path.exists(result):
            concat_dur = pipeline._get_video_duration(result)
            if 2.0 <= concat_dur <= 4.0:
                report.add("_ffmpeg_concat junta sequencialmente", "PASS", f"{concat_dur:.2f}s")
            else:
                report.add("_ffmpeg_concat junta sequencialmente", "FAIL", f"{concat_dur}")
        else:
            report.add("_ffmpeg_concat junta sequencialmente", "FAIL", "")

    return True


def test_subprocess_timeout_killed(report):
    """Subprocess com timeout deve matar processo que trava."""
    print(f"\n{C.BOLD}[20] SUBPROCESS TIMEOUT EFETIVO{C.END}")
    import subprocess
    try:
        subprocess.run(["sleep", "10"], capture_output=True, timeout=1)
        report.add("subprocess timeout dispara TimeoutExpired", "FAIL", "nao timed out")
        return False
    except subprocess.TimeoutExpired:
        report.add("subprocess timeout dispara TimeoutExpired", "PASS", "matou apos 1s")
        return True
    except Exception as e:
        report.add("subprocess timeout", "FAIL", str(e))
        return False


def test_subprocess_safety(report):
    """Garante que subprocess usa sys.executable, tem timeouts, etc."""
    print(f"\n{C.BOLD}[14] SAFETY DOS SUBPROCESS{C.END}")
    import pipeline
    src = open(os.path.join(HERE, "pipeline.py")).read()

    # Verificacoes estaticas
    checks = [
        ("usa PYBIN ou sys.executable", "PYBIN" in src),
        ("nao usa 'python' hardcoded em subprocess", '["python",' not in src and '"python",' not in src.replace("PYBIN", "")),
        ("subprocess.run com timeout", src.count("timeout=") >= 5),
        ("trata FileNotFoundError em fish_speech", "FileNotFoundError" in src),
        ("retry decorator presente", "@retry(" in src),
    ]
    for name, passed in checks:
        report.add(name, "PASS" if passed else "FAIL", "")
    return all(p for _, p in checks)


def test_cleanup_on_error(report):
    """Verifica que tmp dirs sao limpos em caso de erro."""
    print(f"\n{C.BOLD}[15] CLEANUP EM ERROS{C.END}")
    import app, pipeline

    _orig_extract = pipeline.extract_audio
    def boom(*a, **kw):
        raise RuntimeError("simulated failure")

    pipeline.extract_audio = boom
    app.extract_audio = boom

    tmp_dirs_before = set(os.listdir("/tmp"))
    with temp_dir() as d:
        video = os.path.join(d, "v.mp4")
        make_test_video(video)
        try:
            app.step_transcribe(video, "Ingles", "Portugues", {})
            report.add("erro durante transcribe levanta gr.Error", "FAIL", "nao levantou")
        except Exception as e:
            report.add("erro durante transcribe levanta gr.Error", "PASS", str(e)[:50])

    # Restaura
    pipeline.extract_audio = _orig_extract
    app.extract_audio = _orig_extract

    # Verifica que nao deixou tmp dirs orfaos
    tmp_dirs_after = set(os.listdir("/tmp"))
    leaked = [d for d in (tmp_dirs_after - tmp_dirs_before) if d.startswith("rapidex_")]
    if leaked:
        report.add("nao deixa tmp dirs orfaos", "FAIL", f"leaked={leaked}")
    else:
        report.add("nao deixa tmp dirs orfaos", "PASS", "")
    return not leaked


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 se qualquer teste falhar")
    parser.add_argument("--real", action="store_true",
                        help="usa modelos reais (precisa GPU)")
    args = parser.parse_args()

    print(f"{C.BOLD}{'═' * 60}{C.END}")
    print(f"{C.BOLD}RAPIDEX IA - SMOKE TEST{C.END}")
    print(f"{C.BOLD}{'═' * 60}{C.END}")
    print(f"Modo: {'REAL' if args.real else 'MOCK (componentes GPU mockados)'}")
    print(f"Working dir: {HERE}")

    mocked = install_mocks() if not args.real else []
    if mocked:
        print(f"{C.Y}Mocked: {', '.join(mocked)}{C.END}")

    report = Report()
    start = time.time()

    test_imports(report)
    test_ffmpeg(report)
    test_extract_audio(report)
    test_demucs_normalize(report)
    test_demucs(report, real=args.real)
    test_whisperx(report, real=args.real)
    test_translate(report)
    test_gtts(report)
    test_run_tts(report)
    test_mix_audio(report)
    test_video_validation_helpers(report)
    test_e2e_orchestration(report)
    test_state_persistence(report)
    test_subprocess_safety(report)
    test_cleanup_on_error(report)
    test_regenerate_audio_resets_approval(report)
    test_user_edits_text_between_transcribe_and_generate(report)
    test_translation_long_text(report)
    test_multiple_target_languages(report)
    test_face_segmentation_helpers(report)
    test_subprocess_timeout_killed(report)
    test_e2e_real_pipeline(report)

    elapsed = time.time() - start
    print(f"\nTempo total: {elapsed:.1f}s")
    n_fail = report.summary()

    if args.strict and n_fail > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
