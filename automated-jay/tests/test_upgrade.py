"""Checks how a new exe brings an earlier exe's files up to its defaults (bot/config.merge_defaults).

    python -X utf8 -m pytest tests -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.config import merge_defaults


def test_unchanged_values_follow_the_new_defaults():
    old = {"lord": ["ikit", "warpseer"], "reserve": 0}
    new = {"lord": ["ikit", "thanquol", "warpseer"], "reserve": 0}
    assert merge_defaults(dict(old), new, [old]) == new


def test_changed_values_are_kept():
    old = {"off_list": "ask", "reserve": 0}
    new = {"off_list": "replace", "reserve": 0}
    user = {"off_list": "ask", "reserve": 500}
    assert merge_defaults(user, new, [old]) == {"off_list": "replace", "reserve": 500}
    user = {"off_list": "keep", "reserve": 0}
    assert merge_defaults(user, new, [old])["off_list"] == "keep"


def test_new_keys_added_player_keys_kept_dropped_defaults_dropped():
    old = {"player_faction_key": "skryre", "faction_paths": [[1, 2]]}
    new = {"player_factions": ["skryre", "scruten"], "faction_paths": [[1, 2]]}
    user = {"player_faction_key": "skryre", "faction_paths": [[1, 2]], "ui_root_ptr": 1234}
    assert merge_defaults(user, new, [old]) == {"faction_paths": [[1, 2]], "ui_root_ptr": 1234,
                                                "player_factions": ["skryre", "scruten"]}


def test_nested_dicts_and_ticks():
    old = {"army_builder": {"enabled_armies": [{"cqi": 2492}], "template": {"lord": ["ikit"]}},
           "characters": {"ikit": {"order": [1]}}}
    new = {"army_builder": {"enabled_armies": [], "template": {"lord": ["ikit", "thanquol"]}},
           "characters": {"ikit": {"order": [1]}, "thanquol": {"order": [2]}}}
    user = {"army_builder": {"enabled_armies": [{"cqi": 55}], "template": {"lord": ["ikit"]}},
            "characters": {"ikit": {"order": [3]}}}
    assert merge_defaults(user, new, [old]) == {
        "army_builder": {"enabled_armies": [{"cqi": 55}], "template": {"lord": ["ikit", "thanquol"]}},
        "characters": {"ikit": {"order": [3]}, "thanquol": {"order": [2]}}}


def test_a_key_the_player_removed_stays_removed():
    old = {"a": 1, "b": 2}
    new = {"a": 1, "b": 3}
    assert merge_defaults({"a": 1}, new, [old]) == {"a": 1}


def test_unknown_history_only_adds_keys():
    new = {"a": 2, "b": 1}
    assert merge_defaults({"a": 1}, new, []) == {"a": 1, "b": 1}


def test_any_earlier_release_counts_as_unchanged():
    v010, v011 = {"schedule": ["skills"]}, {"schedule": ["tech", "skills"]}
    new = {"schedule": ["rites", "tech", "skills"]}
    assert merge_defaults({"schedule": ["skills"]}, new, [v010, v011]) == new
    assert merge_defaults({"schedule": ["tech", "skills"]}, new, [v010, v011]) == new
