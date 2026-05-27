import asyncio, json, websockets

async def test():
    uri = 'ws://localhost:8000/api/v1/ws/chat'
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({'message': 'cria o projeto teste_api', 'session_id': 'test-tools'}))
        print('Sent. Waiting...')
        for _ in range(5):
            try:
                resp = await asyncio.wait_for(ws.recv(), timeout=20)
                data = json.loads(resp)
                print(f"[{data['type']}]", str(data.get('text',''))[:200])
                if data['type'] in ('done', 'error', 'chunk'):
                    break
            except asyncio.TimeoutError:
                print('TIMEOUT')
                break

asyncio.run(test())
