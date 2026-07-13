import os
import sys
import tempfile
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from plugin import Plugin


class FakeRelationQuery:
    def __init__(self, relations):
        self.relations = list(relations)
        self.filter_kwargs = None
        self.ordering = None

    def filter(self, **kwargs):
        self.filter_kwargs = kwargs
        allowed_ids = set(kwargs["series_id__in"])
        self.relations = [
            relation for relation in self.relations
            if relation.series_id in allowed_ids
        ]
        return self

    def order_by(self, *fields):
        self.ordering = fields
        self.relations.sort(key=lambda relation: (relation.series_id, relation.id))
        return self

    def __iter__(self):
        return iter(self.relations)


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.plugin = Plugin()

    def test_parse_series_whitelist(self):
        self.assertEqual(
            self.plugin._parse_series_whitelist("12, 34, 12, 0056"),
            [12, 34, 56],
        )
        self.assertEqual(self.plugin._parse_series_whitelist(""), [])

    def test_parse_series_whitelist_rejects_invalid_ids(self):
        for value in ("abc", "1, -2", "1, 2.5", "0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.plugin._parse_series_whitelist(value)

    def test_filter_deduplicates_before_batching(self):
        relations = [
            SimpleNamespace(id=8, series_id=10),
            SimpleNamespace(id=3, series_id=10),
            SimpleNamespace(id=4, series_id=20),
            SimpleNamespace(id=5, series_id=30),
        ]
        query = FakeRelationQuery(relations)

        selected, missing, total = self.plugin._select_series_relations(
            query, [20, 10, 99, 30], "2"
        )

        self.assertEqual(query.filter_kwargs, {"series_id__in": [20, 10, 99, 30]})
        self.assertEqual(query.ordering, ("series_id", "id"))
        self.assertEqual([(item.series_id, item.id) for item in selected], [(20, 4), (10, 3)])
        self.assertEqual(missing, [99])
        self.assertEqual(total, 3)

    def test_series_rerun_adds_only_missing_episodes(self):
        series = SimpleNamespace(id=7, name="Example Show", year=2024)
        existing_episode = SimpleNamespace(
            series=series,
            name="Pilot",
            season_number=1,
            episode_number=1,
            uuid="existing-uuid",
        )
        new_episode = SimpleNamespace(
            series=series,
            name="Second",
            season_number=1,
            episode_number=2,
            uuid="new-uuid",
        )
        episode_relations = [
            SimpleNamespace(episode=existing_episode, stream_id="old-stream"),
            SimpleNamespace(episode=new_episode, stream_id="new-stream"),
        ]

        query_calls = {}

        class EpisodeQuery(list):
            def select_related(self, *args):
                query_calls["select_related"] = args
                return self

            def order_by(self, *fields):
                query_calls["order_by"] = fields
                return self

        class EpisodeManager:
            def filter(self, **kwargs):
                query_calls["filter"] = kwargs
                return EpisodeQuery(episode_relations)

        refresh_calls = []
        models = types.ModuleType("apps.vod.models")
        models.M3UEpisodeRelation = SimpleNamespace(objects=EpisodeManager())
        tasks = types.ModuleType("apps.vod.tasks")
        tasks.refresh_series_episodes = lambda **kwargs: refresh_calls.append(kwargs)

        relation = SimpleNamespace(
            series=series,
            series_id=series.id,
            m3u_account=object(),
            external_series_id="provider-7",
            category=None,
        )

        with tempfile.TemporaryDirectory() as root:
            season_folder = os.path.join(root, "Example Show (2024)", "Season 01")
            os.makedirs(season_folder)
            existing_path = os.path.join(
                season_folder, "Example Show - S01E01 - Pilot.strm"
            )
            with open(existing_path, "w", encoding="utf-8") as handle:
                handle.write("keep-me")

            with patch.dict(
                sys.modules,
                {"apps.vod.models": models, "apps.vod.tasks": tasks},
            ):
                result = self.plugin._process_single_series(
                    relation, "http://dispatcharr:9191", False, root, SimpleNamespace()
                )

            self.assertEqual(result["episodes"], 1)
            self.assertEqual(len(refresh_calls), 1)
            self.assertEqual(query_calls["filter"], {
                "m3u_account": relation.m3u_account,
                "episode__series_id": series.id,
            })
            self.assertEqual(query_calls["select_related"], ("episode",))
            self.assertEqual(query_calls["order_by"], (
                "episode__season_number",
                "episode__episode_number",
            ))
            with open(existing_path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "keep-me")
            self.assertTrue(os.path.exists(os.path.join(
                season_folder, "Example Show - S01E02 - Second.strm"
            )))

    def test_cleanup_deletes_only_whitelisted_series(self):
        allowed = SimpleNamespace(id=1, name="Allowed", year=None)

        class SeriesManager:
            def filter(self, **kwargs):
                return [allowed] if 1 in kwargs["id__in"] else []

        models = types.ModuleType("apps.vod.models")
        models.Series = SimpleNamespace(objects=SeriesManager())
        logger = SimpleNamespace(
            info=lambda *args: None,
            warning=lambda *args: None,
            error=lambda *args: None,
        )

        with tempfile.TemporaryDirectory() as root:
            allowed_season = os.path.join(root, "Allowed", "Season 01")
            other_season = os.path.join(root, "Other", "Season 01")
            os.makedirs(allowed_season)
            os.makedirs(other_season)
            for folder in (allowed_season, other_season):
                with open(os.path.join(folder, "episode.strm"), "w", encoding="utf-8"):
                    pass

            with patch.dict(sys.modules, {"apps.vod.models": models}):
                result = self.plugin._cleanup_series(
                    {"series_root_folder": root, "series_whitelist": "1"}, logger
                )

            self.assertEqual(result["deleted"], 1)
            self.assertFalse(os.path.exists(os.path.join(root, "Allowed")))
            self.assertTrue(os.path.exists(os.path.join(root, "Other")))


if __name__ == "__main__":
    unittest.main()
