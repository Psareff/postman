import queue
import socket
import threading
import tkinter as tk
from tkinter import ttk, messagebox


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5555


class MailProtocolClient:
    def __init__(self):
        self.sock = None
        self.buffer = b""
        self.lock = threading.Lock()

    def is_connected(self):
        return self.sock is not None

    def connect_and_register(self, host: str, port: int, username: str) -> str:
        with self.lock:
            if self.sock is not None:
                raise RuntimeError("Уже подключено к серверу.")

            sock = socket.create_connection((host, port), timeout=10)
            sock.settimeout(10)

            self.sock = sock
            self.buffer = b""

            try:
                self._send_line(f"REGISTER {username}")
                resp = self._recv_line()
                if not resp.startswith("OK"):
                    self._close_nolock()
                    raise RuntimeError(f"Ошибка регистрации: {resp}")
                return resp
            except Exception:
                self._close_nolock()
                raise

    def send_letter(self, recipients_csv: str, body: str) -> str:
        with self.lock:
            self._require_connection()

            self._send_line(f"SEND {recipients_csv}")
            resp = self._recv_line()
            if not resp.startswith("OK"):
                return resp

            lines = body.splitlines()
            for line in lines:
                self._send_line(line)

            self._send_line(".")
            return self._recv_line()

    def read_letter(self):
        with self.lock:
            self._require_connection()

            self._send_line("READ")
            resp = self._recv_line()

            if resp == "LETTER":
                lines = []
                while True:
                    line = self._recv_line()
                    if line == ".":
                        break
                    lines.append(line)
                return {
                    "type": "letter",
                    "message": "\n".join(lines)
                }

            return {
                "type": "status",
                "message": resp
            }

    def quit(self):
        with self.lock:
            if self.sock is None:
                return

            try:
                self._send_line("QUIT")
                try:
                    self._recv_line()
                except Exception:
                    pass
            finally:
                self._close_nolock()

    def close(self):
        with self.lock:
            self._close_nolock()

    def _require_connection(self):
        if self.sock is None:
            raise RuntimeError("Нет подключения к серверу.")

    def _send_line(self, text: str):
        if self.sock is None:
            raise RuntimeError("Сокет не открыт.")
        data = (text + "\n").encode("utf-8")
        self.sock.sendall(data)

    def _recv_line(self) -> str:
        if self.sock is None:
            raise RuntimeError("Сокет не открыт.")

        while b"\n" not in self.buffer:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("Сервер закрыл соединение.")
            self.buffer += chunk

        line, self.buffer = self.buffer.split(b"\n", 1)
        line = line.decode("utf-8", errors="replace")
        if line.endswith("\r"):
            line = line[:-1]
        return line

    def _close_nolock(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None
        self.buffer = b""


class MailGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mail GUI")
        self.geometry("980x720")
        self.minsize(900, 650)

        self.client = MailProtocolClient()
        self.events = queue.Queue()

        self.connected = False
        self.busy = False

        self.host_var = tk.StringVar(value=DEFAULT_HOST)
        self.port_var = tk.StringVar(value=str(DEFAULT_PORT))
        self.user_var = tk.StringVar()
        self.to_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Не подключено")

        self._build_ui()
        self._refresh_controls()

        self.after(100, self._process_events)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.rowconfigure(3, weight=1)

        conn = ttk.LabelFrame(self, text="Подключение")
        conn.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        conn.columnconfigure(1, weight=1)
        conn.columnconfigure(3, weight=1)
        conn.columnconfigure(5, weight=1)

        ttk.Label(conn, text="Host:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.host_entry = ttk.Entry(conn, textvariable=self.host_var)
        self.host_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(conn, text="Port:").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.port_entry = ttk.Entry(conn, textvariable=self.port_var, width=10)
        self.port_entry.grid(row=0, column=3, padx=5, pady=5, sticky="ew")

        ttk.Label(conn, text="Username:").grid(row=0, column=4, padx=5, pady=5, sticky="w")
        self.user_entry = ttk.Entry(conn, textvariable=self.user_var)
        self.user_entry.grid(row=0, column=5, padx=5, pady=5, sticky="ew")

        self.connect_btn = ttk.Button(conn, text="Подключиться", command=self._on_connect)
        self.connect_btn.grid(row=0, column=6, padx=5, pady=5)

        self.disconnect_btn = ttk.Button(conn, text="Отключиться", command=self._on_disconnect)
        self.disconnect_btn.grid(row=0, column=7, padx=5, pady=5)

        status_frame = ttk.Frame(self)
        status_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        status_frame.columnconfigure(1, weight=1)

        ttk.Label(status_frame, text="Статус:").grid(row=0, column=0, sticky="w")
        ttk.Label(status_frame, textvariable=self.status_var).grid(row=0, column=1, sticky="w")

        middle = ttk.Frame(self)
        middle.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        middle.columnconfigure(0, weight=1)
        middle.columnconfigure(1, weight=1)
        middle.rowconfigure(0, weight=1)

        send_frame = ttk.LabelFrame(middle, text="Отправка письма")
        send_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        send_frame.columnconfigure(0, weight=1)
        send_frame.rowconfigure(2, weight=1)

        ttk.Label(send_frame, text="Получатели (через запятую):").grid(
            row=0, column=0, sticky="w", padx=8, pady=(8, 4)
        )
        self.to_entry = ttk.Entry(send_frame, textvariable=self.to_var)
        self.to_entry.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

        ttk.Label(send_frame, text="Текст письма:").grid(
            row=2, column=0, sticky="nw", padx=8, pady=(0, 4)
        )

        self.body_text = tk.Text(send_frame, wrap="word", height=15)
        self.body_text.grid(row=3, column=0, sticky="nsew", padx=8, pady=(0, 8))

        send_btns = ttk.Frame(send_frame)
        send_btns.grid(row=4, column=0, sticky="ew", padx=8, pady=(0, 8))
        self.send_btn = ttk.Button(send_btns, text="Отправить", command=self._on_send)
        self.send_btn.pack(side="left")
        self.clear_body_btn = ttk.Button(send_btns, text="Очистить", command=self._clear_body)
        self.clear_body_btn.pack(side="left", padx=8)

        read_frame = ttk.LabelFrame(middle, text="Чтение почты")
        read_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        read_frame.columnconfigure(0, weight=1)
        read_frame.rowconfigure(1, weight=1)

        top_read = ttk.Frame(read_frame)
        top_read.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        self.read_btn = ttk.Button(top_read, text="Прочитать следующее письмо", command=self._on_read)
        self.read_btn.pack(side="left")

        self.letter_text = tk.Text(read_frame, wrap="word", height=20)
        self.letter_text.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        log_frame = ttk.LabelFrame(self, text="Лог")
        log_frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, wrap="word", height=10, state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

    def _append_log(self, text: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_letter(self, text: str):
        self.letter_text.delete("1.0", "end")
        self.letter_text.insert("1.0", text)

    def _clear_body(self):
        self.body_text.delete("1.0", "end")

    def _refresh_controls(self):
        can_connect = (not self.connected) and (not self.busy)
        can_use = self.connected and (not self.busy)

        self.connect_btn.configure(state="normal" if can_connect else "disabled")
        self.disconnect_btn.configure(state="normal" if can_use else "disabled")
        self.send_btn.configure(state="normal" if can_use else "disabled")
        self.read_btn.configure(state="normal" if can_use else "disabled")
        self.clear_body_btn.configure(state="normal" if not self.busy else "disabled")

        state_conn_entries = "normal" if not self.connected and not self.busy else "disabled"
        self.host_entry.configure(state=state_conn_entries)
        self.port_entry.configure(state=state_conn_entries)
        self.user_entry.configure(state=state_conn_entries)

        self.to_entry.configure(state="normal" if can_use else "disabled")
        self.body_text.configure(state="normal" if can_use else "disabled")

    def _set_busy(self, value: bool, status_text: str | None = None):
        self.busy = value
        if status_text is not None:
            self.status_var.set(status_text)
        self._refresh_controls()

    def _run_in_background(self, func, on_success=None, on_error=None, busy_text="Выполняется..."):
        if self.busy:
            return

        self._set_busy(True, busy_text)

        def worker():
            try:
                result = func()
                self.events.put(("success", on_success, result))
            except Exception as e:
                self.events.put(("error", on_error, e))
            finally:
                self.events.put(("busy", False, None))

        threading.Thread(target=worker, daemon=True).start()

    def _process_events(self):
        try:
            while True:
                kind, callback, payload = self.events.get_nowait()

                if kind == "success":
                    if callback:
                        callback(payload)

                elif kind == "error":
                    if callback:
                        callback(payload)
                    else:
                        self._append_log(f"Ошибка: {payload}")
                        messagebox.showerror("Ошибка", str(payload))

                elif kind == "busy":
                    self.busy = bool(callback)
                    if self.connected:
                        self.status_var.set("Подключено")
                    else:
                        self.status_var.set("Не подключено")
                    self._refresh_controls()

        except queue.Empty:
            pass

        self.after(100, self._process_events)

    def _on_connect(self):
        host = self.host_var.get().strip()
        port_str = self.port_var.get().strip()
        username = self.user_var.get().strip()

        if not host:
            messagebox.showwarning("Проверка", "Введите host.")
            return

        if not username:
            messagebox.showwarning("Проверка", "Введите username.")
            return

        try:
            port = int(port_str)
        except ValueError:
            messagebox.showwarning("Проверка", "Порт должен быть числом.")
            return

        def task():
            return self.client.connect_and_register(host, port, username)

        def ok(resp):
            self.connected = True
            self.status_var.set("Подключено")
            self._refresh_controls()
            self._append_log(f"[mail] connected to {host}:{port}")
            self._append_log(f"[mail] вы вошли как «{username}»")
            self._append_log(f"Сервер: {resp}")

        def err(exc):
            self.connected = False
            self.status_var.set("Не подключено")
            self._refresh_controls()
            self._append_log(f"Ошибка подключения: {exc}")
            messagebox.showerror("Ошибка подключения", str(exc))

        self._run_in_background(task, on_success=ok, on_error=err, busy_text="Подключение...")

    def _on_disconnect(self):
        if not self.connected:
            return

        def task():
            self.client.quit()
            return None

        def ok(_):
            self.connected = False
            self.status_var.set("Не подключено")
            self._refresh_controls()
            self._append_log("[mail] session terminated.")

        def err(exc):
            self.client.close()
            self.connected = False
            self.status_var.set("Не подключено")
            self._refresh_controls()
            self._append_log(f"Отключение с ошибкой: {exc}")

        self._run_in_background(task, on_success=ok, on_error=err, busy_text="Отключение...")

    def _on_send(self):
        if not self.connected:
            return

        recipients = self.to_var.get().strip()
        body = self.body_text.get("1.0", "end-1c")

        if not recipients:
            messagebox.showwarning("Проверка", "Введите хотя бы одного получателя.")
            return

        if any(line == "." for line in body.splitlines()):
            messagebox.showwarning(
                "Проверка",
                "Строка '.' используется протоколом как конец письма.\n"
                "Удалите такую строку из текста письма."
            )
            return

        def task():
            return self.client.send_letter(recipients, body)

        def ok(resp):
            self._append_log(f"SEND {recipients}")
            self._append_log(f"Сервер: {resp}")
            if resp.startswith("OK"):
                self._clear_body()

        def err(exc):
            self._append_log(f"Ошибка отправки: {exc}")
            messagebox.showerror("Ошибка отправки", str(exc))

        self._run_in_background(task, on_success=ok, on_error=err, busy_text="Отправка письма...")

    def _on_read(self):
        if not self.connected:
            return

        def task():
            return self.client.read_letter()

        def ok(result):
            if result["type"] == "letter":
                self._set_letter(result["message"])
                self._append_log("─── New letter ───────────────────")
                self._append_log(result["message"])
                self._append_log("──────────────────────────────────")
            else:
                self._append_log(f"Сервер: {result['message']}")

        def err(exc):
            self._append_log(f"Ошибка чтения: {exc}")
            messagebox.showerror("Ошибка чтения", str(exc))

        self._run_in_background(task, on_success=ok, on_error=err, busy_text="Чтение письма...")

    def _on_close(self):
        try:
            self.client.close()
        finally:
            self.destroy()


if __name__ == "__main__":
    app = MailGUI()
    app.mainloop()
