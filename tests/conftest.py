# -*- coding: utf-8 -*-
"""
pytest 共用設定。

這個專案的模組習慣用**相對路徑**讀 `factor_definitions.json`（例如
`transform_modes.py` 開頭 `open("factor_definitions.json")`），代表哪個目錄底下執行
會影響能不能 import——這是既有的架構限制，不是這份測試套件造成的，但測試必須繞過它：
把 repo 根目錄加進 CWD 與 sys.path，讓 `pytest`（不管從哪個目錄呼叫）都能正確 import。
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
