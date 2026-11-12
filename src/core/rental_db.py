"""
Rental Market Intelligence Database Architecture (SQLAlchemy + SQLite/PostGIS).

Provides normalized relational tables for:
- rental_data_sources
- rental_listings (strict separation of Verified_Achieved, Advertised_Asking, Broker_Reported, Historical_Benchmark)
- rental_operating_expenses
- rental_price_history
- locality_rental_statistics
- rental_collection_jobs

Designed to run zero-config on SQLite locally or connect to PostgreSQL/PostGIS via DATABASE_URL.
"""
import os
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent.parent
_SEED_DATA_DIR = BASE_DIR / "data"
if os.environ.get("VERCEL"):
    import shutil

    DATA_DIR = Path("/tmp") / "propai_data"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _seed_db = _SEED_DATA_DIR / "rental_intelligence.db"
    _tmp_db = DATA_DIR / "rental_intelligence.db"
    if _seed_db.exists() and not _tmp_db.exists():
        shutil.copy2(_seed_db, _tmp_db)
else:
    DATA_DIR = _SEED_DATA_DIR
    DATA_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_DB_URL = f"sqlite:///{(DATA_DIR / 'rental_intelligence.db').as_posix()}"
DATABASE_URL = os.environ.get("RENTAL_DATABASE_URL", DEFAULT_DB_URL)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()


def _gen_uuid() -> str:
    return str(uuid.uuid4())


class RentalDataSource(Base):
    __tablename__ = "rental_data_sources"

    id = Column(String(36), primary_key=True, default=_gen_uuid)
    source_name = Column(String(64), unique=True, nullable=False, index=True)
    source_type = Column(String(32), nullable=False)  # 'gov_registry', 'rera', 'broker_feed', 'user_lease', 'portal_restricted', 'dataset_benchmark'
    api_available = Column(Boolean, default=False)
    licensing_status = Column(String(64), nullable=False)
    redistribution_permitted = Column(Boolean, default=False)
    is_enabled = Column(Boolean, default=True)
    last_successful_collection = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)


class RentalListing(Base):
    __tablename__ = "rental_listings"

    id = Column(String(36), primary_key=True, default=_gen_uuid)
    source_name = Column(String(64), nullable=False, index=True)
    external_listing_id = Column(String(128), nullable=True, index=True)
    canonical_group_id = Column(String(36), nullable=True, index=True)

    # Strict provenance separation: 'Verified_Achieved', 'Advertised_Asking', 'Broker_Reported', 'User_Submitted', 'Historical_Benchmark'
    data_category = Column(String(32), nullable=False, index=True)
    verification_status = Column(String(32), nullable=False, default="unverified")

    property_type = Column(String(40), nullable=False, index=True)  # 'apartment', 'standalone_house', 'villa', 'office', 'retail', 'industrial'
    bhk = Column(Float, nullable=True)
    bathrooms = Column(Float, nullable=True)
    carpet_area_sqft = Column(Float, nullable=False)
    builtup_area_sqft = Column(Float, nullable=True)
    floor_number = Column(Integer, nullable=True)
    total_floors = Column(Integer, nullable=True)
    building_age_years = Column(Float, nullable=True)

    monthly_rent_inr = Column(Float, nullable=False)
    security_deposit_inr = Column(Float, nullable=True)
    maintenance_monthly_inr = Column(Float, default=0.0)
    lease_duration_months = Column(Integer, nullable=True)
    implied_gross_yield_pct = Column(Float, nullable=True)

    furnishing = Column(String(32), nullable=True)  # 'unfurnished', 'semi_furnished', 'fully_furnished'
    parking_slots = Column(Integer, default=0)

    latitude = Column(Float, nullable=False, index=True)
    longitude = Column(Float, nullable=False, index=True)
    country_code = Column(String(8), nullable=False, default="IN")
    state = Column(String(64), nullable=False, index=True)
    city = Column(String(64), nullable=False, index=True)
    locality = Column(String(128), nullable=False, index=True)
    pin_code = Column(String(16), nullable=True)

    observation_date = Column(Date, nullable=False, default=date.today)
    last_verified_date = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    is_stale = Column(Boolean, default=False)
    is_outlier = Column(Boolean, default=False)
    is_duplicate = Column(Boolean, default=False)
    confidence_score = Column(Float, default=0.7)
    created_at = Column(DateTime, default=datetime.utcnow)

    expenses = relationship("RentalOperatingExpense", back_populates="listing", cascade="all, delete-orphan")
    price_history = relationship("RentalPriceHistory", back_populates="listing", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_rental_geo", "latitude", "longitude"),
        Index("idx_rental_city_type_cat", "city", "property_type", "data_category"),
    )


