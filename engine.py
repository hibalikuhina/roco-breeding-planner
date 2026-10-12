"""Offline catalog and explicitly configurable breeding projections."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CATALOG = json.loads((ROOT / "data" / "pokedex.json").read_text(encoding="utf-8"))
PETS = {p["id"]: p for p in CATALOG["pets"]}
TRAITS = ("异色", "炫彩", "大块头", "小不点", "婉转声", "粗嗓门")


def groups(pet_id: str) -> set[str]:
    return set(PETS.get(pet_id, {}).get("egg_groups") or [])


def compatible(mother: dict, father: dict) -> bool:
    return bool(groups(mother["pet_id"]) & groups(father["pet_id"]))


def sex_rate(pet_id: str, sex: str) -> float | None:
    ratio = PETS.get(pet_id, {}).get("gender_ratio") or {}
    total = (ratio.get("female") or 0) + (ratio.get("male") or 0)
    return (ratio.get("female" if sex == "母" else "male", 0) / total) if total else None


def record_traits(record: dict) -> dict[str, float]:
    size = inferred_size(record)
    legacy_medals = set(x.strip() for x in (record.get("medals") or "").split(",") if x.strip())
    values = {
        "异色": bool(record.get("shiny")), "炫彩": bool(record.get("colorful")),
        "大块头": size == "大块头倾向" or (size in ("未录体重", "需录身高", "图鉴范围缺失") and (record.get("size_label") == "大块头" or "大块头" in legacy_medals)),
        "小不点": size == "小不点倾向" or (size in ("未录体重", "需录身高", "图鉴范围缺失") and (record.get("size_label") == "小不点" or "小不点" in legacy_medals)),
        "婉转声": record.get("voice_label") == "婉转声" or "婉转声" in legacy_medals,
        "粗嗓门": record.get("voice_label") == "粗嗓门" or "粗嗓门" in legacy_medals,
    }
    return {trait: float(value) for trait, value in values.items()}


def _range(text: str | None) -> tuple[float, float] | None:
    numbers = re.findall(r"\d+(?:\.\d+)?", text or "")
    return (float(numbers[0]), float(numbers[1])) if len(numbers) >= 2 else None


def _value(text: str | None) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", text or "")
    return float(match.group()) if match else None


def inferred_size(record: dict) -> str:
    """A guide based on adult body ranges, not a verified medal determination."""
    pet = PETS.get(record.get("pet_id"), {})
    weight, height = _value(record.get("size_raw")), _value(record.get("height_raw"))
    weight_range, height_range = _range(pet.get("weight")), _range(pet.get("height"))
    if weight is None:
        return "未录体重"
    if not weight_range or not height_range:
        return "图鉴范围缺失"
    if height is None:
        return "需录身高"
    def position(value, bounds):
        return (value - bounds[0]) / (bounds[1] - bounds[0]) if bounds[1] > bounds[0] else None
    wp, hp = position(weight, weight_range), position(height, height_range)
    if wp is None or hp is None:
        return "图鉴范围无效"
    if wp >= .98 and hp >= .98:
        return "大块头倾向"
    if wp <= .02 and hp <= .02:
        return "小不点倾向"
    return "普通体型倾向"


@dataclass
class Candidate:
    pet_id: str
    sex: str
    label: str
    traits: dict[str, float | None]
    route: tuple[str, ...]
    probability: float | None = 1.0  # Chance the intermediate has the required sex.


def _combine(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else a * b


def child_trait(m: float | None, f: float | None, rate: float | None, base: float = 0) -> float | None:
    if m == 0 and f == 0:
        return base
    if rate is None or m is None or f is None:
        return None
    return 1 - (1 - base) * (1 - m * rate) * (1 - f * rate)


def breed(mother: Candidate, father: Candidate, rules: dict[str, float | None], sex: str) -> Candidate | None:
    if not compatible({"pet_id": mother.pet_id}, {"pet_id": father.pet_id}):
        return None
    child_pet = PETS[mother.pet_id]["family_base_id"]
    ratio = sex_rate(child_pet, sex)
    if ratio == 0:
        return None
    traits = {t: child_trait(mother.traits[t], father.traits[t], rules.get(t)) for t in TRAITS}
    label = f"{PETS[child_pet]['name']}({sex})"
    step = f"{mother.label} × {father.label} → {label}"
    route = mother.route + tuple(x for x in father.route if x not in mother.route) + (step,)
    return Candidate(child_pet, sex, label, traits, route, _combine(_combine(mother.probability, father.probability), ratio))


def target_chance(candidate: Candidate, targets: list[str]) -> float | None:
    """Independence approximation; never presented as a verified game mechanic."""
    result: float | None = 1.0
    for trait in targets:
        result = _combine(result, candidate.traits[trait])
    return result


def search(records: list[dict], target_pet: str, targets: list[str], generations: int,
           rules: dict[str, float | None], limit: int = 200) -> list[Candidate]:
    target_pet = PETS[target_pet]["family_base_id"]
    owned = [Candidate(r["pet_id"], r["sex"], r["name"], record_traits(r), ())
             for r in records if r["pet_id"] in PETS and r["sex"] in ("公", "母")]
    mothers = [c for c in owned if c.sex == "母"]
    fathers = [c for c in owned if c.sex == "公"]
    frontier = []
    for m in mothers:
        for f in fathers:
            child = breed(m, f, rules, "母")
            if child:
                frontier.append(child)
            child = breed(m, f, rules, "公")
            if child:
                frontier.append(child)
    results: list[Candidate] = []
    for generation in range(1, min(3, max(1, generations)) + 1):
        results.extend(c for c in frontier if c.pet_id == target_pet and target_chance(c, targets) != 0)
        if generation == generations:
            break
        next_frontier = []
        # A projected offspring can be paired with a currently owned parent.
        # This keeps the plan actionable and avoids an unbounded fantasy lineage.
        for c in frontier:
            partners = fathers if c.sex == "母" else mothers
            for partner in partners:
                m, f = (c, partner) if c.sex == "母" else (partner, c)
                for sex in ("母", "公"):
                    child = breed(m, f, rules, sex)
                    if child:
                        next_frontier.append(child)
        next_frontier.sort(key=lambda c: (target_chance(c, targets) or 0, c.probability or 0), reverse=True)
        frontier = next_frontier[:limit]
    results.sort(key=lambda c: (target_chance(c, targets) or 0, c.probability or 0, -len(c.route)), reverse=True)
    seen = set()
    unique = []
    for result in results:
        key = result.route
        if key not in seen:
            seen.add(key)
            unique.append(result)
        if len(unique) >= limit:
            break
    return unique
