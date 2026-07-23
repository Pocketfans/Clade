from hashlib import md5

from ..speciation import SpeciationService
from ..speciation_naming import fallback_common_name, fallback_latin_name


def test_latin_fallback_preserves_keyword_order_and_genus() -> None:
    assert fallback_latin_name(
        "Aqua primus", {"key_innovations": ["快速游泳"]}
    ) == "Aqua natans"
    assert fallback_latin_name(
        "Aqua primus", {"key_innovations": ["深海适应"]}
    ) == "Aqua profundus"
    assert fallback_latin_name(
        "单名", {"key_innovations": ["耐寒"]}
    ) == "Species cryophilus"


def test_latin_fallback_preserves_hash_inputs() -> None:
    innovations = ["未知特征"]
    innovation_suffix = md5(str(innovations).encode()).hexdigest()[:6]
    assert fallback_latin_name(
        "Aqua primus", {"key_innovations": innovations}
    ) == f"Aqua sp{innovation_suffix}"

    content = {"key_innovations": []}
    content_suffix = md5(str(content).encode()).hexdigest()[:6]
    assert fallback_latin_name(
        "Aqua primus", content
    ) == f"Aqua sp{content_suffix}"


def test_common_fallback_preserves_feature_and_taxon_rules() -> None:
    assert fallback_common_name(
        "远古海虫", {"key_innovations": ["多鞭毛"]}
    ) == "多鞭海虫"
    assert fallback_common_name(
        "远古海虫", {"key_innovations": ["坚固外壳"]}
    ) == "坚固海虫"


def test_empty_common_fallback_preserves_hash_input() -> None:
    content = {"key_innovations": []}
    suffix = md5(str(content).encode()).hexdigest()[:2]

    assert fallback_common_name("虫", content) == f"型{suffix}生物"


def test_speciation_service_keeps_fallback_name_methods() -> None:
    service = object.__new__(SpeciationService)
    content = {"key_innovations": ["透明"]}

    assert service._fallback_latin_name(
        "Aqua primus", content
    ) == fallback_latin_name("Aqua primus", content)
    assert service._fallback_common_name(
        "远古海虫", content
    ) == fallback_common_name("远古海虫", content)
