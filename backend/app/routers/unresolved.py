from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..database import get_db
from .. import schemas
from ..csv_utils import csv_response

router = APIRouter(prefix="/unresolved", tags=["unresolved"])

_SQL = """
    SELECT
        dn.id,
        dn.name,
        dn.entity_type,
        dn.notes,
        COALESCE(SUM(d.amount), 0) AS total_donated
    FROM donors dn
    LEFT JOIN donations d ON d.donor_id = dn.id
    WHERE dn.needs_review = TRUE
    GROUP BY dn.id, dn.name, dn.entity_type, dn.notes
    ORDER BY total_donated DESC NULLS LAST
    LIMIT :limit OFFSET :offset
"""


@router.get("", response_model=list[schemas.UnresolvedDonor])
def list_unresolved(
    limit: int = Query(100, le=500),
    offset: int = 0,
    format: str | None = None,
    db: Session = Depends(get_db),
):
    rows = db.execute(text(_SQL), {"limit": limit, "offset": offset}).mappings().all()

    if format == "csv":
        return csv_response(
            [dict(r) for r in rows],
            filename="unresolved_donors",
        )

    return [
        schemas.UnresolvedDonor(
            id=r["id"],
            name=r["name"],
            entity_type=r["entity_type"],
            total_donated=float(r["total_donated"]),
            notes=r["notes"],
        )
        for r in rows
    ]
