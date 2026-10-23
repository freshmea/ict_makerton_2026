"""Small stdio client for the official SolidCraft CLI (no private HTTP API).

Use --headless for an isolated design, otherwise connect to the desktop app.
No control token is ever printed or written to the evidence files.
"""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
CLI = Path('C:/Users/Administrator/Downloads/solidcraft-windows-x64-portable/solidcraft-0.20.0-windows-x64-portable/solidcraft-cli.exe')


class Client:
    def __init__(self, headless=False, port=22062, timeout=55):
        self.timeout = timeout
        args = [str(CLI), 'mcp', '--allow-path', str(ROOT.parents[2])]
        if not headless:
            control = Path(os.environ['LOCALAPPDATA']) / 'SolidCraft/control'
            files = list(control.glob(str(port) + '.token'))
            if len(files) != 1:
                raise RuntimeError('Expected exactly one running SolidCraft control endpoint')
            f = files[0]
            args += ['--connect', '127.0.0.1:' + f.stem, '--token', f.read_text().strip()]
        self.process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True, encoding='utf-8')
        self.queue = queue.Queue()
        self.errors = []
        self.counter = 0
        threading.Thread(target=lambda: [self.queue.put(s) for s in self.process.stdout], daemon=True).start()
        threading.Thread(target=lambda: [self.errors.append(s) for s in self.process.stderr], daemon=True).start()
        self.initialization = self.request('initialize', {'protocolVersion': '2024-11-05',
            'capabilities': {}, 'clientInfo': {'name': 'Codex-FWB-P2', 'version': '1'}})
        self.process.stdin.write(json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized'}) + '\n')
        self.process.stdin.flush()

    def request(self, method, params):
        self.counter += 1
        self.process.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': self.counter,
                                            'method': method, 'params': params}) + '\n')
        self.process.stdin.flush()
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                r = json.loads(self.queue.get(timeout=1))
            except (ValueError, queue.Empty):
                if self.process.poll() is not None:
                    raise RuntimeError('SolidCraft exited: ' + ''.join(self.errors)[-2000:])
                continue
            if r.get('id') == self.counter:
                return r
        raise TimeoutError(method + ': inspect running state before retrying a mutation')

    def call(self, name, arguments=None):
        r = self.request('tools/call', {'name': name, 'arguments': arguments or {}})
        if r.get('error') or r.get('result', {}).get('isError'):
            raise RuntimeError(json.dumps(r, ensure_ascii=False))
        return r

    @staticmethod
    def value(r):
        texts = [c['text'] for c in r.get('result', {}).get('content', []) if c['type'] == 'text']
        if len(texts) == 1:
            try:
                return json.loads(texts[0])
            except ValueError:
                return texts[0]
        return texts

    def close(self):
        self.process.terminate()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('request_file', type=Path)
    ap.add_argument('--headless', action='store_true')
    ap.add_argument('--output', type=Path)
    ns = ap.parse_args()
    calls = json.loads(ns.request_file.read_text(encoding='utf-8-sig'))
    c = Client(ns.headless)
    results = []
    try:
        for call in calls:
            r = c.call(call['name'], call.get('arguments', {}))
            for item in r.get('result', {}).get('content', []):
                if item['type'] == 'image':
                    item['data'] = '[omitted; saved by screenshot tool]'
            results.append({'name': call['name'], 'result': c.value(r)})
        output = json.dumps(results, ensure_ascii=False, indent=2)
        if ns.output:
            ns.output.parent.mkdir(parents=True, exist_ok=True)
            ns.output.write_text(output, encoding='utf-8')
        else:
            print(output)
    finally:
        c.close()
