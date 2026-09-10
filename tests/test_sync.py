from pathlib import Path
import tempfile
import types
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from plugin import Plugin
from reconciliation import Library


class Query(list):
    def select_related(self, *args): return self
    def order_by(self, *args): return self
    def filter(self, **kwargs):
        if 'name__iexact' in kwargs:
            return Query(r for r in self if r.name.casefold() == kwargs['name__iexact'].casefold() and ('year' not in kwargs or r.year == kwargs['year']))
        if 'id' in kwargs:
            return Query(r for r in self if r.id == kwargs['id'])
        if 'series_id__in' in kwargs:
            return Query(r for r in self if r.series_id in kwargs['series_id__in'])
        if 'episode__series_id' in kwargs:
            return Query(r for r in self if r.episode.series_id == kwargs['episode__series_id'])
        return self


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / 'Series'
        self.root.mkdir()
        self.settings = {'series_root_folder': str(self.root), 'root_folder': str(Path(self.tmp.name).resolve() / 'Movies'), 'dispatcharr_url': 'http://dispatcharr:9191', 'series_whitelist': '1,2', 'series_batch_size': '1', 'generate_series_nfo': False}
        self.logger = NS(info=lambda *a: None, error=lambda *a: None)
        self.plugin = Plugin()
        account = NS(id=1, is_active=True)
        self.shows = [NS(id=i, uuid='show-uuid'+str(i), name='Show ' + str(i), year=2024) for i in (1,2)]
        self.relations = Query(NS(id=i, series_id=i, series=s, m3u_account=account, external_series_id=str(i), category=None) for i,s in enumerate(self.shows,1))
        self.episodes = Query(NS(id=i, episode=NS(uuid='uuid'+str(i),series_id=i, name='Pilot',season_number=1,episode_number=1),stream_id=str(i),series_relation_id=i) for i in (1,2))
        models = types.ModuleType('apps.vod.models')
        models.Series = NS(objects=Query(self.shows))
        models.M3USeriesRelation = NS(objects=self.relations)
        models.M3UEpisodeRelation = NS(objects=self.episodes)
        tasks = types.ModuleType('apps.vod.tasks')
        self.refreshes = []
        tasks.refresh_series_episodes = lambda **kw: self.refreshes.append(kw)
        self.addCleanup(patch.stopall)
        patch.dict('sys.modules', {'apps.vod.models':models, 'apps.vod.tasks':tasks}).start()
        with Library(self.root, initialize=True): pass

    def run_action(self, action='generate_series'):
        return self.plugin.run(action, {}, {'settings':self.settings,'logger':self.logger})

    def test_batches_reach_all_and_update_urls_without_renames(self):
        self.assertEqual(self.run_action()['counts']['created'],1)
        self.assertEqual(self.run_action()['counts']['created'],1)
        old_paths = sorted(self.root.rglob('*.strm'))
        self.shows[0].name = 'Renamed'
        self.episodes[0].stream_id = 'changed'
        result = self.run_action()
        self.assertEqual(result['counts']['updated'],1)
        self.assertEqual(sorted(self.root.rglob('*.strm')),old_paths)
        self.assertIn('stream_id=changed',old_paths[0].read_text())

    def test_preview_does_not_refresh(self):
        result = self.run_action('preview_series')
        self.assertEqual(result['counts']['created'],1)
        self.assertEqual(self.refreshes,[])
        self.assertEqual(list(self.root.rglob('*.strm')),[])

    def test_disabled_account_and_blank_whitelist_preserve_library(self):
        self.run_action()
        self.settings['series_whitelist']=''
        self.assertEqual(self.run_action()['processed'],0)
        self.assertEqual(len(list(self.root.rglob('*.strm'))),1)
        self.settings['series_whitelist']='1'
        self.relations[0].m3u_account.is_active=False
        self.assertEqual(self.run_action()['missing_series_ids'],[1])

    def test_duplicate_episode_relation_is_deterministic(self):
        duplicate = NS(**vars(self.episodes[0]))
        duplicate.id=99;duplicate.stream_id='wrong'
        self.episodes.insert(0,duplicate)
        self.run_action()
        self.assertIn('stream_id=1',next(self.root.rglob('*.strm')).read_text())

    def test_adoption_matches_uuid_and_leaves_nfo_untouched(self):
        folder=self.root/'Show 1 (2024)'/'Season 01';folder.mkdir(parents=True)
        path=folder/'Show 1 - S01E01 - Pilot.strm'
        path.write_text('http://dispatcharr:9191/proxy/vod/episode/uuid1?stream_id=old')
        nfo=path.with_suffix('.nfo');nfo.write_text('rich metadata')
        self.settings['generate_series_nfo']=True
        self.shows[0].description='';self.shows[1].description=''
        for r in self.episodes:r.episode.description=''
        self.run_action('adopt_series')
        self.assertIn('stream_id=1',path.read_text())
        self.assertEqual(nfo.read_text(),'rich metadata')
        self.assertEqual(len(list(self.root.rglob('*.strm'))),1)
        self.assertEqual(self.refreshes,[])

    def test_exception_reports_failure_and_preserves_existing(self):
        self.run_action()
        self.episodes[1].episode.episode_number=None
        self.assertEqual(self.run_action()['status'],'error')
        self.assertEqual(len(list(self.root.rglob('*.strm'))),1)

    def test_adoption_preserves_legacy_names(self):
        folder=self.root/'Legacy Title'/'Season 01';folder.mkdir(parents=True)
        path=folder/'S01E01.strm'
        path.write_text('http://dispatcharr:9191/proxy/vod/episode/uuid1?stream_id=old')
        self.assertEqual(self.run_action('preview_adopt_series')['counts']['updated'],1)
        self.assertIn('stream_id=old',path.read_text())
        self.assertEqual(self.run_action('adopt_series')['status'],'ok')
        self.run_action()
        self.assertEqual(list(self.root.rglob('*.strm')),[path])
        self.assertIn('stream_id=1',path.read_text())

    def test_movies_share_update_and_nfo_repair_engine(self):
        import sys
        movie=NS(id=1,uuid='movie-uuid',name='Movie',year=2020,description='',rating='',tmdb_id='',imdb_id='')
        relation=NS(id=1,movie_id=1,movie=movie,m3u_account=NS(id=1,is_active=True),stream_id='old',category=None)
        sys.modules['apps.vod.models'].M3UMovieRelation=NS(objects=Query([relation]))
        root=Path(self.settings['root_folder']);root.mkdir()
        self.assertEqual(self.run_action('initialize_movies')['status'],'ok')
        self.assertEqual(self.run_action('generate_movies')['counts']['created'],2)
        path=next(root.rglob('*.strm'));nfo=path.with_suffix('.nfo');nfo.unlink()
        relation.stream_id='new';movie.name='New title'
        result=self.run_action('generate_movies')
        self.assertEqual(result['counts']['updated'],1)
        self.assertEqual(result['counts']['created'],1)
        self.assertTrue(nfo.exists())
        self.assertIn('stream_id=new',path.read_text())

    def test_priority_changes_source_but_preserves_ties(self):
        account=NS(id=2)
        first=NS(id=3,m3u_account=account)
        second=NS(id=2,m3u_account=NS(id=1))
        sources={'s':3}
        self.assertIs(self.plugin._preferred([first,second],{},sources,'s'),first)
        self.assertIs(self.plugin._preferred([first,second],{'account_priority':'1'},sources,'s'),second)

    def test_title_selection_persists_and_syncs_without_ids(self):
        self.settings['series_whitelist']=''
        self.settings['series_titles']='Show 1 (2024)'
        result=self.run_action()
        self.assertEqual(result['status'],'ok')
        self.assertEqual(result['processed'],1)
        with Library(self.root) as library:
            self.assertEqual(library.state['series_title_selections']['show 1 (2024)']['id'],1)
        self.shows[0].name='Provider renamed show'
        result=self.run_action()
        self.assertEqual(result['status'],'ok')
        self.assertEqual(result['counts']['unchanged'],1)

    def test_check_selection_is_read_only_and_needs_no_refresh(self):
        self.settings['series_whitelist']=''
        self.settings['series_titles']='Show 1 (2024)'
        before={p:p.stat().st_mtime_ns for p in self.root.parent.rglob('*')}
        result=self.run_action('preview_selection_series')
        self.assertEqual(result['series_ids'],[1])
        after={p:p.stat().st_mtime_ns for p in self.root.parent.rglob('*')}
        self.assertEqual(before,after)
        self.assertEqual(self.refreshes,[])

    def test_removing_last_title_clears_pin_without_deleting_media(self):
        self.settings['series_whitelist']=''
        self.settings['series_titles']='Show 1 (2024)'
        self.run_action()
        self.settings['series_titles']=''
        self.assertEqual(self.run_action()['status'],'ok')
        with Library(self.root) as library:
            self.assertEqual(library.state['series_title_selections'],{})
        self.assertEqual(len(list(self.root.rglob('*.strm'))),1)
