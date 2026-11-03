"""Мост для поиска партий в браузере: отдаёт work/queries.json и принимает найденные партии
   (POST /result -> дописывает строку в work/found.jsonl). CORS открыт для 365chess."""
import http.server, json, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
class H(http.server.BaseHTTPRequestHandler):
    def cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
    def do_OPTIONS(self):
        self.send_response(204); self.cors(); self.end_headers()
    def do_GET(self):
        if self.path.startswith("/page"):
            # посредник: отдаёт запросы окну 365chess (opener) и пишет его ответы в found.jsonl
            body = b"""<!doctype html><meta charset=utf-8><title>sak bridge</title><pre id=log>bridge</pre><script>
fetch('/q').then(r=>r.json()).then(q=>{ window.Q=q; if(window.opener) window.opener.postMessage({sakQ:q},'*'); });
addEventListener('message', e=>{ if(e.data&&e.data.sakR){ fetch('/result',{method:'POST',body:JSON.stringify(e.data.sakR)});
  document.getElementById('log').textContent += '\\n' + e.data.sakR.n + ' ' + (e.data.sakR.score||0); }
  if(e.data&&e.data.sakAsk&&window.Q) e.source.postMessage({sakQ:window.Q},'*'); });
</script>"""
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(body); return
        body = open("work/queries.json", "rb").read()
        self.send_response(200); self.cors(); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        data = self.rfile.read(int(self.headers["Content-Length"]))
        with open("work/found.jsonl", "ab") as f: f.write(data.strip() + b"\n")
        self.send_response(200); self.cors(); self.end_headers(); self.wfile.write(b"ok")
http.server.ThreadingHTTPServer(("127.0.0.1", 8799), H).serve_forever()
