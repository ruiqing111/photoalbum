"""本地 AI 相册 · 一键启动。

默认开一个原生窗口（pywebview + Edge WebView2，Chromium 内核），像普通桌面应用一样，
没有地址栏、没有浏览器标签页。加 --browser 则退回用系统浏览器打开。
"""
import argparse
import os
import socket
import sys
import threading
import time
import webbrowser

import uvicorn

# 双击打包好的 --noconsole exe 时没有控制台，sys.stdout / sys.stderr 都是 None；
# 而 uvicorn 的日志格式化器会调 sys.stdout.isatty()，一碰就 AttributeError 直接崩。
# 所以先把它们兜到空设备上，保证「没有控制台」也能正常起服务。
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")


class _Server(uvicorn.Server):
    """让 uvicorn 能跑在后台线程里（非主线程不允许注册信号处理）。"""

    def install_signal_handlers(self):
        pass


_mutex = None


def _already_running():
    """同一时间只允许一个实例。

    多个实例会同时读写同一个索引库、同时给缩略图预热，在移动硬盘上会把
    I/O 队列彻底打满（盘掉线、整窗卡死都是这么来的）。第二个实例只负责
    把已经打开的窗口叫到前台，然后自己退出。
    """
    global _mutex
    if os.name != "nt":
        return False
    import ctypes
    ERROR_ALREADY_EXISTS = 183
    # 必须用 use_last_error=True 的 WinDLL 再配 ctypes.get_last_error()：
    # 直接 k.GetLastError() 拿到的是别的调用留下的旧错误码（实测首次启动
    # 也会返回 183），程序会误以为自己已经开过，直接退出、什么都不弹。
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    u = ctypes.WinDLL("user32", use_last_error=True)
    _mutex = k.CreateMutexW(None, False, "Local\\PhotoAlbumSingletonV2")
    if ctypes.get_last_error() != ERROR_ALREADY_EXISTS:
        return False
    hwnd = u.FindWindowW(None, "照片 · 本地相册")
    if hwnd:
        u.ShowWindow(hwnd, 9)          # SW_RESTORE
        u.SetForegroundWindow(hwnd)
    else:
        u.MessageBoxW(
            None, "相册已经在运行了，请切换到已打开的窗口。\n"
                  "同时开多个窗口会让索引库和缩略图缓存互相抢盘。",
            "照片相册", 0x40)
    return True


def _wait_ready(port, timeout=15.0):
    """等端口真的能连上，免得窗口先开出来是一张空白页。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.05)
    return False


def _serve_in_background(port):
    server = _Server(uvicorn.Config(
        "app.server:app", host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server, thread


class _Api:
    """暴露给网页的原生能力，前端通过 window.pywebview.api 调用。"""

    def pick_folder(self, title=None):
        """调起系统文件夹选择框，返回选中的绝对路径；取消则返回 None。

        注意：原来的 tkinter 子进程方案在 pywebview 窗口里会卡死（子进程起来了却弹不出窗口），
        所以原生窗口下改用 pywebview 自带的对话框，它挂在应用窗口上，稳定且更原生。
        """
        import webview as wv
        win = wv.active_window() or (wv.windows[0] if wv.windows else None)
        if win is None:
            return None
        picked = win.create_file_dialog(wv.FileDialog.FOLDER, allow_multiple=False)
        if not picked:
            return None
        return picked[0]


def main():
    ap = argparse.ArgumentParser(description="本地 AI 照片相册")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--browser", action="store_true", help="用系统浏览器打开，不开原生窗口")
    args = ap.parse_args()
    url = f"http://127.0.0.1:{args.port}"

    if _already_running():
        return

    server, thread = _serve_in_background(args.port)
    if not _wait_ready(args.port):
        print("服务启动失败，请检查端口是否被占用")
        return

    webview = None
    if not args.browser:
        try:
            import webview as _webview
            webview = _webview
        except ImportError:
            print("没装 pywebview，已改用浏览器打开。想要原生窗口：py -3 -m pip install pywebview")

    if webview is None:
        webbrowser.open(url)
        print(f"相册已启动: {url}  (Ctrl+C 停止)")
        try:
            while thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            server.should_exit = True
        return

    webview.create_window("照片 · 本地相册", url, width=1400, height=900,
                          min_size=(960, 640), text_select=True, js_api=_Api())
    try:
        webview.start()          # 阻塞直到用户关掉窗口
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True        # 关窗即停服务，别留着后台线程占端口


if __name__ == "__main__":
    main()
