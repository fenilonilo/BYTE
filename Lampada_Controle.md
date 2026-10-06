# Lampada_Controle — controle da lâmpada Tuya (segmento `home`)

> Notas para construir a tool Tuya do agente `home`. Atualizado: 2026-10-05.
> **Nunca colocar Local Key / Access Secret neste arquivo.** Credenciais vão no `.env` (gitignored).

## Status atual

| Item | Estado |
|---|---|
| Python | 3.13.5 (anaconda) |
| `tinytuya` | 1.20.0 instalado (`pip install tinytuya`) |
| Scan LAN (broadcast, 20s), após mover p/ mesma rede | **1 dispositivo achado** |
| Scan LAN forçado `192.168.0.0/24` (30s) | **0 dispositivos** |
| Conta iot.tuya.com / Cloud Project | feito; trial renovado (região `us`) |
| Wizard / `getdevices()` | feito; `local_key` (16 chars) no `.env` |
| `dev_id` | `eb7c0d8b57531cb337uy7v` (id não é segredo) |
| IP | `192.168.0.227` (reservar no DHCP) |
| Protocolo | 3.3 |
| productKey | `keypymhxrj35tnqj` |
| `local_key` | no `.env` como `BYTE_TUYA_LOCAL_KEY` |
| Mapa de DPS da lâmpada | confirmado (ver abaixo) |
| Controle local | **funciona**; adapter + port + testes prontos |

Rede do PC: Wi-Fi `192.168.0.143/24` (outras interfaces são WSL/VirtualBox, irrelevantes).

### Por que o scan achou 0
Causas prováveis, da mais para a menos provável:
1. Lâmpada em outra rede/VLAN/SSID (ex.: rede 2.4 GHz separada, guest) → broadcast UDP 6666/6667 não chega.
2. Lâmpada desligada, sem Wi-Fi, ou ainda não pareada.
3. Firewall do Windows bloqueando UDP 6666/6667/7000 de entrada (Python precisa de regra em rede Privada).
4. Roteador com "AP isolation"/"client isolation" ligado.
5. Protocolo 3.5 usa porta 7000 (tinytuya 1.20 já cobre).

## Passo a passo (do usuário)

1. Parear a lâmpada no app Smart Life (reset conforme manual: ligar/desligar ~3x até piscar).
   Rede **2.4 GHz**, mesma rede do PC/servidor.
2. Criar conta em <https://iot.tuya.com> → Cloud → Create Cloud Project.
   - Data center: **Western America (`us`)** (relato de usuário BR que só conseguiu assim). Se o app não vincular, testar *Central Europe* (`eu`) ou o data center que o Smart Life usa.
   - Development method: *Smart Home*.
3. Em *Service API*, confirmar **IoT Core** e **Authorization** (e idealmente *Device Status Notification*).
4. Em *Devices → Link Tuya App Account → Add App Account*, escanear o QR com o Smart Life.
5. Do projeto, pegar **Access ID** e **Access Secret** (aba *Overview*).
6. Rodar o wizard (pasta fora do repo ou gitignored — gera `devices.json`, `tuya-raw.json`, `tinytuya.json`, `snapshot.json` com keys):
   ```
   python -m tinytuya wizard
   ```
   Pede: API Key (Access ID), API Secret, região (`us`), e um Device ID qualquer (opcional).
7. Reservar IP da lâmpada no roteador (reserva DHCP por MAC).

## O que preciso do usuário

- [ ] Access ID e Access Secret do Cloud Project (passar via arquivo `.env`, **não** por chat se possível)
- [ ] Região escolhida (`us`/`eu`/`cn`/`in`)
- [ ] Marca/modelo da lâmpada (colorida RGB? só branca? temperatura de cor?)
- [ ] Confirmar: lâmpada e PC no **mesmo Wi-Fi/sub-rede**? Lâmpada aparece online no Smart Life?
- [ ] IP da lâmpada (app Smart Life → dispositivo → ícone lápis → *Device Information*, ou lista de clientes do roteador)
- [ ] Se usuário preferir, rodar o wizard ele mesmo (`! python -m tinytuya wizard` no prompt) e eu leio o `devices.json`

## Comandos de diagnóstico

```
python -m tinytuya scan                      # descobre IP + versão do protocolo
python -m tinytuya scan -force 192.168.0.0/24
python -m tinytuya wizard                    # baixa id + local_key da nuvem
python -m tinytuya snapshot                  # status de cada device do snapshot
```

Liberar firewall (PowerShell admin), se for o caso:
```
New-NetFirewallRule -DisplayName "Tuya UDP in" -Direction Inbound -Protocol UDP -LocalPort 6666,6667,7000 -Action Allow -Profile Private
```

## Teste de controle local (rascunho — não validado)

```python
import tinytuya

d = tinytuya.BulbDevice(dev_id="ID", address="192.168.0.X", local_key="KEY", version=3.3)
print(d.status())                 # DPS reais — ver mapa abaixo
d.turn_on()
d.set_brightness_percentage(40)
d.set_colour(255, 80, 0)
d.turn_off()
```
Se `BulbDevice` não casar com os DPS: `d.set_value(20, True)` (DPS bruto).
Versão do protocolo errada → erro/sem resposta; tentar 3.3 → 3.4 → 3.5.

## Mapa completo de funções (confirmado na lâmpada real, controle local v3.3)

