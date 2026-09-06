#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多 AI 议事助手 - 本地代理服务器
作用：托管 index.html，并把浏览器的 API 请求代理转发到各家大模型接口，绕过浏览器 CORS 限制。
用法：python server.py ，然后浏览器打开 http://localhost:8787
"""
import http.server
import json
import urllib.request
import urllib.error
import os
import webbrowser
import threading
import time
from datetime import datetime

PORT = 8787
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, "index.html")


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def _send_json_error(self, code, message):
        body = json.dumps({"error": {"message": message}}, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            try:
                with open(HTML_PATH, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self._send_json_error(404, "index.html 不存在，请确认 server.py 和 index.html 在同一目录")
        else:
            self._send_json_error(404, "Not Found")

    def do_POST(self):
        if self.path == "/save-discussion":
            self._save_discussion()
            return
        if self.path != "/proxy":
            self._send_json_error(404, "Not Found")
            return
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(content_length)
            req = json.loads(raw.decode("utf-8"))

            target_url = req["url"]
            target_headers = req.get("headers", {})
            target_body = req.get("body", "").encode("utf-8")

            api_req = urllib.request.Request(
                target_url,
                data=target_body,
                headers=target_headers,
                method="POST",
            )

            try:
                with urllib.request.urlopen(api_req, timeout=150) as resp:
                    resp_body = resp.read()
                    self.send_response(resp.status)
                    ct = resp.headers.get("Content-Type", "application/json")
                    self.send_header("Content-Type", ct)
                    self.send_header("Content-Length", str(len(resp_body)))
                    self.end_headers()
                    self.wfile.write(resp_body)
            except urllib.error.HTTPError as e:
                # API 返回错误状态码，原样透传给浏览器
                resp_body = e.read()
                self.send_response(e.code)
                ct = e.headers.get("Content-Type", "application/json")
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", str(len(resp_body)))
                self.end_headers()
                self.wfile.write(resp_body)
            except urllib.error.URLError as e:
                self._send_json_error(502, "网络错误或无法连接到接口: " + str(e.reason))
            except TimeoutError:
                self._send_json_error(504, "接口请求超时（150秒）")
        except KeyError as e:
            self._send_json_error(400, "代理请求缺少字段: " + str(e))
        except json.JSONDecodeError:
            self._send_json_error(400, "代理请求体不是合法 JSON")
        except Exception as e:
            self._send_json_error(500, "代理内部错误: " + str(e))

    def _save_discussion(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(content_length)
            data = json.loads(raw.decode("utf-8"))

            save_dir = os.path.join(BASE_DIR, "讨论记录")
            os.makedirs(save_dir, exist_ok=True)

            now = datetime.now()
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            time_str = now.strftime("%Y-%m-%d %H:%M:%S")

            topic = (data.get("topic") or "未命名讨论").strip()
            if data.get("filename"):
                filename = data["filename"]
            else:
                safe_topic = "".join(c for c in topic if c not in '\\/:*?"<>|').strip()
                if len(safe_topic) > 30:
                    safe_topic = safe_topic[:30]
                if not safe_topic:
                    safe_topic = "未命名讨论"
                filename = timestamp + "_" + safe_topic + ".md"
            filepath = os.path.join(save_dir, filename)

            seats = data.get("seats", [])
            seat_str = "、".join(s.get("name", "") + " (" + s.get("model", "") + ")" for s in seats)
            rounds = int(data.get("rounds", 1))
            results = data.get("results", {})

            lines = []
            lines.append("# " + topic)
            lines.append("")
            lines.append("- 时间：" + time_str)
            lines.append("- 参与席位：" + seat_str)
            lines.append("- 轮次：" + str(rounds))
            lines.append("")
            lines.append("## 用户问题")
            lines.append("")
            lines.append(data.get("content", ""))
            lines.append("")
            lines.append("## 讨论记录")
            lines.append("")

            for r in range(1, rounds + 1):
                lines.append("### 第 " + str(r) + " 轮")
                lines.append("")
                for seat in seats:
                    sid = seat.get("id", "")
                    seat_results = results.get(sid, [])
                    for item in seat_results:
                        if item.get("round") == r:
                            lines.append("#### " + seat.get("name", ""))
                            lines.append("")
                            status = item.get("status", "")
                            if status == "done":
                                lines.append(item.get("text", ""))
                            elif status == "error":
                                lines.append("*[错误] " + item.get("text", "") + "*")
                            else:
                                lines.append("*[未完成]*")
                            lines.append("")
                lines.append("")

            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            resp = json.dumps({"ok": True, "path": filepath, "filename": filename}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        except Exception as e:
            self._send_json_error(500, "保存失败: " + str(e))

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))


def open_browser():
    time.sleep(1.2)
    try:
        webbrowser.open("http://localhost:%d" % PORT)
    except Exception:
        pass


if __name__ == "__main__":
    print("=" * 50)
    print("  多 AI 议事助手 - 本地代理已启动")
    print("  浏览器地址: http://localhost:%d" % PORT)
    print("  按 Ctrl+C 停止服务")
    print("=" * 50)
    threading.Thread(target=open_browser, daemon=True).start()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), ProxyHandler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
        server.server_close()
