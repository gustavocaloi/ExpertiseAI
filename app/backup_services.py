"""Versioned JSON archive: trusted-schema SQLite rows and complete persistent file stores.

Call export/restore under the exclusive storage admission lock.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from uuid import uuid4

from . import config, db, services, monitoria_services, kb_routes

FORMAT = 'expertise-ai-platform-backup'
VERSION = 1
CHUNK_SIZE = 1024 * 1024


class InvalidBackup(ValueError):
    pass


class _LimitedWriter:
    """Bound temporary disk use while streaming UTF-8 JSON."""
    def __init__(self, handle):
        self.handle = handle
        self.size = 0

    def write(self, value):
        self.size += len(value.encode('utf-8'))
        if self.size > config.BACKUP_MAX_BYTES:
            raise InvalidBackup('Backup excede o limite configurado em EXPAI_BACKUP_MAX_MB.')
        return self.handle.write(value)


def stores():
    roots = {'kb': Path(services.KB_ROOT).absolute(),
             'monitoria': Path(monitoria_services.MONITORIA_ROOT).absolute(),
             'upload_jobs': Path(kb_routes._UPLOAD_JOBS_DIR).absolute()}
    if any(path.is_symlink() for path in roots.values()):
        raise InvalidBackup('Diretórios de armazenamento não podem ser links simbólicos.')
    roots = {key: path.resolve() for key, path in roots.items()}
    paths = list(roots.values())
    database = Path(db.DB_PATH).resolve()
    for i, path in enumerate(paths):
        if database.is_relative_to(path):
            raise InvalidBackup('Diretórios de armazenamento devem ser independentes, sem links simbólicos.')
        if any(path == other or path.is_relative_to(other) or other.is_relative_to(path) for other in paths[i+1:]):
            raise InvalidBackup('Diretórios de armazenamento não podem se sobrepor.')
    return roots


def _quote(name):
    return '"' + name.replace('"', '""') + '"'


def _tables(conn):
    return sorted(row[1] for row in conn.execute('PRAGMA table_list')
                  if row[0] == 'main' and row[2] in {'table', 'virtual'}
                  and (not row[1].startswith('sqlite_') or row[1] == 'sqlite_sequence'))


def _columns(conn, table):
    return [row[1] for row in conn.execute(f'PRAGMA table_info({_quote(table)})')]


def _schema(conn):
    rows = list(conn.execute("SELECT type, name, tbl_name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"))
    return hashlib.sha256(json.dumps([list(row) for row in rows], ensure_ascii=False).encode()).hexdigest()


def _snapshot(target):
    source = db.get_connection()
    dest = sqlite3.connect(target)
    try:
        source.backup(dest)
    finally:
        source.close()
        dest.close()


def _encode_cell(value):
    return {'base64': base64.b64encode(value).decode('ascii')} if isinstance(value, bytes) else value


def _decode_cell(value):
    if isinstance(value, dict) and set(value) == {'base64'}:
        return base64.b64decode(value['base64'], validate=True)
    if value is None or type(value) in (str, int, float):
        return value
    raise InvalidBackup('Valor inválido em uma tabela do backup.')


def _safe_path(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise InvalidBackup('Caminho de arquivo inválido.')
    path = PurePosixPath(value)
    if path.is_absolute() or PureWindowsPath(value).drive or any(p in {'', '.', '..'} for p in value.split('/')):
        raise InvalidBackup('Caminho de arquivo inválido.')
    return path


def export_backup(output: Path):
    roots = stores()
    for path in roots['upload_jobs'].glob('*.json'):
        if json.loads(path.read_text()).get('status') == 'processing':
            raise InvalidBackup('Aguarde o término dos uploads antes de gerar o backup.')
    with tempfile.TemporaryDirectory(prefix='expai-snapshot-') as work:
        snapshot = Path(work) / 'snapshot.sqlite3'
        _snapshot(snapshot)
        conn = sqlite3.connect(snapshot)
        try:
            # Active imports cannot be resumed from temporary input files. Export only quiescent state.
            if conn.execute("SELECT 1 FROM monitoria_jobs WHERE status='processing' LIMIT 1").fetchone():
                raise InvalidBackup('Aguarde o término dos processamentos antes de gerar o backup.')
            header = {'format': FORMAT, 'version': VERSION, 'created_at': datetime.now(timezone.utc).isoformat(),
                      'schema_sha256': _schema(conn), 'source_roots': {k: str(v) for k, v in roots.items()}}
            with output.open('w', encoding='utf-8') as handle:
                out = _LimitedWriter(handle)
                out.write(json.dumps(header, ensure_ascii=False)[:-1] + ',"tables":{')
                for ti, table in enumerate(_tables(conn)):
                    if ti:
                        out.write(',')
                    columns = _columns(conn, table)
                    out.write(json.dumps(table) + ':' + json.dumps({'columns': columns})[:-1] + ',"rows":[')
                    for ri, row in enumerate(conn.execute(f'SELECT * FROM {_quote(table)}')):
                        if ri:
                            out.write(',')
                        values = list(row)
                        if table == 'monitoria_conversations':
                            audio_column = columns.index('audio_path')
                            if values[audio_column]:
                                values[audio_column] = str(Path(values[audio_column]).resolve())
                        out.write(json.dumps([_encode_cell(v) for v in values], ensure_ascii=False, allow_nan=False))
                    out.write(']}')
                out.write('},"files":[')
                count = 0
                for store, root in roots.items():
                    if not root.exists():
                        continue
                    for directory, dirs, names in os.walk(root, followlinks=False):
                        if any((Path(directory) / d).is_symlink() for d in dirs):
                            raise InvalidBackup('Armazenamento contém link simbólico; backup interrompido.')
                        for name in sorted(names):
                            path = Path(directory) / name
                            if path.is_symlink() or not path.is_file():
                                raise InvalidBackup('Armazenamento contém arquivo especial; backup interrompido.')
                            relative = path.relative_to(root)
                            internal_lock = (store == 'kb' and len(relative.parts) == 2
                                             and path.name == Path(services.DOCUMENTS_INDEX_FILENAME).with_suffix('.lock').name)
                            if internal_lock or (store == 'kb' and relative.parts[0] == '_tmp_uploads'):
                                continue
                            if count:
                                out.write(',')
                            entry = {'store': store, 'path': path.relative_to(root).as_posix(), 'size': path.stat().st_size}
                            out.write(json.dumps(entry, ensure_ascii=False)[:-1] + ',"chunks":[')
                            digest = hashlib.sha256()
                            with path.open('rb') as source:
                                ci = 0
                                while chunk := source.read(CHUNK_SIZE):
                                    if ci:
                                        out.write(',')
                                    out.write(json.dumps(base64.b64encode(chunk).decode('ascii')))
                                    digest.update(chunk)
                                    ci += 1
                            out.write('],"sha256":' + json.dumps(digest.hexdigest()) + '}')
                            count += 1
                out.write(']}')
            if output.stat().st_size > config.BACKUP_MAX_BYTES:
                raise InvalidBackup('Backup excede o limite configurado em EXPAI_BACKUP_MAX_MB.')
        finally:
            conn.close()


def _load_json(path):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise InvalidBackup('JSON contém chaves duplicadas.')
            obj[key] = value
        return obj
    if path.stat().st_size > config.BACKUP_MAX_BYTES:
        raise InvalidBackup('Arquivo excede o limite de backup configurado.')
    try:
        with path.open(encoding='utf-8') as source:
            return json.load(source, object_pairs_hook=unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(InvalidBackup('Número JSON inválido.')))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise InvalidBackup('Arquivo JSON inválido ou corrompido.') from exc


def _stage_database(payload, staged_db, staged_roots, roots):
    _snapshot(staged_db)  # Only installed, trusted DDL is used. Never execute SQL from the archive.
    conn = sqlite3.connect(staged_db)
    try:
        if payload.get('schema_sha256') != _schema(conn):
            raise InvalidBackup('Backup incompatível com o esquema desta versão da plataforma.')
        tables = payload['tables']
        if not isinstance(tables, dict) or set(tables) != set(_tables(conn)):
            raise InvalidBackup('Backup não contém todas as tabelas esperadas.')
        for table in tables:
            conn.execute(f'DELETE FROM {_quote(table)}')
        # sqlite_sequence must be inserted last to preserve deleted IDs and future AUTOINCREMENT values.
        for table in sorted(tables, key=lambda t: (t == 'sqlite_sequence', t)):
            columns = _columns(conn, table)
            data = tables[table]
            if data['columns'] != columns or not isinstance(data['rows'], list):
                raise InvalidBackup('Colunas ou registros incompatíveis no backup.')
            if table == 'sqlite_sequence':
                conn.execute('DELETE FROM sqlite_sequence')
            for row in data['rows']:
                if not isinstance(row, list) or len(row) != len(columns):
                    raise InvalidBackup('Registro de tabela inválido.')
                values = [_decode_cell(v) for v in row]
                if table == 'monitoria_conversations':
                    index = columns.index('audio_path')
                    if values[index]:
                        origin = Path(payload['source_roots']['monitoria'])
                        relative = Path(values[index]).relative_to(origin)
                        _safe_path(relative.as_posix())
                        if not (staged_roots['monitoria'] / relative).is_file():
                            raise InvalidBackup('Backup não contém um áudio referenciado pela Monitoria.')
                        values[index] = str(roots['monitoria'] / relative)
                conn.execute(f'INSERT INTO {_quote(table)} ({",".join(_quote(c) for c in columns)}) VALUES ({",".join("?" for _ in columns)})', values)
        if conn.execute('PRAGMA foreign_key_check').fetchone():
            raise InvalidBackup('Backup contém relacionamentos inválidos.')
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise InvalidBackup('Backup falhou na validação de integridade.')
        if not conn.execute("SELECT 1 FROM users u WHERE NOT EXISTS (SELECT 1 FROM companies c WHERE NOT EXISTS (SELECT 1 FROM user_company_roles r WHERE r.user_id=u.id AND r.company_id=c.id AND r.role='admin' AND r.is_active=1)) AND EXISTS (SELECT 1 FROM companies)").fetchone():
            raise InvalidBackup('Backup precisa conter um administrador de todas as empresas.')
        conn.commit()
    finally:
        conn.close()


def _apply_database(source):
    src = sqlite3.connect(source)
    dest = db.get_connection()
    try:
        src.backup(dest)
    finally:
        src.close()
        dest.close()


def _journal_path():
    return Path(config.DATA_DIR) / '.restore-journal.json'


def recover_restore():
    """Roll back an interrupted commit before initializing the database or serving requests."""
    journal = _journal_path()
    if not journal.exists():
        return
    record = json.loads(journal.read_text())
    if Path(record['database_target']) != Path(db.DB_PATH).absolute():
        raise RuntimeError('Recuperação pendente exige o mesmo EXPAI_DB_PATH da restauração interrompida.')
    for entry in reversed(record['stores']):
        target, previous = Path(entry['target']), Path(entry['previous'])
        if previous.exists():
            if target.exists():
                shutil.rmtree(target)
            previous.rename(target)
        elif not entry['existed'] and target.exists():
            shutil.rmtree(target)
    _apply_database(Path(record['database']))
    journal.unlink()
    for entry in record['stores']:
        shutil.rmtree(entry['staged'], ignore_errors=True)
    shutil.rmtree(record['work'], ignore_errors=True)


def restore_backup(source: Path):
    roots = stores()
    payload = _load_json(source)
    if not isinstance(payload, dict) or payload.get('format') != FORMAT or type(payload.get('version')) is not int or payload['version'] != VERSION:
        raise InvalidBackup('Formato ou versão do backup não suportado.')
    work = Path(tempfile.mkdtemp(prefix='.restore-', dir=config.DATA_DIR))
    staged_roots = {}
    swapped = False
    try:
        for key, target in roots.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            staged_roots[key] = Path(tempfile.mkdtemp(prefix=f'.{target.name}-restore-', dir=target.parent))
        seen = set()
        if not isinstance(payload.get('files'), list) or set(payload.get('source_roots', {})) != set(roots):
            raise InvalidBackup('Manifesto de arquivos incompleto.')
        for item in payload['files']:
            store = item['store']
            if store not in roots:
                raise InvalidBackup('Armazenamento desconhecido.')
            relative = _safe_path(item['path'])
            identity = (store, relative.as_posix())
            if identity in seen:
                raise InvalidBackup('Arquivo duplicado no backup.')
            seen.add(identity)
            target = staged_roots[store] / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            digest, size = hashlib.sha256(), 0
            if not isinstance(item['chunks'], list) or type(item['size']) is not int or item['size'] < 0:
                raise InvalidBackup('Conteúdo de arquivo inválido.')
            with target.open('xb') as out:
                for chunk in item['chunks']:
                    if not isinstance(chunk, str) or len(chunk) > (CHUNK_SIZE + 2) // 3 * 4:
                        raise InvalidBackup('Bloco de arquivo inválido.')
                    raw = base64.b64decode(chunk, validate=True)
                    out.write(raw)
                    size += len(raw)
                    digest.update(raw)
            if size != item['size'] or digest.hexdigest() != item['sha256']:
                raise InvalidBackup('Arquivo do backup corrompido: tamanho ou SHA-256 divergente.')
        staged_db = work / 'restored.sqlite3'
        _stage_database(payload, staged_db, staged_roots, roots)
        previous_db = work / 'previous.sqlite3'
        _snapshot(previous_db)
        entries = [{'target': str(target), 'previous': str(target.with_name(f'.{target.name}-previous-{uuid4().hex}')),
                    'staged': str(staged_roots[key]), 'existed': target.exists()} for key, target in roots.items()]
        record = {'database': str(previous_db), 'database_target': str(Path(db.DB_PATH).absolute()),
                  'work': str(work), 'stores': entries}
        journal = _journal_path()
        journal_tmp = work / 'journal.json'
        with journal_tmp.open('x') as handle:
            json.dump(record, handle)
            handle.flush()
            os.fsync(handle.fileno())
        journal_tmp.replace(journal)
        swapped = True
        try:
            for entry in entries:
                target = Path(entry['target'])
                if entry['existed']:
                    target.rename(entry['previous'])
                Path(entry['staged']).rename(target)
            _apply_database(staged_db)
            epoch = Path(config.DATA_DIR) / '.session-epoch'
            epoch_tmp = work / 'epoch'
            epoch_tmp.write_text(uuid4().hex)
            epoch_tmp.replace(epoch)
            services.clear_storage_caches()
            kb_routes._UPLOAD_JOBS.clear()
            journal.unlink()  # Commit point; a leftover journal always means rollback on restart.
        except BaseException:
            recover_restore()
            raise
        for entry in entries:
            shutil.rmtree(entry['previous'], ignore_errors=True)
        return {'status': 'restored', 'files': len(seen), 'login_required': True}
    except (KeyError, TypeError, ValueError, sqlite3.Error, FileExistsError, NotADirectoryError) as exc:
        if isinstance(exc, InvalidBackup):
            raise
        raise InvalidBackup('Estrutura ou conteúdo do backup inválido.') from exc
    finally:
        for path in staged_roots.values():
            shutil.rmtree(path, ignore_errors=True)
        if not swapped or not _journal_path().exists():
            shutil.rmtree(work, ignore_errors=True)
