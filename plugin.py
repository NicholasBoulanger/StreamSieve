"""
VOD .strm Generator Plugin for Dispatcharr
v1.6.0 - Owned-file reconciliation

MIT License
Copyright (c) 2025-2026 shedunraid
https://github.com/shedunraid/VODVSCODE
"""
import os
import re
from typing import Dict, Any


class Plugin:
    """Generate .strm files for VOD movies from Dispatcharr."""

    name = "StreamSieve"
    version = "1.6.0"
    description = "Generate and reconcile owned movie/series STRM and NFO libraries. Initialize roots, preview changes, then synchronize. Legacy files require explicit adoption."

    fields = [{'id': 'root_folder',
  'label': 'Root Folder for Movies',
  'type': 'string',
  'default': '/VODS/Movies',
  'help_text': 'Path where movie folders will be created'},
 {'id': 'series_root_folder',
  'label': 'Root Folder for Series',
  'type': 'string',
  'default': '/VODS/Series',
  'help_text': 'Path where series folders will be created'},
 {'id': 'dispatcharr_url',
  'label': 'Dispatcharr URL (IMPORTANT!)',
  'type': 'string',
  'default': 'http://192.168.99.11:9191',
  'help_text': 'Must be accessible from your media server; this URL is written into .strm files.'},
 {'id': 'batch_size',
  'label': 'Batch Size (Movies)',
  'type': 'select',
  'default': '100',
  'options': [{'value': '10', 'label': '10 movies'},
              {'value': '100', 'label': '100 movies'},
              {'value': '200', 'label': '200 movies'},
              {'value': '500', 'label': '500 movies'},
              {'value': '1000', 'label': '1000 movies'},
              {'value': 'all', 'label': 'All movies'}],
  'help_text': 'Number of movies to process in this run'},
 {'id': 'generate_nfo',
  'label': 'Generate Movie NFO Files',
  'type': 'boolean',
  'default': True,
  'help_text': 'Create .nfo metadata files for movies'},
 {'id': 'series_batch_size',
  'label': 'Batch Size (Series)',
  'type': 'select',
  'default': '10',
  'options': [{'value': '1', 'label': '1 series (testing)'},
              {'value': '5', 'label': '5 series'},
              {'value': '10', 'label': '10 series'},
              {'value': '25', 'label': '25 series'},
              {'value': 'all', 'label': 'All series (slow!)'}],
  'help_text': 'Unique whitelisted series to refresh and process in this run'},
 {'id': 'series_whitelist',
  'label': 'Series Whitelist (Dispatcharr IDs)',
  'type': 'string',
  'default': '',
  'placeholder': '12, 34, 56',
  'help_text': 'Comma-separated Dispatcharr Series database IDs. Only these series are eligible; '
               'leave blank to process no series.'},
 {'id': 'generate_series_nfo',
  'label': 'Generate Series NFO Files',
  'type': 'boolean',
  'default': True,
  'help_text': 'Create .nfo metadata files for series and episodes'},
 {'id': 'account_priority',
  'label': 'Account priority (Dispatcharr IDs)',
  'type': 'string',
  'default': '',
  'help_text': 'Comma-separated account IDs, highest preference first. Other eligible accounts '
               'follow by relation ID.'}]

    actions = [{'id': 'scan_all_vods',
  'label': 'Scan VOD catalog',
  'description': 'Show available movies and series'},
 {'id': 'initialize_series',
  'label': 'Initialize (series)',
  'description': 'Create ownership state for an existing mounted root; leaves media untouched'},
 {'id': 'preview_series',
  'label': 'Preview (series)',
  'description': 'Read-only preview using the current Dispatcharr catalog; no provider refresh'},
 {'id': 'adopt_series',
  'label': 'Adopt matching legacy STRMs (series)',
  'description': 'Claim unambiguous existing Dispatcharr proxy UUIDs and preserve legacy paths; '
                 'NFOs remain unmanaged'},
 {'id': 'generate_series',
  'label': 'Synchronize (series)',
  'description': 'Create missing files and update owned files; no automatic deletion'},
 {'id': 'cleanup_series',
  'label': 'Retire owned files (series)',
  'description': 'Copy verified owned files to sibling state/recovery storage, then remove them; '
                 'series limited to current whitelist'},
 {'id': 'initialize_movies',
  'label': 'Initialize (movies)',
  'description': 'Create ownership state for an existing mounted root; leaves media untouched'},
 {'id': 'preview_movies',
  'label': 'Preview (movies)',
  'description': 'Read-only preview using the current Dispatcharr catalog; no provider refresh'},
 {'id': 'adopt_movies',
  'label': 'Adopt matching legacy STRMs (movies)',
  'description': 'Claim unambiguous existing Dispatcharr proxy UUIDs and preserve legacy paths; '
                 'NFOs remain unmanaged'},
 {'id': 'generate_movies',
  'label': 'Synchronize (movies)',
  'description': 'Create missing files and update owned files; no automatic deletion'},
 {'id': 'cleanup_movies',
  'label': 'Retire owned files (movies)',
  'description': 'Copy verified owned files to sibling state/recovery storage, then remove them; '
                 'series limited to current whitelist'},
 {'id': 'preview_adopt_series',
  'label': 'Preview adoption (series)',
  'description': 'Read-only report of matching legacy STRMs eligible for ownership'},
 {'id': 'preview_adopt_movies',
  'label': 'Preview adoption (movies)',
  'description': 'Read-only report of matching legacy STRMs eligible for ownership'},
 {'id': 'preview_cleanup_series',
  'label': 'Preview retirement (series)',
  'description': 'Read-only count of owned, unmodified files eligible for recovery storage'},
 {'id': 'restore_series',
  'label': 'Restore retired files (series)',
  'description': 'Restore verified recovery copies without overwriting conflicting files'},
 {'id': 'preview_cleanup_movies',
  'label': 'Preview retirement (movies)',
  'description': 'Read-only count of owned, unmodified files eligible for recovery storage'},
 {'id': 'restore_movies',
  'label': 'Restore retired files (movies)',
  'description': 'Restore verified recovery copies without overwriting conflicting files'}]

    def run(self, action: str, params: dict, context: dict):
        """Execute plugin action."""
        logger = context.get("logger")
        settings = context.get("settings", {})

        logger.info("=" * 60)
        logger.info("VOD .strm Generator v%s", self.version)
        logger.info("Action: %s", action)
        logger.info("=" * 60)

        try:
            if action == "scan_all_vods":
                return self._scan_all_vods(settings, logger)
            if action in {item['id'] for item in self.actions}:
                return self._library_action(action, settings, logger)
            return {"status": "error", "message": f"Unknown action: {action}"}
        except Exception as exc:
            logger.error("StreamSieve action failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    def _scan_all_vods(self, settings: Dict[str, Any], logger):
        """Scan and show total movies and series available."""
        logger.info("Scanning VODs in Dispatcharr...")
        logger.info("")

        try:
            from apps.vod.models import M3UMovieRelation, M3USeriesRelation
        except ImportError as e:
            logger.error("Failed to import models: %s", e)
            return {"status": "error", "message": f"Import error: {e}"}

        try:
            # Count movies and series
            movie_count = M3UMovieRelation.objects.count()
            series_count = M3USeriesRelation.objects.count()

            logger.info("=" * 60)
            logger.info("MOVIES: %d", movie_count)
            logger.info("SERIES: %d", series_count)
            logger.info("=" * 60)
            logger.info("")
            logger.info("Use 'Generate Movie .strm Files' for movies")
            logger.info("Use 'Generate Series .strm Files' for series")

            return {
                "status": "ok",
                "message": f"Found {movie_count} movies and {series_count} series",
                "movies": movie_count,
                "series": series_count
            }
        except Exception as e:
            logger.error("Scan failed: %s", e)
            return {"status": "error", "message": f"Scan error: {e}"}

    def _library_action(self, action, settings, logger):
        # Loaded by path because Dispatcharr may load plugin.py outside a package.
        import importlib.util
        from urllib.parse import urlsplit, urlencode
        spec = importlib.util.spec_from_file_location('streamsieve_reconciliation', os.path.join(os.path.dirname(__file__), 'reconciliation.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        series_mode = action.endswith('series')
        root = settings.get('series_root_folder' if series_mode else 'root_folder', '/VODS/Series' if series_mode else '/VODS/Movies')
        other = settings.get('root_folder' if series_mode else 'series_root_folder', '/VODS/Movies' if series_mode else '/VODS/Series')
        first, second = os.path.abspath(root), os.path.abspath(other)
        if os.path.commonpath([first, second]) in (first, second):
            raise ValueError('Movie and series roots must not overlap')
        preview = action.startswith('preview_')
        initialize = action.startswith('initialize_')
        adopt = action.startswith('adopt_') or action.startswith('preview_adopt_')
        cleanup = action.startswith('cleanup_') or action.startswith('preview_cleanup_')
        restore = action.startswith('restore_')
        with module.Library(root, preview=preview, initialize=initialize) as library:
            if initialize:
                return {'status': 'ok', 'message': 'Library initialized; existing files remain unmanaged'}
            whitelist = self._parse_series_whitelist(settings.get('series_whitelist', '')) if series_mode else []
            if restore:
                result = library.restore({'series:' + str(i) for i in whitelist} if series_mode else None)
                return {'status': 'error' if result['conflict'] else 'ok', 'message': 'Recovery complete; existing conflicting files were preserved', **result}
            if cleanup:
                result = library.retire({'series:' + str(i) for i in whitelist} if series_mode else None)
                return {'status': 'error' if result['conflict'] else 'ok', 'message': 'Retirement preview; no files changed' if preview else 'Owned files copied to sibling state/recovery directory and removed from library', **result}
            base = settings.get('dispatcharr_url', '').rstrip('/')
            parsed = urlsplit(base)
            if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError('Set a valid HTTP(S) Dispatcharr URL without credentials, query, or fragment')
            counts = dict(created=0, updated=0, unchanged=0, unmanaged=0, conflict=0, adopted=0, errors=0)
            details = []
            def write(key, path, content, owner, can_adopt=False):
                if adopt and not can_adopt:
                    return
                result = library.write(key, path, content, owner, adopt=can_adopt)
                counts[result] += 1
                if result != 'unchanged':
                    logger.info('%s: %s', result, path)
                    if len(details) < 100:
                        details.append({'operation': result, 'path': path})
            # Locate legacy proxy files by UUID, preserving arbitrary existing
            # filenames. Ambiguous mappings are errors, never guesses by title.
            legacy = {}
            if library.root.exists():
                for directory, dirs, files in os.walk(library.root, followlinks=False):
                    for filename in files:
                        if not filename.lower().endswith('.strm'):
                            continue
                        relative = os.path.relpath(os.path.join(directory, filename), library.root)
                        target = library.path(relative)
                        if target.stat().st_size > 8192:
                            continue
                        try:
                            old = urlsplit(target.read_text().strip())
                        except (UnicodeError, ValueError):
                            continue
                        prefix = parsed.path.rstrip('/') + '/proxy/vod/'
                        if old.scheme in ('http', 'https') and old.netloc == parsed.netloc and old.path.startswith(prefix):
                            parts = old.path[len(prefix):].strip('/').split('/')
                            if len(parts) == 2:
                                legacy.setdefault(tuple(parts), []).append(relative)
            def existing(kind, identity):
                paths = legacy.get((kind, str(identity)), [])
                if len(paths) > 1:
                    raise ValueError('Ambiguous legacy paths for ' + kind + ' ' + str(identity))
                return paths[0] if paths else None
            def adoptable(path, kind, identity):
                return adopt and existing(kind, identity) == path
            if series_mode:
                from apps.vod.models import M3USeriesRelation, M3UEpisodeRelation
                from apps.vod.tasks import refresh_series_episodes
                query = M3USeriesRelation.objects.filter(series_id__in=whitelist).select_related('series', 'm3u_account', 'category').order_by('series_id', 'id')
                grouped = {}
                for relation in query:
                    if self._eligible(relation):
                        grouped.setdefault(relation.series_id, []).append(relation)
                relations = [self._preferred(grouped[i], settings, library.state.setdefault('sources', {}), 'series:' + str(i)) for i in whitelist if i in grouped]
                missing = [i for i in whitelist if i not in grouped]
            else:
                from apps.vod.models import M3UMovieRelation
                grouped = {}
                for relation in M3UMovieRelation.objects.select_related('movie', 'm3u_account', 'category').order_by('movie_id', 'id'):
                    if self._eligible(relation):
                        grouped.setdefault(relation.movie_id, []).append(relation)
                relations = [self._preferred(grouped[i], settings, library.state.setdefault('sources', {}), 'movie:' + str(i)) for i in sorted(grouped)]
                missing = []
            total = len(relations)
            batch = settings.get('series_batch_size' if series_mode else 'batch_size', '10' if series_mode else '100')
            limit = total if batch == 'all' else int(batch)
            if limit <= 0 and total:
                raise ValueError('Batch size must be positive')
            start = library.state['cursor'] % total if total else 0
            selected = relations if adopt else (relations[start:] + relations[:start])[:limit]
            for relation in selected:
                try:
                    if series_mode:
                        series = relation.series
                        owner = 'series:' + str(series.id)
                        if not preview and not adopt:
                            refresh_series_episodes(account=relation.m3u_account, series=series, external_series_id=relation.external_series_id)
                        episodes = M3UEpisodeRelation.objects.filter(m3u_account=relation.m3u_account, episode__series_id=series.id).select_related('episode').order_by('episode__season_number', 'episode__episode_number', 'id')
                        by_episode = {}
                        for candidate in episodes:
                            # Newer Dispatcharr schemas explicitly associate episode
                            # streams with a provider-series relation.
                            parent = getattr(candidate, 'series_relation_id', None)
                            if parent is not None and parent != relation.id:
                                continue
                            by_episode.setdefault(str(candidate.episode.uuid), []).append(candidate)
                        legacy_folders = set()
                        for identity in by_episode:
                            old_path = existing('episode', identity)
                            if old_path:
                                parts = old_path.split(os.sep)
                                if len(parts) < 3:
                                    raise ValueError('Legacy series path has no show/season hierarchy: ' + old_path)
                                legacy_folders.add(os.path.dirname(os.path.dirname(old_path)))
                        if len(legacy_folders) > 1:
                            raise ValueError('Episodes map to multiple legacy show folders')
                        folder = library.assign(owner, next(iter(legacy_folders)) if legacy_folders else self._series_folder_name(series))
                        if settings.get('generate_series_nfo', True) and by_episode:
                            write(owner + ':nfo', folder + '/tvshow.nfo', self._generate_tvshow_nfo(series, relation.category.name if relation.category else '') + '\n', owner)
                        numbers = set()
                        for identity, candidates in by_episode.items():
                            candidate = min(candidates, key=lambda r: r.id)
                            episode = candidate.episode
                            season, number = episode.season_number, episode.episode_number
                            if not isinstance(season, int) or not isinstance(number, int) or season < 0 or number <= 0 or (season, number) in numbers:
                                raise ValueError('Invalid or ambiguous episode numbering')
                            numbers.add((season, number))
                            title = self._clean_title(series.name or 'Unknown Series')
                            name = f'{title} - S{season:02d}E{number:02d}'
                            if episode.name:
                                name += ' - ' + self._clean_title(episode.name)
                            key = owner + ':episode:' + str(getattr(episode, 'id', identity))
                            legacy_path = existing('episode', identity)
                            stem = library.assign(key, legacy_path[:-5] if legacy_path else folder + f'/Season {season:02d}/' + self._sanitize_filename(name))
                            path = stem + '.strm'
                            url = base + '/proxy/vod/episode/' + identity + '?' + urlencode({'stream_id': candidate.stream_id}) + '\n'
                            write(key + ':strm', path, url, owner, adoptable(path, 'episode', identity))
                            if settings.get('generate_series_nfo', True):
                                write(key + ':nfo', stem + '.nfo', self._generate_episode_nfo(episode) + '\n', owner)
                    else:
                        movie = relation.movie
                        owner = 'movie:' + str(movie.id)
                        title = self._clean_title(movie.name or f'Unknown Movie {movie.id}')
                        name = self._sanitize_filename(title + (f' ({movie.year})' if movie.year else ''))
                        legacy_path = existing('movie', movie.uuid)
                        folder = library.assign(owner, os.path.dirname(legacy_path) if legacy_path else name)
                        stem = library.assign(owner + ':media', legacy_path[:-5] if legacy_path else folder + '/' + name)
                        path = stem + '.strm'
                        url = base + '/proxy/vod/movie/' + str(movie.uuid) + '?' + urlencode({'stream_id': relation.stream_id}) + '\n'
                        write(owner + ':strm', path, url, owner, adoptable(path, 'movie', movie.uuid))
                        if settings.get('generate_nfo', True):
                            write(owner + ':nfo', stem + '.nfo', self._generate_nfo(movie, relation.category.name if relation.category else '') + '\n', owner)
                except Exception as exc:
                    counts['errors'] += 1
                    logger.error('Item reconciliation failed: %s', exc)
            if total and not adopt:
                library.checkpoint((start + len(selected)) % total)
            return {'status': 'error' if counts['errors'] or counts['conflict'] else 'ok', 'message': 'Preview complete' if preview else 'Reconciliation complete; automatic orphan removal is disabled', 'counts': counts, 'processed': len(selected), 'total': total, 'missing_series_ids': missing, 'changes': details}

    @staticmethod
    def _eligible(relation):
        account = relation.m3u_account
        return getattr(account, 'is_active', True) and getattr(account, 'enabled', True) and getattr(relation, 'is_active', True)

    @staticmethod
    def _preferred(relations, settings, sources=None, key=None):
        priority = [int(i.strip()) for i in settings.get('account_priority', '').split(',') if i.strip()]
        previous = sources.get(key) if sources is not None else None
        def rank(relation):
            account_id = getattr(relation, 'm3u_account_id', getattr(relation.m3u_account, 'id', None))
            return (priority.index(account_id) if account_id in priority else len(priority), relation.id != previous, relation.id)
        selected = min(relations, key=rank)
        if sources is not None:
            sources[key] = selected.id
        return selected

    def _generate_movies(self, settings, logger):
        return self._library_action('generate_movies', settings, logger)

    def _generate_series(self, settings, logger):
        return self._library_action('generate_series', settings, logger)

    def _cleanup_movies(self, settings, logger):
        return self._library_action('cleanup_movies', settings, logger)

    def _cleanup_series(self, settings, logger):
        return self._library_action('cleanup_series', settings, logger)

    def _parse_series_whitelist(self, value) -> list:
        """Parse comma-separated Dispatcharr Series primary keys."""
        if value is None:
            return []

        if isinstance(value, (list, tuple, set)):
            tokens = [str(item).strip() for item in value]
        else:
            tokens = [token.strip() for token in str(value).split(',')]

        series_ids = []
        invalid_tokens = []
        for token in tokens:
            if not token:
                continue
            if not token.isdigit() or int(token) <= 0:
                invalid_tokens.append(token)
                continue
            series_id = int(token)
            if series_id not in series_ids:
                series_ids.append(series_id)

        if invalid_tokens:
            raise ValueError(
                "IDs must be positive whole numbers; invalid value(s): "
                + ", ".join(invalid_tokens)
            )

        return series_ids

    def _series_folder_name(self, series) -> str:
        """Build the on-disk folder name shared by generation and cleanup."""
        raw_name = series.name or f"Unknown Series {series.id}"
        series_name = self._clean_title(raw_name)
        sanitized_name = self._sanitize_filename(series_name)
        if series.year:
            return f"{sanitized_name} ({series.year})"
        return sanitized_name

    def _clean_title(self, title: str) -> str:
        """Remove language prefixes (EN -, FR -, etc.) from movie titles."""
        if not title:
            return title

        # Remove common language prefixes: EN -, FR -, US -, etc.
        cleaned = re.sub(r'^[A-Z]{2,3}\s*-\s*', '', title)
        return cleaned.strip()

    def _extract_genres(self, category_name: str) -> list:
        """Extract genre names from category name."""
        if not category_name:
            return []

        # Remove common prefixes (EN -, FR -, US -, etc.)
        genre_text = re.sub(r'^[A-Z]{2,3}\s*-\s*', '', category_name)

        # Remove (movie) or (series) suffix
        genre_text = re.sub(r'\s*\((movie|series)\)\s*$', '', genre_text, flags=re.IGNORECASE)

        # Split on common separators
        genres = re.split(r'[/&,]', genre_text)

        # Clean up each genre
        cleaned_genres = []
        for genre in genres:
            genre = genre.strip()
            # Capitalize first letter of each word
            genre = ' '.join(word.capitalize() for word in genre.split())
            if genre:
                cleaned_genres.append(genre)

        return cleaned_genres or ["Unknown"]

    def _generate_tvshow_nfo(self, series, category_name: str) -> str:
        """Generate tvshow.nfo XML content for a series."""
        # Extract basic info (clean language prefix)
        raw_title = series.name or "Unknown"
        title = self._clean_title(raw_title)
        year = series.year or ""
        plot = series.description or ""

        # Extract genres from category
        genres = self._extract_genres(category_name)

        # Build XML
        xml_lines = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>']
        xml_lines.append('<tvshow>')
        xml_lines.append(f'    <title>{self._xml_escape(title)}</title>')

        if year:
            xml_lines.append(f'    <year>{year}</year>')

        for genre in genres:
            xml_lines.append(f'    <genre>{self._xml_escape(genre)}</genre>')

        if plot:
            xml_lines.append(f'    <plot>{self._xml_escape(plot)}</plot>')

        xml_lines.extend(self._metadata_ids(series))
        xml_lines.append('</tvshow>')

        return '\n'.join(xml_lines)

    def _generate_episode_nfo(self, episode) -> str:
        """Generate episode.nfo XML content for an episode."""
        # Extract episode info (clean language prefix)
        raw_title = episode.name or ""
        title = self._clean_title(raw_title) if raw_title else "Episode"
        season_num = episode.season_number or 0
        episode_num = episode.episode_number or 0
        plot = episode.description or ""

        # Build XML
        xml_lines = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>']
        xml_lines.append('<episodedetails>')
        xml_lines.append(f'    <title>{self._xml_escape(title)}</title>')
        xml_lines.append(f'    <season>{season_num}</season>')
        xml_lines.append(f'    <episode>{episode_num}</episode>')

        if plot:
            xml_lines.append(f'    <plot>{self._xml_escape(plot)}</plot>')

        xml_lines.extend(self._metadata_ids(episode))
        xml_lines.append('</episodedetails>')

        return '\n'.join(xml_lines)

    def _generate_nfo(self, movie, category_name: str) -> str:
        """Generate NFO XML content for a movie."""
        # Extract basic info (clean language prefix)
        raw_title = movie.name or "Unknown"
        title = self._clean_title(raw_title)
        year = movie.year or ""
        plot = movie.description or ""
        rating = movie.rating or ""
        tmdb_id = movie.tmdb_id or ""
        imdb_id = movie.imdb_id or ""

        # Extract genres from category
        genres = self._extract_genres(category_name)

        # Build XML
        xml_lines = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>']
        xml_lines.append('<movie>')
        xml_lines.append(f'    <title>{self._xml_escape(title)}</title>')

        if year:
            xml_lines.append(f'    <year>{year}</year>')

        for genre in genres:
            xml_lines.append(f'    <genre>{self._xml_escape(genre)}</genre>')

        if plot:
            xml_lines.append(f'    <plot>{self._xml_escape(plot)}</plot>')

        if rating:
            xml_lines.append(f'    <rating>{rating}</rating>')

        if tmdb_id:
            xml_lines.append(f'    <tmdbid>{tmdb_id}</tmdbid>')

        if imdb_id:
            xml_lines.append(f'    <imdbid>{imdb_id}</imdbid>')

        xml_lines.append('</movie>')

        return '\n'.join(xml_lines)

    def _metadata_ids(self, item):
        result = []
        for provider in ('tmdb', 'imdb'):
            value = getattr(item, provider + '_id', None)
            if value:
                result.append(f'    <uniqueid type="{provider}">{self._xml_escape(value)}</uniqueid>')
        return result

    def _xml_escape(self, text: str) -> str:
        """Escape special XML characters."""
        if not text:
            return ""
        text = str(text)
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        text = text.replace('"', '&quot;')
        text = text.replace("'", '&apos;')
        return text

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize filename by removing invalid characters."""
        if not name:
            return "Unknown"

        # Remove invalid characters for Windows/Linux filesystems
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name)

        # Replace multiple spaces with single space
        name = re.sub(r'\s+', ' ', name)

        # Trim and limit length
        name = name.strip().encode('utf-8')[:180].decode('utf-8', errors='ignore')

        # Remove trailing dots/spaces (Windows issue)
        name = name.rstrip('. ')

        if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM' + str(i) for i in range(1, 10)), *('LPT' + str(i) for i in range(1, 10))}:
            name = '_' + name
        return name or "Unknown"
