from __future__ import annotations

import logging

from ...models.species import Species

logger = logging.getLogger(f"{__package__}.speciation")


def process_ai_activated_genes(
    species: Species,
    activated_genes: list[str],
    turn_index: int,
) -> int:
    """处理 AI 指定要激活的休眠基因 v2.0。"""
    if not activated_genes:
        return 0

    if not species.dormant_genes:
        return 0

    # 导入显隐性系数
    try:
        from .gene_constants import (
            DOMINANCE_EXPRESSION_FACTOR,
            DominanceType,
            OrganStage,
        )
    except ImportError:
        DOMINANCE_EXPRESSION_FACTOR = {
            "recessive": 0.25,
            "codominant": 0.60,
            "dominant": 1.0,
            "overdominant": 1.15,
        }
        DominanceType = None
        OrganStage = None

    activated_count = 0

    for gene_name in activated_genes:
        # 尝试在休眠特质中查找
        if "traits" in species.dormant_genes:
            for trait_name, gene_data in species.dormant_genes[
                "traits"
            ].items():
                # 模糊匹配：基因名包含或被包含
                if (
                    gene_name in trait_name or trait_name in gene_name
                ) and not gene_data.get("activated", False):
                    # 阻止 AI 激活有害突变
                    mutation_effect = gene_data.get(
                        "mutation_effect", "beneficial"
                    )
                    if mutation_effect in (
                        "mildly_harmful",
                        "harmful",
                        "lethal",
                    ):
                        logger.warning(
                            f"[AI基因激活] 阻止激活有害突变: {trait_name}"
                        )
                        continue

                    potential_value = gene_data.get("potential_value", 8.0)
                    dominance = gene_data.get("dominance", "codominant")

                    # 应用显隐性效果
                    if DominanceType:
                        try:
                            dom_type = DominanceType(dominance)
                            expression_factor = (
                                DOMINANCE_EXPRESSION_FACTOR.get(dom_type, 0.6)
                            )
                        except ValueError:
                            expression_factor = (
                                DOMINANCE_EXPRESSION_FACTOR.get(
                                    dominance, 0.6
                                )
                            )
                    else:
                        expression_factor = DOMINANCE_EXPRESSION_FACTOR.get(
                            dominance, 0.6
                        )

                    expressed_value = potential_value * expression_factor

                    species.abstract_traits[trait_name] = min(
                        15.0, expressed_value
                    )
                    gene_data["activated"] = True
                    gene_data["activation_turn"] = turn_index
                    gene_data["expressed_value"] = expressed_value
                    activated_count += 1

                    dom_label = {
                        "dominant": "显性",
                        "recessive": "隐性",
                        "codominant": "共显性",
                        "overdominant": "超显性",
                    }.get(dominance, "")
                    logger.info(
                        f"[AI基因激活] {species.common_name} 激活特质: "
                        f"{trait_name} = {expressed_value:.1f} "
                        f"(潜力{potential_value:.1f}, {dom_label})"
                    )
                    break

        # 尝试在休眠器官中查找
        if "organs" in species.dormant_genes:
            for organ_name, gene_data in species.dormant_genes[
                "organs"
            ].items():
                # 检查是否正在发育或已成熟
                dev_stage = gene_data.get("development_stage")
                is_already_active = (
                    gene_data.get("activated", False) and dev_stage == 3
                )

                if (
                    gene_name in organ_name or organ_name in gene_name
                ) and not is_already_active:
                    organ_data = gene_data.get("organ_data", {})
                    organ_category = organ_data.get("category", "sensory")

                    # AI 激活直接跳到功能原型阶段（60%效率）
                    if dev_stage is None or dev_stage < 2:
                        gene_data["development_stage"] = 2
                        gene_data["stage_start_turn"] = turn_index
                        efficiency = 0.60
                    else:
                        efficiency = {
                            0: 0.0,
                            1: 0.25,
                            2: 0.60,
                            3: 1.0,
                        }.get(dev_stage, 0.6)

                    species.organs[organ_category] = {
                        "type": organ_data.get("type", organ_name),
                        "parameters": {
                            **organ_data.get("parameters", {}),
                            "efficiency_modifier": efficiency,
                        },
                        "acquired_turn": turn_index,
                        "is_active": True,
                        "maturity": efficiency,
                        "development_stage": gene_data.get(
                            "development_stage", 2
                        ),
                    }
                    gene_data["activated"] = True
                    gene_data["activation_turn"] = turn_index
                    activated_count += 1

                    stage_names = {
                        0: "原基",
                        1: "初级",
                        2: "功能原型",
                        3: "成熟",
                    }
                    logger.info(
                        f"[AI基因激活] {species.common_name} 激活器官: "
                        f"{organ_name} "
                        f"({stage_names.get(gene_data.get('development_stage'), '未知')}, "
                        f"效率{efficiency:.0%})"
                    )
                    break

    return activated_count


