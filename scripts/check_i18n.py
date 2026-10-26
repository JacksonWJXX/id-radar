"""前端业务文件不得散落中文文案；仅允许简体中文注释。"""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FILES = ("app.js", "plans.js", "index.html")


def without_js_comments(text):
    result, quote, mode, escaped = [], None, None, False
    index = 0
    while index < len(text):
        char, next_char = text[index], text[index:index + 2]
        if mode == "line":
            result.append("\n" if char == "\n" else " ")
            if char == "\n":
                mode = None
        elif mode == "block":
            result.append("\n" if char == "\n" else " ")
            if next_char == "*/":
                result.append(" "); index += 1; mode = None
        elif quote:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in ("'", '"', "`"):
            quote = char; result.append(char)
        elif next_char in ("//", "/*"):
            mode = "line" if next_char == "//" else "block"
            result.append("  "); index += 1
        else:
            result.append(char)
        index += 1
    return "".join(result)


def violations():
    found = []
    for name in FILES:
        text = (ROOT / "idradar" / "static" / name).read_text(encoding="utf-8")
        text = re.sub(r"<!--[\s\S]*?-->", lambda match: "\n" * match.group().count("\n"), text) if name.endswith(".html") else without_js_comments(text)
        for number, line in enumerate(text.splitlines(), 1):
            if re.search(r"[\u3400-\u9fff]", line):
                found.append(f"{name}:{number}: {line.strip()}")
    return found


if __name__ == "__main__":
    errors = violations()
    if errors:
        raise SystemExit("\n".join(errors))
    print("前端中文文案均已集中，无业务文件残留。")
