from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.tool import Tool
from app.application.tools.args import (
    object_schema,
    opt_bool,
    opt_enum,
    opt_int,
    opt_str,
    str_arg,
)
from app.domain.exceptions import UnknownUriError
from app.domain.music import MediaKind, PlaybackChange, Repeat, Skip
from app.domain.tools import ToolSpec

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from app.domain.music import MusicItem, PlaybackState
    from app.ports.music import MusicPort


class KnownUris:
    """URIs the model may play: only ones that a search or the playlists returned.

    The model must never invent a uri; it asks for one first (oldest forgotten past `limit`)."""

    def __init__(self, limit: int = 200) -> None:
        self._limit = limit
        self._uris: dict[str, None] = {}

    def remember(self, items: tuple[MusicItem, ...]) -> None:
        for item in items:
            self._uris.pop(item.uri, None)
            self._uris[item.uri] = None
        while len(self._uris) > self._limit:
            del self._uris[next(iter(self._uris))]

    def require(self, uri: str) -> str:
        if uri not in self._uris:
            raise UnknownUriError("uri desconhecida: use search_music ou list_playlists primeiro")
        return uri


def describe_playback(state: PlaybackState) -> str:
    what = "nada" if state.item is None else f"{state.item.name} {state.item.artist}".strip()
    status = "tocando" if state.playing else "pausado"
    return f"{status}: {what} no aparelho {state.device}, volume {state.volume}%"


def describe_items(items: tuple[MusicItem, ...]) -> str:
    lines = [f"{i.uri} | {i.name} {i.artist}".strip() for i in items]
    return "; ".join(lines) or "nada encontrado"


class MusicState(Tool):
    spec = ToolSpec(
        name="music_state",
        description="Mostra o que está tocando agora, o volume e o aparelho.",
        parameters=object_schema({}),
        segment="music",
    )

    def __init__(self, music: MusicPort) -> None:
        self._music = music

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        return describe_playback(await self._music.state())


class ListMusicDevices(Tool):
    spec = ToolSpec(
        name="list_music_devices",
        description="Lista os aparelhos onde a música pode tocar (pelo nome).",
        parameters=object_schema({}),
        segment="music",
    )

    def __init__(self, music: MusicPort) -> None:
        self._music = music

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        return "; ".join(await self._music.devices()) or "nenhum aparelho disponível"


class SearchMusic(Tool):
    spec = ToolSpec(
        name="search_music",
        description="Procura músicas, álbuns, playlists ou artistas. Devolve 'uri | nome artista'.",
        parameters=object_schema(
            {
                "query": ("string", "O que procurar."),
                "kind": ("string", "track, album, playlist ou artist (padrão track)."),
            },
            required=["query"],
        ),
        segment="music",
    )

    def __init__(self, music: MusicPort, known: KnownUris) -> None:
        self._music = music
        self._known = known

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        kind = opt_enum(args, "kind", MediaKind) or MediaKind.TRACK
        items = await self._music.search(str_arg(args, "query"), kind)
        self._known.remember(items)
        return describe_items(items)


class ListPlaylists(Tool):
    spec = ToolSpec(
        name="list_playlists",
        description="Lista as playlists do usuário. Devolve 'uri | nome'.",
        parameters=object_schema({}),
        segment="music",
    )

    def __init__(self, music: MusicPort, known: KnownUris) -> None:
        self._music = music
        self._known = known

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        items = await self._music.playlists()
        self._known.remember(items)
        return describe_items(items)


class PlayMusic(Tool):
    spec = ToolSpec(
        name="play_music",
        description=(
            "Toca uma uri devolvida por search_music ou list_playlists, ou retoma a reprodução "
            "se uri não for informada. 'device' move a reprodução para outro aparelho."
        ),
        parameters=object_schema(
            {
                "uri": ("string", "Uri a tocar (nunca invente uma)."),
                "device": ("string", "Nome do aparelho de destino."),
            },
            required=[],
        ),
        segment="music",
    )

    def __init__(self, music: MusicPort, known: KnownUris) -> None:
        self._music = music
        self._known = known

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        uri = opt_str(args, "uri")
        if uri is not None:
            self._known.require(uri)
        return describe_playback(await self._music.play(uri, opt_str(args, "device")))


class ControlMusic(Tool):
    spec = ToolSpec(
        name="control_music",
        description=(
            "Pausa, volume, aleatório, repetição, pular ou avançar. Só informe o que mudar."
        ),
        parameters=object_schema(
            {
                "paused": ("boolean", "true pausa, false retoma."),
                "volume": ("integer", "Volume de 0 a 100."),
                "shuffle": ("boolean", "Modo aleatório."),
                "repeat": ("string", "off, track ou context."),
                "skip": ("string", "next ou previous."),
                "seek_ms": ("integer", "Posição em milissegundos."),
            },
            required=[],
        ),
        segment="music",
    )

    def __init__(self, music: MusicPort, on_volume: Callable[[int], None] | None = None) -> None:
        self._music = music
        self._on_volume = on_volume

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        change = PlaybackChange(
            paused=opt_bool(args, "paused"),
            volume=opt_int(args, "volume"),
            shuffle=opt_bool(args, "shuffle"),
            repeat=opt_enum(args, "repeat", Repeat),
            seek_ms=opt_int(args, "seek_ms"),
            skip=opt_enum(args, "skip", Skip),
        )
        state = await self._music.apply(change)
        if change.volume is not None and self._on_volume is not None:
            self._on_volume(change.volume)
        return describe_playback(state)


class QueueMusic(Tool):
    spec = ToolSpec(
        name="queue_music",
        description="Adiciona à fila uma uri devolvida por search_music ou list_playlists.",
        parameters=object_schema({"uri": ("string", "Uri a enfileirar (nunca invente uma).")}),
        segment="music",
    )

    def __init__(self, music: MusicPort, known: KnownUris) -> None:
        self._music = music
        self._known = known

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        await self._music.queue(self._known.require(str_arg(args, "uri")))
        return "adicionada à fila"
