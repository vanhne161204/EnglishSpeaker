"""Phase 0 spike for Shadowing deep scoring (PRD §8.14): is Azure worth it?

Sends one recording and its sentence to Azure Pronunciation Assessment (REST API
for short audio, scripted mode) and prints the scores. Run it on a few of your own
recordings to see whether the scores make sense for Vietnamese learners, and
whether the free F0 tier accepts pronunciation assessment at all.

Set the key first (PowerShell), from the Azure portal -> your Speech resource ->
"Keys and Endpoint":

    $env:AZURE_SPEECH_KEY="..."; $env:AZURE_SPEECH_REGION="southeastasia"

Score your own recording (any 16-bit PCM WAV; it is converted to 16 kHz mono):

    .venv/Scripts/python.exe scripts/check_azure_pronunciation.py my.wav "I went to Da Nang."

Sanity check with a native-like voice made by Gemini TTS (needs GEMINI_API_KEY in
backend/.env). It should score high; if it does not, the setup is wrong:

    .venv/Scripts/python.exe scripts/check_azure_pronunciation.py --tts "I went to Da Nang."

Limits: at most 30 seconds of audio for pronunciation assessment. Each run costs
about $0.0004 for 1 second of audio on the paid tier, or nothing within F0.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import os
import sys
import wave
from array import array
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TARGET_RATE = 16_000
MAX_SECONDS = 30
#: Azure S1 speech to text ($1.0/h) + enhanced add-on ($0.3/h), Southeast Asia.
PRICE_PER_HOUR = 1.3


def _env(name: str, default: str | None = None) -> str | None:
    """Read a variable from the environment, then from backend/.env."""
    if os.environ.get(name):
        return os.environ[name]
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"')
    return default


def to_16k_mono(wav_bytes: bytes) -> tuple[bytes, float]:
    """Any 16-bit PCM WAV -> 16 kHz mono WAV (Azure's format). Returns (wav, seconds)."""
    with wave.open(io.BytesIO(wav_bytes)) as source:
        channels = source.getnchannels()
        width = source.getsampwidth()
        rate = source.getframerate()
        frames = source.readframes(source.getnframes())
    if width != 2:
        raise SystemExit(f"Need 16-bit PCM WAV, got {8 * width}-bit.")
    samples = array("h")
    samples.frombytes(frames)
    if sys.byteorder == "big":
        samples.byteswap()
    mono = (
        [sum(samples[i : i + channels]) // channels for i in range(0, len(samples), channels)]
        if channels > 1
        else list(samples)
    )
    if rate != TARGET_RATE and mono:
        # Linear interpolation: plenty for speech in a spike.
        count = int(len(mono) * TARGET_RATE / rate)
        step = rate / TARGET_RATE
        resampled = array("h")
        for k in range(count):
            position = k * step
            i = int(position)
            nxt = mono[min(i + 1, len(mono) - 1)]
            resampled.append(int(mono[i] + (nxt - mono[i]) * (position - i)))
        out = resampled
    else:
        out = array("h", mono)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(TARGET_RATE)
        target.writeframes(out.tobytes())
    return buffer.getvalue(), len(out) / TARGET_RATE


async def tts_wav(sentence: str) -> bytes:
    from app.ai.providers.gemini_tts import GeminiSynthesizer
    from app.core.config import settings

    key = _env("GEMINI_API_KEY")
    if not key:
        raise SystemExit("--tts needs GEMINI_API_KEY in the environment or backend/.env.")
    synthesizer = GeminiSynthesizer(key, settings.shadowing_tts_model, settings.shadowing_tts_voice)
    clip = await synthesizer.synthesize(sentence)
    return clip.wav


def assess(wav16: bytes, sentence: str) -> httpx.Response:
    key = _env("AZURE_SPEECH_KEY")
    region = _env("AZURE_SPEECH_REGION", "southeastasia")
    if not key:
        raise SystemExit("Set AZURE_SPEECH_KEY (Azure portal -> Speech resource -> Keys).")
    url = _env("AZURE_SPEECH_ENDPOINT") or (
        f"https://{region}.stt.speech.microsoft.com"
        "/speech/recognition/conversation/cognitiveservices/v1"
    )
    parameters = {
        "ReferenceText": sentence,
        "GradingSystem": "HundredMark",
        "Granularity": "Phoneme",
        "Dimension": "Comprehensive",
        "EnableMiscue": "True",
        "EnableProsodyAssessment": "True",
    }
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
        "Accept": "application/json",
        "Pronunciation-Assessment": base64.b64encode(json.dumps(parameters).encode()).decode(),
    }
    return httpx.post(
        url,
        params={"language": "en-US", "format": "detailed"},
        headers=headers,
        content=wav16,
        timeout=30,
    )


def report(response: httpx.Response, seconds: float) -> None:
    print(f"HTTP {response.status_code}")
    if response.status_code != 200:
        print(response.text[:500])
        if response.status_code in (401, 403):
            print("-> Check the key and region. F0 may also not allow this feature.")
        return
    body = response.json()
    print(f"RecognitionStatus: {body.get('RecognitionStatus')}")
    best = (body.get("NBest") or [{}])[0]
    print(f"Heard: {best.get('Display')!r}")
    for name in ("PronScore", "AccuracyScore", "FluencyScore", "CompletenessScore", "ProsodyScore"):
        print(f"  {name:<18} {best.get(name)}")
    print("Words:")
    for word in best.get("Words", []):
        name = word.get("Word", "")
        accuracy = word.get("AccuracyScore")
        print(f"  {name:<16} {accuracy!s:>6}  {word.get('ErrorType')}")
    print(f"Audio {seconds:.1f}s -> about ${seconds / 3600 * PRICE_PER_HOUR:.5f} on the paid tier.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("wav", nargs="?", help="16-bit PCM WAV file to score")
    parser.add_argument("sentence", nargs="?", help="The sentence that was read")
    parser.add_argument("--tts", metavar="SENTENCE", help="Score a Gemini TTS voice instead")
    args = parser.parse_args()

    if args.tts:
        sentence = args.tts
        raw = asyncio.run(tts_wav(sentence))
    elif args.wav and args.sentence:
        sentence = args.sentence
        raw = Path(args.wav).read_bytes()
    else:
        parser.error("give a WAV file and its sentence, or --tts SENTENCE")

    wav16, seconds = to_16k_mono(raw)
    if seconds > MAX_SECONDS:
        raise SystemExit(f"{seconds:.0f}s is too long: pronunciation assessment takes 30s at most.")
    report(assess(wav16, sentence), seconds)


if __name__ == "__main__":
    main()
