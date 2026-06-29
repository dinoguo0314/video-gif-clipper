"""
Video GIF Clipper
Randomly extracts N clips from a video and converts them to GIF.
Requires FFmpeg installed and available in PATH.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import random
import threading
import os
import sys
from pathlib import Path

# Common install locations to check when ffmpeg is not in PATH
_FFMPEG_SEARCH_DIRS = [
    r"C:\ffmpeg",
    r"C:\Program Files\ffmpeg",
    r"C:\Program Files (x86)\ffmpeg",
    str(Path.home() / "ffmpeg"),
]


def _exe_dir() -> Path:
    """Return the directory containing the running executable or script."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def setup_ffmpeg_path() -> None:
    """Add ffmpeg bin dir to PATH if ffmpeg is not already findable."""
    try:
        subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
        return  # already in PATH
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    # When running as a bundled exe, check next to the executable first
    bundled = _exe_dir() / "ffprobe.exe"
    if bundled.exists():
        os.environ["PATH"] = str(bundled.parent) + os.pathsep + os.environ.get("PATH", "")
        return

    for base in _FFMPEG_SEARCH_DIRS:
        for candidate in Path(base).rglob("ffprobe.exe") if Path(base).exists() else []:
            bin_dir = str(candidate.parent)
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
            return


