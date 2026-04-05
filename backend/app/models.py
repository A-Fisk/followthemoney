from sqlalchemy import (
    Boolean, Column, Date, ForeignKey, Integer, Numeric,
    String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship

from .database import Base


class Party(Base):
    __tablename__ = "parties"
    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False, unique=True)
    abbreviation = Column(Text)
    ideology_tags = Column(ARRAY(Text))

    politicians = relationship("Politician", back_populates="party")
    donations_received = relationship("Donation", back_populates="recipient_party")
    expenditure = relationship("Expenditure", back_populates="party")
    public_funding = relationship("PublicFunding", back_populates="party")


class Politician(Base):
    __tablename__ = "politicians"
    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False, unique=True)
    party_id = Column(Integer, ForeignKey("parties.id"))
    chamber = Column(String(10))
    electorate = Column(Text)
    active = Column(Boolean, default=True)

    party = relationship("Party", back_populates="politicians")
    donations_received = relationship("Donation", back_populates="recipient_politician")
    interests = relationship("Interest", back_populates="politician")
    votes = relationship("Vote", back_populates="politician")


class Donor(Base):
    __tablename__ = "donors"
    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False, unique=True)
    abn = Column(Text)
    entity_type = Column(Text)
    anzsic_code = Column(Text)
    industry_label = Column(Text)
    controlling_person = Column(Text)
    notes = Column(Text)
    needs_review = Column(Boolean, default=False)

    donations = relationship("Donation", back_populates="donor")
    interests = relationship("Interest", back_populates="donor")


class Donation(Base):
    __tablename__ = "donations"
    id = Column(Integer, primary_key=True)
    donor_id = Column(Integer, ForeignKey("donors.id"))
    recipient_party_id = Column(Integer, ForeignKey("parties.id"))
    recipient_politician_id = Column(Integer, ForeignKey("politicians.id"))
    amount = Column(Numeric(14, 2), nullable=False)
    financial_year = Column(Text, nullable=False)
    donation_type = Column(Text)
    source_file = Column(Text)
    source_url = Column(Text)

    donor = relationship("Donor", back_populates="donations")
    recipient_party = relationship("Party", back_populates="donations_received")
    recipient_politician = relationship("Politician", back_populates="donations_received")


class Expenditure(Base):
    __tablename__ = "expenditure"
    id = Column(Integer, primary_key=True)
    party_id = Column(Integer, ForeignKey("parties.id"))
    financial_year = Column(Text, nullable=False)
    category = Column(Text, nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    source_url = Column(Text)

    party = relationship("Party", back_populates="expenditure")


class PublicFunding(Base):
    __tablename__ = "public_funding"
    id = Column(Integer, primary_key=True)
    party_id = Column(Integer, ForeignKey("parties.id"))
    financial_year = Column(Text, nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    basis = Column(Text)
    source_url = Column(Text)

    party = relationship("Party", back_populates="public_funding")


class Interest(Base):
    __tablename__ = "interests"
    id = Column(Integer, primary_key=True)
    politician_id = Column(Integer, ForeignKey("politicians.id"))
    donor_id = Column(Integer, ForeignKey("donors.id"))
    description = Column(Text)
    value_approx = Column(Numeric(14, 2))
    date_received = Column(Date)
    date_declared = Column(Date)
    source_url = Column(Text)

    politician = relationship("Politician", back_populates="interests")
    donor = relationship("Donor", back_populates="interests")


class Bill(Base):
    __tablename__ = "bills"
    id = Column(Integer, primary_key=True)
    title = Column(Text, nullable=False)
    issue_tags = Column(ARRAY(Text))
    summary = Column(Text)
    theyvoteforyou_id = Column(Text, unique=True)

    votes = relationship("Vote", back_populates="bill")
    industry_relevance = relationship("BillIndustryRelevance", back_populates="bill")


class Vote(Base):
    __tablename__ = "votes"
    id = Column(Integer, primary_key=True)
    politician_id = Column(Integer, ForeignKey("politicians.id"))
    bill_id = Column(Integer, ForeignKey("bills.id"))
    vote_direction = Column(Text)
    vote_date = Column(Date)
    __table_args__ = (UniqueConstraint("politician_id", "bill_id"),)

    politician = relationship("Politician", back_populates="votes")
    bill = relationship("Bill", back_populates="votes")


class BillIndustryRelevance(Base):
    __tablename__ = "bill_industry_relevance"
    bill_id = Column(Integer, ForeignKey("bills.id"), primary_key=True)
    anzsic_code = Column(Text, primary_key=True)
    relevance_note = Column(Text)

    bill = relationship("Bill", back_populates="industry_relevance")
