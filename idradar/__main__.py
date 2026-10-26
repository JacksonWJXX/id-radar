"""仅在本机监听，服务就绪后打开浏览器。"""

import socket
import argparse
import threading
import time
import webbrowser

import uvicorn
from .i18n import t


def open_when_ready():
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", 8765), timeout=0.2):
                webbrowser.open("http://127.0.0.1:8765")
                return
        except OSError:
            time.sleep(0.1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=t("cli.description", lang="en") + " / " + t("cli.description", lang="zh"))
    parser.add_argument("--demo", action="store_true", help=t("cli.demo", lang="en") + " / " + t("cli.demo", lang="zh"))
    args = parser.parse_args(argv)
    # 先确认端口可用，避免误打开占用同一端口的其他程序。
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 8765))
    except OSError:
        raise SystemExit(t("port", lang="zh") + "\n" + t("port", lang="en")) from None
    if args.demo:
        from .server import create_app
        application = create_app(demo=True)
        print(t("demo.url", lang="zh") + "\n" + t("demo.url", lang="en"))
    else:
        threading.Thread(target=open_when_ready, daemon=True).start()
        application = "idradar.server:app"
    uvicorn.run(application, host="127.0.0.1", port=8765, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
