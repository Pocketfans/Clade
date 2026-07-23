from __future__ import annotations


def fallback_latin_name(parent_latin: str, ai_content: dict) -> str:
    """生成备用拉丁名。"""
    import hashlib

    genus = parent_latin.split()[0] if " " in parent_latin else "Species"
    innovations = ai_content.get("key_innovations", [])
    if innovations:
        innovation = innovations[0].lower()
        if "鞭毛" in innovation or "游" in innovation:
            epithet = "natans"
        elif "深" in innovation or "底" in innovation:
            epithet = "profundus"
        elif "快" in innovation or "速" in innovation:
            epithet = "velox"
        elif "慢" in innovation or "缓" in innovation:
            epithet = "lentus"
        elif "大" in innovation or "巨" in innovation:
            epithet = "magnus"
        elif "小" in innovation or "微" in innovation:
            epithet = "minutus"
        elif "透明" in innovation:
            epithet = "hyalinus"
        elif "耐盐" in innovation or "盐" in innovation:
            epithet = "salinus"
        elif "耐热" in innovation or "热" in innovation:
            epithet = "thermophilus"
        elif "耐寒" in innovation or "冷" in innovation:
            epithet = "cryophilus"
        else:
            hash_suffix = hashlib.md5(str(innovations).encode()).hexdigest()[:6]
            epithet = f"sp{hash_suffix}"
    else:
        hash_suffix = hashlib.md5(str(ai_content).encode()).hexdigest()[:6]
        epithet = f"sp{hash_suffix}"
    return f"{genus} {epithet}"


def fallback_common_name(parent_common: str, ai_content: dict) -> str:
    """生成备用中文名。"""
    import hashlib

    if len(parent_common) >= 2:
        taxon = (
            parent_common[-2:]
            if parent_common[-1] in "虫藻菌类贝鱼"
            else parent_common[-3:]
        )
    else:
        taxon = "生物"

    innovations = ai_content.get("key_innovations", [])
    if innovations:
        innovation = innovations[0]
        if "鞭毛" in innovation:
            if "多" in innovation or "4" in innovation or "增" in innovation:
                feature = "多鞭"
            elif "长" in innovation:
                feature = "长鞭"
            else:
                feature = "异鞭"
        elif "游" in innovation or "速" in innovation:
            if "快" in innovation or "提升" in innovation:
                feature = "快游"
            else:
                feature = "慢游"
        elif "深" in innovation or "底" in innovation:
            feature = "深水"
        elif "浅" in innovation or "表" in innovation:
            feature = "浅水"
        elif "耐盐" in innovation or "盐" in innovation:
            feature = "耐盐"
        elif "透明" in innovation:
            feature = "透明"
        elif "大" in innovation or "巨" in innovation:
            feature = "巨型"
        elif "小" in innovation or "微" in innovation:
            feature = "微型"
        elif "滤食" in innovation:
            feature = "滤食"
        elif "夜" in innovation:
            feature = "夜行"
        else:
            words = [c for c in innovation if "\u4e00" <= c <= "\u9fff"]
            feature = "".join(words[:2]) if len(words) >= 2 else "变异"
    else:
        hash_suffix = hashlib.md5(str(ai_content).encode()).hexdigest()[:2]
        feature = f"型{hash_suffix}"

    return f"{feature}{taxon}"
