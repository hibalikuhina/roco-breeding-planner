"""Regenerate the compact offline catalog from the attributed upstream JSON."""
import json
import urllib.request
from pathlib import Path

SOURCE = "https://jayegt002.github.io/rocom-wiki-data/data/pets.json"
GROUPS = {1: "未发现", 2: "巨灵组", 3: "两栖组", 4: "昆虫组", 5: "天空组", 6: "动物组", 7: "妖精组", 8: "植物组", 9: "拟人组", 10: "软体组", 11: "大地组", 12: "魔力组", 13: "海洋组", 14: "飞龙组", 15: "机械组"}


def main():
    with urllib.request.urlopen(SOURCE, timeout=30) as response:
        records = json.load(response)["records"]
    bases = {}
    for record in records:
        evolution = (record.get("attributes") or {}).get("evolution_id")
        if evolution and record.get("stage") == 1:
            bases.setdefault(evolution, record["id"])
    pets = []
    for record in records:
        attributes = record.get("attributes") or {}
        evolution = attributes.get("evolution_id")
        group_ids = record.get("egg_group") or []
        pets.append({
            "id": record["id"], "number": record.get("number"),
            "name": record.get("title") or record.get("name"),
            "stage": record.get("stage"),
            "family_base_id": bases.get(evolution, record["id"]),
            "egg_groups": [GROUPS.get(n, str(n)) for n in group_ids if n != 1],
            "egg_group_ids": group_ids,
            "egg_size": attributes.get("egg_size"),
            "gender_ratio": record.get("gender_ratio"),
            "has_shiny": attributes.get("has_shiny"),
            "height": record.get("height"), "weight": record.get("weight"),
            "season": record.get("season"),
        })
    output = {"source": SOURCE, "egg_groups": GROUPS, "pets": pets}
    path = Path(__file__).resolve().parent / "data" / "pokedex.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(pets)} records to {path}")


if __name__ == "__main__":
    main()
