"""Remote access gateway for a real AOSP Android Emulator instance."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

ANDROID_HOME = Path(os.environ.get("ANDROID_HOME", "/opt/android-sdk"))
IMAGE_DIR = Path(os.environ.get("AOSP_IMAGE_DIR", "/opt/aosp-image"))
DATA_DIR = Path(os.environ.get("ANDROID_DATA_DIR", "/data"))
AVD_HOME = Path(os.environ.get("ANDROID_AVD_HOME", "/data/avd"))
SERIAL = os.environ.get("ANDROID_SERIAL", "emulator-5554")
EMULATOR_BIN = ANDROID_HOME / "emulator" / "emulator"
ADB_BIN = ANDROID_HOME / "platform-tools" / "adb"
MEMORY_MB = max(2048, int(os.environ.get("EMULATOR_MEMORY_MB", "4096")))
CPU_CORES = max(2, int(os.environ.get("EMULATOR_CORES", "4")))

app = FastAPI(title="AOSP Android 12 Remote Lab", docs_url=None, redoc_url=None)
children: dict[str, asyncio.subprocess.Process] = {}
emulator_process: asyncio.subprocess.Process | None = None
emulator_lock = asyncio.Lock()

KEYCODES = {
    "HOME": 3,
    "BACK": 4,
    "CALL": 5,
    "ENDCALL": 6,
    "POWER": 26,
    "VOLUME_UP": 24,
    "VOLUME_DOWN": 25,
    "ENTER": 66,
    "MENU": 82,
    "NOTIFICATIONS": 83,
    "APP_SWITCH": 187,
    "ESCAPE": 111,
    "DPAD_UP": 19,
    "DPAD_DOWN": 20,
    "DPAD_LEFT": 21,
    "DPAD_RIGHT": 22,
    "DPAD_CENTER": 23,
}


class KeyInput(BaseModel):
    key: str = Field(min_length=1, max_length=32)


class TapInput(BaseModel):
    x: int = Field(ge=0, le=10000)
    y: int = Field(ge=0, le=10000)


class SwipeInput(BaseModel):
    x1: int = Field(ge=0, le=10000)
    y1: int = Field(ge=0, le=10000)
    x2: int = Field(ge=0, le=10000)
    y2: int = Field(ge=0, le=10000)
    duration_ms: int = Field(default=300, ge=1, le=5000)


def _emulator_log_tail(limit: int = 4000) -> str | None:
    log_path = DATA_DIR / "emulator.log"
    try:
        with log_path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read().decode("utf-8", "replace").strip() or None
    except OSError:
        return None


def _image_files() -> dict[str, bool]:
    return {
        "system.img": (IMAGE_DIR / "system.img").is_file(),
        "ramdisk.img": (IMAGE_DIR / "ramdisk.img").is_file(),
        "kernel": (IMAGE_DIR / "kernel-ranchu").is_file() or (IMAGE_DIR / "kernel").is_file(),
    }


def _avd_config() -> None:
    avd_dir = AVD_HOME / "aosp12.avd"
    avd_dir.mkdir(parents=True, exist_ok=True)
    AVD_HOME.mkdir(parents=True, exist_ok=True)
    (AVD_HOME / "aosp12.ini").write_text(
        f"path={avd_dir}\n"
        "path.rel=avd/aosp12.avd\n"
        "target=android-31\n",
        encoding="utf-8",
    )
    (avd_dir / "config.ini").write_text(
        "AvdId=aosp12\n"
        "avd.ini.displayname=AOSP Android 12\n"
        "abi.type=x86_64\n"
        "hw.cpu.arch=x86_64\n"
        f"hw.cpu.ncore={CPU_CORES}\n"
        f"hw.ramSize={MEMORY_MB}\n"
        "hw.lcd.width=480\n"
        "hw.lcd.height=960\n"
        "hw.lcd.density=240\n"
        "hw.keyboard=yes\n"
        "hw.mainKeys=no\n"
        "hw.gpu.enabled=yes\n"
        "hw.gpu.mode=swiftshader\n"
        "hw.audioInput=no\n"
        "hw.audioOutput=no\n"
        "hw.camera.back=none\n"
        "hw.camera.front=none\n"
        "disk.dataPartition.size=6G\n"
        "PlayStore.enabled=false\n"
        "image.sysdir.1=/opt/aosp-image/\n"
        "tag.id=default\n"
        "target=android-31\n",
        encoding="utf-8",
    )


async def _spawn(name: str, *args: str, env: dict[str, str] | None = None) -> asyncio.subprocess.Process:
    old = children.get(name)
    if old and old.returncode is None:
        return old
    merged_env = os.environ.copy()
    merged_env.update({"DISPLAY": ":0", "ANDROID_HOME": str(ANDROID_HOME), "ANDROID_SDK_ROOT": str(ANDROID_HOME)})
    if env:
        merged_env.update(env)
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        env=merged_env,
    )
    children[name] = proc
    return proc


async def _start_desktop() -> None:
    # All remote desktop listeners bind to the container network only; nginx is the public gateway.
    await _spawn("xvfb", "Xvfb", ":0", "-screen", "0", "1440x1200x24", "-ac", "+extension", "GLX", "+render", "-noreset")
    await asyncio.sleep(0.8)
    await _spawn("openbox", "openbox")
    await _spawn(
        "x11vnc", "x11vnc", "-display", ":0", "-forever", "-shared", "-nopw",
        "-listen", "0.0.0.0", "-rfbport", "5900", "-noxdamage", "-repeat",
    )
    await _spawn("websockify", "websockify", "--web=/usr/share/novnc", "6080", "127.0.0.1:5900")
    await asyncio.sleep(0.5)
    # adb is started by the first API call / emulator startup.


async def _adb(*args: str, timeout: float = 5.0) -> tuple[int, str, str]:
    if not ADB_BIN.is_file():
        return 127, "", f"adb não encontrado em {ADB_BIN}"
    try:
        proc = await asyncio.create_subprocess_exec(
            str(ADB_BIN), *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "ANDROID_HOME": str(ANDROID_HOME), "ANDROID_SDK_ROOT": str(ANDROID_HOME)},
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode or 0, out.decode("utf-8", "replace").strip(), err.decode("utf-8", "replace").strip()
    except asyncio.TimeoutError:
        return 124, "", "timeout a executar adb"
    except FileNotFoundError:
        return 127, "", "adb não encontrado"


async def _require_adb() -> None:
    code, out, err = await _adb("-s", SERIAL, "get-state", timeout=3)
    if code != 0 or out != "device":
        raise HTTPException(status_code=503, detail="O dispositivo Android ainda não está disponível. Consulte o estado do arranque.")


async def _start_emulator() -> None:
    global emulator_process
    async with emulator_lock:
        if emulator_process is not None and emulator_process.returncode is None:
            return
        missing = [name for name, present in _image_files().items() if not present]
        if missing:
            raise HTTPException(
                status_code=503,
                detail=("Imagem AOSP não preparada. Faltam: " + ", ".join(missing)
                        + ". Compile a tag Android 12 e copie out/target/product/sdk_phone_x86_64 para a pasta aosp-image."),
            )
        if not EMULATOR_BIN.is_file():
            raise HTTPException(status_code=503, detail=f"Android Emulator não encontrado em {EMULATOR_BIN}.")
        _avd_config()
        kernel = IMAGE_DIR / "kernel-ranchu"
        if not kernel.is_file():
            kernel = IMAGE_DIR / "kernel"
        cmd = [
            str(EMULATOR_BIN), "-avd", "aosp12", "-sysdir", str(IMAGE_DIR), "-kernel", str(kernel),
            "-no-audio", "-no-boot-anim", "-gpu", "swiftshader", "-no-snapshot",
            "-memory", str(MEMORY_MB), "-cores", str(CPU_CORES), "-camera-back", "none", "-camera-front", "none",
        ]
        merged = os.environ.copy()
        merged.update({
            "DISPLAY": ":0", "ANDROID_HOME": str(ANDROID_HOME), "ANDROID_SDK_ROOT": str(ANDROID_HOME),
            "ANDROID_AVD_HOME": str(AVD_HOME), "HOME": "/data/home",
        })
        Path("/data/home").mkdir(parents=True, exist_ok=True)
        log_path = DATA_DIR / "emulator.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with log_path.open("wb") as log_handle:
                emulator_process = await asyncio.create_subprocess_exec(
                    *cmd, stdout=log_handle, stderr=asyncio.subprocess.STDOUT,
                    stdin=asyncio.subprocess.DEVNULL, env=merged,
                )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=f"Não foi possível iniciar o emulador: {exc}") from exc
        # The emulator process may start immediately; boot readiness is monitored separately.
        await asyncio.sleep(0.3)
        if emulator_process.returncode is not None:
            rc = emulator_process.returncode
            emulator_process = None
            tail = _emulator_log_tail() or "sem log disponível"
            raise HTTPException(status_code=503, detail=f"O emulador terminou durante o arranque (código {rc}). Log: {tail}")


async def _stop_emulator() -> None:
    global emulator_process
    async with emulator_lock:
        proc = emulator_process
        if proc is None or proc.returncode is not None:
            emulator_process = None
            return
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=12)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        emulator_process = None


@app.on_event("startup")
async def startup() -> None:
    await _start_desktop()
    # Starting the real AOSP image is best-effort: a deployment can still serve an accurate
    # diagnostic/status page before its build artifacts have been mounted.
    try:
        await _start_emulator()
        await _adb("start-server", timeout=5)
    except HTTPException:
        pass


@app.on_event("shutdown")
async def shutdown() -> None:
    await _stop_emulator()
    for name, proc in list(children.items()):
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=3)
            except asyncio.TimeoutError:
                proc.kill()


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "service": "aosp-android12-remote-lab"}


@app.get("/api/status")
async def status() -> dict:
    files = _image_files()
    process_running = emulator_process is not None and emulator_process.returncode is None
    state = "offline"
    version = sdk = build_id = None
    adb_error = None
    code, state_out, err = await _adb("-s", SERIAL, "get-state", timeout=2)
    if code == 0 and state_out == "device":
        code2, boot, err2 = await _adb("-s", SERIAL, "shell", "getprop", "sys.boot_completed", timeout=3)
        code3, version_out, _ = await _adb("-s", SERIAL, "shell", "getprop", "ro.build.version.release", timeout=3)
        code4, sdk_out, _ = await _adb("-s", SERIAL, "shell", "getprop", "ro.build.version.sdk", timeout=3)
        code5, build_out, _ = await _adb("-s", SERIAL, "shell", "getprop", "ro.build.display.id", timeout=3)
        state = "booted" if code2 == 0 and boot == "1" else "starting"
        version = version_out if code3 == 0 and version_out else None
        sdk = sdk_out if code4 == 0 and sdk_out else None
        build_id = build_out if code5 == 0 and build_out else None
        adb_error = err2 or None
    else:
        adb_error = err or None
        if process_running:
            state = "starting"
    return {
        "service": "AOSP Android 12 remote lab",
        "emulator_process_running": process_running,
        "android_state": state,
        "android_version": version,
        "android_sdk": sdk,
        "build_id": build_id,
        "expected_android_version": "12",
        "image_dir": str(IMAGE_DIR),
        "image_files": files,
        "image_ready": all(files.values()),
        "adb_error": adb_error,
        "emulator_log_tail": None if state == "booted" else _emulator_log_tail(),
        "stream": "noVNC/WebSocket",
        "input": "noVNC mouse/keyboard + Android input API",
    }


@app.post("/api/start")
async def start() -> dict:
    await _start_emulator()
    await _adb("start-server", timeout=5)
    return {"ok": True, "message": "Processo do emulador iniciado; o arranque do Android pode demorar."}


@app.post("/api/stop")
async def stop() -> dict:
    await _stop_emulator()
    return {"ok": True, "message": "Emulador parado; os dados persistentes foram mantidos."}


@app.post("/api/restart")
async def restart() -> dict:
    await _stop_emulator()
    await _start_emulator()
    return {"ok": True, "message": "Emulador reiniciado; aguarde até o Android concluir o arranque."}


@app.post("/api/reboot")
async def reboot() -> dict:
    await _require_adb()
    code, _, err = await _adb("-s", SERIAL, "reboot", timeout=3)
    if code != 0:
        raise HTTPException(status_code=503, detail=err or "O comando de reinício falhou.")
    return {"ok": True, "message": "Foi enviado o comando de reinício ao Android."}


@app.post("/api/input/key")
async def input_key(body: KeyInput) -> dict:
    await _require_adb()
    key = body.key.upper()
    if key not in KEYCODES:
        raise HTTPException(status_code=422, detail=f"Tecla não permitida. Teclas disponíveis: {', '.join(KEYCODES)}")
    code, _, err = await _adb("-s", SERIAL, "shell", "input", "keyevent", str(KEYCODES[key]), timeout=4)
    if code != 0:
        raise HTTPException(status_code=503, detail=err or "Não foi possível enviar o evento de tecla.")
    return {"ok": True, "key": key}


@app.post("/api/input/tap")
async def input_tap(body: TapInput) -> dict:
    await _require_adb()
    code, _, err = await _adb("-s", SERIAL, "shell", "input", "tap", str(body.x), str(body.y), timeout=4)
    if code != 0:
        raise HTTPException(status_code=503, detail=err or "Não foi possível enviar o toque.")
    return {"ok": True, "x": body.x, "y": body.y}


@app.post("/api/input/swipe")
async def input_swipe(body: SwipeInput) -> dict:
    await _require_adb()
    code, _, err = await _adb(
        "-s", SERIAL, "shell", "input", "swipe", str(body.x1), str(body.y1), str(body.x2), str(body.y2), str(body.duration_ms), timeout=5
    )
    if code != 0:
        raise HTTPException(status_code=503, detail=err or "Não foi possível enviar o gesto.")
    return {"ok": True}
