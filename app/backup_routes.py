from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import logging
import tempfile
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from . import backup_services, config, db
from .maintenance import finish_thread
from .security import TokenData, decode_access_token, oauth2_scheme

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/admin/backup', tags=['backup'])


class _BackupDownloadResponse(FileResponse):
    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            Path(self.path).unlink(missing_ok=True)


def require_platform_admin(token: Optional[str] = Depends(oauth2_scheme)) -> TokenData:
    # Never inherit the development-mode auth bypass from require_role.
    if not config.ACCESS_CONTROL_ENABLED:
        raise HTTPException(403, 'Backup e restauração exigem controle de acesso habilitado.')
    if not token:
        raise HTTPException(401, 'Autenticação de administrador obrigatória.')
    user = decode_access_token(token)
    current = db.get_user_by_id(user.user_id)
    if not current or current['email'] != user.email:
        raise HTTPException(401, 'Usuário não encontrado ou removido.')
    if not db.is_platform_admin(user.user_id):
        raise HTTPException(403, 'Backup global restrito a administradores de todas as empresas cadastradas.')
    return user


@router.get('/status')
def backup_status(user: TokenData = Depends(require_platform_admin)):
    return {'format': backup_services.FORMAT, 'version': backup_services.VERSION,
            'max_bytes': config.BACKUP_MAX_BYTES, 'scope': 'platform'}


@router.post('/export')
async def export_backup(user: TokenData = Depends(require_platform_admin)):
    with tempfile.NamedTemporaryFile(prefix='expertise-backup-', suffix='.json', delete=False) as handle:
        path = Path(handle.name)
    try:
        await finish_thread(backup_services.export_backup, path)
    except backup_services.InvalidBackup as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(409, str(exc)) from exc
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    logger.info('Backup global gerado pelo usuário id=%s.', user.user_id)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return _BackupDownloadResponse(path, filename=f'expertise-ai-backup-{stamp}.json', media_type='application/json',
                                   headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


@router.post('/restore')
async def restore_backup(file: UploadFile = File(...), confirmation: str = Form(...),
                         user: TokenData = Depends(require_platform_admin)):
    if confirmation != 'RESTAURAR':
        raise HTTPException(422, 'Digite RESTAURAR para confirmar a substituição de todos os dados.')
    with tempfile.NamedTemporaryFile(prefix='expertise-restore-', suffix='.json', delete=False) as handle:
        path = Path(handle.name)
        try:
            size = 0
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > config.BACKUP_MAX_BYTES:
                    raise HTTPException(413, 'Arquivo excede o limite de backup configurado.')
                handle.write(chunk)
            handle.flush()
            result = await finish_thread(backup_services.restore_backup, path)
            logger.info('Restauração global concluída pelo usuário id=%s.', user.user_id)
            return result
        except backup_services.InvalidBackup as exc:
            raise HTTPException(422, str(exc)) from exc
        finally:
            path.unlink(missing_ok=True)
            await file.close()
