from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


def _iso_now() -> str:
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    except Exception:
        return ""


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def _whisper_path() -> str | None:
    # optional: OpenAI Whisper CLI (python -m whisper) installs a `whisper` entry
    return shutil.which("whisper")


def _write_json(path: Path, obj: dict) -> None:
    try:
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # best effort
        pass


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}


def _build_recording_paths(fmt: str) -> tuple[Path, Path]:
    base = Path(os.getcwd()).resolve() / "data" / "recordings"
    _ensure_dir(base)
    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    safe_fmt = (fmt or "ogg").lower().strip()
    ext = "ogg" if safe_fmt in {"ogg", "opus"} else ("flac" if safe_fmt == "flac" else "ogg")
    audio_path = base / f"meeting-{ts}.{ext}"
    meta_path = audio_path.with_suffix(".json")
    return audio_path, meta_path


def list_avfoundation_audio_devices() -> dict[str, Any]:
    """List macOS AVFoundation audio devices via ffmpeg.

    Returns: { supported: bool, devices: [{index:int, name:str}], message?:str }
    """
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        return {"supported": False, "devices": [], "message": "ffmpeg not found"}
    if os.name != "posix" or not hasattr(os, "uname") or os.uname().sysname.lower() != "darwin":
        return {"supported": False, "devices": [], "message": "only supported on macOS (avfoundation)"}
    try:
        proc = subprocess.run(
            [ffmpeg, "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            capture_output=True,
            text=True,
            timeout=10,
        )
        text_out = (proc.stderr or "") + "\n" + (proc.stdout or "")
    except Exception as e:
        return {"supported": False, "devices": [], "message": f"ffmpeg list_devices failed: {e}"}

    devices: list[dict[str, Any]] = []
    in_audio = False
    for line in text_out.splitlines():
        if "AVFoundation audio devices" in line:
            in_audio = True
            continue
        if "AVFoundation video devices" in line:
            in_audio = False
            continue
        if not in_audio:
            continue
        m = re.search(r"\[(\d+)\]\s*(.+)$", line.strip())
        if not m:
            continue
        idx = int(m.group(1))
        name = m.group(2).strip()
        devices.append({"index": idx, "name": name})
    return {"supported": True, "devices": devices}


@dataclass
class RecorderRuntimeState:
    supported: bool = True
    running: bool = False
    status: str = "idle"  # idle|listening|recording|silence|stopping|error
    message: str = ""
    auto_listen: bool = False
    format: str = "ogg"
    saved_count: int = 0
    last_saved_audio: str | None = None
    last_saved_at: str | None = None
    audio_file: str | None = None
    meta_file: str | None = None
    started_at: str | None = None
    mic_index: int | None = None
    system_index: int | None = None
    threshold_db: float = -45.0
    silence_stop_seconds: int = 60
    has_sound: bool = False
    silence_started_wall: float | None = None
    first_sound_sec: float | None = None
    last_sound_end_sec: float | None = None


class MeetingRecorder:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[str] | None = None
        self._stderr_thread: threading.Thread | None = None
        self._watchdog_thread: threading.Thread | None = None
        self._listen_watchdog_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._state = RecorderRuntimeState(supported=bool(_ffmpeg_path()))
        self._listen_initial_silence_seen = False
        self._switching_to_recording = False

    def status(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._state)

    def list_devices(self) -> dict[str, Any]:
        return list_avfoundation_audio_devices()

    def start(
        self,
        *,
        mic_index: int,
        system_index: int | None = None,
        threshold_db: float = -45.0,
        silence_stop_seconds: int = 60,
        fmt: str = "ogg",
    ) -> dict[str, Any]:
        ffmpeg = _ffmpeg_path()
        if not ffmpeg:
            with self._lock:
                self._state.supported = False
                self._state.status = "error"
                self._state.message = "ffmpeg not found"
            return self.status()

        fmt_norm = (fmt or "ogg").lower().strip() or "ogg"
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._state.message = "recorder already running"
                return self.status()
            saved_count = int(getattr(self._state, "saved_count", 0) or 0)
            last_saved_audio = getattr(self._state, "last_saved_audio", None)
            last_saved_at = getattr(self._state, "last_saved_at", None)
            self._stop_event.clear()
            self._listen_initial_silence_seen = False
            self._switching_to_recording = False
            self._state = RecorderRuntimeState(
                supported=True,
                running=True,
                status="listening",
                message="",
                auto_listen=True,
                format=fmt_norm,
                saved_count=saved_count,
                last_saved_audio=last_saved_audio,
                last_saved_at=last_saved_at,
                audio_file=None,
                meta_file=None,
                started_at=_iso_now(),
                mic_index=mic_index,
                system_index=system_index,
                threshold_db=float(threshold_db),
                silence_stop_seconds=int(silence_stop_seconds),
            )

        args: list[str] = [ffmpeg, "-hide_banner", "-loglevel", "info", "-nostats"]
        # Inputs: macOS avfoundation audio device is specified as ":<index>"
        inputs: list[int] = [mic_index]
        if system_index is not None and int(system_index) != int(mic_index):
            inputs.append(int(system_index))
        for idx in inputs:
            args += ["-f", "avfoundation", "-i", f":{idx}"]

        thr = float(threshold_db)
        silence_d = 0.3  # faster trigger for listening
        if len(inputs) == 1:
            filt = f"aresample=16000,silencedetect=noise={thr}dB:d={silence_d}"
            args += ["-af", filt, "-f", "null", "-"]
        else:
            labels = "".join([f"[{i}:a]" for i in range(len(inputs))])
            filt = f"{labels}amix=inputs={len(inputs)}:duration=longest:dropout_transition=2,aresample=16000,silencedetect=noise={thr}dB:d={silence_d}[a]"
            args += ["-filter_complex", filt, "-map", "[a]", "-f", "null", "-"]

        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )
        except Exception as e:
            with self._lock:
                self._state.running = False
                self._state.status = "error"
                self._state.message = f"failed to start ffmpeg: {e}"
            _write_json(meta_path, {**_read_json(meta_path), "status": "error", "error": str(e)})
            return self.status()

        with self._lock:
            self._proc = proc

        self._stderr_thread = threading.Thread(target=self._consume_stderr, daemon=True)
        self._stderr_thread.start()
        # Listening mode: if audio is already above threshold at start (no initial silence detected),
        # switch into recording to avoid missing content.
        self._listen_watchdog_thread = threading.Thread(target=self._listen_start_watchdog, daemon=True)
        self._listen_watchdog_thread.start()

        return self.status()

    def stop(
        self,
        *,
        reason: str = "manual",
        disable_auto: bool = True,
        restart_listen: bool = False,
        finalize_recording: bool = True,
    ) -> dict[str, Any]:
        with self._lock:
            proc = self._proc
            meta_file = Path(self._state.meta_file) if self._state.meta_file else None
            audio_file = Path(self._state.audio_file) if self._state.audio_file else None
            auto_listen = bool(self._state.auto_listen)
            if not proc or proc.poll() is not None:
                self._state.running = False
                self._state.status = "idle"
                if disable_auto:
                    self._state.auto_listen = False
                self._proc = None
                return self.status()
            self._state.status = "stopping"
            self._state.message = reason
            self._stop_event.set()
            if disable_auto:
                self._state.auto_listen = False
                auto_listen = False

        try:
            proc.send_signal(signal.SIGINT)
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass

        try:
            proc.wait(timeout=8)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

        # mark stopped
        with self._lock:
            self._state.running = False
            self._state.status = "idle"
            self._proc = None

        if finalize_recording and meta_file:
            _write_json(
                meta_file,
                {
                    **_read_json(meta_file),
                    "status": "recorded",
                    "ended_at": _iso_now(),
                    "reason": reason,
                    "has_sound": bool(self._state.has_sound),
                    "first_sound_sec": self._state.first_sound_sec,
                    "last_sound_end_sec": self._state.last_sound_end_sec,
                },
            )

        # background post-processing: trim & transcribe
        if finalize_recording and audio_file and meta_file and audio_file.exists():
            try:
                self._state.saved_count = int(self._state.saved_count or 0) + 1
                self._state.last_saved_audio = audio_file.name
                self._state.last_saved_at = _iso_now()
            except Exception:
                pass
            threading.Thread(target=self._postprocess, args=(audio_file, meta_file), daemon=True).start()

        if restart_listen and auto_listen and self._state.mic_index is not None:
            try:
                self.start(
                    mic_index=int(self._state.mic_index),
                    system_index=int(self._state.system_index) if self._state.system_index is not None else None,
                    threshold_db=float(self._state.threshold_db),
                    silence_stop_seconds=int(self._state.silence_stop_seconds),
                    fmt=str(self._state.format or "ogg"),
                )
            except Exception:
                # best effort: keep idle
                pass

        return self.status()

    # --------------------- internal threads ---------------------

    def _listen_start_watchdog(self) -> None:
        # If the stream is already "non-silent" at startup, silencedetect won't emit silence_start:0.
        # After a short grace period, start recording proactively (best effort).
        time.sleep(1.0)
        with self._lock:
            if self._stop_event.is_set():
                return
            if not self._proc or self._proc.poll() is not None:
                return
            if not self._state.auto_listen or self._state.status != "listening":
                return
            if self._listen_initial_silence_seen:
                return
        try:
            self._trigger_recording_switch("sound_at_start")
        except Exception:
            pass

    def _trigger_recording_switch(self, why: str) -> None:
        with self._lock:
            if not self._state.auto_listen or self._state.status != "listening":
                return
            if self._switching_to_recording:
                return
            if self._state.mic_index is None:
                return
            self._switching_to_recording = True
            cfg = {
                "mic_index": int(self._state.mic_index),
                "system_index": int(self._state.system_index) if self._state.system_index is not None else None,
                "threshold_db": float(self._state.threshold_db),
                "silence_stop_seconds": int(self._state.silence_stop_seconds),
                "fmt": str(self._state.format or "ogg"),
            }
            self._state.message = f"switch_to_recording: {why}"
        threading.Thread(target=self._switch_to_recording_worker, kwargs=cfg, daemon=True).start()

    def _switch_to_recording_worker(
        self,
        *,
        mic_index: int,
        system_index: int | None,
        threshold_db: float,
        silence_stop_seconds: int,
        fmt: str,
    ) -> None:
        try:
            # stop listening process (no file)
            self.stop(reason="switch_to_recording", disable_auto=False, restart_listen=False, finalize_recording=False)
            with self._lock:
                if not self._state.auto_listen:
                    return
            self._start_recording(
                mic_index=mic_index,
                system_index=system_index,
                threshold_db=threshold_db,
                silence_stop_seconds=silence_stop_seconds,
                fmt=fmt,
            )
        finally:
            with self._lock:
                self._switching_to_recording = False

    def _start_recording(
        self,
        *,
        mic_index: int,
        system_index: int | None,
        threshold_db: float,
        silence_stop_seconds: int,
        fmt: str,
    ) -> None:
        ffmpeg = _ffmpeg_path()
        if not ffmpeg:
            with self._lock:
                self._state.supported = False
                self._state.status = "error"
                self._state.message = "ffmpeg not found"
            return

        audio_path, meta_path = _build_recording_paths(fmt)
        _write_json(
            meta_path,
            {
                "status": "recording",
                "created_at": _iso_now(),
                "audio_file": audio_path.name,
                "format": fmt,
                "mic_index": mic_index,
                "system_index": system_index,
                "threshold_db": threshold_db,
                "silence_stop_seconds": silence_stop_seconds,
            },
        )

        fmt_norm = (fmt or "ogg").lower().strip() or "ogg"
        with self._lock:
            if self._proc and self._proc.poll() is None:
                return
            saved_count = int(getattr(self._state, "saved_count", 0) or 0)
            last_saved_audio = getattr(self._state, "last_saved_audio", None)
            last_saved_at = getattr(self._state, "last_saved_at", None)
            self._stop_event.clear()
            self._listen_initial_silence_seen = False
            self._state = RecorderRuntimeState(
                supported=True,
                running=True,
                status="recording",
                message="",
                auto_listen=True,
                format=fmt_norm,
                saved_count=saved_count,
                last_saved_audio=last_saved_audio,
                last_saved_at=last_saved_at,
                audio_file=str(audio_path),
                meta_file=str(meta_path),
                started_at=_iso_now(),
                mic_index=mic_index,
                system_index=system_index,
                threshold_db=float(threshold_db),
                silence_stop_seconds=int(silence_stop_seconds),
                has_sound=True,  # triggered by sound
                first_sound_sec=0.0,
                silence_started_wall=None,
                last_sound_end_sec=None,
            )

        args: list[str] = [ffmpeg, "-hide_banner", "-loglevel", "info", "-y"]
        inputs: list[int] = [mic_index]
        if system_index is not None and int(system_index) != int(mic_index):
            inputs.append(int(system_index))
        for idx in inputs:
            args += ["-f", "avfoundation", "-i", f":{idx}"]

        thr = float(threshold_db)
        silence_d = 1.0
        if len(inputs) == 1:
            filt = f"aresample=48000,silencedetect=noise={thr}dB:d={silence_d}"
            args += ["-af", filt]
        else:
            labels = "".join([f"[{i}:a]" for i in range(len(inputs))])
            filt = f"{labels}amix=inputs={len(inputs)}:duration=longest:dropout_transition=2,aresample=48000,silencedetect=noise={thr}dB:d={silence_d}[a]"
            args += ["-filter_complex", filt, "-map", "[a]"]

        if fmt_norm == "flac":
            args += ["-c:a", "flac", str(audio_path)]
        else:
            args += [
                "-c:a",
                "libopus",
                "-b:a",
                "32k",
                "-vbr",
                "on",
                "-compression_level",
                "10",
                "-application",
                "audio",
                "-f",
                "ogg",
                str(audio_path),
            ]

        try:
            proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )
        except Exception as e:
            with self._lock:
                self._state.running = False
                self._state.status = "error"
                self._state.message = f"failed to start ffmpeg: {e}"
            _write_json(meta_path, {**_read_json(meta_path), "status": "error", "error": str(e)})
            return

        with self._lock:
            self._proc = proc

        self._stderr_thread = threading.Thread(target=self._consume_stderr, daemon=True)
        self._stderr_thread.start()
        self._watchdog_thread = threading.Thread(target=self._silence_watchdog, daemon=True)
        self._watchdog_thread.start()

    def _consume_stderr(self) -> None:
        proc = None
        meta_path = None
        with self._lock:
            proc = self._proc
            meta_path = Path(self._state.meta_file) if self._state.meta_file else None
        if not proc or not proc.stderr:
            return

        # Parse ffmpeg silencedetect logs:
        #   silence_start: 12.345
        #   silence_end: 15.678 | silence_duration: 3.333
        re_start = re.compile(r"silence_start:\s*([0-9.]+)")
        re_end = re.compile(r"silence_end:\s*([0-9.]+)")

        for line in proc.stderr:
            if self._stop_event.is_set():
                break
            if not line:
                continue
            m1 = re_start.search(line)
            if m1:
                try:
                    t = float(m1.group(1))
                except Exception:
                    t = None  # type: ignore[assignment]
                switch_why: str | None = None
                with self._lock:
                    if self._state.status == "listening":
                        if t is not None and t <= 0.05:
                            self._listen_initial_silence_seen = True
                        elif t is not None and not self._listen_initial_silence_seen:
                            # sound existed at start (then became silent) -> start recording best effort
                            switch_why = "sound_at_start"
                    else:
                        # recording mode:
                        # If we never saw any sound and silence starts later, it means we started with sound.
                        if self._state.first_sound_sec is None and t is not None and t > 0:
                            self._state.first_sound_sec = 0.0
                            self._state.has_sound = True
                            self._state.status = "recording"
                        if t is not None:
                            self._state.last_sound_end_sec = t
                        # only trigger silence-stop timer after we have seen sound at least once
                        if self._state.has_sound:
                            self._state.silence_started_wall = time.monotonic()
                            self._state.status = "silence"
                if switch_why:
                    try:
                        self._trigger_recording_switch(switch_why)
                    except Exception:
                        pass
                    continue
                with self._lock:
                    if self._state.status == "listening":
                        continue
                if meta_path:
                    _write_json(meta_path, {**_read_json(meta_path), "last_event": "silence_start", "last_sound_end_sec": t})
                continue

            m2 = re_end.search(line)
            if m2:
                try:
                    t = float(m2.group(1))
                except Exception:
                    t = None  # type: ignore[assignment]
                switch_why = None
                with self._lock:
                    if self._state.status == "listening":
                        switch_why = "silence_end"
                    else:
                        self._state.has_sound = True
                        if self._state.first_sound_sec is None and t is not None:
                            # sound begins at silence_end (approx)
                            self._state.first_sound_sec = max(0.0, float(t) - 0.01)
                        self._state.silence_started_wall = None
                        self._state.status = "recording"
                if switch_why:
                    try:
                        self._trigger_recording_switch(switch_why)
                    except Exception:
                        pass
                    continue
                if meta_path:
                    _write_json(meta_path, {**_read_json(meta_path), "last_event": "silence_end", "first_sound_sec": self._state.first_sound_sec})
                continue

        # If ffmpeg exits unexpectedly, update state
        try:
            code = proc.poll()
        except Exception:
            code = None
        if code is None:
            return
        with self._lock:
            # Ignore stale threads from previous processes (e.g. switch listening -> recording)
            if proc is not self._proc:
                return
            # If we intentionally stopped/are stopping, don't surface it as an error.
            if self._state.status in {"stopping", "idle"}:
                self._state.running = False
                self._proc = None
                return
            if code == 0:
                self._state.running = False
                self._state.status = "idle"
                self._state.message = "ffmpeg exited"
                self._proc = None
                return
            self._state.running = False
            self._state.status = "error"
            self._state.message = f"ffmpeg exited with code {code}"
            self._proc = None

    def _silence_watchdog(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(0.5)
            with self._lock:
                running = bool(self._proc and self._proc.poll() is None)
                silence_started = self._state.silence_started_wall
                stop_after = self._state.silence_stop_seconds
                has_sound = self._state.has_sound
                auto_listen = bool(self._state.auto_listen)
            if not running:
                return
            if has_sound and silence_started and (time.monotonic() - silence_started) >= max(5, int(stop_after)):
                # auto stop after silence timeout
                try:
                    self.stop(reason="silence_timeout", disable_auto=not auto_listen, restart_listen=auto_listen, finalize_recording=True)
                except Exception:
                    pass
                return

    def _postprocess(self, audio_path: Path, meta_path: Path) -> None:
        # best effort: trim leading/trailing silence using ffmpeg -ss/-to based on detected timestamps
        ffmpeg = _ffmpeg_path()
        if not ffmpeg:
            return
        meta = _read_json(meta_path)
        _write_json(meta_path, {**meta, "status": "postprocessing", "postprocess_started_at": _iso_now()})
        try:
            first_sound = meta.get("first_sound_sec")
            last_sound_end = meta.get("last_sound_end_sec")
            if isinstance(first_sound, (int, float)) and isinstance(last_sound_end, (int, float)) and last_sound_end > first_sound:
                ss = max(0.0, float(first_sound) - 0.2)
                to = float(last_sound_end) + 0.2
                tmp = audio_path.with_suffix(audio_path.suffix + ".trim.tmp")
                # re-encode to keep container consistent
                cmd = [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(audio_path),
                    "-ss",
                    f"{ss:.2f}",
                    "-to",
                    f"{to:.2f}",
                ]
                if audio_path.suffix.lower() == ".flac":
                    cmd += ["-c:a", "flac", str(tmp)]
                else:
                    cmd += ["-c:a", "libopus", "-b:a", "32k", "-vbr", "on", "-compression_level", "10", "-application", "audio", "-f", "ogg", str(tmp)]
                subprocess.run(cmd, check=True, timeout=180)
                try:
                    tmp.replace(audio_path)
                except Exception:
                    pass
        except Exception as e:
            _write_json(meta_path, {**_read_json(meta_path), "postprocess_error": str(e)})

        # transcribe (optional)
        whisper = _whisper_path()
        if not whisper:
            _write_json(meta_path, {**_read_json(meta_path), "status": "done", "message": "whisper not found"})
            return
        try:
            _write_json(meta_path, {**_read_json(meta_path), "status": "transcribing", "transcribe_started_at": _iso_now()})
            model = (os.getenv("WHISPER_MODEL") or "base").strip()
            lang = (os.getenv("WHISPER_LANGUAGE") or "Chinese").strip()
            # write transcript next to audio (minutes scanner will treat it as sidecar and skip duplication)
            subprocess.run(
                [
                    whisper,
                    str(audio_path),
                    "--model",
                    model,
                    "--language",
                    lang,
                    "--task",
                    "transcribe",
                    "--output_format",
                    "txt",
                    "--output_dir",
                    str(audio_path.parent),
                ],
                check=True,
                timeout=6 * 3600,
            )
            transcript = audio_path.with_suffix(".txt")
            if transcript.exists():
                _write_json(
                    meta_path,
                    {
                        **_read_json(meta_path),
                        "status": "done",
                        "transcribe_done_at": _iso_now(),
                        "transcript_file": transcript.name,
                    },
                )
            else:
                _write_json(meta_path, {**_read_json(meta_path), "status": "done", "message": "transcript not found"})
        except Exception as e:
            _write_json(meta_path, {**_read_json(meta_path), "status": "error", "transcribe_error": str(e)})


_RECORDER: MeetingRecorder | None = None
_RECORDER_LOCK = threading.Lock()


def get_meeting_recorder() -> MeetingRecorder:
    global _RECORDER
    with _RECORDER_LOCK:
        if _RECORDER is None:
            _RECORDER = MeetingRecorder()
        return _RECORDER
