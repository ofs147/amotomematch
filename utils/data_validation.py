"""AOMatch Character Database v2 CSV 验证器。"""

import argparse
import csv
from pathlib import Path
from typing import Dict, List, Sequence

from utils.data_utils import parse_tags
from utils.schema import (
    CSV_COLUMNS,
    DICTIONARY_TAG_FIELDS,
    NUMERIC_FEATURES,
    REQUIRED_BASIC_FIELDS,
    TAG_DICTIONARY,
    TAG_FIELDS,
)


FORBIDDEN_TAG_SEPARATORS = ("；", "、", "|", "，")


def validate_tag_dictionary() -> List[str]:
    """检查标准标签是否在不同字段重复归属。"""
    errors: List[str] = []
    owners: Dict[str, str] = {}
    for field, allowed_tags in TAG_DICTIONARY.items():
        if len(allowed_tags) != len(set(allowed_tags)):
            errors.append(f"Tag Dictionary 的 {field} 内存在重复标签")
        for tag in allowed_tags:
            if tag in owners:
                errors.append(f"标签“{tag}”同时属于 {owners[tag]} 和 {field}")
            owners[tag] = field
    return errors


def validate_rows(fieldnames: Sequence[str], rows: Sequence[Dict[str, str]]) -> List[str]:
    """验证字段、ID、必填值、Numeric 范围和 Tag 合法性。"""
    errors = validate_tag_dictionary()

    if tuple(fieldnames) != CSV_COLUMNS:
        errors.append("CSV 字段或字段顺序与 utils/schema.py 的 CSV_COLUMNS 不一致")

    seen_ids = set()
    for line_number, row in enumerate(rows, start=2):
        label = f"第 {line_number} 行"

        for field in REQUIRED_BASIC_FIELDS:
            if not (row.get(field) or "").strip():
                errors.append(f"{label}缺少必填字段 {field}")

        character_id = (row.get("character_id") or "").strip()
        if character_id in seen_ids:
            errors.append(f"{label}的 character_id 重复：{character_id}")
        seen_ids.add(character_id)

        for field in NUMERIC_FEATURES:
            raw_value = (row.get(field) or "").strip()
            if not raw_value or raw_value.upper() == "NA":
                continue
            try:
                value = float(raw_value)
            except ValueError:
                errors.append(f"{label}的 {field} 不是有效数字：{raw_value}")
                continue
            if not 1 <= value <= 5:
                errors.append(f"{label}的 {field} 超出 1～5：{raw_value}")
            elif not (value * 2).is_integer():
                errors.append(f"{label}的 {field} 必须使用 0.5 步进：{raw_value}")

        tags_seen_in_row: Dict[str, str] = {}
        for field in TAG_FIELDS:
            raw_value = (row.get(field) or "").strip()
            if any(separator in raw_value for separator in FORBIDDEN_TAG_SEPARATORS):
                errors.append(f"{label}的 {field} 使用了非标准 Tag 分隔符")

            raw_tags = [tag.strip() for tag in raw_value.split(";") if tag.strip()]
            if len(raw_tags) != len(set(raw_tags)):
                errors.append(f"{label}的 {field} 内存在重复标签")

            for tag in parse_tags(raw_value):
                if field in DICTIONARY_TAG_FIELDS and tag not in TAG_DICTIONARY[field]:
                    errors.append(f"{label}的 {field} 包含未登记标签：{tag}")
                if field != "keywords" and tag in tags_seen_in_row:
                    errors.append(
                        f"{label}的标签“{tag}”同时出现在 "
                        f"{tags_seen_in_row[tag]} 和 {field}"
                    )
                tags_seen_in_row[tag] = field

    return errors


def validate_csv(path: Path) -> List[str]:
    """读取并验证一个 v2 CSV，返回全部错误。"""
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        rows = list(reader)
        return validate_rows(reader.fieldnames or (), rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="验证 AOMatch Character Database v2")
    parser.add_argument("path", type=Path, help="要验证的 characters_v2.csv 路径")
    args = parser.parse_args()

    errors = validate_csv(args.path)
    if errors:
        print("验证失败：")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)
    print(f"验证通过：{args.path}")


if __name__ == "__main__":
    main()