def get_video_duration(video_path: str) -> float:
    """Return video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = (result.stdout or "").strip()
    if result.returncode != 0 or not output:
        detail = (result.stderr or "").strip() or "No output from ffprobe."
        raise RuntimeError(f"ffprobe failed to read video duration:\n{detail}")
    return float(output)


def pick_non_overlapping_starts(duration: float, clip_duration: float, count: int) -> list[float]:
    """Pick `count` random start times with no overlapping clips."""
    max_start = duration - clip_duration
    if max_start <= 0:
        raise ValueError("Video is too short for the requested clip duration.")

    min_gap = clip_duration  # clips must not overlap
    attempts = 0
    while attempts < 10000:
        starts = sorted(random.uniform(0, max_start) for _ in range(count))
        valid = all(
            starts[i + 1] - starts[i] >= min_gap
            for i in range(len(starts) - 1)
        )
        if valid:
            return starts
        attempts += 1

    # Fallback: evenly spaced with jitter
    segment = max_start / count
    starts = []
    for i in range(count):
        base = i * segment
        jitter = random.uniform(0, max(0, segment - clip_duration))
        starts.append(min(base + jitter, max_start))
    return starts


def clip_to_gif(
    video_path: str,
    start: float,
    duration: float,
    output_path: str,
    width: int,
    fps: int,
    colors: int,
) -> None:
    """Convert one clip segment to GIF via FFmpeg palette trick for quality."""
    palette_path = output_path + ".palette.png"

    # Step 1: generate palette
    palette_cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-t", str(duration),
        "-i", video_path,
        "-vf", f"fps={fps},scale={width}:-1:flags=lanczos,palettegen=max_colors={colors}",
        palette_path
    ]
    r = subprocess.run(palette_cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Palette generation failed:\n{r.stderr}")

    # Step 2: render GIF using palette
    gif_cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-t", str(duration),
        "-i", video_path,
        "-i", palette_path,
        "-lavfi", f"fps={fps},scale={width}:-1:flags=lanczos[x];[x][1:v]paletteuse",
        output_path
    ]
    r = subprocess.run(gif_cmd, capture_output=True, text=True)
    os.remove(palette_path)
    if r.returncode != 0:
        raise RuntimeError(f"GIF conversion failed:\n{r.stderr}")


def check_ffmpeg() -> bool:
    try:
        subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Video GIF Clipper")
        self.resizable(False, False)
        setup_ffmpeg_path()
        self._build_ui()
        self._check_ffmpeg_on_start()

    def _check_ffmpeg_on_start(self):
        if not check_ffmpeg():
            messagebox.showerror(
                "FFmpeg Not Found",
                "FFmpeg is not installed or not in PATH.\n\n"
                "Please install FFmpeg:\n"
                "  Windows: https://ffmpeg.org/download.html\n"
                "  Mac:     brew install ffmpeg\n"
                "  Linux:   sudo apt install ffmpeg"
            )

    def _build_ui(self):
        pad = {"padx": 10, "pady": 5}

        # ── Video file ──────────────────────────────────────────────
        frm_file = ttk.LabelFrame(self, text="影片檔案 / Video File")
        frm_file.grid(row=0, column=0, columnspan=2, sticky="ew", **pad)

        self.video_path = tk.StringVar()
        ttk.Entry(frm_file, textvariable=self.video_path, width=50).grid(row=0, column=0, padx=5, pady=5)
        ttk.Button(frm_file, text="瀏覽 Browse", command=self._browse_video).grid(row=0, column=1, padx=5)

        # ── Output folder ───────────────────────────────────────────
        frm_out = ttk.LabelFrame(self, text="輸出資料夾 / Output Folder")
        frm_out.grid(row=1, column=0, columnspan=2, sticky="ew", **pad)

        self.output_dir = tk.StringVar()
        ttk.Entry(frm_out, textvariable=self.output_dir, width=50).grid(row=0, column=0, padx=5, pady=5)
        ttk.Button(frm_out, text="瀏覽 Browse", command=self._browse_output).grid(row=0, column=1, padx=5)

        # ── Parameters ──────────────────────────────────────────────
        frm_params = ttk.LabelFrame(self, text="參數設定 / Parameters")
        frm_params.grid(row=2, column=0, columnspan=2, sticky="ew", **pad)

        params = [
            ("片段數量 Clip Count",   "clip_count",    "10",  "個"),
            ("每段秒數 Duration (s)", "clip_duration", "5",   "秒"),
            ("GIF 寬度 Width (px)",   "gif_width",     "480", "px"),
            ("FPS",                   "gif_fps",       "15",  "fps"),
            ("色彩數 Colors",         "gif_colors",    "256", "色"),
        ]

        self._vars = {}
        for i, (label, key, default, unit) in enumerate(params):
            ttk.Label(frm_params, text=label).grid(row=i, column=0, sticky="w", padx=8, pady=3)
            var = tk.StringVar(value=default)
            self._vars[key] = var
            ttk.Entry(frm_params, textvariable=var, width=8).grid(row=i, column=1, padx=5)
            ttk.Label(frm_params, text=unit).grid(row=i, column=2, sticky="w")

        # ── Progress ────────────────────────────────────────────────
        self.progress = ttk.Progressbar(self, length=400, mode="determinate")
        self.progress.grid(row=3, column=0, columnspan=2, **pad)

        self.status_var = tk.StringVar(value="就緒 Ready")
        ttk.Label(self, textvariable=self.status_var).grid(row=4, column=0, columnspan=2)

        # ── Button ──────────────────────────────────────────────────
        self.btn_start = ttk.Button(self, text="開始轉換 Start", command=self._start)
        self.btn_start.grid(row=5, column=0, columnspan=2, pady=10)

    def _browse_video(self):
        path = filedialog.askopenfilename(
            title="選擇影片 / Select Video",
            filetypes=[("Video files", "*.mp4 *.mov *.avi *.mkv *.webm *.flv *.wmv"), ("All", "*.*")]
        )
        if path:
            self.video_path.set(path)
            if not self.output_dir.get():
                self.output_dir.set(str(Path(path).parent))

    def _browse_output(self):
        path = filedialog.askdirectory(title="選擇輸出資料夾 / Select Output Folder")
        if path:
            self.output_dir.set(path)

    def _get_int(self, key: str) -> int:
        try:
            val = int(self._vars[key].get())
            assert val > 0
            return val
        except (ValueError, AssertionError):
            raise ValueError(f"Invalid value for {key}")

    def _start(self):
        video = self.video_path.get().strip()
        out_dir = self.output_dir.get().strip()

        if not video or not os.path.isfile(video):
            messagebox.showerror("Error", "請選擇有效的影片檔案。\nPlease select a valid video file.")
            return
        if not out_dir:
            messagebox.showerror("Error", "請選擇輸出資料夾。\nPlease select an output folder.")
            return

        try:
            count    = self._get_int("clip_count")
            duration = self._get_int("clip_duration")
            width    = self._get_int("gif_width")
            fps      = self._get_int("gif_fps")
            colors   = self._get_int("gif_colors")
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return

        self.btn_start.config(state="disabled")
        thread = threading.Thread(
            target=self._run,
            args=(video, out_dir, count, duration, width, fps, colors),
            daemon=True
        )
        thread.start()

    def _run(self, video, out_dir, count, duration, width, fps, colors):
        try:
            self._set_status("讀取影片資訊… / Reading video info…")
            total_duration = get_video_duration(video)

            self._set_status("計算隨機時間點… / Picking random timestamps…")
            starts = pick_non_overlapping_starts(total_duration, duration, count)

            os.makedirs(out_dir, exist_ok=True)
            video_stem = Path(video).stem

            self.progress["maximum"] = count
            self.progress["value"] = 0

            for i, start in enumerate(starts, 1):
                self._set_status(f"轉換中 Converting {i}/{count}… (t={start:.1f}s)")
                out_file = os.path.join(out_dir, f"{video_stem}_clip{i:02d}_{int(start)}s.gif")
                clip_to_gif(video, start, duration, out_file, width, fps, colors)
                self.progress["value"] = i
                self.update_idletasks()

            self._set_status(f"完成！Saved {count} GIFs → {out_dir}")
            messagebox.showinfo("Done", f"已成功產生 {count} 個 GIF！\nSaved to: {out_dir}")

        except Exception as e:
            messagebox.showerror("Error", str(e))
            self._set_status("發生錯誤 Error occurred")
        finally:
            self.btn_start.config(state="normal")
            self.progress["value"] = 0

    def _set_status(self, msg: str):
        self.status_var.set(msg)
        self.update_idletasks()


def run_cli():
    import argparse
    parser = argparse.ArgumentParser(
        description="Randomly extract clips from a video and convert to GIF."
    )
    parser.add_argument("input",               help="Input video file path")
    parser.add_argument("--output", "-o",      default="", help="Output folder (default: same as input)")
    parser.add_argument("--count",  "-n",      type=int, default=10,  help="Number of clips (default: 10)")
    parser.add_argument("--duration", "-d",    type=int, default=5,   help="Clip duration in seconds (default: 5)")
    parser.add_argument("--width", "-w",       type=int, default=480, help="GIF width in pixels (default: 480)")
    parser.add_argument("--fps",               type=int, default=15,  help="GIF FPS (default: 15)")
    parser.add_argument("--colors",            type=int, default=256, help="GIF color count (default: 256)")
    args = parser.parse_args()

    video = args.input
    if not os.path.isfile(video):
        print(f"Error: File not found: {video}", file=sys.stderr)
        sys.exit(1)

    out_dir = args.output or str(Path(video).parent)
    os.makedirs(out_dir, exist_ok=True)

    setup_ffmpeg_path()

    print(f"Reading video: {video}")
    total = get_video_duration(video)
    print(f"Duration: {total:.1f}s")

    starts = pick_non_overlapping_starts(total, args.duration, args.count)
    video_stem = Path(video).stem
    results = []

    for i, start in enumerate(starts, 1):
        out_file = os.path.join(out_dir, f"{video_stem}_clip{i:02d}_{int(start)}s.gif")
        print(f"[{i}/{args.count}] t={start:.1f}s → {os.path.basename(out_file)}")
        clip_to_gif(video, start, args.duration, out_file, args.width, args.fps, args.colors)
        results.append(out_file)
        print(f"       OK ({os.path.getsize(out_file)//1024} KB)")

    print(f"\nDone. {len(results)} GIFs saved to: {out_dir}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_cli()
    else:
        app = App()
        app.mainloop()
