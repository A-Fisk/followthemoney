from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..database import get_db
from .. import schemas
from ..csv_utils import csv_response

router = APIRouter(prefix="/parties", tags=["parties"])


@router.get("", response_model=list[schemas.PartyListItem])
def list_parties(
    q: str | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    format: str | None = None,
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text("""
            SELECT p.id, p.name, p.abbreviation,
                   COALESCE(SUM(d.amount), 0) AS total_donations
            FROM parties p
            LEFT JOIN donations d ON d.recipient_party_id = p.id
            WHERE (:q IS NULL OR p.name ILIKE '%' || :q || '%'
                               OR p.abbreviation ILIKE '%' || :q || '%')
            GROUP BY p.id, p.name, p.abbreviation
            HAVING COALESCE(SUM(d.amount), 0) > 0 OR :q IS NOT NULL
            ORDER BY total_donations DESC
            LIMIT :limit OFFSET :offset
        """),
        {"q": q, "limit": limit, "offset": offset},
    ).mappings().all()

    if format == "csv":
        return csv_response([dict(r) for r in rows], filename="parties")

    return [
        schemas.PartyListItem(
            id=r["id"], name=r["name"], abbreviation=r["abbreviation"],
            total_donations=float(r["total_donations"]),
        )
        for r in rows
    ]


@router.get("/{id}", response_model=schemas.PartyDetail)
def get_party(id: int, format: str | None = None, db: Session = Depends(get_db)):
    party = db.execute(
        text("SELECT id, name, abbreviation FROM parties WHERE id = :id"),
        {"id": id},
    ).mappings().first()

    if not party:
        raise HTTPException(status_code=404, detail="Party not found")

    # Total donations
    total = db.execute(
        text("SELECT COALESCE(SUM(amount), 0) AS total FROM donations WHERE recipient_party_id = :id"),
        {"id": id},
    ).mappings().first()

    # Top donors
    top_donors = db.execute(
        text("""
            SELECT dn.id, dn.name, dn.industry_label, dn.needs_review,
                   SUM(d.amount) AS total
            FROM donations d
            JOIN donors dn ON dn.id = d.donor_id
            WHERE d.recipient_party_id = :id
            GROUP BY dn.id, dn.name, dn.industry_label, dn.needs_review
            ORDER BY total DESC
            LIMIT 20
        """),
        {"id": id},
    ).mappings().all()

    # Industry breakdown
    industry = db.execute(
        text("""
            SELECT COALESCE(dn.industry_label, 'Unknown') AS industry_label,
                   SUM(d.amount) AS total
            FROM donations d
            JOIN donors dn ON dn.id = d.donor_id
            WHERE d.recipient_party_id = :id
            GROUP BY dn.industry_label
            ORDER BY total DESC
        """),
        {"id": id},
    ).mappings().all()

    # Donations by year
    by_year = db.execute(
        text("""
            SELECT financial_year, SUM(amount) AS total
            FROM donations
            WHERE recipient_party_id = :id
            GROUP BY financial_year
            ORDER BY financial_year DESC
        """),
        {"id": id},
    ).mappings().all()

    # Expenditure
    expenditure = db.execute(
        text("""
            SELECT financial_year, category, SUM(amount) AS amount
            FROM expenditure
            WHERE party_id = :id
            GROUP BY financial_year, category
            ORDER BY financial_year DESC, amount DESC
        """),
        {"id": id},
    ).mappings().all()

    # Financial summary (Total Receipts / Payments / Debts from Party Returns)
    financials = db.execute(
        text("""
            SELECT financial_year, total_receipts, total_payments,
                   total_debts, total_discretionary_benefits
            FROM party_financials
            WHERE party_id = :id
            ORDER BY financial_year DESC
        """),
        {"id": id},
    ).mappings().all()

    if format == "csv":
        rows = [
            {"financial_year": r["financial_year"], "total": float(r["total"])}
            for r in by_year
        ]
        return csv_response(rows, filename=f"party_{id}_donations_by_year")

    def _opt_float(val) -> float | None:
        return float(val) if val is not None else None

    return schemas.PartyDetail(
        id=party["id"],
        name=party["name"],
        abbreviation=party["abbreviation"],
        total_donations=float(total["total"]),
        top_donors=[
            schemas.TopDonorRow(
                donor=schemas.DonorMin(id=r["id"], name=r["name"],
                                       industry_label=r["industry_label"],
                                       needs_review=r["needs_review"]),
                total=float(r["total"]),
            )
            for r in top_donors
        ],
        industry_breakdown=[
            schemas.IndustryRow(industry_label=r["industry_label"], total=float(r["total"]))
            for r in industry
        ],
        donations_by_year=[
            schemas.YearRow(financial_year=r["financial_year"], total=float(r["total"]))
            for r in by_year
        ],
        expenditure=[
            schemas.ExpenditureRow(financial_year=r["financial_year"],
                                   category=r["category"], amount=float(r["amount"]))
            for r in expenditure
        ],
        financials=[
            schemas.PartyFinancialsRow(
                financial_year=r["financial_year"],
                total_receipts=_opt_float(r["total_receipts"]),
                total_payments=_opt_float(r["total_payments"]),
                total_debts=_opt_float(r["total_debts"]),
                total_discretionary_benefits=_opt_float(r["total_discretionary_benefits"]),
            )
            for r in financials
        ],
    )
