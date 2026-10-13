"""Regenerate the offline catalog, using the current WIKI for season labels."""
import json
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

SOURCE = "https://jayegt002.github.io/rocom-wiki-data/data/pets.json"
SEASON_SOURCE = "https://wiki.biligame.com/nrc/%E7%B2%BE%E7%81%B5%E5%88%97%E8%A1%A8"
GROUPS = {1: "未发现", 2: "巨灵组", 3: "两栖组", 4: "昆虫组", 5: "天空组", 6: "动物组", 7: "妖精组", 8: "植物组", 9: "拟人组", 10: "软体组", 11: "大地组", 12: "魔力组", 13: "海洋组", 14: "飞龙组", 15: "机械组"}


class SeasonTableParser(HTMLParser):
    """Read the per-form season markers from the WIKI's rendered pet table."""

    def __init__(self):
        super().__init__()
        self.seasons = {}

    def handle_starttag(self, tag, attrs):
        if tag != "tr":
            return
        attrs = dict(attrs)
        pet_id = attrs.get("data-id")
        if not pet_id or not re.fullmatch(r"pet_\d+", pet_id):
            return
        season = attrs.get("data-season")
        if season != "none" and not (season and re.fullmatch(r"S[1-9]\d*", season)):
            raise ValueError(f"Unexpected WIKI season for {pet_id}: {season!r}")
        if pet_id in self.seasons:
            raise ValueError(f"Duplicate WIKI pet ID: {pet_id}")
        self.seasons[pet_id] = None if season == "none" else season


def fetch_wiki_seasons():
    request = urllib.request.Request(SEASON_SOURCE, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        page = response.read().decode("utf-8")
    parser = SeasonTableParser()
    parser.feed(page)
    if not parser.seasons:
        raise ValueError("No pet season rows found on the WIKI page")
    return parser.seasons


def main():
    with urllib.request.urlopen(SOURCE, timeout=30) as response:
        records = json.load(response)["records"]
    seasons = fetch_wiki_seasons()
    missing = {record["id"] for record in records} - seasons.keys()
    if missing:
        raise ValueError(f"WIKI season data missing {len(missing)} pet IDs: {sorted(missing)[:10]}")
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
            "gender_ratio": record.get("gender_ratio"),
            "has_shiny": attributes.get("has_shiny"),
            "adult_height_range": record.get("height"),
            "adult_weight_range": record.get("weight"),
            "season": seasons[record["id"]],
        })
    output = {"source": SOURCE, "season_source": SEASON_SOURCE, "egg_groups": GROUPS, "pets": pets}
    path = Path(__file__).resolve().parent / "data" / "pokedex.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(pets)} records to {path}")


if __name__ == "__main__":
    main()