def summarize_dormant_genes(
    species: Species,
    pressure_types: list[str] | None = None,
    pressure_strength: float = 5.0,
) -> str:
    """智能筛选并总结休眠基因信息，供 AI 参考分化方向 v2.0"""
    if not species.dormant_genes:
        return "无休眠基因"

    pressure_types = pressure_types or ["competition"]
    dormant_traits = species.dormant_genes.get("traits", {})
    dormant_organs = species.dormant_genes.get("organs", {})

    # 过滤未激活的休眠基因
    available_traits = [
        (name, data)
        for name, data in dormant_traits.items()
        if not data.get("activated", False)
    ]
    available_organs = [
        (name, data)
        for name, data in dormant_organs.items()
        if not data.get("activated", False)
        or data.get("development_stage", 3) < 3
    ]

    if not available_traits and not available_organs:
        return "无可激活基因"

    # 分离有害突变和有益基因
    harmful_traits = []
    beneficial_traits = []
    for name, data in available_traits:
        mutation_effect = data.get("mutation_effect", "beneficial")
        if mutation_effect in ("mildly_harmful", "harmful", "lethal"):
            harmful_traits.append((name, data))
        else:
            beneficial_traits.append((name, data))

    # === 智能筛选特质 ===
    def score_trait(item: tuple) -> float:
        """计算特质的优先级分数"""
        name, data = item
        score = 0.0

        # 1. 潜力值权重 (0-15 -> 0-3分)
        potential = data.get("potential_value", 5.0)
        score += potential / 5.0

        # 2. 压力匹配加成 (+5分)
        gene_pressures = set(data.get("pressure_types", []))
        if gene_pressures & set(pressure_types):
            score += 5.0

        # 3. 暴露次数加成
        exposure = data.get("exposure_count", 0)
        score += min(exposure * 0.5, 2.0)

        # 4. 显隐性加成（显性更容易表达）
        dominance = data.get("dominance", "codominant")
        if dominance == "dominant":
            score += 1.0
        elif dominance == "overdominant":
            score += 1.5
        elif dominance == "recessive":
            score -= 0.5

        # 5. 高压力时优先选择与压力直接相关的
        if pressure_strength >= 7:
            pressure_keywords = {
                "cold": ["耐寒", "寒"],
                "heat": ["耐热", "热"],
                "drought": ["耐旱", "旱", "保水"],
                "temperature_fluctuation": ["耐寒", "耐热", "温度", "适应"],
                "competition": ["竞争", "适应", "运动", "效率"],
                "predation": ["防御", "速度", "感知", "逃避"],
                "hunting": ["捕猎", "追踪", "攻击"],
                "starvation": ["代谢", "储能", "消化", "效率"],
                "disease": ["免疫", "抗性"],
                "salinity": ["耐盐", "渗透"],
                "pressure_deep": ["耐压", "深海"],
                "light_limitation": ["光合", "弱光"],
            }
            for ptype in pressure_types:
                for keyword in pressure_keywords.get(ptype, []):
                    if keyword in name:
                        score += 3.0
                        break

        return score

    # 排序有益特质
    sorted_traits = sorted(beneficial_traits, key=score_trait, reverse=True)
    top_traits = sorted_traits[:3]

    # === 智能筛选器官 ===
    def score_organ(item: tuple) -> float:
        """计算器官的优先级分数"""
        name, data = item
        score = 0.0

        organ_data = data.get("organ_data", {})
        category = organ_data.get("category", "")

        # 压力匹配
        gene_pressures = set(data.get("pressure_types", []))
        if gene_pressures & set(pressure_types):
            score += 3.0

        # 高压力时优先防御/感知器官
        if pressure_strength >= 7:
            if category in ["defense", "sensory"]:
                score += 2.0

        # 已有发育进度的器官优先
        dev_stage = data.get("development_stage")
        if dev_stage is not None:
            score += (dev_stage + 1) * 0.5

        # 暴露次数
        exposure = data.get("exposure_count", 0)
        score += min(exposure * 0.3, 1.0)

        return score

    sorted_organs = sorted(available_organs, key=score_organ, reverse=True)
    top_organs = sorted_organs[:1]

    # === 生成简洁摘要 ===
    lines = []

    if top_traits:
        trait_items = []
        for name, data in top_traits:
            potential = data.get("potential_value", 8.0)
            dominance = data.get("dominance", "codominant")

            # 显隐性标记
            dom_mark = ""
            if dominance == "dominant":
                dom_mark = "[显]"
            elif dominance == "recessive":
                dom_mark = "[隐]"
            elif dominance == "overdominant":
                dom_mark = "[超显]"

            # 压力匹配标记
            gene_pressures = set(data.get("pressure_types", []))
            is_matched = "⭐" if gene_pressures & set(pressure_types) else ""

            trait_items.append(
                f"{is_matched}{name}{dom_mark}({potential:.0f})"
            )
        lines.append(f"推荐特质: {', '.join(trait_items)}")

    if top_organs:
        name, data = top_organs[0]
        organ_data = data.get("organ_data", {})
        category = organ_data.get("category", "")

        # 发育阶段标记
        dev_stage = data.get("development_stage")
        stage_mark = ""
        if dev_stage is not None:
            stage_names = {0: "原基", 1: "初级", 2: "功能", 3: "成熟"}
            stage_mark = f"[{stage_names.get(dev_stage, '未知')}]"

        lines.append(f"推荐器官: {name}({category}){stage_mark}")

    # 有害突变警告（仅在有害突变数量较多时提示）
    if len(harmful_traits) >= 2:
        harm_names = [n for n, _ in harmful_traits[:2]]
        lines.append(f"⚠️ 遗传负荷: {', '.join(harm_names)} (避免激活)")

    if not lines:
        return "无推荐基因"

    # 极简提示
    lines.append(
        "(⭐=匹配当前压力优先激活; [显]=显性易表达; "
        "[隐]=隐性需高压激活)"
    )

    return "\n".join(lines)


