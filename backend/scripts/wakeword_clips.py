"""Synthetic pt-BR training clips for the "Ei Byte" wake word (Microsoft Edge TTS, online).

    python scripts/wakeword_clips.py [out_dir]

Writes 16 kHz mono PCM16 WAVs to <out_dir>/synth_positive and <out_dir>/synth_negative.
Only the phrases below leave the machine. Needs: pip install edge-tts soundfile scipy numpy
"""

from __future__ import annotations

import asyncio
import itertools
import sys
import tempfile
from pathlib import Path

import edge_tts
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

VOICES = ["pt-BR-AntonioNeural", "pt-BR-FranciscaNeural", "pt-BR-ThalitaMultilingualNeural"]
RATES = ["-15%", "-5%", "+0%", "+10%", "+20%"]
PITCHES = ["-20Hz", "-10Hz", "+0Hz", "+10Hz", "+20Hz"]
POSITIVE = ["Ei Báite", "Ei Báitchi", "Ei, Báite", "Ei, Báitchi"]
# Near misses first: the model must learn what is NOT the wake word.
HARD_NEGATIVE = [
    "Ei",
    "Báite",
    "Báitchi",
    "Ei Beto",
    "Ei Pedro",
    "Ei Pete",
    "Ei Fabiano",
    "Ei você",
    "Ei, bate aqui",
    "Ei, baita",
    "Uma baita casa",
    "Ei Mateus",
    "Ei Google",
    "Ei Alexa",
    "Ei Siri",
    "Ei Jarvis",
    "Oi Byte",
    "O byte e o bit",
    "Quantos bytes tem?",
    "Ei, espera",
    "Ei, fecha a porta",
    "Ei Bete",
    "Ei Naite",
    "Ei Faite",
    "Ei Chico",
    "Ei, olha só",
]
SENTENCES = [
    "Hoje o dia está bem quente lá fora.",
    "Preciso comprar pão e leite antes do jantar.",
    "Você viu o jogo de ontem à noite?",
    "A reunião foi remarcada para a próxima semana.",
    "Acende a luz da sala, por favor.",
    "Quanto custa uma passagem de ônibus até o centro?",
    "Vou levar o cachorro para passear daqui a pouco.",
    "O trânsito estava horrível hoje cedo.",
    "Minha mãe ligou e perguntou se vamos almoçar com ela.",
    "Tem alguma coisa boa passando na televisão?",
    "Não esquece de pagar a conta de luz amanhã.",
    "Coloca uma música animada para tocar.",
    "O médico disse que preciso beber mais água.",
    "Amanhã eu acordo cedo para ir à academia.",
    "Que horas começa o filme?",
    "Desliga o ar condicionado quando sair do quarto.",
    "A internet está muito lenta hoje.",
    "Eu gosto de café sem açúcar pela manhã.",
    "Já terminou de arrumar a mala da viagem?",
    "Esse restaurante tem uma comida deliciosa.",
    "Chegou uma encomenda para você na portaria.",
    "Vamos jantar fora no sábado, o que acha?",
    "A previsão do tempo diz que vai chover à tarde.",
    "Preciso trocar a lâmpada do corredor.",
    "O aniversário dela é no fim do mês.",
    "Pode abaixar um pouco o volume da televisão?",
    "Eu esqueci o carregador do celular em casa.",
    "Nossa, que calor que está fazendo hoje!",
    "Depois do trabalho eu passo no mercado.",
    "Quem vai buscar as crianças na escola hoje?",
    "O professor explicou a matéria de novo para a turma.",
    "Faz tempo que eu não viajo para a praia.",
    "Deixa a janela aberta que o ar está bom.",
    "Vou fazer um bolo de cenoura para o lanche.",
    "A bateria do notebook está quase acabando.",
    "Me lembra de ligar para o dentista na segunda.",
    "Qual é a senha do wifi da casa nova?",
    "Hoje eu não estou com vontade de cozinhar.",
    "Esse livro é muito bom, você precisa ler.",
    "Fecha a porta da cozinha, está entrando barulho.",
    "A feira de domingo estava cheia de gente.",
    "Vamos assistir um episódio antes de dormir.",
    "O preço da gasolina subiu de novo esta semana.",
    "Meu irmão comprou um computador novo.",
    "Eu preciso terminar esse relatório até as cinco.",
    "Tem café fresco na garrafa térmica.",
    "A reunião de hoje foi bem produtiva.",
    "Pode me passar o sal, por favor?",
    "Vou tomar um banho e já volto.",
    "O gato pulou em cima da mesa outra vez.",
]
SAMPLE_RATE = 16_000
SILENCE_DB = -40.0
PAD_SECONDS = 0.12
CONCURRENCY = 4


def trim_to_speech(audio: np.ndarray) -> np.ndarray:
    """Cut the silence TTS puts around the phrase, keeping a short pad."""
    loud = np.flatnonzero(np.abs(audio) > 10 ** (SILENCE_DB / 20) * np.abs(audio).max())
    if loud.size == 0:
        return audio
    pad = int(PAD_SECONDS * SAMPLE_RATE)
    return audio[max(loud[0] - pad, 0) : loud[-1] + pad]


async def synth(
    sem: asyncio.Semaphore, text: str, voice: str, rate: str, pitch: str, path: Path
) -> bool:
    if path.exists():  # noqa: ASYNC240 - resume a partial run
        return True
    async with sem:
        last = ""
        for _ in range(3):
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    mp3 = Path(tmp) / "x.mp3"
                    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(str(mp3))
                    audio, sr = sf.read(mp3, dtype="float32")
                if audio.ndim > 1:
                    audio = audio.mean(axis=1)
                audio = trim_to_speech(resample_poly(audio, SAMPLE_RATE, sr))
                part = path.with_suffix(
                    ".tmp"
                )  # never leave a half-written clip for the resume check
                sf.write(
                    part,
                    (np.clip(audio, -1, 1) * 32767).astype("<i2"),
                    SAMPLE_RATE,
                    subtype="PCM_16",
                    format="WAV",
                )
                part.replace(path)
                return True
            except Exception as exc:
                last = type(exc).__name__
                await asyncio.sleep(2)
        print(f"skipped {path.name}: {last}", flush=True)
    return False


async def main(out: Path) -> None:
    sem = asyncio.Semaphore(CONCURRENCY)
    jobs: list[tuple[str, str, str, str, Path]] = []
    pos, neg = out / "synth_positive", out / "synth_negative"
    pos.mkdir(parents=True, exist_ok=True)
    neg.mkdir(parents=True, exist_ok=True)
    for i, (text, voice, rate, pitch) in enumerate(
        itertools.product(POSITIVE, VOICES, RATES, PITCHES)
    ):
        jobs.append((text, voice, rate, pitch, pos / f"p{i:04d}.wav"))
    for i, (text, voice, rate) in enumerate(
        itertools.product(HARD_NEGATIVE + SENTENCES, VOICES, ["-5%", "+10%"])
    ):
        jobs.append((text, voice, rate, "+0Hz", neg / f"n{i:04d}.wav"))
    done = 0
    for coro in asyncio.as_completed([synth(sem, *job) for job in jobs]):
        done += await coro
        if done % 100 == 0:
            print(f"{done}/{len(jobs)}", flush=True)
    print(f"done: {done}/{len(jobs)} clips in {out}")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1] if len(sys.argv) > 1 else "wakeword_data")))
