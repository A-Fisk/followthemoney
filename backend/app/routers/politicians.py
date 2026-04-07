from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..database import get_db
from .. import schemas
from ..csv_utils import csv_response

router = APIRouter(prefix="/politicians", tags=["politicians"])


@router.get("", response_model=list[schemas.PoliticianListItem])
def list_politicians(
    q: str | None = None,
    chamber: str | None = None,
    party_id: int | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    format: str | None = None,
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text("""
            SELECT p.id, p.name, p.chamber, p.electorate, p.active,
                   pt.id AS party_id, pt.name AS party_name, pt.abbreviation
            FROM politicians p
            LEFT JOIN parties pt ON pt.id = p.party_id
            WHERE (:q IS NULL OR p.name ILIKE '%' || :q || '%')
              AND (:chamber IS NULL OR p.chamber = :chamber)
              AND (:party_id IS NULL OR p.party_id = :party_id)
            ORDER BY p.name
            LIMIT :limit OFFSET :offset
        """),
        {"q": q, "chamber": chamber, "party_id": party_id,
         "limit": limit, "offset": offset},
    ).mappings().all()

    if format == "csv":
        return csv_response(
            [{"id": r["id"], "name": r["name"], "chamber": r["chamber"],
              "electorate": r["electorate"], "party": r["party_name"]} for r in rows],
            filename="politicians",
        )

    result = []
    for r in rows:
        party = schemas.PartyMin(id=r["party_id"], name=r["party_name"],
                                  abbreviation=r["abbreviation"]) if r["party_id"] else None
        result.append(schemas.PoliticianListItem(
            id=r["id"], name=r["name"], chamber=r["chamber"],
            electorate=r["electorate"], active=r["active"], party=party,
        ))
    return result


@router.get("/{id}", response_model=schemas.PoliticianDetail)
def get_politician(id: int, format: str | None = None, db: Session = Depends(get_db)):
    # Base info
    pol = db.execute(
        text("""
            SELECT p.id, p.name, p.chamber, p.electorate, p.active,
                   pt.id AS party_id, pt.name AS party_name, pt.abbreviation
            FROM politicians p
            LEFT JOIN parties pt ON pt.id = p.party_id
            WHERE p.id = :id
        """),
        {"id": id},
    ).mappings().first()

    if not pol:
        raise HTTPException(status_code=404, detail="Politician not found")

    # Direct donations received
    donations_rows = db.execute(
        text("""
            SELECT d.id, d.amount, d.financial_year, d.donation_type, d.source_url,
                   dn.id AS donor_id, dn.name AS donor_name,
                   dn.industry_label, dn.needs_review
            FROM donations d
            JOIN donors dn ON dn.id = d.donor_id
            WHERE d.recipient_politician_id = :id
            ORDER BY d.financial_year DESC, d.amount DESC
        """),
        {"id": id},
    ).mappings().all()

    # Interests (gifts/travel) — days_late is a stored generated column
    interests_rows = db.execute(
        text("""
            SELECT i.id, i.description, i.value_approx, i.date_received,
                   i.date_declared, i.days_late, i.source_url,
                   dn.id AS donor_id, dn.name AS donor_name,
                   dn.industry_label, dn.needs_review
            FROM interests i
            LEFT JOIN donors dn ON dn.id = i.donor_id
            WHERE i.politician_id = :id
            ORDER BY i.date_declared DESC NULLS LAST
        """),
        {"id": id},
    ).mappings().all()

    # Votes
    votes_rows = db.execute(
        text("""
            SELECT v.id, v.vote_direction, v.vote_date,
                   b.id AS bill_id, b.title, b.issue_tags, b.theyvoteforyou_id,
                   b.tvfy_house, b.tvfy_number
            FROM votes v
            JOIN bills b ON b.id = v.bill_id
            WHERE v.politician_id = :id
            ORDER BY v.vote_date DESC NULLS LAST
        """),
        {"id": id},
    ).mappings().all()

    if format == "csv":
        rows = [
            {
                "financial_year": r["financial_year"],
                "amount": float(r["amount"]),
                "donor": r["donor_name"],
                "industry": r["industry_label"] or "",
                "donation_type": r["donation_type"] or "",
                "source_url": r["source_url"] or "",
            }
            for r in donations_rows
        ]
        return csv_response(rows, filename=f"politician_{id}_donations")

    party = schemas.PartyMin(id=pol["party_id"], name=pol["party_name"],
                              abbreviation=pol["abbreviation"]) if pol["party_id"] else None

    donations = [
        schemas.DonationRow(
            id=r["id"], amount=float(r["amount"]), financial_year=r["financial_year"],
            donation_type=r["donation_type"], source_url=r["source_url"],
            donor=schemas.DonorMin(id=r["donor_id"], name=r["donor_name"],
                                   industry_label=r["industry_label"],
                                   needs_review=r["needs_review"]),
        )
        for r in donations_rows
    ]

    interests = [
        schemas.InterestRow(
            id=r["id"], description=r["description"], value_approx=r["value_approx"],
            date_received=r["date_received"], date_declared=r["date_declared"],
            days_late=r["days_late"], source_url=r["source_url"],
            donor=schemas.DonorMin(id=r["donor_id"], name=r["donor_name"],
                                   industry_label=r["industry_label"],
                                   needs_review=r["needs_review"]) if r["donor_id"] else None,
        )
        for r in interests_rows
    ]

    votes = [
        schemas.VoteRow(
            id=r["id"], vote_direction=r["vote_direction"], vote_date=r["vote_date"],
            bill_id=r["bill_id"], bill_title=r["title"],
            issue_tags=r["issue_tags"], theyvoteforyou_id=r["theyvoteforyou_id"],
            tvfy_house=r["tvfy_house"], tvfy_number=r["tvfy_number"],
        )
        for r in votes_rows
    ]

    return schemas.PoliticianDetail(
        id=pol["id"], name=pol["name"], chamber=pol["chamber"],
        electorate=pol["electorate"], active=pol["active"],
        party=party, direct_donations=donations, interests=interests, votes=votes,
    )
