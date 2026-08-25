# -*- coding: utf-8 -*-
"""
factor_defs_schema.py 的單元測試——這支模組本身就是「格式檢查員」，
它自己的檢查邏輯錯了，全專案的保護就形同虛設，所以特別要有測試。
"""
import copy
import json

import pytest

from factor_defs_schema import FactorDefinitionsError, validate_and_load


@pytest.fixture
def valid_defs():
    """以repo裡真實的 factor_definitions.json 為基準，回傳一份可以自由修改的複本。
    這樣測試永遠貼著『現行真實格式』走，不會因為手刻一份簡化版schema而跟現實脫鉤。"""
    with open("factor_definitions.json", encoding="utf-8") as f:
        return json.load(f)


def _write(tmp_path, data):
    path = tmp_path / "factor_definitions.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


class TestValidFile:
    def test_real_repo_file_passes(self):
        """回歸鎖：如果有人不小心把repo裡真的那份factor_definitions.json改壞，
        這個測試會第一個爆掉——比等到CI跑到update_dashboard.py才發現快得多。"""
        d = validate_and_load()
        assert isinstance(d, dict)
        assert len(d["factors"]) >= 1

    def test_returns_plain_dict_not_pydantic_model(self, tmp_path, valid_defs):
        """全專案既有程式碼都用 DEFS["factors"][0]["params"] 這種dict語法存取，
        驗證器絕對不能回傳pydantic model實例，不然到處都要重寫。"""
        path = _write(tmp_path, valid_defs)
        d = validate_and_load(path)
        assert type(d) is dict
        assert type(d["factors"]) is list
        assert type(d["factors"][0]) is dict

    def test_extra_undeclared_fields_are_tolerated(self, tmp_path, valid_defs):
        """schema沒列出的欄位(像_readme這種純註解性質的欄位)不該讓驗證失敗——
        這份檢查員抓的是『必要欄位缺漏/型別錯誤』，不是要求每加一句註解都要先改schema。"""
        d = copy.deepcopy(valid_defs)
        d["_a_brand_new_comment_field_nobody_told_the_schema_about"] = "hello"
        path = _write(tmp_path, d)
        validate_and_load(path)  # 不該拋例外


class TestCatchesRealBreakage:
    """每個案例都對應真實可能發生的手滑錯誤，斷言錯誤訊息裡點名了正確的欄位——
    不是只測『有沒有拋例外』，還測『拋出的訊息有沒有指到問題所在』。"""

    def test_missing_required_field(self, tmp_path, valid_defs):
        d = copy.deepcopy(valid_defs)
        del d["factors"][0]["explain_tpl"]
        path = _write(tmp_path, d)
        with pytest.raises(FactorDefinitionsError, match="explain_tpl"):
            validate_and_load(path)

    def test_unknown_fetch_kind(self, tmp_path, valid_defs):
        """2026-08-11讓篩選平台整個掛掉的那類錯誤——data_sources.fetch打錯字，
        沒人抓得到、要等到執行到fetch_declared_sources()才KeyError。"""
        d = copy.deepcopy(valid_defs)
        d["data_sources"][0]["fetch"] = "yahooo"
        path = _write(tmp_path, d)
        with pytest.raises(FactorDefinitionsError, match="fetch"):
            validate_and_load(path)

    def test_duplicate_factor_key(self, tmp_path, valid_defs):
        d = copy.deepcopy(valid_defs)
        d["factors"].append(copy.deepcopy(d["factors"][0]))
        path = _write(tmp_path, d)
        with pytest.raises(FactorDefinitionsError, match="重複的 key"):
            validate_and_load(path)

    def test_duplicate_score_col(self, tmp_path, valid_defs):
        d = copy.deepcopy(valid_defs)
        clone = copy.deepcopy(d["factors"][0])
        clone["key"] = "some_other_key"  # key不重複，但score_col故意撞名
        d["factors"].append(clone)
        path = _write(tmp_path, d)
        with pytest.raises(FactorDefinitionsError, match="重複的 score_col"):
            validate_and_load(path)

    def test_duplicate_data_source_column(self, tmp_path, valid_defs):
        d = copy.deepcopy(valid_defs)
        d["data_sources"].append(copy.deepcopy(d["data_sources"][0]))
        path = _write(tmp_path, d)
        with pytest.raises(FactorDefinitionsError, match="重複的 column"):
            validate_and_load(path)

    def test_dead_zone_reversed(self, tmp_path, valid_defs):
        d = copy.deepcopy(valid_defs)
        d["validation"]["dead_zone"] = [52, 48]
        path = _write(tmp_path, d)
        with pytest.raises(FactorDefinitionsError, match="dead_zone"):
            validate_and_load(path)

    def test_label_thresholds_unsorted(self, tmp_path, valid_defs):
        d = copy.deepcopy(valid_defs)
        d["global"]["label_thresholds"] = list(reversed(d["global"]["label_thresholds"]))
        path = _write(tmp_path, d)
        with pytest.raises(FactorDefinitionsError, match="label_thresholds"):
            validate_and_load(path)

    def test_score_col_must_be_valid_identifier(self, tmp_path, valid_defs):
        """score_col 最終會被當成 pandas DataFrame 欄名使用(df["xxx"])，
        帶空格或特殊符號會在下游造成難以追查的錯誤，這裡直接在源頭擋掉。"""
        d = copy.deepcopy(valid_defs)
        d["factors"][0]["score_col"] = "not a valid column!"
        path = _write(tmp_path, d)
        with pytest.raises(FactorDefinitionsError):
            validate_and_load(path)

    def test_percentile_window_must_be_positive(self, tmp_path, valid_defs):
        d = copy.deepcopy(valid_defs)
        d["global"]["percentile_window_days"] = -100
        path = _write(tmp_path, d)
        with pytest.raises(FactorDefinitionsError, match="percentile_window_days"):
            validate_and_load(path)

    def test_error_message_lists_every_problem_not_just_the_first(self, tmp_path, valid_defs):
        d = copy.deepcopy(valid_defs)
        del d["factors"][0]["explain_tpl"]
        d["data_sources"][0]["fetch"] = "totally_wrong"
        path = _write(tmp_path, d)
        with pytest.raises(FactorDefinitionsError) as exc_info:
            validate_and_load(path)
        msg = str(exc_info.value)
        assert "explain_tpl" in msg
        assert "fetch" in msg