class RentalOperatingExpense(Base):
    __tablename__ = "rental_operating_expenses"

    id = Column(String(36), primary_key=True, default=_gen_uuid)
    listing_id = Column(String(36), ForeignKey("rental_listings.id", ondelete="CASCADE"), nullable=False)
    property_tax_annual = Column(Float, default=0.0)
    maintenance_annual = Column(Float, default=0.0)
    insurance_annual = Column(Float, default=0.0)
    utilities_annual = Column(Float, default=0.0)
    management_fee_pct = Column(Float, default=0.0)
    vacancy_rate_pct = Column(Float, default=5.0)
    annual_noi_inr = Column(Float, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)

    listing = relationship("RentalListing", back_populates="expenses")


class RentalPriceHistory(Base):
    __tablename__ = "rental_price_history"

    id = Column(String(36), primary_key=True, default=_gen_uuid)
    listing_id = Column(String(36), ForeignKey("rental_listings.id", ondelete="CASCADE"), nullable=True)
    city = Column(String(64), nullable=False, index=True)
    locality = Column(String(128), nullable=False, index=True)
    property_type = Column(String(40), nullable=False)
    data_category = Column(String(32), nullable=False)
    monthly_rent_inr = Column(Float, nullable=False)
    rent_per_sqft_inr = Column(Float, nullable=True)
    gross_yield_pct = Column(Float, nullable=True)
    snapshot_date = Column(Date, nullable=False, default=date.today, index=True)

    listing = relationship("RentalListing", back_populates="price_history")


class LocalityRentalStatistic(Base):
    __tablename__ = "locality_rental_statistics"

    id = Column(String(36), primary_key=True, default=_gen_uuid)
    city = Column(String(64), nullable=False, index=True)
    locality = Column(String(128), nullable=False, index=True)
    property_type = Column(String(40), nullable=False)
    data_category = Column(String(32), nullable=False)
    min_monthly_rent = Column(Float, nullable=False)
    median_monthly_rent = Column(Float, nullable=False)
    mean_monthly_rent = Column(Float, nullable=False)
    max_monthly_rent = Column(Float, nullable=False)
    median_rent_per_sqft = Column(Float, nullable=False)
    median_gross_yield_pct = Column(Float, nullable=True)
    median_cap_rate_pct = Column(Float, nullable=True)
    observation_count = Column(Integer, default=0)
    confidence_score = Column(Float, default=0.5)
    snapshot_date = Column(Date, nullable=False, default=date.today)


class RentalCollectionJob(Base):
    __tablename__ = "rental_collection_jobs"

    id = Column(String(36), primary_key=True, default=_gen_uuid)
    source_name = Column(String(64), nullable=False, index=True)
    location_query = Column(String(128), nullable=False)
    radius_km = Column(Float, default=5.0)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    records_collected = Column(Integer, default=0)
    records_accepted = Column(Integer, default=0)
    records_rejected = Column(Integer, default=0)
    error_log = Column(Text, nullable=True)
    status = Column(String(24), default="PENDING")  # 'PENDING', 'SUCCESS', 'FAILED', 'RESTRICTED'


