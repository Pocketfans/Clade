from __future__ import annotations


def next_lineage_code(parent_code: str, existing_codes: set[str]) -> str:
    """生成单个子代编码。"""
    base = f"{parent_code}a"
    index = 1
    new_code = f"{base}{index}"
    while new_code in existing_codes:
        index += 1
        new_code = f"{base}{index}"
    return new_code


def generate_multiple_lineage_codes(
    parent_code: str,
    existing_codes: set[str],
    num_offspring: int,
) -> list[str]:
    """生成多个使用字母后缀的子代编码。"""
    letters = "abcdefghijklmnopqrstuvwxyz"
    codes = []

    for index in range(num_offspring):
        if index < len(letters):
            letter = letters[index]
            new_code = f"{parent_code}{letter}"
        else:
            repeat_index = index // len(letters) - 1
            letter_index = index % len(letters)
            letter = letters[letter_index]
            repeat = "#" * repeat_index
            new_code = f"{parent_code}{repeat}{letter}"

        if new_code in existing_codes:
            suffix = 1
            while f"{new_code}{suffix}" in existing_codes:
                suffix += 1
            new_code = f"{new_code}{suffix}"

        codes.append(new_code)

    return codes
