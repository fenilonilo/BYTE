# Weather — design (Spec 6)

Date: 2026-10-23. Status: draft, awaiting owner approval.

## Intent

The owner wants Byte to know the weather: the current temperature in their city (Goiânia, GO),
whether it is raining right now, and the forecast for the coming days — and to see all of it
in the web panel, looking as good as the rest of it. They also ask about other cities (before a
trip, say) by voice or chat.

One distinction matters to the owner:

- **Asking** ("vai chover em Floripa no sábado?") → Byte only answers. The panel does not change.
- **Asking to show** ("mostra no painel a previsão de Floripa") → the panel's weather section
  switches to that city.

## Goals

1. A `get_weather` tool: current conditions and forecast for the home city (default) or any city
   by name. Works in chat and live.
2. A `show_weather` tool: switches what the panel's weather section displays. Called only when
   the owner asks to *show/display* (the tool description says so; this is routing, not safety).
3. The panel: a chip next to the clock and a new section **"05 Tempo"**, layout A ("Instrumento",
   chosen by the owner from three mockups — see below).
4. Cheap in tokens: the tool result is a few compact lines, never raw JSON.

## Non-goals

- Proactive weather warnings ("vai chover em 1 h") — no push, no reminder integration. Could plug
  into `ReminderHub` later.
- Weather history, maps, radar, alerts from civil defence, air quality, UV.
- A city picker or search box in the panel. Other cities reach the panel only through Byte.
- More than one city displayed at once.

## Anti-goals

- The panel changing city when the owner only *asked* about another city.
- Hitting the weather provider on every 20 s panel poll.
- A new credential or account to manage.

## Data source (builder's default, owner did not choose)

**Open-Meteo** — free, no key, no account, has a geocoding endpoint:

- Geocoding: `https://geocoding-api.open-meteo.com/v1/search?name=<name>&count=10&language=pt`
- Forecast: `https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..&timezone=auto&forecast_days=7`
  with `current=temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m,is_day`,
  `hourly=temperature_2m,precipitation_probability,weather_code,is_day`,
  `daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max`.

HTTP through `aiohttp` (already a dependency, same as the Google Calendar adapter). No new
package. Fits **Integrations** in `CLAUDE.md`: a driven adapter behind a port, vendor errors
wrapped in a `DomainError` subclass with `__cause__` kept.

"Raining now" = current `weather_code` is drizzle, rain, showers or thunderstorm (WMO 51–67,
80–82, 95–99) **or** current `precipitation > 0`. The WMO-code → condition mapping lives in the
adapter.

## Shape

### Domain (`app/domain/weather.py`)

Frozen dataclasses, stdlib only:

