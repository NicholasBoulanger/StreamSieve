"""Run StreamSieve inside Dispatcharr's Python environment, once or periodically."""
import argparse
import json
import logging
import os
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings', required=True, help='JSON file containing StreamSieve settings')
    parser.add_argument('--django-settings', default='dispatcharr.settings')
    parser.add_argument('--kind', choices=('series', 'movies', 'both'), default='series')
    parser.add_argument('--interval', type=int, default=0, help='Seconds between runs; zero runs once')
    parser.add_argument('--preview', action='store_true')
    args = parser.parse_args()
    if args.interval and args.interval < 60:
        parser.error('Interval must be zero or at least 60 seconds')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', args.django_settings)
    import django
    django.setup()
    from plugin import Plugin
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('streamsieve')
    while True:
        failed = False
        try:
            settings = json.loads(Path(args.settings).read_text())
            kinds = ('series', 'movies') if args.kind == 'both' else (args.kind,)
            for kind in kinds:
                result = Plugin().run(('preview_' if args.preview else 'generate_') + kind, {}, {'settings': settings, 'logger': logger})
                logger.info('%s', json.dumps(result))
                failed |= result['status'] != 'ok'
        except Exception:
            logger.exception('Scheduled reconciliation failed')
            failed = True
        if not args.interval:
            return int(failed)
        # The next run starts only after this run finishes; library locks also
        # serialize this process with manual Dispatcharr actions.
        time.sleep(args.interval)


if __name__ == '__main__':
    raise SystemExit(main())
