"""Offline catalog and explicitly configurable breeding projections."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CATALOG = json.loads((ROOT / "data" / "pokedex.json").read_text(encoding="utf-8"))
PETS = {p["id"]: p for p in CATALOG["pets"]}
TRAITS = ("异色", "炫彩", "大块头", "小不点", "婉转声", "粗嗓门")
ATTRS = ("生命", "物攻", "物防", "魔攻", "魔防", "速度")
NATURES = {
    "大胆": ("物攻", "物防"), "固执": ("物攻", "魔攻"), "调皮": ("物攻", "魔防"), "勇敢": ("物攻", "速度"), "逞强": ("物攻", "生命"),
    "稳重": ("物防", "物攻"), "天真": ("物防", "魔攻"), "懒散": ("物防", "魔防"), "悠闲": ("物防", "速度"), "坦率": ("物防", "生命"),
    "聪明": ("魔攻", "物攻"), "专注": ("魔攻", "物防"), "偏执": ("魔攻", "魔防"), "冷静": ("魔攻", "速度"), "理性": ("魔攻", "生命"),
    "警惕": ("魔防", "物攻"), "温顺": ("魔防", "物防"), "害羞": ("魔防", "魔攻"), "慎重": ("魔防", "速度"), "焦虑": ("魔防", "生命"),
    "胆小": ("速度", "物攻"), "急躁": ("速度", "物防"), "开朗": ("速度", "魔攻"), "莽撞": ("速度", "魔防"), "热情": ("速度", "生命"),
    "沉默": ("生命", "物攻"), "忧郁": ("生命", "物防"), "平和": ("生命", "魔攻"), "粗心": ("生命", "魔防"), "踏实": ("生命", "速度"),
}
NATURE_BY_PAIR = {pair: name for name, pair in NATURES.items()}
VOICE = ("婉转声", "粗嗓门", "普通")
DEFAULT_RULES = {
    "shiny_parent": 0.72, "shiny_hidden": 1.0,
    "color_parent": 0.36, "color_hidden": 1.0,
    "nature_male": 30.0, "nature_female": 30.0,
    "size_edge": 2.0, "size_swing": 2.0,
    "voice_same": 90.0, "voice_one": 2.0,
    "voice_opposite": 0.0, "voice_neither": 0.5,
}
RULE_INFO = (
    ("shiny_parent", "异色亲本→显性蛋", "配置与玩家资料：每位 0.72%"),
    ("shiny_hidden", "普通蛋→隐性异色", "配置 im_shining：约 1%；触发顺序未核实"),
    ("color_parent", "炫彩亲本→显性蛋", "配置与玩家资料：每位 0.36%"),
    ("color_hidden", "普通蛋→隐性炫彩", "暂设 1%；未查明具体出处"),
    ("nature_male", "完整性格随父", "配置与玩家资料：30%"),
    ("nature_female", "完整性格随母", "配置与玩家资料：30%"),
    ("size_edge", "体型奖牌边缘", "玩家蛋重表支持两端各 2%；成年精灵仍是估算"),
    ("size_swing", "子代体型浮动", "暂设图鉴区间 ±2%；未查明具体出处"),
    ("voice_same", "同侧声音牌×同侧", "暂设 90%；奖牌模型假设"),
    ("voice_one", "同侧声音牌×无牌", "暂设 2%；奖牌模型假设"),
    ("voice_opposite", "相反声音牌→每侧", "暂设 0%；其余为无牌"),
    ("voice_neither", "无牌×无牌→每侧", "暂设 0.5%；其余为无牌"),
)


def groups(pet_id: str) -> set[str]:
    return set(PETS.get(pet_id, {}).get("egg_groups") or [])


def compatible(mother: dict, father: dict) -> bool:
    return bool(groups(mother["pet_id"]) & groups(father["pet_id"]))


def sex_rate(pet_id: str, sex: str) -> float | None:
    ratio = PETS.get(pet_id, {}).get("gender_ratio") or {}
    total = (ratio.get("female") or 0) + (ratio.get("male") or 0)
    return (ratio.get("female" if sex == "母" else "male", 0) / total) if total else None


def record_traits(record: dict, edge_percent: float = 2.0) -> dict[str, float | None]:
    size = inferred_size(record, edge_percent)
    size_known = size in ("大块头", "小不点", "普通体型")
    legacy_medals = set(x.strip() for x in (record.get("medals") or "").split(",") if x.strip())
    voice = record.get("voice_label") or next((v for v in VOICE[:2] if v in legacy_medals), "")
    values = {
        "异色": bool(record.get("shiny")), "炫彩": bool(record.get("colorful")),
        "大块头": (size == "大块头") if size_known else None,
        "小不点": (size == "小不点") if size_known else None,
        "婉转声": (voice == "婉转声") if voice else None,
        "粗嗓门": (voice == "粗嗓门") if voice else None,
    }
    return {trait: float(value) if value is not None else None for trait, value in values.items()}


def weight_medals(record: dict, edge_percent: float = 2.0) -> frozenset[str]:
    size = inferred_size(record, edge_percent)
    return frozenset((size,)) if size in ("大块头", "小不点") else frozenset()


def _range(text: str | None) -> tuple[float, float] | None:
    numbers = re.findall(r"\d+(?:\.\d+)?", text or "")
    return (float(numbers[0]), float(numbers[1])) if len(numbers) >= 2 else None


def _value(text: str | None) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", text or "")
    return float(match.group()) if match else None


def size_position(record: dict) -> float | None:
    pet = PETS.get(record.get("pet_id"), {})
    value = _value(record.get("size_raw"))
    bounds = _range(pet.get("adult_weight_range") or pet.get("weight"))
    if value is None or bounds is None or bounds[1] <= bounds[0]:
        return None
    return max(0.0, min(1.0, (value - bounds[0]) / (bounds[1] - bounds[0])))


def inferred_size(record: dict, edge_percent: float = 2.0) -> str:
    """Classify weight medals using the configured edge of the adult weight range."""
    pet = PETS.get(record.get("pet_id"), {})
    weight = _value(record.get("size_raw"))
    weight_range = _range(pet.get("adult_weight_range") or pet.get("weight"))
    if weight is None:
        return "未录体重"
    if not weight_range:
        return "图鉴范围缺失"
    def position(value, bounds):
        return (value - bounds[0]) / (bounds[1] - bounds[0]) if bounds[1] > bounds[0] else None
    wp = position(weight, weight_range)
    if wp is None:
        return "图鉴范围无效"
    edge = edge_percent / 100
    if wp >= 1 - edge:
        return "大块头"
    if wp <= edge:
        return "小不点"
    return "普通体型"


@dataclass
class Candidate:
    pet_id: str
    sex: str
    label: str
    traits: dict[str, float | None]
    route: tuple[str, ...]
    probability: float | None = 1.0  # Chance the intermediate has the required sex.
    natures: dict[tuple[str, str] | None, float] | None = None
    voice: dict[str, float] | None = None
    size: tuple[float, float] | None = None
    visible: dict[str, float | None] | None = None
    hidden: dict[str, float | None] | None = None
    record_id: int | None = None
    mother_record_id: int | None = None
    father_record_id: int | None = None
    virtual_keys: frozenset[str] = frozenset()
    weight_medals: frozenset[str] = frozenset()
    retained_size_medals: frozenset[str] = frozenset()
    conditional_medal_parents: tuple[str, ...] = ()
    mother: Candidate | None = None
    father: Candidate | None = None


def display_identity(pet_id: str) -> str:
    """Use the family catalog number to identify one pet across its forms."""
    base_id = PETS[pet_id]["family_base_id"]
    return PETS[base_id]["number"]


def final_route_key(candidate: Candidate) -> tuple:
    """Group routes by the parents shown in the list and the final offspring."""
    def parent_key(parent: Candidate) -> tuple:
        return (display_identity(parent.pet_id), parent.sex, parent.record_id is not None)

    def first_pairs(current: Candidate) -> tuple:
        if current.mother is None or current.father is None:
            return ()
        if current.mother.mother is None and current.father.mother is None:
            return ((parent_key(current.mother), parent_key(current.father)),)
        return first_pairs(current.mother) + first_pairs(current.father)

    return first_pairs(candidate), display_identity(candidate.pet_id)


def first_generation_uses_record(candidate: Candidate, record_id: int) -> bool:
    """Selected records belong to an initial pairing, not only a later pairing."""
    if candidate.mother is None or candidate.father is None:
        return False
    if not candidate.mother.route and not candidate.father.route:
        return record_id in (candidate.mother.record_id, candidate.father.record_id)
    return (first_generation_uses_record(candidate.mother, record_id)
            or first_generation_uses_record(candidate.father, record_id))


def _combine(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else a * b


def record_natures(record: dict) -> dict[tuple[str, str] | None, float]:
    pair = (record.get("nature_plus"), record.get("nature_minus"))
    if pair in NATURE_BY_PAIR:
        return {pair: 1.0}
    name = (record.get("nature_name") or "").strip()
    return {NATURES[name]: 1.0} if name in NATURES else {None: 1.0}


def breeding_record_key(record: dict) -> tuple:
    """Attributes that affect breeding; nicknames and notes do not distinguish parents."""
    weight = _value(record.get("size_raw"))
    voice = record.get("voice_label") or next(
        (value for value in VOICE[:2] if value in (record.get("medals") or "")), "")
    nature = next(iter(record_natures(record)))
    return (record.get("pet_id"), record.get("sex"), weight, voice,
            bool(record.get("shiny")), bool(record.get("colorful")), nature)


def group_breeding_records(records: list[dict]) -> list[list[dict]]:
    grouped: dict[tuple, list[dict]] = {}
    for record in records:
        grouped.setdefault(breeding_record_key(record), []).append(record)
    return list(grouped.values())


def nature_chance(candidate: Candidate, name: str = "", plus: str = "", minus: str = "") -> float | None:
    if not name and not plus and not minus:
        return 1.0
    if not candidate.natures or candidate.natures.get(None, 0) > 1e-12:
        return None
    return sum(chance for pair, chance in candidate.natures.items() if pair is not None
               and (not name or NATURE_BY_PAIR[pair] == name)
               and (not plus or pair[0] == plus) and (not minus or pair[1] == minus))


def _nature_child(mother: Candidate, father: Candidate, rules: dict[str, float]) -> dict:
    result: dict[tuple[str, str] | None, float] = {}
    for source, rate in ((father.natures, rules["nature_male"]), (mother.natures, rules["nature_female"])):
        for pair, chance in source.items():
            result[pair] = result.get(pair, 0.0) + rate * chance
    random_rate = 1 - rules["nature_male"] - rules["nature_female"]
    for pair in NATURE_BY_PAIR:
        result[pair] = result.get(pair, 0.0) + random_rate / len(NATURE_BY_PAIR)
    return result


def _appearance(m: float | None, f: float | None, rate: float) -> float | None:
    if m is None or f is None:
        return None
    return 1 - (1 - m * rate) * (1 - f * rate)


def _voice_child(mother: dict[str, float] | None, father: dict[str, float] | None,
                 rules: dict[str, float]) -> dict[str, float] | None:
    if mother is None or father is None:
        return None
    result = {v: 0.0 for v in VOICE}
    for left, p_left in mother.items():
        for right, p_right in father.items():
            if left == right == "普通":
                outcomes = {"婉转声": rules["voice_neither"], "粗嗓门": rules["voice_neither"]}
            elif left == right:
                outcomes = {left: rules["voice_same"]}
            elif "普通" in (left, right):
                outcomes = {right if left == "普通" else left: rules["voice_one"]}
            else:
                outcomes = {"婉转声": rules["voice_opposite"], "粗嗓门": rules["voice_opposite"]}
            for label, chance in outcomes.items():
                result[label] += p_left * p_right * chance
            result["普通"] += p_left * p_right * (1 - sum(outcomes.values()))
    return result


def _size_child(a: tuple[float, float] | None, b: tuple[float, float] | None,
                swing: float) -> tuple[float, float] | None:
    if a is None or b is None:
        return None
    return (a[0] + b[0]) / 2, (a[1] + b[1]) / 4 + swing * swing / 3


def _size_tail(state: tuple[float, float] | None, edge: float, high: bool,
               uniform_halfwidth: float | None = None) -> float | None:
    if state is None:
        return None
    mean, variance = state
    threshold = 1 - edge if high else edge
    if uniform_halfwidth is not None and uniform_halfwidth > 0:
        lower, upper = mean - uniform_halfwidth, mean + uniform_halfwidth
        chance = (upper - threshold) / (upper - lower) if high else (threshold - lower) / (upper - lower)
        return max(0.0, min(1.0, chance))
    if variance < 1e-12:
        return float(mean >= threshold if high else mean <= threshold)
    # First-generation parents are exact values: uniform ±swing is exact.
    # For later generations use a normal approximation of propagated moments.
    sigma = math.sqrt(variance)
    cdf = (1 + math.erf((threshold - mean) / (sigma * math.sqrt(2)))) / 2
    chance = max(0.0, min(1.0, 1 - cdf if high else cdf))
    return 0.0 if chance < 1e-12 else 1.0 if chance > 1 - 1e-12 else chance


def breed(mother: Candidate, father: Candidate, rules: dict[str, float], sex: str) -> Candidate | None:
    if not compatible({"pet_id": mother.pet_id}, {"pet_id": father.pet_id}):
        return None
    child_pet = PETS[mother.pet_id]["family_base_id"]
    ratio = sex_rate(child_pet, sex)
    if ratio == 0:
        return None
    traits: dict[str, float | None] = {}
    visible, hidden = {}, {}
    for trait, key in (("异色", "shiny"), ("炫彩", "color")):
        visible[trait] = _appearance(mother.traits[trait], father.traits[trait], rules[key + "_parent"])
    if PETS[child_pet].get("has_shiny") is False:
        visible["异色"] = 0.0
    ordinary = ((1 - visible["异色"]) * (1 - visible["炫彩"])
                if all(value is not None for value in visible.values()) else None)
    for trait, key in (("异色", "shiny"), ("炫彩", "color")):
        hidden[trait] = ordinary * rules[key + "_hidden"] if ordinary is not None else None
        traits[trait] = visible[trait] + hidden[trait] if hidden[trait] is not None else None
    if PETS[child_pet].get("has_shiny") is False:
        hidden["异色"] = 0.0
        traits["异色"] = 0.0
    voice = _voice_child(mother.voice, father.voice, rules)
    traits["婉转声"] = voice["婉转声"] if voice else None
    traits["粗嗓门"] = voice["粗嗓门"] if voice else None
    size = _size_child(mother.size, father.size, rules["size_swing"])
    for trait, high in (("大块头", True), ("小不点", False)):
        first_generation = (mother.size is not None and father.size is not None
                            and mother.size[1] == 0 and father.size[1] == 0)
        traits[trait] = _size_tail(size, rules["size_edge"], high,
                                  rules["size_swing"] if first_generation else None)
    label = f"{PETS[child_pet]['name']}({sex})"
    step = f"{mother.label} × {father.label} → {label}"
    route = mother.route + father.route + (step,)
    retained = set()
    conditional = []
    for trait in ("大块头", "小不点"):
        for parent in (mother, father):
            if trait in parent.weight_medals:
                retained.add(trait)
            elif parent.route and ((parent.traits[trait] or 0) > 0
                                   or trait in parent.retained_size_medals):
                retained.add(trait)
                conditional.append(f"{parent.label} 须先孵出{trait}奖牌")
    return Candidate(child_pet, sex, label, traits, route,
                     _combine(_combine(mother.probability, father.probability), ratio),
                     _nature_child(mother, father, rules), voice, size, visible, hidden,
                     None, mother.record_id, father.record_id,
                     mother.virtual_keys | father.virtual_keys,
                     retained_size_medals=frozenset(retained),
                     conditional_medal_parents=tuple(dict.fromkeys(conditional)),
                     mother=mother, father=father)


def target_chance(candidate: Candidate, targets: list[str], nature: tuple[str, str, str] = ("", "", "")) -> float | None:
    """Independence approximation; never presented as a verified game mechanic."""
    result: float | None = nature_chance(candidate, *nature)
    for trait in targets:
        if candidate.traits[trait] == 0:
            return 0.0
        result = _combine(result, candidate.traits[trait])
    return result


def retained_zero_route(candidate: Candidate, targets: list[str],
                        nature: tuple[str, str, str] = ("", "", "")) -> bool:
    """Keep a zero estimate when a parent has or may hatch with the size medal."""
    if target_chance(candidate, targets, nature) != 0 or nature_chance(candidate, *nature) == 0:
        return False
    size_targets = set(targets) & {"大块头", "小不点"}
    if not size_targets or not size_targets <= candidate.retained_size_medals:
        return False
    return all(candidate.traits[trait] != 0 for trait in targets if trait not in size_targets)


def _virtual_parent(pet: dict, sex: str) -> Candidate:
    traits = {trait: 0.0 for trait in TRAITS}
    return Candidate(pet["id"], sex, f"[未录入] {pet['name']}({sex})", traits, (),
                     1.0, {None: 1.0}, {"普通": 1.0}, (0.5, 0.0),
                     virtual_keys=frozenset((f"{pet['id']}:{sex}",)))


def _opportunity(candidate: Candidate, targets: list[str], nature: tuple[str, str, str]) -> tuple:
    # Retain near-edge intermediate offspring even when the current medal chance is zero.
    score = 1.0
    for trait in targets:
        if trait == "大块头":
            score *= candidate.size[0] if candidate.size else 0.0
        elif trait == "小不点":
            score *= 1 - candidate.size[0] if candidate.size else 0.0
        else:
            score *= candidate.traits[trait] if candidate.traits[trait] is not None else 0.5
    chance = nature_chance(candidate, *nature)
    score *= chance if chance is not None else 0.5
    return score, -len(candidate.virtual_keys), candidate.probability or 0


def _trim_frontier(frontier: list[Candidate], limit: int, targets: list[str],
                   nature: tuple[str, str, str]) -> list[Candidate]:
    frontier.sort(key=lambda c: _opportunity(c, targets, nature), reverse=True)
    if len(frontier) <= limit:
        return frontier
    # Keep species/sex variety before filling the remaining beam slots.
    chosen, seen = [], set()
    for candidate in frontier:
        key = (candidate.pet_id, candidate.sex)
        if key not in seen:
            chosen.append(candidate)
            seen.add(key)
            if len(chosen) == limit:
                return chosen
    chosen_ids = {id(c) for c in chosen}
    chosen.extend(c for c in frontier if id(c) not in chosen_ids)
    return chosen[:limit]


def search(records: list[dict], target_pet: str | None, targets: list[str], generations: int,
           rules: dict[str, float], nature: tuple[str, str, str] = ("", "", ""), limit: int = 200,
           mother_id: int | None = None, father_id: int | None = None,
           allow_unrecorded: bool = False) -> list[Candidate]:
    if target_pet:
        target_pet = display_identity(target_pet)
    owned = []
    for matching in group_breeding_records(records):
        r = next((record for record in matching if record["id"] in (mother_id, father_id)), matching[0])
        if r["pet_id"] not in PETS or r["sex"] not in ("公", "母"):
            continue
        wp = size_position(r)
        voice_label = r.get("voice_label") or next((v for v in VOICE[:2] if v in (r.get("medals") or "")), "")
        owned.append(Candidate(r["pet_id"], r["sex"], f"{r['name']} [#{r['id']}]",
                               record_traits(r, rules["size_edge"] * 100), (), 1.0,
                               record_natures(r), {voice_label: 1.0} if voice_label in VOICE else None,
                               (wp, 0.0) if wp is not None else None,
                               record_id=r["id"],
                               weight_medals=weight_medals(r, rules["size_edge"] * 100)))
    owned_kinds = {(display_identity(candidate.pet_id), candidate.sex) for candidate in owned}
    virtual = ([_virtual_parent(p, sex) for p in CATALOG["pets"] if groups(p["id"])
                for sex in ("母", "公") if sex_rate(p["id"], sex) != 0
                and (display_identity(p["id"]), sex) not in owned_kinds]
               if allow_unrecorded else [])
    mothers = [c for c in owned + virtual if c.sex == "母"]
    fathers = [c for c in owned + virtual if c.sex == "公"]
    selected_mother = next((c for c in owned if c.record_id == mother_id), None)
    selected_father = next((c for c in owned if c.record_id == father_id), None)
    if mother_id is not None and selected_mother is None:
        return []
    if father_id is not None and selected_father is None:
        return []
    relevant_groups = set()
    if target_pet:
        relevant_groups.update(g for p in CATALOG["pets"] if display_identity(p["id"]) == target_pet
                               for g in groups(p["id"]))
    if selected_mother:
        relevant_groups.update(groups(selected_mother.pet_id))
    if selected_father:
        relevant_groups.update(groups(selected_father.pet_id))
    initial_mothers = ([m for m in mothers if m.record_id == mother_id or
                        bool((groups(m.pet_id) | groups(PETS[m.pet_id]["family_base_id"]))
                             & relevant_groups)] if relevant_groups else mothers)
    fathers_by_group: dict[str, list[Candidate]] = {}
    for father in fathers:
        for group in groups(father.pet_id):
            fathers_by_group.setdefault(group, []).append(father)
    frontier = []
    for m in initial_mothers:
        possible_fathers = {id(f): f for group in groups(m.pet_id)
                            for f in fathers_by_group.get(group, ())}.values()
        for f in possible_fathers:
            child = breed(m, f, rules, "母")
            if child:
                frontier.append(child)
            child = breed(m, f, rules, "公")
            if child:
                frontier.append(child)
    def expand_with_base(candidates: list[Candidate]) -> list[Candidate]:
        children = []
        for candidate in candidates:
            partners = fathers if candidate.sex == "母" else mothers
            for partner in partners:
                m, f = (candidate, partner) if candidate.sex == "母" else (partner, candidate)
                for sex in ("母", "公"):
                    child = breed(m, f, rules, sex)
                    if child:
                        children.append(child)
        return children

    def expand_two_offspring(candidates: list[Candidate]) -> list[Candidate]:
        children = []
        projected_mothers = [c for c in candidates if c.sex == "母"]
        projected_fathers = [c for c in candidates if c.sex == "公"]
        for mother in projected_mothers:
            for father in projected_fathers:
                for sex in ("母", "公"):
                    child = breed(mother, father, rules, sex)
                    if child:
                        children.append(child)
        return children

    results: list[Candidate] = []
    first_generation: list[Candidate] = []
    for generation in range(1, min(3, max(1, generations)) + 1):
        results.extend(c for c in frontier if (target_pet is None or display_identity(c.pet_id) == target_pet)
                       and (mother_id is None or first_generation_uses_record(c, mother_id))
                       and (father_id is None or first_generation_uses_record(c, father_id))
                       and (target_chance(c, targets, nature) != 0
                            or retained_zero_route(c, targets, nature)))
        if generation == generations:
            break
        trimmed = _trim_frontier(frontier, limit, targets, nature)
        if generation == 1:
            first_generation = trimmed
            frontier = expand_with_base(trimmed)
        else:
            frontier = expand_with_base(trimmed)
            if mother_id is None and father_id is None:
                frontier += expand_two_offspring(first_generation)
    def result_rank(candidate: Candidate):
        chance = target_chance(candidate, targets, nature)
        category = 0 if chance is not None and chance > 0 else 1 if chance is None else 2
        return (category, len(candidate.route), len(candidate.virtual_keys),
                -(chance or 0), -(candidate.probability or 0))
    results.sort(key=result_rank)
    seen = set()
    unique = []
    for result in results:
        key = result.route
        if key not in seen:
            seen.add(key)
            unique.append(result)
    grouped: dict[tuple, list[Candidate]] = {}
    for candidate in unique:
        grouped.setdefault(final_route_key(candidate), []).append(candidate)
    zero_keys = [key for key, variants in grouped.items()
                 if all(target_chance(c, targets, nature) == 0 for c in variants)]
    zero_key_set = set(zero_keys)
    other_keys = [key for key in grouped if key not in zero_key_set]
    reserved = min(len(zero_keys), limit, max(20, limit - len(other_keys)))
    def diverse_keys(keys: list[tuple], slots: int) -> list[tuple]:
        if slots <= 0:
            return []
        chosen, seen_buckets = [], set()
        for key in keys:
            candidate = grouped[key][0]
            intermediates = tuple(sorted(display_identity(parent.pet_id)
                                         for parent in (candidate.mother, candidate.father)
                                         if parent.route))
            bucket = (intermediates, tuple(sorted(groups(candidate.pet_id))))
            if bucket not in seen_buckets:
                chosen.append(key)
                seen_buckets.add(bucket)
                if len(chosen) == slots:
                    return chosen
        chosen_set = set(chosen)
        chosen.extend(key for key in keys if key not in chosen_set)
        return chosen[:slots]

    selected_keys = diverse_keys(other_keys, limit - reserved) + diverse_keys(zero_keys, reserved)
    return [candidate for key in selected_keys for candidate in grouped[key]]
