"""Regression checks for grouping direct and projected parents."""

import unittest

from app import group_final_routes, grouped_parent_summary
from engine import Candidate, PETS, final_route_key


class FinalPairGroupingTest(unittest.TestCase):
    def test_unrecorded_and_projected_parent_share_one_row(self):
        mother_id = next(p["id"] for p in PETS.values() if p["name"] == "小草虫")
        father_id = next(p["id"] for p in PETS.values() if p["name"] == "叮叮卯")
        recorded_father = Candidate(father_id, "公", "叮叮卯", {}, (), record_id=1)
        unrecorded_mother = Candidate(mother_id, "母", "[未录入] 小草虫", {}, ())
        projected_mother = Candidate(mother_id, "母", "小草虫", {}, ("先孵出小草虫",))
        direct = Candidate(mother_id, "公", "小草虫", {}, ("直接繁育",),
                           mother=unrecorded_mother, father=recorded_father)
        projected = Candidate(mother_id, "母", "小草虫", {},
                              ("先孵出小草虫", "再繁育"),
                              mother=projected_mother, father=recorded_father)

        self.assertEqual(final_route_key(direct), final_route_key(projected))
        groups = group_final_routes([direct, projected])
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["candidates"]), 2)
        self.assertIn("未录入/需先孵出", grouped_parent_summary(groups[0], "mother"))
        self.assertIn("已录入", grouped_parent_summary(groups[0], "father"))


if __name__ == "__main__":
    unittest.main()
