"""키즈빌리지 상품 수집기 GUI (tkinter)."""
from __future__ import annotations

import logging
import platform
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from src.config_loader import load_config
from src.models import ProductStatus
from src.orchestrator import ProductOrchestrator


class QueueHandler(logging.Handler):
    """로그 레코드를 큐에 넣는 핸들러. GUI 쓰레드에서 폴링하여 Text 위젯에 표시한다."""

    def __init__(self, log_queue: queue.Queue[str]) -> None:
        super().__init__()
        self._queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        self._queue.put(msg)


class App(tk.Tk):
    POLL_MS = 100

    def __init__(self) -> None:
        super().__init__()
        self.title("키즈빌리지 상품 수집기")
        self.resizable(False, False)

        self._log_queue: queue.Queue[str] = queue.Queue()
        self._running = False

        self._build_ui()
        self._setup_logging()
        self.after(self.POLL_MS, self._poll_log_queue)

    # ─── UI 구성 ────────────────────────────────────────

    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 4}

        # --- 입력 영역 ---
        input_frame = ttk.LabelFrame(self, text="설정", padding=10)
        input_frame.pack(fill="x", **pad)

        ttk.Label(input_frame, text="아이디:").grid(row=0, column=0, sticky="e", **pad)
        self._var_username = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self._var_username, width=30).grid(
            row=0, column=1, columnspan=2, sticky="w", **pad
        )

        ttk.Label(input_frame, text="비밀번호:").grid(row=1, column=0, sticky="e", **pad)
        self._var_password = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self._var_password, width=30, show="*").grid(
            row=1, column=1, columnspan=2, sticky="w", **pad
        )

        ttk.Label(input_frame, text="CSV 파일:").grid(row=2, column=0, sticky="e", **pad)
        self._var_csv = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self._var_csv, width=30).grid(
            row=2, column=1, sticky="w", **pad
        )
        ttk.Button(input_frame, text="찾아보기", command=self._browse_csv).grid(
            row=2, column=2, **pad
        )

        ttk.Label(input_frame, text="출력 폴더:").grid(row=3, column=0, sticky="e", **pad)
        self._var_output = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self._var_output, width=30).grid(
            row=3, column=1, sticky="w", **pad
        )
        ttk.Button(input_frame, text="찾아보기", command=self._browse_output).grid(
            row=3, column=2, **pad
        )

        # --- 버튼 영역 ---
        btn_frame = ttk.Frame(self, padding=5)
        btn_frame.pack(fill="x", **pad)

        self._btn_run = ttk.Button(btn_frame, text="실행", command=self._on_run)
        self._btn_run.pack(side="left", padx=10)

        self._btn_open = ttk.Button(btn_frame, text="출력 폴더 열기", command=self._open_output)
        self._btn_open.pack(side="left", padx=10)

        # --- 진행률 ---
        progress_frame = ttk.LabelFrame(self, text="진행상황", padding=10)
        progress_frame.pack(fill="x", **pad)

        self._var_progress_text = tk.StringVar(value="대기 중")
        ttk.Label(progress_frame, textvariable=self._var_progress_text).pack(anchor="w")

        self._progressbar = ttk.Progressbar(progress_frame, length=400, mode="determinate")
        self._progressbar.pack(fill="x", pady=4)

        # --- 로그 ---
        log_frame = ttk.LabelFrame(self, text="로그", padding=10)
        log_frame.pack(fill="both", expand=True, **pad)

        self._log_text = tk.Text(log_frame, height=15, width=60, state="disabled", wrap="word")
        scrollbar = ttk.Scrollbar(log_frame, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=scrollbar.set)
        self._log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    # ─── 로깅 연결 ──────────────────────────────────────

    def _setup_logging(self) -> None:
        handler = QueueHandler(self._log_queue)
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
        ))
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(handler)

    def _poll_log_queue(self) -> None:
        while True:
            try:
                msg = self._log_queue.get_nowait()
            except queue.Empty:
                break
            self._log_text.configure(state="normal")
            self._log_text.insert("end", msg + "\n")
            self._log_text.see("end")
            self._log_text.configure(state="disabled")
        self.after(self.POLL_MS, self._poll_log_queue)

    # ─── 파일 탐색 ──────────────────────────────────────

    def _browse_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="CSV 파일 선택",
            initialdir=Path.cwd(),
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if path:
            self._var_csv.set(path)

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="출력 폴더 선택", initialdir=Path.cwd())
        if path:
            self._var_output.set(path)

    def _open_output(self) -> None:
        output_dir = Path(self._var_output.get())
        if not output_dir.exists():
            messagebox.showwarning("경고", f"출력 폴더가 존재하지 않습니다:\n{output_dir}")
            return
        system = platform.system()
        if system == "Darwin":
            subprocess.Popen(["open", str(output_dir)])
        elif system == "Windows":
            subprocess.Popen(["explorer", str(output_dir)])
        else:
            subprocess.Popen(["xdg-open", str(output_dir)])

    # ─── 실행 ───────────────────────────────────────────

    def _on_run(self) -> None:
        username = self._var_username.get().strip()
        password = self._var_password.get().strip()
        csv_path = self._var_csv.get().strip()
        output_dir = self._var_output.get().strip()

        if not username or not password:
            messagebox.showwarning("입력 오류", "아이디와 비밀번호를 입력해주세요.")
            return
        if not csv_path or not Path(csv_path).exists():
            messagebox.showwarning("입력 오류", "유효한 CSV 파일을 선택해주세요.")
            return

        self._set_running(True)

        thread = threading.Thread(
            target=self._run_pipeline,
            args=(username, password, csv_path, output_dir),
            daemon=True,
        )
        thread.start()

    def _run_pipeline(
        self, username: str, password: str, csv_path: str, output_dir: str
    ) -> None:
        try:
            config = load_config()
            config.wholesale.username = username
            config.wholesale.password = password
            config.paths.input_csv = csv_path
            config.paths.output_dir = output_dir

            orchestrator = ProductOrchestrator(
                config, on_progress=self._on_progress
            )
            results = orchestrator.run()

            if not results:
                self._finish("처리할 상품이 없거나 로그인에 실패했습니다.")
                return

            ok = sum(1 for r in results if r.status == ProductStatus.DONE)
            fail = len(results) - ok
            self._finish(f"완료: 성공 {ok}건, 실패 {fail}건")

        except Exception as e:
            logging.getLogger(__name__).error("Pipeline error: %s", e)
            self._finish(f"오류 발생: {e}")

    def _on_progress(self, current: int, total: int, product_id: str) -> None:
        self._progressbar["maximum"] = total
        self._progressbar["value"] = current
        self._var_progress_text.set(f"{current}/{total}  처리 중: {product_id}")

    def _finish(self, message: str) -> None:
        self._var_progress_text.set(message)
        self._set_running(False)

    def _set_running(self, running: bool) -> None:
        self._running = running
        state = "disabled" if running else "normal"
        self._btn_run.configure(state=state)
        if not running:
            self._progressbar["value"] = self._progressbar["maximum"]


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
