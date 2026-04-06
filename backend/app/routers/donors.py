from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..database import get_db
from .. import schemas
from ..csv_utils import csv_response

router = APIRouter(prefix="/donors", tags=["donors"])


@router.get("", response_model=list[schemas.DonorListItem])
def list_donors(
    q: str | None = None,
    industry: str | None = None,
    needs_review: bool | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    format: str | None = None,
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text("""
            SELECT id, name, abn, entity_type, anzsic_code, industry_label, needs_review
            FROM donors
            WHERE (:q IS NULL OR name ILIKE '%' || :q || '%')
              AND (:industry IS NULL OR industry_label ILIKE '%' || :industry || '%')
              AND (:needs_review IS NULL OR needs_review = :needs_review)
            ORDER BY name
            LIMIT :limit OFFSET :offset
        """),
        {"q": q, "industry": industry, "needs_review": needs_review,
         "limit": limit, "offset": offset},
    ).mappings().all()

    if format == "csv":
        return csv_response([dict(r) for r in rows], filename="donors")

    return [schemas.DonorListItem(**dict(r)) for r in rows]


@router.get("/{id}", response_model=schemas.DonorDetail)
def get_donor(id: int, format: str | None = None, db: Session = Depends(get_db)):
    # Base info
    donor = db.execute(
        text("""
            SELECT id, name, abn, entity_type, anzsic_code, industry_label,
                   controlling_person, notes, needs_review
            FROM donors WHERE id = :id
        """),
        {"id": id},
    ).mappings().first()

    if not donor:
        raise HTTPException(status_code=404, detail="Donor not found")

    # Total donated
    total_row = db.execute(
        text("SELECT COALESCE(SUM(amount), 0) AS total FROM donations WHERE donor_id = :id"),
        {"id": id},
    ).mappings().first()

    # Donations by party (aggregated)
    by_party = db.execute(
        text("""
            SELECT pt.id AS party_id, pt.name AS party_name, pt.abbreviation,
                   SUM(d.amount) AS total
            FROM donations d
            JOIN parties pt ON pt.id = d.recipient_party_id
            WHERE d.donor_id = :id
            GROUP BY pt.id, pt.name, pt.abbreviation
            ORDER BY total DESC
        """),
        {"id": id},
    ).mappings().all()

    # Individual donations
    donations = db.execute(
        text("""
            SELECT d.id, d.amount, d.financial_year, d.donation_type, d.source_url,
                   pt.id AS party_id, pt.name AS party_name, pt.abbreviation,
                   pol.id AS politician_id, pol.name AS politician_name
            FROM donations d
            LEFT JOIN parties pt ON pt.id = d.recipient_party_id
            LEFT JOIN politicians pol ON pol.id = d.recipient_politician_id
            WHERE d.donor_id = :id
            ORDER BY d.financial_year DESC, d.amount DESC
        """),
        {"id": id},
    ).mappings().all()

    if format == "csv":
        rows = [
            {
                "financial_year": r["financial_year"],
                "amount": r["amount"],
                "recipient_party": r["party_name"] or "",
                "recipient_politician": r["politician_name"] or "",
                "donation_type": r["donation_type"] or "",
                "source_url": r["source_url"] or "",
            }
            for r in donations
        ]
        return csv_response(rows, filename=f"donor_{id}_donations")

    donations_out = []
    for r in donations:
        party = schemas.PartyMin(id=r["party_id"], name=r["party_name"], abbreviation=r["abbreviation"]) if r["party_id"] else None
        donations_out.append(schemas.DonationByPartyRow(
            id=r["id"], amount=float(r["amount"]), financial_year=r["financial_year"],
            donation_type=r["donation_type"], source_url=r["source_url"],
            party=party, politician_id=r["politician_id"], politician_name=r["politician_name"],
        ))

    donations_by_party = [
        schemas.PartyTotalRow(
            party=schemas.PartyMin(id=r["party_id"], name=r["party_name"], abbreviation=r["abbreviation"]),
            total=float(r["total"]),
        )
        for r in by_party
    ]

    return schemas.DonorDetail(
        id=donor["id"],
        name=donor["name"],
        abn=donor["abn"],
        entity_type=donor["entity_type"],
        anzsic_code=donor["anzsic_code"],
        industry_label=donor["industry_label"],
        controlling_person=donor["controlling_person"],
        notes=donor["notes"],
        needs_review=donor["needs_review"],
        total_donated=float(total_row["total"]),
        donations_by_party=donations_by_party,
        donations=donations_out,
    )
