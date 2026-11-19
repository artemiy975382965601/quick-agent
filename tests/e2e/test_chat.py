def _events(response):
    events = []
    name = None
    data = []
    for line in response.iter_lines():
        if line.startswith('event:'):
            name = line[6:].strip()
        elif line.startswith('data:'):
            chunk = line[5:]
            if chunk.startswith(' '):
                chunk = chunk[1:]
            data.append(chunk)
        elif line == '':
            if name is not None:
                events.append((name, '\n'.join(data)))
            name = None
            data = []
    return events


def test_echo(client):
    response = client.post('/sessions/create/', json={'id': 'test'})
    assert response.status_code == 201

    with client.stream('POST', '/chat/test/start', json={'query': 'test'}) as response:
        assert response.status_code == 200
        assert 'text/event-stream' in response.headers.get('content-type', '')
        events = _events(response)

    kinds = [name for name, _ in events]
    assert 'tool_called' in kinds
    assert 'done' in kinds
    assert 'error' not in kinds

    tool_names = [data for name, data in events if name == 'tool_called']
    assert 'echo' in tool_names

    deltas = [data for name, data in events if name == 'delta']
    assert deltas
    assert any(d.strip() for d in deltas)

    assert kinds[-1] == 'done'
