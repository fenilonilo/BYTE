# Ar-condicionado — Controle via LG ThinQ

Dispositivo: **Ar-condicionado** (alias no app ThinQ), modelo `RAC_056905_WW`, tipo `DEVICE_AIR_CONDITIONER`.
Biblioteca: `thinqconnect` (ThinQ Connect API, PAT). Código: `app/adapters/thinq/thinq_climate.py`.

## Configuração

| Variável | Obrigatória | Padrão | Nota |
|---|---|---|---|
| `BYTE_THINQ_ACCESS_SECRET` | sim | — | Personal Access Token (https://connect-pat.lgthinq.com) |
| `BYTE_THINQ_COUNTRY` | não | `BR` | |
| `BYTE_THINQ_CLIENT_ID` | não | `byte-thinq-client` | qualquer string estável |

Instalar: `pip install -e ".[thinq]"`. O dispositivo é achado pelo alias (sem id no `.env`).

## Arquitetura

```
ClimatePort (app/ports/climate.py)
├── InMemoryClimate  (app/adapters/memory/)   testes
└── ThinQClimate     (app/adapters/thinq/)    produção
```

`ClimatePort`:

| Método | Função |
|---|---|
| `devices()` | nomes dos ACs da conta |
| `get_state(device)` | `ClimateState` atual |
| `apply(device, ClimateChange)` | aplica mudança parcial, devolve o novo estado |

Nome desconhecido → `UnknownClimateDeviceError`. Falha da API → `ClimateError` (com o código ThinQ na mensagem). O nome não diferencia maiúsculas.

## Funções mapeadas

Campo de `ClimateChange` → recurso ThinQ. Cada campo vira uma chamada de controle própria.

| Função | Campo | Valores | Payload ThinQ |
|---|---|---|---|
| Ligar / desligar | `power` | `True` / `False` | `{"operation": {"airConOperationMode": "POWER_ON" \| "POWER_OFF"}}` |
| Modo | `mode` | `cool`, `dry`, `fan`, `auto` | `{"airConJobMode": {"currentJobMode": "COOL" \| "AIR_DRY" \| "FAN" \| "AUTO"}}` |
| Temperatura-alvo | `target_temperature` | 18–30 °C, passo 0.5 | `{"temperature": {"targetTemperature": N, "unit": "C"}}` |
| Ventilação | `fan_speed` | `auto`, `low`, `mid`, `high` | `{"airFlow": {"windStrength": "AUTO" \| "LOW" \| "MID" \| "HIGH"}}` |
| Ventilação natural | `fan_speed` | `nature` | `{"airFlow": {"windStrengthDetail": "NATURE"}}` |
| Swing vertical | `swing` | `True` / `False` | `{"windDirection": {"rotateUpDown": bool}}` |
| Economia de energia | `power_save` | `True` / `False` | `{"powerSave": {"powerSaveEnabled": bool}}` |
| Luz do display | `display_light` | `True` / `False` | `{"display": {"light": "ON" \| "OFF"}}` |
| Timer: desligar em | `stop_in_minutes` | 0–1440 (0 cancela) | `{"timer": {"relativeHourToStop": h, "relativeMinuteToStop": m}}`; cancelar: `{"timer": {"relativeStopTimer": "UNSET"}}` |
| Timer: ligar em | `start_in_minutes` | 0–1440 (0 cancela) | `{"timer": {"relativeHourToStart": h, "relativeMinuteToStart": m}}`; cancelar: `{"timer": {"relativeStartTimer": "UNSET"}}` |
| Sleep timer | `sleep_in_minutes` | 0–1440 (0 cancela) | `{"sleepTimer": {"relativeHourToStop": h, "relativeMinuteToStop": m}}`; cancelar: `{"sleepTimer": {"relativeStopTimer": "UNSET"}}` |

Ordem de envio: power, modo, temperatura, ventilação, swing, economia, display, timers. O power vai primeiro para os demais ajustes cair num aparelho ligado.

## Estado lido (`ClimateState`)

| Campo | Origem ThinQ |
|---|---|
| `power` | `operation.airConOperationMode == POWER_ON` |
| `mode` | `airConJobMode.currentJobMode` |
| `target_temperature` | `temperature.targetTemperature` |
| `current_temperature` | `temperature.currentTemperature` |
| `fan_speed` | `airFlow.windStrength`; `nature` quando `windStrengthDetail == NATURE` |
| `swing` | `windDirection.rotateUpDown` |
| `power_save` | `powerSave.powerSaveEnabled` |
| `display_light` | `display.light == ON` |
| `stop_timer_minutes` / `start_timer_minutes` | `timer.relative{Stop,Start}Timer == SET` → horas×60 + minutos, senão `None` |
| `sleep_timer_minutes` | `sleepTimer`, mesma regra |
| `filter_used_hours` | `filterInfo.usedTime` (a unidade não consta no perfil; foi lida como horas) |
| `has_error` | `runState.currentState == ERROR` |

Só leitura, sem uso no controle: `minTargetTemperature`, `maxTargetTemperature`, `filterInfo.filterLifetime`, `temperatureInUnits` (°F). Notificação push disponível: `WATER_IS_FULL` (não assinada).

## Regras e limites

- **Aparelho desligado recusa ajustes** (`COMMAND_NOT_SUPPORTED_IN_POWER_OFF`, 2304). Mande `power=True` na mesma mudança ou antes. O adapter já envia o power primeiro.
- Os timers de desligar e ligar só aceitam `UNSET` como escrita de estado; para armar, escreva hora e minuto.
- Temperatura fora de 18–30 ou fora do passo de 0.5 é rejeitada no domínio, antes de chamar a API.
- Uma `ClimateChange` vazia é rejeitada (`ClimateError`).
- O adapter abre uma sessão HTTP por chamada (`# ponytail:`). Compartilhar uma sessão se latência ou rate limit pesarem.

## Verificação ao vivo

Testado no aparelho real: ligar/desligar, temperatura, ventilação (low, nature), swing, economia, display, modo e os timers de desligar e sleep (definir e cancelar). Estado original restaurado depois.

**Não testado ao vivo:** timer de ligar (`start_in_minutes`). A ThinQ pode exigir o aparelho desligado para armá-lo.

## Pendente

- Tools do agente (`requires_confirmation` para ligar/desligar, pois é ação física) quando existirem `Tool` e `ToolRunner` (Spec 1). Segmento `home`.
- Contract suite do `ClimatePort` rodando contra os dois adapters (o real com marcador `integration`).
