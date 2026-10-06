# Spotfy_Controle — controle do Spotify (segmento `music`)

> Notas para construir a tool de música do agente. Atualizado: 2026-10-05.
> **Nunca colocar refresh token neste arquivo.** Credenciais vão no `.env` (gitignored).

## Status atual

| Item | Estado |
|---|---|
| Conta | Spotify **Premium** (obrigatório para controlar reprodução) |
| App (Developer Dashboard) | criado, modo *Development* (só a conta do dono) |
| Client ID | `bf76bfb8ad3a457c83e0650e6736ab0b` (não é segredo; PKCE não usa Client Secret) |
| Redirect URI cadastrado | `http://127.0.0.1:8888/callback` (`localhost` não é aceito) |
| Auth | OAuth 2.0 Authorization Code + **PKCE** |
| Refresh token | no `.env` como `BYTE_SPOTIFY_REFRESH_TOKEN` |
| Dispositivo de saída | Google Nest Mini, aparece no Spotify Connect como **`BatCaverna`** |
| `.env` | `BYTE_SPOTIFY_CLIENT_ID`, `BYTE_SPOTIFY_REFRESH_TOKEN`, `BYTE_SPOTIFY_DEVICE=BatCaverna` |
| Port + domain + adapter | **prontos**: `MusicPort`, `SpotifyMusic`, `InMemoryMusic` |
| Teste real no Nest | **passou**: devices, estado, playlists, volume, pause, resume, next, busca |
| `Tool`s + segmento `music` | **não feito** (depende do `ToolRunner`, ainda não existe) |

Dispositivos vistos pela API: `BatCaverna` (Nest Mini) e `S24 Ultra de Felipe` (celular).

## Mapa de funções

| Grupo | Função | Método no `MusicPort` | Endpoint Spotify |
|---|---|---|---|
| Reprodução | tocar faixa (`uri`) | `play(uri)` | `PUT /me/player/play` `{"uris":[...]}` |
| Reprodução | tocar álbum/playlist/artista | `play(uri)` | `PUT /me/player/play` `{"context_uri":...}` |
| Reprodução | retomar | `play()` | `PUT /me/player/play` |
| Reprodução | pausar | `apply(paused=True)` | `PUT /me/player/pause` |
| Reprodução | próxima / anterior | `apply(skip=Skip.NEXT/PREVIOUS)` | `POST /me/player/next`, `/previous` |
| Reprodução | ir para posição | `apply(seek_ms=...)` | `PUT /me/player/seek` |
| Modo | volume 0-100 | `apply(volume=...)` | `PUT /me/player/volume` |
| Modo | shuffle | `apply(shuffle=...)` | `PUT /me/player/shuffle` |
| Modo | repeat off/track/context | `apply(repeat=...)` | `PUT /me/player/repeat` |
| Fila | adicionar à fila | `queue(uri)` | `POST /me/player/queue` |
| Estado | o que está tocando | `state()` | `GET /me/player` |
| Dispositivos | listar | `devices()` | `GET /me/player/devices` |
| Dispositivos | mover reprodução | `play(device=nome)` | `PUT /me/player/play?device_id=` |
| Busca | faixa/álbum/playlist/artista | `search(query, kind)` | `GET /search` |
| Biblioteca | listar playlists | `playlists()` | `GET /me/playlists` |

Fora do escopo por ora (YAGNI): curtir/descurtir faixa, criar/editar playlist, histórico.

Regras do projeto:
- A tool recebe **nome de dispositivo** ("BatCaverna"), nunca `device_id`. O adapter resolve o id pela lista da API.
- `uri` vem de resultado de `search`/`playlists`, nunca inventada pelo modelo.
- Nada aqui é destrutivo/físico, então **sem** `requires_confirmation`.
- Não logar nome de faixa, busca nem resposta; só tool, duração e status.

## Scopes pedidos

`user-read-playback-state`, `user-modify-playback-state`, `user-read-currently-playing`, `playlist-read-private`.

Para curtir faixas depois: `user-library-modify` + `user-library-read` (precisa rodar o login de novo).

## Como (re)fazer o login

1. Redirect URI `http://127.0.0.1:8888/callback` cadastrado no app (Settings → Redirect URIs → Add → Save).
2. `python scripts/spotify_login.py <client_id>`: abre o navegador, autorizar.
3. O script imprime `BYTE_SPOTIFY_REFRESH_TOKEN=...`; copiar para o `.env`.
4. O adapter renova o access token sozinho (expira em ~1h) e guarda o refresh token novo, se o Spotify mandar.

Erros já vistos:
- `redirect_uri: Not matching configuration` → URI não cadastrado, ou com espaço/`/` a mais.
- `KeyError: 'devices'` → resposta JSON descartada porque `Content-Length` vinha ausente (chunked). Corrigido: o adapter checa `content_type`, não `content_length`.

## Pegadinhas

- **Dispositivo Cast (Nest Mini)**: só aparece na lista da API se o Spotify o viu recentemente na rede. Se `play` der `unknown device`, tocar algo no Nest pelo app do Spotify uma vez.
- **Estado atrasado**: logo depois de um comando, `GET /me/player` pode devolver o valor antigo. O adapter espera `SETTLE_SECONDS` (0,7 s) antes de ler. Para **volume** o Nest demora mais, então `apply(volume=N)` devolve `N` direto, em vez do valor lido da API.
- **Sem dispositivo ativo**: comandos como pausar/volume dão 404 `no active device`. Comece com `play()`, que usa `BYTE_SPOTIFY_DEVICE`.
- **Modo Development**: busca limitada (adapter usa `limit=5`; o teto é 10). Algumas rotas da API foram restringidas para apps em Development.
- **Playlists com emoji**: o terminal Windows (cp1252) quebra no `print`; usar `PYTHONIOENCODING=utf-8` em scripts de teste. Não é bug do adapter.

## Arquivos

- `app/domain/music.py`: `MusicItem`, `PlaybackState`, `PlaybackChange`, `Repeat`, `MediaKind`, `Skip`
- `app/ports/music.py`: `MusicPort`
- `app/adapters/spotify/spotify_music.py`: adapter real (aiohttp; extra `spotify`)
- `app/adapters/memory/in_memory_music.py`: adapter para testes
- `app/api/deps.py`: `get_music()`
- `scripts/spotify_login.py`: login único (PKCE)
- `tests/unit/domain/test_music.py`, `tests/unit/adapters/test_in_memory_music.py`, `tests/unit/adapters/test_spotify_music.py`

## Próximos passos

1. Esperar o `ToolRunner` / `Registry[Tool]` (Spec 1) e então escrever os `Tool`s em `application/tools/`, registrados no segmento `music` em `api/deps.py`.
2. Suite de contrato do `MusicPort`, rodando contra o in-memory (e o Spotify com marcador `integration`).
3. Opcional: curtir/descurtir faixa; trocar a espera fixa por polling se o estado atrasado incomodar.
