from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..database import get_db
from .. import schemas

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=schemas.SearchResponse)
def search(
    q: str = Query(..., min_length=2),
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db),
):
    politicians = db.execute(
        text("""
            SELECT p.id, p.name, pt.abbreviation AS secondary
            FROM politicians p
            LEFT JOIN parties pt ON pt.id = p.party_id
            WHERE p.name ILIKE '%' || :q || '%'
            ORDER BY p.name
            LIMIT :limit
        """),
        {"q": q, "limit": limit},
    ).mappings().all()

    parties = db.execute(
        text("""
            SELECT id, name, abbreviation AS secondary
            FROM parties
            WHERE name ILIKE '%' || :q || '%' OR abbreviation ILIKE '%' || :q || '%'
            ORDER BY name
            LIMIT :limit
        """),
        {"q": q, "limit": limit},
    ).mappings().all()

    donors = db.execute(
        text("""
            SELECT id, name, industry_label AS secondary
            FROM donors
            WHERE name ILIKE '%' || :q || '%'
            ORDER BY name
            LIMIT :limit
        """),
        {"q": q, "limit": limit},
    ).mappings().all()

    # Suppress party/donor alias entries when a matching politician is returned.
    # e.g. "ALP NSW Branch - Tanya Plibersek" and "The Hon Tanya Plibersek Mp"
    # should not appear alongside the politician "Tanya Plibersek".
    pol_last_names = {r["name"].rsplit(" ", 1)[-1].lower() for r in politicians}

    def _is_politician_alias(name: str) -> bool:
        n = name.lower()
        return any(last in n for last in pol_last_names)

    results: list[schemas.SearchResultItem] = []
    for r in politicians:
        results.append(schemas.SearchResultItem(
            id=r["id"], name=r["name"], type="politician", secondary=r["secondary"]))
    for r in parties:
        if not _is_politician_alias(r["name"]):
            results.append(schemas.SearchResultItem(
                id=r["id"], name=r["name"], type="party", secondary=r["secondary"]))
    for r in donors:
        if not _is_politician_alias(r["name"]):
            results.append(schemas.SearchResultItem(
                id=r["id"], name=r["name"], type="donor", secondary=r["secondary"]))

    return schemas.SearchResponse(query=q, results=results)
