"""B 模块准确性评测入口（9/25–27 交付项）。

用法：

    python tests/check_agent_accuracy.py                      # 全部套件，退出码 0/1
    python tests/check_agent_accuracy.py --suite math         # 只跑一个套件
    python tests/check_agent_accuracy.py --out tests/_accuracy_report.json   # 落盘完整报告

评测集、阈值与口径都写在 `backend/app/ai/evaluation.py`，本文件只是命令行入口，
保证“跑一次评测”对评审者只需一条命令，和 `tests/check_ai_contracts.py` 的用法保持一致。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.ai.evaluation import main  # noqa: E402

if __name__ == '__main__':
    print('B 模块准确性评测（规则与本地检索；真实模型效果未包含，见报告 scope）')
    raise SystemExit(main(sys.argv[1:]))
