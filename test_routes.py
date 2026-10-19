"""Regression checks for grouping direct and projected parents."""

import unittest

from app import first_generation_summary, group_final_routes
from engine import (Candidate, DEFAULT_RULES, PETS, final_route_key,
                    first_generation_uses_record, groups, search)


class FinalPairGroupingTest(unittest.TestCase):
    def test_dual_group_offspring_reaches_second_group(self):
        father = {"id": 17, "name": "星尘虫", "pet_id": "pet_000320", "sex": "公",
                  "size_raw": "1.40", "voice_label": "婉转声", "shiny": 0, "colorful": 0}
        rules = {key: value / 100 for key, value in DEFAULT_RULES.items()}
        results = search([father], None, ["异色", "炫彩", "大块头", "婉转声"], 2,
                         rules, father_id=17, allow_unrecorded=True)
        bridged = [candidate for candidate in results
                   if candidate.father.route and PETS[candidate.father.pet_id]["name"] == "小草虫"
                   and "拟人组" in groups(candidate.pet_id)
                   and "昆虫组" not in groups(candidate.pet_id)]
        self.assertTrue(bridged)
        self.assertTrue(all(candidate.conditional_medal_parents for candidate in bridged))

    def test_unrecorded_and_projected_parent_share_one_row(self):
        mother_id = next(p["id"] for p in PETS.values() if p["name"] == "小草虫")
        father_id = next(p["id"] for p in PETS.values() if p["name"] == "叮叮卯")
        recorded_father = Candidate(father_id, "公", "叮叮卯", {}, (), record_id=1)
        unrecorded_mother = Candidate(mother_id, "母", "[未录入] 小草虫", {}, ())
        projected_mother = Candidate(mother_id, "母", "小草虫", {}, ("先孵出小草虫",),
                                     mother=unrecorded_mother, father=recorded_father)
        direct = Candidate(mother_id, "公", "小草虫", {}, ("直接繁育",),
                           mother=unrecorded_mother, father=recorded_father)
        projected = Candidate(mother_id, "母", "小草虫", {},
                              ("先孵出小草虫", "再繁育"),
                              mother=projected_mother, father=recorded_father)

        self.assertEqual(final_route_key(direct), final_route_key(projected))
        groups = group_final_routes([direct, projected])
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["candidates"]), 2)
        self.assertIn("未录入", first_generation_summary(projected, "mother"))
        self.assertIn("已录入", first_generation_summary(projected, "father"))
        self.assertTrue(first_generation_uses_record(projected, 1))

    def test_selected_parent_can_appear_before_final_pair(self):
        mother_id = next(p["id"] for p in PETS.values() if p["name"] == "小草虫")
        father_id = next(p["id"] for p in PETS.values() if p["name"] == "叮叮卯")
        selected_father = Candidate(father_id, "公", "叮叮卯", {}, (), record_id=7)
        virtual_mother = Candidate(mother_id, "母", "[未录入] 小草虫", {}, ())
        virtual_father = Candidate(mother_id, "公", "[未录入] 小草虫", {}, ())
        son = Candidate(mother_id, "公", "小草虫", {}, ("first",),
                        mother=virtual_mother, father=selected_father)
        daughter = Candidate(mother_id, "母", "小草虫", {}, ("first",),
                             mother=virtual_mother, father=selected_father)
        son_route = Candidate(mother_id, "母", "小草虫", {}, ("first", "second"),
                              mother=virtual_mother, father=son)
        daughter_route = Candidate(mother_id, "公", "小草虫", {}, ("first", "second"),
                                   mother=daughter, father=virtual_father)

        for route in (son_route, daughter_route):
            self.assertTrue(first_generation_uses_record(route, 7))
            self.assertIn("已录入", first_generation_summary(route, "father"))
            self.assertIn("未录入", first_generation_summary(route, "mother"))
        later_only = Candidate(mother_id, "母", "小草虫", {}, ("first", "second"),
                               mother=daughter, father=selected_father)
        self.assertTrue(first_generation_uses_record(later_only, 7))
        unrelated_first = Candidate(mother_id, "母", "小草虫", {}, ("first",),
                                    mother=virtual_mother, father=virtual_father)
        selected_only_later = Candidate(mother_id, "公", "小草虫", {}, ("first", "second"),
                                        mother=unrelated_first, father=selected_father)
        self.assertFalse(first_generation_uses_record(selected_only_later, 7))


if __name__ == "__main__":
    unittest.main()