def init_rental_db(seed_historical_benchmarks: bool = True) -> None:
    """Creates all rental database tables and initializes compliant source metadata."""
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        # 1. Initialize source registry idempotently
        default_sources = [
            {
                "source_name": "pan_india_rental_yield_index",
                "source_type": "dataset_benchmark",
                "api_available": True,
                "licensing_status": "Verified Repo Training Dataset (rental.parquet)",
                "redistribution_permitted": True,
                "is_enabled": True,
                "last_successful_collection": datetime(2025, 6, 15),
                "notes": "219 regional rental observations from datasets/training/rental.parquet",
            },
            {
                "source_name": "igr_odisha_lease_registry",
                "source_type": "gov_registry",
                "api_available": False,
                "licensing_status": "Public Portal Lookup (No Bulk Open API)",
                "redistribution_permitted": False,
                "is_enabled": True,
                "notes": "Official IGR Odisha registered lease deed schema ready for authorized feed",
            },
            {
                "source_name": "rera_odisha_disclosures",
                "source_type": "rera",
                "api_available": False,
                "licensing_status": "Public Regulatory Filing",
                "redistribution_permitted": True,
                "is_enabled": True,
                "notes": "Odisha RERA commercial & residential project lease disclosures",
            },
            {
                "source_name": "verified_broker_submission",
                "source_type": "broker_feed",
                "api_available": True,
                "licensing_status": "Partner Submission Intake",
                "redistribution_permitted": True,
                "is_enabled": True,
                "notes": "Direct verified broker comparable submissions via /api/rental/verify",
            },
            {
                "source_name": "user_submitted_lease",
                "source_type": "user_lease",
                "api_available": True,
                "licensing_status": "First-Party User Consent",
                "redistribution_permitted": True,
                "is_enabled": True,
                "notes": "Executed rental agreement uploads via /api/rental/verify",
            },
            {
                "source_name": "99acres",
                "source_type": "portal_restricted",
                "api_available": False,
                "licensing_status": "Restricted / No Public Redistribution API",
                "redistribution_permitted": False,
                "is_enabled": False,
                "notes": "Marked unavailable to respect bot protection and portal terms of service",
            },
            {
                "source_name": "magicbricks",
                "source_type": "portal_restricted",
                "api_available": False,
                "licensing_status": "Restricted / No Public Redistribution API",
                "redistribution_permitted": False,
                "is_enabled": False,
                "notes": "Marked unavailable to respect bot protection and portal terms of service",
            },
            {
                "source_name": "housing_com",
                "source_type": "portal_restricted",
                "api_available": False,
                "licensing_status": "Restricted / No Public Redistribution API",
                "redistribution_permitted": False,
                "is_enabled": False,
                "notes": "Marked unavailable pending licensed partner API key",
            },
            {
                "source_name": "nobroker",
                "source_type": "portal_restricted",
                "api_available": False,
                "licensing_status": "Restricted / No Public Redistribution API",
                "redistribution_permitted": False,
                "is_enabled": False,
                "notes": "Marked unavailable pending licensed partner API key",
            },
        ]

        for src in default_sources:
            existing = db.query(RentalDataSource).filter_by(source_name=src["source_name"]).first()
            if not existing:
                db.add(RentalDataSource(**src))

        db.commit()

        # 2. Import repository's verified rental.parquet benchmarks cleanly labeled as Historical_Benchmark
        if seed_historical_benchmarks:
            parquet_path = BASE_DIR / "datasets" / "training" / "rental.parquet"
            if parquet_path.exists():
                existing_count = (
                    db.query(RentalListing)
                    .filter_by(source_name="pan_india_rental_yield_index")
                    .count()
                )
                if existing_count == 0:
                    try:
                        import pandas as pd
                        df = pd.read_parquet(parquet_path)
                        for _, row in df.iterrows():
                            obs_date = date(2025, 6, 15)
                            if "transaction_date" in row and row["transaction_date"]:
                                try:
                                    obs_date = datetime.strptime(str(row["transaction_date"])[:10], "%Y-%m-%d").date()
                                except ValueError:
                                    pass

                            area = float(row.get("area_sqft", 1000.0) or 1000.0)
                            bhk_est = 1.0 if area < 750 else (2.0 if area < 1200 else 3.0)
                            city_raw = str(row.get("city", "City"))
                            listing = RentalListing(
                                source_name="pan_india_rental_yield_index",
                                external_listing_id=str(row.get("property_id", _gen_uuid())),
                                data_category="Historical_Benchmark",
                                verification_status="verified_hub_benchmark",
                                property_type="apartment",
                                bhk=bhk_est,
                                bathrooms=max(1.0, bhk_est - 0.0 if bhk_est <= 2 else 2.0),
                                carpet_area_sqft=round(area * 0.80, 1),
                                builtup_area_sqft=round(area, 1),
                                monthly_rent_inr=float(row.get("price_inr", 0.0)),
                                implied_gross_yield_pct=float(row.get("gross_rental_yield_pct", 3.8)),
                                furnishing="semi_furnished",
                                parking_slots=1,
                                latitude=float(row["latitude"]),
                                longitude=float(row["longitude"]),
                                country_code=str(row.get("country_code", "IN")),
                                state=str(row.get("state", "India")),
                                city=city_raw,
                                locality=city_raw,
                                observation_date=obs_date,
                                last_verified_date=obs_date,
                                is_active=True,
                                is_stale=False,
                                is_outlier=False,
                                is_duplicate=False,
                                confidence_score=0.82,
                            )
                            db.add(listing)
                        db.commit()
                    except Exception:
                        db.rollback()


def get_db():
    """FastAPI dependency generator providing a scoped SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
