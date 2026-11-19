from __future__ import annotations

import re
import unicodedata

MAX_WORDS = 5

_YES = frozenset(
    {
        "sim",
        "pode",
        "confirmo",
        "confirma",
        "confirmado",
        "claro",
        "ok",
        "okay",
        "positivo",
        "autorizo",
        "isso",
        "certo",
    }
)

_DENY = frozenset(
    {
        "nao",
        "nem",
        "nunca",
        "negativo",
        "cancela",
        "cancelar",
        "para",
        "pare",
        "parar",
        "espera",
        "espere",
        "deixa",
        "deixe",
        "deixar",
        "esquece",
        "esqueca",
        "esquecer",
        "depois",
    }
)

_PHRASES = ("manda ver",)


def _words(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z]+", folded.lower())


def is_affirmative(text: str) -> bool:
    """True only for a short, unambiguous pt-BR "yes". The deny list always wins."""
    words = _words(text)
    if not words or len(words) > MAX_WORDS:
        return False
    if _DENY.intersection(words):
        return False
    joined = " ".join(words)
    return bool(_YES.intersection(words)) or any(p in joined for p in _PHRASES)
