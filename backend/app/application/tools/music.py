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

    The model must never invent a uri; it asks for one first (oldest forgotten past `limit`).
    The model sees a short id per uri ("3", not "spotify:track:..."): far fewer tokens."""

    def __init__(self, limit: int = 200) -> None:
        self._limit = limit
        self._ids: dict[str, str] = {}  # uri -> short id, oldest first
        self._uris: dict[str, str] = {}  # short id -> uri
        self._next = 1

    def remember(self, items: tuple[MusicItem, ...]) -> None:
        for item in items:
            short = self._ids.pop(item.uri, None)
            if short is None:
                short, self._next = str(self._next), self._next + 1
                self._uris[short] = item.uri
            self._ids[item.uri] = short
        while len(self._ids) > self._limit:
            del self._uris[self._ids.pop(next(iter(self._ids)))]

    def short(self, uri: str) -> str:
        return self._ids[uri]

    def require(self, ref: str) -> str:
        """A short id (model) or a full uri (control panel) -> the full uri, if one was returned."""
        uri = self._uris.get(ref, ref)
        if uri not in self._ids:
            raise UnknownUriError("uri desconhecida: use search_music ou list_playlists primeiro")
        return uri


def describe_playback(state: PlaybackState) -> str:
    what = "nada" if state.item is None else f"{state.item.name} {state.item.artist}".strip()
    status = "tocando" if state.playing else "pausado"
    return f"{status}: {what} no aparelho {state.device}, volume {state.volume}%"


def describe_items(items: tuple[MusicItem, ...], known: KnownUris) -> str:
    known.remember(items)
    lines = [f"{known.short(i.uri)} | {i.name} {i.artist}".strip() for i in items]
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
        description="Procura músicas, álbuns, playlists ou artistas. Devolve 'id | nome artista'.",
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
        return describe_items(items, self._known)


class ListPlaylists(Tool):
    spec = ToolSpec(
        name="list_playlists",
        description="Lista as playlists do usuário. Devolve 'id | nome'.",
        parameters=object_schema({}),
        segment="music",
    )

    def __init__(self, music: MusicPort, known: KnownUris) -> None:
        self._music = music
        self._known = known

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        items = await self._music.playlists()
        return describe_items(items, self._known)


class PlayMusic(Tool):
    spec = ToolSpec(
        name="play_music",
        description=(
            "Toca um id devolvido por search_music ou list_playlists, ou retoma a reprodução "
            "se nenhum for informado. 'device' move a reprodução para outro aparelho."
        ),
        parameters=object_schema(
            {
                "uri": ("string", "Id a tocar (nunca invente um)."),
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
            uri = self._known.require(uri)
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
        description="Adiciona à fila um id devolvido por search_music ou list_playlists.",
        parameters=object_schema({"uri": ("string", "Id a enfileirar (nunca invente um).")}),
        segment="music",
    )

    def __init__(self, music: MusicPort, known: KnownUris) -> None:
        self._music = music
        self._known = known

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        await self._music.queue(self._known.require(str_arg(args, "uri")))
        return "adicionada à fila"
