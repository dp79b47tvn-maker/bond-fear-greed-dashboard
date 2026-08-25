# -*- coding: utf-8 -*-
"""
factor_definitions.json 的格式檢查員（架構檢討第2項）。

問題：這份 JSON 是全專案的「唯一事實來源」，但過去完全沒有格式檢查——漏填一個
必要欄位、打錯一個 key，不會在存檔當下被發現，而是等到某支下游腳本執行到那一行
才 KeyError。2026-08-11 因子從七項改兩項時，data_sources 少宣告一個欄位，
就是這樣一路跑到因子篩選平台才爆掉，整個平台停擺。

這支模組不改變任何人讀 factor_definitions.json 的方式——validate_and_load() 驗證通過
後回傳的還是原本那個 dict，`DEFS["factors"][0]["params"]` 這種既有寫法完全不用改。
差別只在於：現在如果檔案格式有問題，會在載入的當下就得到一句講清楚哪裡錯的訊息，
而不是幾十個呼叫深、跟本來的錯誤完全對不上的 KeyError/TypeError。

三支原本各自 json.load() 這份檔案的模組（update_dashboard.py / transform_modes.py /
generate_hub.py）都改成呼叫這裡的 validate_and_load()，不再各自重複載入邏輯。
scripts/check_consistency.py 也用它——如果檔案本身結構就有問題，一致性檢查應該
第一個講清楚，而不是在後面的AST掃描裡莫名其妙報錯。
"""
import json
import os

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "factor_definitions.json")


class _Lenient(BaseModel):
    """允許 JSON 裡有 schema 沒列出的額外欄位（例如 _readme 這類純文件性質的欄位）——
    這份檢查員的目的是抓『必要欄位缺漏/型別錯誤』，不是要求每次加一句註解說明都要
    先改 schema，那樣會變成維護負擔而不是保護。"""
    model_config = ConfigDict(extra="allow")


class LabelThreshold(_Lenient):
    lt: float
    label: str


class GlobalConfig(_Lenient):
    percentile_window_days: int = Field(gt=0)
    fetch_start_date: str
    output_start_date: str
    composite_method: str
    label_thresholds: list[LabelThreshold] = Field(min_length=1)

    @field_validator("label_thresholds")
    @classmethod
    def _thresholds_sorted_ascending(cls, v):
        lts = [t.lt for t in v]
        if lts != sorted(lts):
            raise ValueError(f"label_thresholds 的 lt 必須由小到大排列，目前是 {lts}")
        return v


class FactorDef(_Lenient):
    key: str = Field(min_length=1)
    score_col: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    kicker: str
    name_tpl: str
    params: dict = Field(default_factory=dict)
    inputs: list[str]
    intermediate_cols: list[str] = Field(default_factory=list)
    formula_tpl: str
    uses_percentile: bool
    invert: bool
    code_location: str
    explain_tpl: str


class DataSource(_Lenient):
    column: str = Field(min_length=1)
    ticker: str
    fetch: str
    source: str

    @field_validator("fetch")
    @classmethod
    def _fetch_kind_known(cls, v):
        # 跟 update_dashboard.fetch_declared_sources() 認得的三種 kind 一致——
        # 這裡是格式檢查(值域對不對)，那邊是「這個值實際能不能執行」，兩者刻意分開，
        # 各自代表不同層次的保護。
        valid = {"yahoo", "fred", "treasury"}
        if v not in valid:
            raise ValueError(f"fetch 必須是 {sorted(valid)} 其中之一，收到 {v!r}")
        return v


class ValidationConfig(_Lenient):
    target: str
    horizons: list[int] = Field(min_length=1)
    dead_zone: list[float] = Field(min_length=2, max_length=2)

    @field_validator("dead_zone")
    @classmethod
    def _dead_zone_ordered(cls, v):
        if v[0] >= v[1]:
            raise ValueError(f"dead_zone 必須是 [下界, 上界] 且下界<上界，收到 {v}")
        return v


class FactorDefinitions(_Lenient):
    """頂層 schema。JSON 裡的欄位叫 "global"，但那是 Python 保留字不能直接當屬性名，
    這裡用 alias 對應——這個位置曾經漏掉過(屬性名打成沒人用的名字、alias沒接對)，
    當時因為頂層有 extra="allow"，"global" 那一整段會被當成「schema沒列出的額外欄位」
    整段跳過驗證，percentile_window_days 填負數、label_thresholds 順序顛倒都不會被抓到
    ——是 tests/test_factor_defs_schema.py 測出來的，這裡特別寫這段避免同類錯誤重演。"""
    version: str
    global_config: GlobalConfig = Field(alias="global")
    factors: list[FactorDef] = Field(min_length=1)
    validation: ValidationConfig
    data_sources: list[DataSource] = Field(min_length=1)

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    @model_validator(mode="after")
    def _no_duplicate_factor_keys(self):
        keys = [f.key for f in self.factors]
        if len(keys) != len(set(keys)):
            dup = [k for k in keys if keys.count(k) > 1]
            raise ValueError(f"factors 裡有重複的 key：{sorted(set(dup))}")
        score_cols = [f.score_col for f in self.factors]
        if len(score_cols) != len(set(score_cols)):
            dup = [c for c in score_cols if score_cols.count(c) > 1]
            raise ValueError(f"factors 裡有重複的 score_col：{sorted(set(dup))}")
        return self

    @model_validator(mode="after")
    def _no_duplicate_data_source_columns(self):
        cols = [s.column for s in self.data_sources]
        if len(cols) != len(set(cols)):
            dup = [c for c in cols if cols.count(c) > 1]
            raise ValueError(f"data_sources 裡有重複的 column：{sorted(set(dup))}")
        return self


class FactorDefinitionsError(Exception):
    """檔案格式有問題時拋出的例外——訊息已經整理成人看得懂的中文，直接印出來就好，
    不用像 pydantic 原生的 ValidationError 一樣自己再解析一次。"""


def validate_and_load(path=None):
    """讀取並驗證 factor_definitions.json，驗證通過就回傳**原始的 dict**
    （不是 pydantic model，也不是 model_dump 的複本）——現有程式碼一律用
    `DEFS["factors"][0]["params"]` 這種既有的 dict 存取方式，不需要因為加了
    schema 檢查而跟著改寫。

    驗證失敗時拋出 FactorDefinitionsError，訊息會列出每個欄位具體錯在哪裡。
    """
    path = path or DEFAULT_PATH
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    try:
        FactorDefinitions.model_validate(raw)
    except ValidationError as e:
        lines = [f"  · {'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()]
        raise FactorDefinitionsError(
            f"{path} 格式有問題，共 {len(e.errors())} 處：\n" + "\n".join(lines)
        ) from e

    return raw
