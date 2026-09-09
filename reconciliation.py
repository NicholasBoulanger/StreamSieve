"""Conservative, single-writer filesystem reconciliation (standard library only)."""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, data):
    path = Path(path)
    mode = (path.stat().st_mode & 0o777) if path.exists() else 0o644
    fd, temporary = tempfile.mkstemp(prefix='.streamsieve-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Library:
    def __init__(self, root, preview=False, initialize=False):
        self.root = Path(os.path.abspath(root))
        if self.root == Path('/'):
            raise ValueError('A filesystem root cannot be a library')
        self._no_links(self.root)
        self.state_dir = self.root.with_name(self.root.name + '.streamsieve-state')
        self._no_links(self.state_dir)
        self.preview = preview
        self.lock = None
        self.state = {'version': 1, 'root': str(self.root), 'instance': '', 'files': {}, 'paths': {}, 'cursor': 0}
        if initialize:
            if not self.root.is_dir():
                raise ValueError('Create and mount the library root before initialization')
            self.state_dir.mkdir(exist_ok=True)
        if not preview:
            if not self.state_dir.is_dir():
                raise ValueError('Initialize this library first; existing files will remain unmanaged')
            self._no_links(self.state_dir / 'lock')
            self.lock = open(self.state_dir / 'lock', 'a+b')
            try:
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self.lock.close()
                raise ValueError('Another StreamSieve action is running')
        try:
            self._load(initialize)
        except Exception:
            self.close()
            raise

    @staticmethod
    def _no_links(path):
        for part in (path, *path.parents):
            if part.is_symlink():
                raise ValueError('Symlink paths are not supported: ' + str(part))

    def path(self, relative):
        rel = Path(relative)
        if rel.is_absolute() or not rel.parts or any(p in ('.', '..') for p in rel.parts):
            raise ValueError('Unsafe library path')
        path = self.root / rel
        self._no_links(path)
        return path

    def _json(self, name):
        path = self.state_dir / name
        self._no_links(path)
        return json.loads(path.read_text()) if path.exists() else None

    def _save(self, name, value):
        path = self.state_dir / name
        self._no_links(path)
        atomic_write(path, (json.dumps(value, sort_keys=True, indent=2) + '\n').encode())

    def _load(self, initialize):
        marker = self.root / '.streamsieve-root'
        self._no_links(marker)
        state = self._json('index.json')
        if state is None:
            if initialize:
                if marker.exists():
                    raise ValueError('Root marker exists without its index; restore state from backup')
                self.state['instance'] = str(uuid.uuid4())
                self._save('index.json', self.state)
                atomic_write(marker, self.state['instance'].encode())
            elif not self.preview:
                raise ValueError('Missing ownership index; restore state from backup')
        else:
            if state.get('version') != 1 or state.get('root') != str(self.root):
                raise ValueError('Unsupported index or changed library root')
            if not marker.exists() or marker.read_text() != state['instance']:
                raise ValueError('Library root marker missing or mismatched; check mounts')
            self.state = state
        if not self.preview:
            self.recover()

    def close(self):
        if self.lock:
            self.lock.close()
            self.lock = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def recover(self):
        pending = self._json('journal.json')
        if not pending:
            return
        path = self.path(pending['path'])
        current = digest(path.read_bytes()) if path.exists() else None
        if current == pending['new_hash']:
            self.state = pending['state']
            self._save('index.json', self.state)
        elif current != pending['old_hash']:
            raise ValueError('Interrupted write conflicts with external edits: ' + pending['path'])
        self._save('journal.json', None)

    def assign(self, key, suggested):
        if key in self.state['paths']:
            return self.state['paths'][key]
        # Conservatively reserve names independent of filesystem case sensitivity.
        import unicodedata
        norm = lambda x: unicodedata.normalize('NFC', x).casefold()
        occupied = {norm(v) for v in self.state['paths'].values()}
        candidate = suggested
        if norm(candidate) in occupied:
            candidate += ' [' + digest(key.encode())[:10] + ']'
        self.path(candidate)
        self.state['paths'][key] = candidate
        return candidate

    def write(self, key, relative, content, owner, adopt=False):
        if not self.preview:
            self.recover()
        data = content.encode('utf-8')
        record = self.state['files'].get(key)
        if record:
            relative = record['path']
        path = self.path(relative)
        current = path.read_bytes() if path.exists() else None
        old_hash = digest(current) if current is not None else None
        if record and old_hash not in (None, record['hash']):
            return 'conflict'
        if not record and current is not None and not adopt:
            return 'unmanaged'
        if not record and any(r['path'].casefold() == relative.casefold() for r in self.state['files'].values()):
            return 'conflict'
        new_hash = digest(data)
        result = 'unchanged' if current == data else ('created' if current is None else 'updated')
        if self.preview:
            return 'adopted' if adopt and not record and current == data else result
        after = copy.deepcopy(self.state)
        after['files'][key] = {'path': relative, 'hash': new_hash, 'owner': owner}
        if after != self.state or result != 'unchanged':
            self._save('journal.json', {'path': relative, 'old_hash': old_hash, 'new_hash': new_hash, 'state': after})
            if current != data:
                path.parent.mkdir(parents=True, exist_ok=True)
                self.path(relative)
                atomic_write(path, data)
            self._save('index.json', after)
            self.state = after
            self._save('journal.json', None)
        return result

    def checkpoint(self, cursor):
        if not self.preview:
            self.recover()
            self.state['cursor'] = cursor
            if self._json('index.json') != self.state:
                self._save('index.json', self.state)

    def retire(self, owners):
        counts = {'retired': 0, 'conflict': 0}
        for key, record in list(self.state['files'].items()):
            if owners is not None and record['owner'] not in owners:
                continue
            path = self.path(record['path'])
            if not path.exists():
                continue
            data = path.read_bytes()
            if digest(data) != record['hash']:
                counts['conflict'] += 1
                continue
            if not self.preview:
                # Retain index ownership for restoration and interruption recovery.
                recovery = self.state_dir / 'recovery' / record['path']
                self._no_links(recovery)
                recovery.parent.mkdir(parents=True, exist_ok=True)
                atomic_write(recovery, data)
                self.path(record['path'])
                if digest(path.read_bytes()) != record['hash']:
                    raise ValueError('File changed during retirement')
                path.unlink()
                parent = path.parent
                while parent != self.root:
                    try:
                        parent.rmdir()
                    except OSError:
                        break
                    parent = parent.parent
            counts['retired'] += 1
        return counts

    def restore(self, owners):
        counts = {'restored': 0, 'conflict': 0}
        for key, record in list(self.state['files'].items()):
            if owners is not None and record['owner'] not in owners:
                continue
            recovery = self.state_dir / 'recovery' / record['path']
            self.path(record['path'])
            self._no_links(recovery)
            if not recovery.is_file():
                continue
            data = recovery.read_bytes()
            target = self.path(record['path'])
            if digest(data) != record['hash'] or (target.exists() and target.read_bytes() != data):
                counts['conflict'] += 1
                continue
            if not target.exists():
                if not self.preview:
                    self.write(key, record['path'], data.decode('utf-8'), record['owner'])
                counts['restored'] += 1
        return counts
