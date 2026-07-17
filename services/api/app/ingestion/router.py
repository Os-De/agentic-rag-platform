import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require_role
from app.core.audit import audit
from app.core.config import get_settings
from app.db.models import DocumentRecord, User
from app.db.session import get_db
from app.ingestion.loaders import EmptyDocument, UnsupportedFileType
from app.ingestion.schemas import DocumentOut
from app.ingestion.service import ingest_bytes

log = structlog.get_logger()
router = APIRouter(tags=["ingestion"])


@router.post("/ingest", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def ingest(
    response: Response,
    file: UploadFile = File(...),
    user: User = Depends(require_role("engineer")),  # RBAC: writers only (architecture §6)
    db: Session = Depends(get_db),
) -> DocumentRecord:
    """Upload a document (.txt/.md/.pdf/.docx/.html) into the knowledge base.

    Identical content is deduplicated: you get the existing record with HTTP 200
    instead of 201, and nothing is re-embedded.
    """
    data = await file.read()
    if len(data) > get_settings().max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")
    try:
        record, created = ingest_bytes(
            file.filename or "unnamed", data, uploaded_by=user.email, db=db
        )
    except UnsupportedFileType as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc
    except EmptyDocument as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    if not created:
        response.status_code = status.HTTP_200_OK
    audit(
        db,
        actor=user.email,
        action="document.ingest",
        resource=record.filename,
        detail=f"chunks={record.num_chunks} created={created}",
    )
    return record


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(
    user: User = Depends(require_role("viewer")),
    db: Session = Depends(get_db),
) -> list[DocumentRecord]:
    """The ingestion registry — what's in the knowledge base."""
    return list(
        db.scalars(select(DocumentRecord).order_by(DocumentRecord.created_at.desc())).all()
    )
