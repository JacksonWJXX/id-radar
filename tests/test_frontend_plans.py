"""用本机已有 Node 运行页面实际使用的纯函数，不启动浏览器或访问网络。"""

from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize("script", ["frontend_plans.cjs", "frontend_components.cjs"])
def test_frontend_adoption_export_selection_and_plan(script):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(["node", str(root / "tests" / script)], cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