- `Condition` (enum): `clear`, `partly_cloudy`, `cloudy`, `fog`, `drizzle`, `rain`, `storm`.
  (Snow is not needed in Brazil; map snow codes to `cloudy` — *builder's call*.)
- `Place`: `name`, `region` (state / admin1), `country`, `latitude`, `longitude`.
- `CurrentWeather`: `temperature`, `feels_like`, `humidity`, `wind_kmh`, `condition`, `raining`,
  `is_day`.
- `HourlyPoint`: `time` (aware datetime), `temperature`, `rain_chance`, `condition`, `is_day`.
- `DailyForecast`: `date`, `condition`, `min`, `max`, `rain_chance`.
- `Forecast`: `place`, `current`, `hours` (next 24 from now), `days` (7, today first).

### Port (`app/ports/weather.py`)

`WeatherPort(ABC)`:

- `async find_place(query: str) -> Place` — raises `UnknownPlaceError` (new `DomainError`) when
  nothing matches.
- `async forecast(place: Place) -> Forecast` — raises `WeatherUnavailableError` on vendor failure.

Two implementations: `OpenMeteoWeather` (`app/adapters/openmeteo/`) and `InMemoryWeather`
(`app/adapters/memory/`, fixed data, unit tests only). Both pass one port contract suite; the real one under
the `integration` + `slow` markers.

**Place resolution** (*builder's call*): the query may be `"Cidade"` or `"Cidade, UF/estado/país"`.
Search by the part before the comma; if there is a part after it, keep results whose region or
country matches it (accent- and case-insensitive, UF abbreviations for Brazilian states); then take
the first result (Open-Meteo orders by relevance/population).

**Cache**: forecasts cached in the adapter per place for 10 minutes; places cached by query for
the process lifetime. Uses the injected monotonic clock. The cache is a rate guard, not a source of
truth — Open-Meteo is.

### Home city

Config: `BYTE_WEATHER_HOME` (default `"Goiânia, GO"`), resolved once (lazily, first use) through
`find_place`. Added to `.env.example` and `config.py`.

### Displayed city — `WeatherDisplay`

A small application-level holder (singleton via `lru_cache` in `api/deps.py`, like the other
in-process state): the place the panel shows, or `None` meaning home.

- Set by the `show_weather` tool.
- Reset to home by the panel's "voltar para Goiânia" control, or by `show_weather` naming the home
  city.
- In memory only; a restart goes back to home. *Builder's call*: no auto-expiry — it stays until
  the owner switches back.

### Tools (`app/application/tools/weather.py`, new segment `weather`)

| Tool | Args | Confirmation | Effect |
|---|---|---|---|
| `get_weather` | `city?: str` (omitted = home), `days?: int` 1–7 (default 3) | no | Returns compact pt-BR text. |
| `show_weather` | `city?: str` (omitted = home) | no | Sets `WeatherDisplay`; returns one line ("Painel mostrando Florianópolis, SC."). |

Neither is `panel_only`: an ESP32 voice request "mostra no painel…" must work too.

`show_weather`'s description must say: use **only** when the owner asks to show/display/put it on
the panel; for a plain question, use `get_weather`. The `get_weather` description says the
opposite.

`get_weather` result format (example, `days=3`):

```
Goiânia, GO — agora 23°C (sensação 24°), chovendo, umidade 82%, vento 12 km/h.
hoje: 18–27°, chuva 80%, chuva
sex: 17–29°, chuva 20%, parcialmente nublado
sáb: 19–31°, chuva 0%, céu limpo
```

The model already gets the current time through the `Agora:` line, so "sábado" resolves without
help. No hourly data in the tool result (token cost); *builder's call* to add a one-line
"próximas horas" summary ("chuva para por volta das 11h") only if cheap.

Errors: `UnknownPlaceError` → the tool reports "não encontrei a cidade X" to the model;
`WeatherUnavailableError` → "previsão indisponível agora". Never log the city (tool argument).

### API (`/api/v1`)

| Route | Purpose |
|---|---|
| `GET /weather` | Forecast for the displayed city: `place`, `is_home`, `current`, `hours` (24), `days` (7), plus `home_current` (temperature, condition, is_day, raining) for the bar chip. Each part fails on its own, like `GET /state`: `forecast` or `home_current` comes back `null` and is listed in `errors`. |
| `DELETE /weather/display` | Back to home. Returns the same body as `GET /weather`. |

Schemas in `api/schemas.py` (`WeatherSchema`, …). When both fail the body still returns 200
with both `null`; the panel shows the section error like the other sections (*builder's call*,
mirrors `/state`).

**Instant switch (owner's requirement).** A `show_weather` — from the panel, chat or the ESP32 —
must reach an open panel at once, not on a poll. New socket:

| Route | Purpose |
|---|---|
| `WS /ws/panel` | Server → panel pushes. Today one message: `{"type":"weather"}` sent whenever `WeatherDisplay` changes (set or reset). The panel reacts by reloading `GET /weather`. One listener; a new connection replaces the old (close 4000), like `/ws/notifications` and `/ws/terminal`. |

- Auth exactly like the other panel sockets: bearer token as the `["bearer", <token>]`
  subprotocol (`accept_authorized` in `api/auth.py`). Never in the URL.
- `WeatherDisplay` takes an optional listener (an ABC in `application/`, same pattern as
  `TerminalListener` in `project_session.py`); the socket handler registers itself as it. A failed
  send must not fail the tool: the tool's result does not depend on whether a panel is open.
- The panel keeps the socket open while signed in and reconnects with backoff; on every (re)connect
  it reloads `/weather`, so a change made while it was disconnected is never missed.
- The message carries no data on purpose: the panel always reads the truth from `GET /weather`.
- *Builder's call*: the socket is generic (`/ws/panel`, typed messages) so later pushes (a light
  switched by voice) can reuse it — but only `weather` is built now. Bearer auth as everywhere.

### Panel (`web/`)

Layout A — "Instrumento" (mockup kept at
`.superpowers/brainstorm/3603-1792734760/content/tempo-layout.html`, option A):

- **Bar chip**, between the agent state and the clock: animated condition icon + home
  temperature (`23°`). Always the home city. Click scrolls to the section.
- **Section "05 Tempo"** (renumber the following sections), same `.sec` structure as the others:
  - Header: `05 Tempo`, right side `goiânia · agora` (lowercase mono label). When showing another
    city: that city's name plus a ghost button **"voltar para Goiânia"** (`DELETE /weather/display`).
  - **Now**: large animated condition object (≈96×80) + big mono temperature with `°C`, a status
    line in a rain blue (`● chovendo agora` / `sem chuva`), and a meta line
    (`sensação · umidade · vento`).
  - **Next 24 h**: one inline SVG — rain-chance bars (blue, translucent) under an amber
    temperature line, with a few hour labels and the peak temperature labelled.
  - **7 days**: rows `dia · ícone · min · range bar · max · chance%`; the range bar is scaled
    across the week's min/max with a blue→amber gradient (like the mockup).
- **Icons**: drawn in `art.js` in the house style (SVG, lit from the upper left, shared gradients
  in `#art-defs`): sun, moon, partly cloudy (day/night), cloud, fog, drizzle/rain, storm. Motion
  in `style.css`: drifting cloud, falling drops, slowly turning sun rays, a flash for storm. All
  motion off under `prefers-reduced-motion`.
- New colour token `--rain` (≈ `#7fb3d5`) on `:root`.
- **Refresh**: on load, every 10 minutes, on every `/ws/panel` `weather` message, and on every
  `/ws/panel` (re)connect. Not part of the 20 s `/state` poll. A refresh that changed nothing leaves the section alone (same rule as
  `applyState`), so animations do not restart.
- **No weather provider configured switch**: Open-Meteo needs no key, so production always uses
  it; if it is down, the chip hides and the section shows the usual section error.
- **"Clima" vs "Tempo"** (*builder's call*): the air-conditioner section keeps its name. The new
  tool descriptions say "tempo lá fora, previsão, chuva, temperatura da cidade"; the AC tools
  already say "ar-condicionado". Add a prompt/test case "como tá o clima hoje?" → `get_weather`
  only if the model gets it wrong in a manual check.
- Accessible: the section is readable as text (temperature, condition word, "chovendo agora");
  icons are `aria-hidden`. Works at phone width.

Contract additions go in `docs/web-api-contract.md`.

## Constraints

Everything in `CLAUDE.md` applies: hexagonal layers, `pyright --strict`, no Pydantic in
`domain/`, ABC ports, one use case per file if a use case is added, `LoggerPort` only, coverage
≥ 80 %, `ruff`/`pyright`/`pytest` green. No new compose service. No new dependency.

Docs to update in the same change: `CLAUDE.md` (segments table, integrations table, current
state), `.env.example`, `docs/web-api-contract.md`.

## Testing

- Domain: WMO mapping lives in the adapter → tested there with recorded Open-Meteo JSON
  (no network), including "raining now" edge cases (code 3 with `precipitation > 0`; code 61 with
  0).
- Place resolution: `"Goiânia, GO"`, `"Santa Maria, RS"` vs the more populous match, unknown city.
- Cache: second call within 10 min does not hit HTTP; after 10 min it does (injected clock).
- Tools: `get_weather` default home, `days` bounds, unknown city, unavailable; `show_weather`
  sets/resets `WeatherDisplay`.
- API: `GET /weather` home vs displayed, partial failure (`null` + `errors`), `DELETE
  /weather/display`, 401.
- `/ws/panel`: rejects a missing/wrong token; `show_weather` and `DELETE /weather/display` push
  `{"type":"weather"}`; a second connection replaces the first (4000); a dead listener does not
  break the tool.
- Port contract suite against `InMemoryWeather`; against `OpenMeteoWeather` under `integration`.

## Left to the builder

File split inside `adapters/openmeteo/`, exact schema field names, SVG drawing details, the
24 h chart's label density, the exact refresh hook in `app.js`, and anything marked
*builder's call* above.