Dispositivo: *Smart Lâmpada Wi-Fi V4 EB*, categoria `dj`, productKey `keypymhxrj35tnqj`. RGB + branco ajustável.

| DPS | Código Tuya | Função | Valores | Exposto na API |
|---|---|---|---|---|
| 20 | `switch_led` | liga/desliga | bool | `power` |
| 21 | `work_mode` | modo | `white` `colour` `scene` `music` | derivado do "look" |
| 22 | `bright_value_v2` | brilho branco | 10–1000 (1–100 %) | `brightness` |
| 23 | `temp_value_v2` | temperatura (quente→fria) | 0–1000 (0–100 %) | `color_temperature` |
| 24 | `colour_data_v2` | cor `HHHHSSSSVVVV` hex | H 0–360, S/V 0–1000 | `color` (hue, sat %, brilho %) |
| 25 | `scene_data_v2` | cena | `NN` + 1–8 unidades de 26 hex | `scene` |
| 26 | `countdown_1` | timer (s), inverte o estado ao zerar | 0–86400 | `timer_minutes` (0 cancela) |
| 34 | `do_not_disturb` | não perturbe | bool | `do_not_disturb` |
| 27 | `music_data` | música (stream do app) | write-only, sem eco | não exposto |
| 28 | `control_data` | transição direta (stream) | write-only, sem eco | não exposto |
| 33 | `power_memory` | estado ao religar após queda | raw | não exposto (não mexer) |

Unidade de cena (26 hex): `switch_s(2) gradient_s(2) modo(2: 00 static, 01 jump, 02 gradient) H(4) S(4) V(4) brilho(4) temp(4)`. Unidade branca zera H/S/V; unidade colorida usa H/S/V.
Ex. real lida: `000e0d0000000000000000c80000` = 1 unidade estática branca, brilho 20 %.

Escrita em um frame só (`set_multiple_values`); o adapter só escreve os DPS que mudam.

**Atenção:** ligar/desligar rápido várias vezes (3x) pode reiniciar a lâmpada em modo de pareamento. Nunca fazer on/off em loop.

## Configuração (já no `.env`, gitignored)

`BYTE_TUYA_LIGHTS={"lampada":{"device_id":"…","address":"192.168.0.227","local_key":"…","version":3.3}}`
Credenciais da nuvem (só para re-obter a key) ficam em `.env.tuya-cloud`, que o app **não** lê (o `Settings` proíbe chaves extras).

## Implementado

- `app/domain/light.py`: `LightState`, `LightChange` (parcial, validado), `Color`, `SceneUnit`; regra pura `LightChange.apply_to`.
- `app/ports/light.py`: `LightPort` (`devices`, `get_state`, `apply`) — nomes, nunca id cru.
- `app/adapters/memory/in_memory_light.py`: fake para testes.
- `app/adapters/tuya/tuya_light.py`: `TuyaLight`, 100 % local (`tinytuya`, extra `tuya`), conexão por chamada, lock (a lâmpada aceita 1 conexão).
- `api/deps.py::get_light()`; `config.py::tuya_lights`.
- Testes: domínio, in-memory, codificação Tuya com DPS reais, e integração real (`tests/integration/test_tuya_light.py`, pula sem `BYTE_TUYA_LIGHTS`).
- **Falta:** a `Tool` do agente (a `Tool`/`ToolRunner` ainda não existem no repo — Spec 1). Ela só chamará `LightPort.apply`. Ligar/desligar não precisa de confirmação; nada aqui é destrutivo.
- Sem fallback de nuvem: o trial expira, controle é só local.

## Riscos / pegadinhas

- Docker no servidor: `network_mode` bridge não recebe broadcast UDP do scan — mas controle **direto por IP** (TCP 6668) funciona de bridge. Só o *scan* precisa de host network.
- Só **uma** conexão local por vez na lâmpada: Smart Life app aberto pode conflitar; tinytuya com `set_socketPersistent(False)` por padrão ok.
- IP mudou → reserva DHCP.
- Local key muda se a lâmpada for re-pareada → rodar o wizard de novo.
- Trial da conta Tuya IoT Core expira (renovar manualmente a cada ~6 meses, gratuito).
- Arquivos do wizard (`devices.json`, `tinytuya.json`, `tuya-raw.json`, `snapshot.json`) contêm segredos → adicionar ao `.gitignore`.

## Log de tentativas

| Data | Ação | Resultado |
|---|---|---|
| 2026-10-05 | `pip install tinytuya` | 1.20.0 ok |
| 2026-10-05 | `tinytuya scan` 20s | 0 devices |
| 2026-10-05 | `tinytuya scan -force 192.168.0.0/24` 30s | 0 devices |
| 2026-10-05 | rescan após lâmpada na mesma rede | 1 device: id `eb7c0d8b57531cb337uy7v`, ip 192.168.0.227, v3.3 |
| 2026-10-05 | Cloud `us` com credenciais do `.env` (via `tinytuya.Cloud`) | token OK; `getdevices()` vazio; API devolve `28841002 IoT Core service subscription has expired` |
| 2026-10-05 | Renovação do trial IoT Core pedida | Pending review |
| 2026-10-05 | Trial aprovado; `getdevices()` | 1 device, key obtida (nuvem diz offline, local responde) |
| 2026-10-05 | `status()` + teste on/off/30%/cor/restore local | tudo OK; restaurou branco 100%, temp 500 (original era 952) |
