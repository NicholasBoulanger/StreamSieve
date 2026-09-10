import copy
import types
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from plugin import Plugin


class Query(list):
    def filter(self, **kwargs):
        def matches(show):
            for name, value in kwargs.items():
                field, _, lookup = name.partition('__')
                actual = getattr(show, field)
                if lookup == 'iexact':
                    if actual.casefold() != value.casefold(): return False
                elif lookup == 'icontains':
                    if value.casefold() not in actual.casefold(): return False
                elif actual != value: return False
            return True
        return Query(show for show in self if matches(show))

    def order_by(self, *args):
        return Query(sorted(self, key=lambda show: show.id))


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.plugin = Plugin()
        self.shows = Query([
            NS(id=1, uuid='one', name='Severance', year=2022),
            NS(id=2, uuid='two', name='The Office', year=2001),
            NS(id=3, uuid='three', name='The Office', year=2005),
            NS(id=4, uuid='four', name='A Title, With Commas', year=None),
        ])
        models = types.ModuleType('apps.vod.models')
        models.Series = NS(objects=self.shows)
        mock = patch.dict('sys.modules', {'apps.vod.models': models})
        mock.start(); self.addCleanup(mock.stop)
        self.logger = NS(info=lambda *args: None, error=lambda *args: None)

    def resolve(self, titles='', ids='', state=None):
        return self.plugin._resolve_series_selection({'series_titles': titles, 'series_whitelist': ids}, state if state is not None else {})

    def test_names_years_commas_and_existing_ids(self):
        ids, labels = self.resolve('severance\nThe Office (2005)\nA Title, With Commas', '99,1')
        self.assertEqual(ids, [99,1,3,4])
        self.assertEqual(labels, ['Severance (2022)', 'The Office (2005)', 'A Title, With Commas'])

    def test_blank_and_duplicate_lines(self):
        self.assertEqual(self.resolve('\n Severance \nseverance\nSeverance')[0], [1])
        self.assertEqual(self.resolve()[0], [])

    def test_unknown_or_partial_title_does_not_select(self):
        for title in ('Sever', 'Missing'):
            with self.subTest(title=title), self.assertRaisesRegex(ValueError, 'No exact show'):
                self.resolve(title)

    def test_ambiguous_titles_require_year(self):
        with self.assertRaisesRegex(ValueError, '2001.*2005'):
            self.resolve('The Office')

    def test_same_title_and_year_requires_explicit_id(self):
        self.shows.append(NS(id=5, uuid='five', name='Severance', year=2022))
        with self.assertRaisesRegex(ValueError, 'advanced ID'):
            self.resolve('Severance (2022)')

    def test_pinned_selection_survives_provider_rename(self):
        state = {}
        self.resolve('Severance', state=state)
        self.shows[0].name = 'Severance UHD'
        self.assertEqual(self.resolve('Severance', state=state)[0], [1])

    def test_reused_database_id_never_retargets_selection(self):
        state = {}
        self.resolve('Severance', state=state)
        self.shows[0].uuid = 'replacement'
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            self.resolve('Severance', state=state)

    def test_removed_title_clears_its_pin(self):
        state = {}
        self.resolve('Severance', state=state)
        self.resolve('', state=state)
        self.assertEqual(state['series_title_selections'], {})

    def test_failed_validation_does_not_change_pins(self):
        state = {}
        self.resolve('Severance', state=state)
        before = copy.deepcopy(state)
        with self.assertRaises(ValueError):
            self.resolve('The Office (2005)\nMissing', state=state)
        self.assertEqual(state, before)

    def test_search_returns_copyable_choices_without_filesystem(self):
        result = self.plugin.run('search_series', {}, {'settings': {'series_search':'office'}, 'logger':self.logger})
        self.assertEqual(result['status'], 'ok')
        self.assertEqual([r['selection'] for r in result['matches']], ['The Office (2001)', 'The Office (2005)'])

    def test_search_is_bounded_and_requires_meaningful_term(self):
        for i in range(30):
            self.shows.append(NS(id=10+i,uuid=str(i),name='Example '+str(i),year=None))
        result = self.plugin._search_series({'series_search':'Example'}, self.logger)
        self.assertEqual(len(result['matches']),20)
        self.assertIn('narrow your search',result['message'])
        with self.assertRaises(ValueError):
            self.plugin._search_series({'series_search':''},self.logger)

    def test_literal_parenthesized_title(self):
        self.shows.append(NS(id=5,uuid='five',name='Example (2024)',year=2025))
        self.assertEqual(self.resolve('Example (2024)')[0],[5])