def process_ai_new_dormant_genes(
    species: Species,
    new_genes_data: dict,
    turn_index: int,
) -> int:
    """处理 AI 返回的新休眠基因并添加到物种基因库。"""
    if not new_genes_data:
        return 0

    # 确保 dormant_genes 结构存在
    if not species.dormant_genes:
        species.dormant_genes = {"traits": {}, "organs": {}}
    species.dormant_genes.setdefault("traits", {})
    species.dormant_genes.setdefault("organs", {})

    added_count = 0

    # 处理特质基因
    traits_list = new_genes_data.get("traits", [])
    if isinstance(traits_list, list):
        for trait_data in traits_list:
            if not isinstance(trait_data, dict):
                continue

            trait_name = trait_data.get("name")
            if not trait_name:
                continue

            # 跳过已存在的基因
            if trait_name in species.dormant_genes["traits"]:
                continue
            if trait_name in (species.abstract_traits or {}):
                continue

            # 解析基因数据
            potential_value = trait_data.get("potential_value", 6.0)
            try:
                potential_value = float(potential_value)
                potential_value = max(0.0, min(15.0, potential_value))
            except (ValueError, TypeError):
                potential_value = 6.0

            pressure_types = trait_data.get(
                "pressure_types", ["competition"]
            )
            if not isinstance(pressure_types, list):
                pressure_types = ["competition"]

            dominance = trait_data.get("dominance", "codominant")
            valid_dominance = [
                "dominant",
                "codominant",
                "recessive",
                "overdominant",
            ]
            if dominance not in valid_dominance:
                dominance = "codominant"

            mutation_effect = trait_data.get(
                "mutation_effect", "beneficial"
            )
            valid_effects = [
                "beneficial",
                "neutral",
                "mildly_harmful",
                "harmful",
                "lethal",
            ]
            if mutation_effect not in valid_effects:
                mutation_effect = "beneficial"

            description = trait_data.get("description", "")

            # 构建休眠基因数据
            dormant_gene = {
                "potential_value": potential_value,
                "activation_threshold": 0.20,
                "pressure_types": pressure_types,
                "exposure_count": 0,
                "activated": False,
                "inherited_from": "llm_speciation",
                "dominance": dominance,
                "mutation_effect": mutation_effect,
                "description": description,
                "created_turn": turn_index,
            }

            # 有害突变的额外处理
            if mutation_effect in (
                "mildly_harmful",
                "harmful",
                "lethal",
            ):
                # 确保有害突变是隐性的
                dormant_gene["dominance"] = "recessive"
                # 提取目标特质（如果描述中提到）
                target_trait = trait_data.get("target_trait")
                if target_trait:
                    dormant_gene["target_trait"] = target_trait
                value_modifier = trait_data.get("value_modifier", -1.0)
                try:
                    dormant_gene["value_modifier"] = float(value_modifier)
                except (ValueError, TypeError):
                    dormant_gene["value_modifier"] = -1.0

            species.dormant_genes["traits"][trait_name] = dormant_gene
            added_count += 1

            effect_label = {
                "beneficial": "有益",
                "neutral": "中性",
                "mildly_harmful": "轻微有害",
                "harmful": "有害",
            }.get(mutation_effect, "")
            dom_label = {
                "dominant": "显",
                "codominant": "共显",
                "recessive": "隐",
                "overdominant": "超显",
            }.get(dominance, "")
            logger.debug(
                f"[LLM新基因] {species.common_name} 获得特质基因: "
                f"{trait_name} "
                f"(潜力{potential_value:.1f}, {dom_label}, {effect_label})"
            )

    # 处理器官原基
    organs_list = new_genes_data.get("organs", [])
    if isinstance(organs_list, list):
        for organ_data in organs_list:
            if not isinstance(organ_data, dict):
                continue

            organ_name = organ_data.get("name")
            if not organ_name:
                continue

            # 跳过已存在的器官
            if organ_name in species.dormant_genes["organs"]:
                continue

            # 解析器官数据
            organ_info = organ_data.get("organ_data", {})
            if not isinstance(organ_info, dict):
                organ_info = {}

            category = organ_info.get("category", "sensory")
            organ_type = organ_info.get("type", organ_name)
            parameters = organ_info.get("parameters", {})
            if not isinstance(parameters, dict):
                parameters = {}

            pressure_types = organ_data.get(
                "pressure_types", ["competition", "predation"]
            )
            if not isinstance(pressure_types, list):
                pressure_types = ["competition", "predation"]

            dominance = organ_data.get("dominance", "codominant")
            valid_dominance = [
                "dominant",
                "codominant",
                "recessive",
                "overdominant",
            ]
            if dominance not in valid_dominance:
                dominance = "codominant"

            description = organ_data.get("description", "")

            # 构建休眠器官数据
            dormant_organ = {
                "organ_data": {
                    "category": category,
                    "type": organ_type,
                    "parameters": parameters,
                },
                "activation_threshold": 0.25,
                "pressure_types": pressure_types,
                "exposure_count": 0,
                "activated": False,
                "inherited_from": "llm_speciation",
                "dominance": dominance,
                "development_stage": None,
                "stage_start_turn": None,
                "description": description,
                "created_turn": turn_index,
            }

            species.dormant_genes["organs"][organ_name] = dormant_organ
            added_count += 1

            dom_label = {
                "dominant": "显",
                "codominant": "共显",
                "recessive": "隐",
                "overdominant": "超显",
            }.get(dominance, "")
            logger.debug(
                f"[LLM新基因] {species.common_name} 获得器官原基: "
                f"{organ_name} ({category}, {dom_label})"
            )

    if added_count > 0:
        logger.info(
            f"[LLM新基因] {species.common_name} 成功添加 "
            f"{added_count} 个LLM生成的休眠基因 "
            f"(特质: {len(traits_list) if isinstance(traits_list, list) else 0}, "
            f"器官: {len(organs_list) if isinstance(organs_list, list) else 0})"
        )

    return added_count
