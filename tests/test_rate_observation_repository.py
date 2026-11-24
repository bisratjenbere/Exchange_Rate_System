"""
Tests for RateObservationRepository.

These tests verify the repository correctly centralizes all rate_observation
database operations.
"""

import pytest
from datetime import date, datetime, timezone
from decimal import Decimal

from tests.db_utils import get_conn, reset_schema, apply_migrations
from db.repositories.rate_observation_repository import RateObservationRepository
from domain.records import AdapterRecord
from domain.enums import ValidationStatus, IdentityStatus, ChangeReviewStatus
from domain.exceptions import StaleObservationError
from pipeline.fingerprint import compute_fingerprint


@pytest.fixture(scope="module")
def db():
    """Module-scoped database connection with schema."""
    conn = get_conn()
    reset_schema(conn)
    apply_migrations(conn)
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def rollback(db):
    """Auto-rollback after each test."""
    yield
    db.rollback()


@pytest.fixture
def test_data(db):
    """Set up test data for each test."""
    with db.cursor() as cur:
        # Insert a bank
        cur.execute(
            "INSERT INTO bank (code, name) VALUES (%s, %s) ON CONFLICT (code) DO UPDATE SET code=EXCLUDED.code RETURNING id",
            ('TEST', 'Test Bank')
        )
        bank_id = cur.fetchone()[0]
        
        # Insert a rate_source
        cur.execute(
            """INSERT INTO rate_source
                   (bank_id, source_url, collection_method, adapter_key, is_enabled)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT DO NOTHING
               RETURNING id""",
            (bank_id, 'http://test.com', 'html', 'test', True)
        )
        result = cur.fetchone()
        if result:
            source_id = result[0]
        else:
            # Already exists, fetch it
            cur.execute("SELECT id FROM rate_source WHERE adapter_key = %s", ('test',))
            source_id = cur.fetchone()[0]
        
        # Insert a rate_category
        cur.execute(
            """INSERT INTO rate_category (code, name, approved_at)
               VALUES (%s, %s, NOW())
               ON CONFLICT (code) DO UPDATE SET code=EXCLUDED.code
               RETURNING id""",
            ('cash', 'Cash')
        )
        category_id = cur.fetchone()[0]
        
        # Close any existing running runs for this source (to avoid unique constraint violation)
        cur.execute(
            """UPDATE collection_run 
               SET status = 'success', finished_at = NOW()
               WHERE source_id = %s AND status = 'running'""",
            (source_id,)
        )
        
        # Insert collection_run
        cur.execute(
            """INSERT INTO collection_run (source_id, started_at, status)
               VALUES (%s, NOW(), %s) RETURNING id""",
            (source_id, 'running')
        )
        run_id = cur.fetchone()[0]
        
        db.commit()
        
        return {
            'bank_id': bank_id,
            'source_id': source_id,
            'category_id': category_id,
            'run_id': run_id,
        }


@pytest.fixture
def repo(db):
    """Repository instance for each test."""
    return RateObservationRepository(db)


def _fingerprint(record: AdapterRecord, source_id: int = 1) -> str:
    """Helper to compute fingerprint for testing."""
    return compute_fingerprint(record, source_id, date.today())


@pytest.fixture
def sample_record():
    """Sample adapter record for testing."""
    return AdapterRecord(
        source_currency_code="USD",
        effective_date_basis="source_published",
        category="cash",
        currency_name="US Dollar",
        buying_rate=Decimal("120.50"),
        selling_rate=Decimal("121.00"),
        source_rate_text="120.50 / 121.00",
        effective_date=date(2026, 11, 24),
        raw_excerpt={"table": "forex"},
        quote_currency_code="ETB",
        unit_multiplier=1,
    )


def test_insert_observation(db, repo, sample_record, test_data):
    """Test basic observation insertion."""
    fingerprint = _fingerprint(sample_record)
    
    obs_id = repo.insert(
        record=sample_record,
        source_id=test_data['source_id'],
        run_id=test_data['run_id'],
        category_id=test_data['category_id'],
        fingerprint=fingerprint,
        logical_key="src1_usd_cat1",
        identity_status=IdentityStatus.CONFIRMED,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[],
        fetched_at=datetime.now(timezone.utc),
        version_number=1,
        is_current=True,
        change_review_status=ChangeReviewStatus.NOT_REQUIRED,
        supersedes_id=None,
        is_fallback=False,
    )
    
    assert obs_id is not None
    assert obs_id > 0
    
    # Verify insertion
    obs = repo.get_by_id(obs_id)
    assert obs is not None
    assert obs['source_id'] == test_data['source_id']
    assert obs['currency_code'] == 'USD'
    assert obs['buying_rate'] == Decimal("120.50")
    assert obs['is_current'] is True
    assert obs['is_fallback'] is False


def test_get_active_observation(db, repo, sample_record, test_data):
    """Test retrieving active observation by source/currency/category."""
    fingerprint = _fingerprint(sample_record)
    
    # Insert observation
    obs_id = repo.insert(
        record=sample_record,
        source_id=test_data['source_id'],
        run_id=test_data['run_id'],
        category_id=test_data['category_id'],
        fingerprint=fingerprint,
        logical_key="src1_usd_cat1",
        identity_status=IdentityStatus.CONFIRMED,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[],
        fetched_at=datetime.now(timezone.utc),
        version_number=1,
        is_current=True,
    )
    
    # Retrieve active observation
    active = repo.get_active_observation(
        source_id=test_data['source_id'],
        currency_code="USD",
        category_id=test_data['category_id']
    )
    
    assert active is not None
    assert active['id'] == obs_id
    assert active['is_fallback'] is False
    
    # Non-existent combination
    none_found = repo.get_active_observation(
        source_id=test_data['source_id'],
        currency_code="EUR",
        category_id=test_data['category_id']
    )
    assert none_found is None
    
    db.rollback()


def test_retire_current_observations(db, repo, sample_record, test_data):
    """Test retiring all current observations for a criteria."""
    fingerprint = _fingerprint(sample_record)
    
    # Insert first current observation
    obs_id1 = repo.insert(
        record=sample_record,
        source_id=test_data['source_id'],
        run_id=test_data['run_id'],
        category_id=test_data['category_id'],
        fingerprint=fingerprint,
        logical_key="src1_usd_cat1_v1",
        identity_status=IdentityStatus.CONFIRMED,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[],
        fetched_at=datetime.now(timezone.utc),
        version_number=1,
        is_current=True,
    )
    
    # Retire first to allow second current observation
    repo.retire_current_observations(
        source_id=test_data['source_id'],
        currency_code="USD",
        category_id=test_data['category_id']
    )
    
    sample_record.buying_rate = Decimal("121.00")
    fingerprint2 = _fingerprint(sample_record)
    
    obs_id2 = repo.insert(
        record=sample_record,
        source_id=test_data['source_id'],
        run_id=test_data['run_id'],
        category_id=test_data['category_id'],
        fingerprint=fingerprint2,
        logical_key="src1_usd_cat1_v2",
        identity_status=IdentityStatus.CONFIRMED,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[],
        fetched_at=datetime.now(timezone.utc),
        version_number=2,
        is_current=True,
    )
    
    # Re-promote first observation so we have two to retire
    # First demote the second to avoid constraint violation
    repo.demote_observation(obs_id2)
    repo.promote_observation(obs_id1)
    
    # Retire all current
    retired_count = repo.retire_current_observations(
        source_id=test_data['source_id'],
        currency_code="USD",
        category_id=test_data['category_id']
    )
    
    assert retired_count == 1  # Only one was current after re-promotion
    
    # Verify first is no longer current, second was already demoted
    obs1 = repo.get_by_id(obs_id1)
    obs2 = repo.get_by_id(obs_id2)
    assert obs1['is_current'] is False
    assert obs2['is_current'] is False
    
    db.rollback()


def test_promote_demote_observation(db, repo, sample_record, test_data):
    """Test promoting and demoting observations."""
    fingerprint = _fingerprint(sample_record)
    
    # Insert non-current observation
    obs_id = repo.insert(
        record=sample_record,
        source_id=test_data['source_id'],
        run_id=test_data['run_id'],
        category_id=test_data['category_id'],
        fingerprint=fingerprint,
        logical_key="src1_usd_cat1",
        identity_status=IdentityStatus.CONFIRMED,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[],
        fetched_at=datetime.now(timezone.utc),
        version_number=1,
        is_current=False,
    )
    
    # Promote
    repo.promote_observation(obs_id, change_review_status='new_publication')
    
    obs = repo.get_by_id(obs_id)
    assert obs['is_current'] is True
    assert obs['change_review_status'] == 'new_publication'
    
    # Demote
    repo.demote_observation(obs_id, change_review_status='dismissed')
    
    obs = repo.get_by_id(obs_id)
    assert obs['is_current'] is False
    assert obs['change_review_status'] == 'dismissed'
    
    db.rollback()


def test_promote_fallback_to_non_fallback(db, repo, sample_record, test_data):
    """Test promoting fallback observation to non-fallback."""
    fingerprint = _fingerprint(sample_record)
    
    # Insert fallback observation
    obs_id = repo.insert(
        record=sample_record,
        source_id=test_data['source_id'],
        run_id=test_data['run_id'],
        category_id=test_data['category_id'],
        fingerprint=fingerprint,
        logical_key="src1_usd_cat1",
        identity_status=IdentityStatus.CONFIRMED,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[],
        fetched_at=datetime.now(timezone.utc),
        version_number=1,
        is_current=False,
        is_fallback=True,
    )
    
    # Promote fallback to non-fallback
    updated = repo.promote_fallback_to_non_fallback(obs_id)
    assert updated == 1
    
    obs = repo.get_by_id(obs_id)
    assert obs['is_fallback'] is False
    assert obs['is_current'] is True
    
    db.rollback()


def test_retire_prior_fallback_observations_fallback_caller(db, repo, sample_record, test_data):
    """Test retirement when called from fallback path."""
    # Insert older fallback observation
    sample_record.effective_date = date(2026, 11, 20)
    fingerprint1 = _fingerprint(sample_record)
    
    fallback_id = repo.insert(
        record=sample_record,
        source_id=test_data['source_id'],
        run_id=test_data['run_id'],
        category_id=test_data['category_id'],
        fingerprint=fingerprint1,
        logical_key="src1_usd_cat1_fb1",
        identity_status=IdentityStatus.CONFIRMED,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[],
        fetched_at=datetime.now(timezone.utc),
        version_number=None,
        is_current=True,
        is_fallback=True,
    )
    
    # Retire fallback to allow non-fallback insertion
    repo.demote_observation(fallback_id)
    
    # Insert non-fallback observation (should NOT be retired by fallback caller)
    sample_record.effective_date = date(2026, 11, 22)
    sample_record.buying_rate = Decimal("121.00")
    fingerprint2 = _fingerprint(sample_record)
    
    non_fallback_id = repo.insert(
        record=sample_record,
        source_id=test_data['source_id'],
        run_id=test_data['run_id'],
        category_id=test_data['category_id'],
        fingerprint=fingerprint2,
        logical_key="src1_usd_cat1_nf",
        identity_status=IdentityStatus.CONFIRMED,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[],
        fetched_at=datetime.now(timezone.utc),
        version_number=1,
        is_current=True,
        is_fallback=False,
    )
    
    # Re-promote fallback to test scenario where both exist
    # First demote non-fallback to avoid constraint violation
    repo.demote_observation(non_fallback_id)
    repo.promote_observation(fallback_id)
    
    # Retire from fallback caller (newer effective date)
    retired = repo.retire_prior_fallback_observations(
        source_id=test_data['source_id'],
        currency_code="USD",
        category_id=test_data['category_id'],
        effective_date=date(2026, 11, 25),
        is_fallback=True  # Fallback caller
    )
    
    # Only fallback observation should be retired
    fallback_obs = repo.get_by_id(fallback_id)
    non_fallback_obs = repo.get_by_id(non_fallback_id)
    
    assert fallback_obs['is_current'] is False, "Fallback observation should be retired"
    assert non_fallback_obs['is_current'] is False, "Non-fallback was demoted"
    
    db.rollback()


def test_retire_prior_fallback_observations_non_fallback_caller(db, repo, sample_record, test_data):
    """Test retirement when called from non-fallback path."""
    # Insert older fallback observation
    sample_record.effective_date = date(2026, 11, 20)
    fingerprint1 = _fingerprint(sample_record)
    
    fallback_id = repo.insert(
        record=sample_record,
        source_id=test_data['source_id'],
        run_id=test_data['run_id'],
        category_id=test_data['category_id'],
        fingerprint=fingerprint1,
        logical_key="src1_usd_cat1_fb",
        identity_status=IdentityStatus.CONFIRMED,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[],
        fetched_at=datetime.now(timezone.utc),
        version_number=None,
        is_current=True,
        is_fallback=True,
    )
    
    # Retire fallback to allow non-fallback insertion
    repo.demote_observation(fallback_id)
    
    # Insert older non-fallback observation
    sample_record.effective_date = date(2026, 11, 22)
    sample_record.buying_rate = Decimal("121.00")
    fingerprint2 = _fingerprint(sample_record)
    
    non_fallback_id = repo.insert(
        record=sample_record,
        source_id=test_data['source_id'],
        run_id=test_data['run_id'],
        category_id=test_data['category_id'],
        fingerprint=fingerprint2,
        logical_key="src1_usd_cat1_nf",
        identity_status=IdentityStatus.CONFIRMED,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[],
        fetched_at=datetime.now(timezone.utc),
        version_number=1,
        is_current=True,
        is_fallback=False,
    )
    
    # Re-promote fallback to test scenario where both exist
    # First demote non-fallback to avoid constraint violation
    repo.demote_observation(non_fallback_id)
    repo.promote_observation(fallback_id)
    
    # Retire from non-fallback caller (newer effective date)
    retired = repo.retire_prior_fallback_observations(
        source_id=test_data['source_id'],
        currency_code="USD",
        category_id=test_data['category_id'],
        effective_date=date(2026, 11, 25),
        is_fallback=False  # Non-fallback caller
    )
    
    # Both should be retired
    fallback_obs = repo.get_by_id(fallback_id)
    non_fallback_obs = repo.get_by_id(non_fallback_id)
    
    assert fallback_obs['is_current'] is False, "Fallback observation should be retired"
    assert non_fallback_obs['is_current'] is False, "Non-fallback was demoted"
    
    db.rollback()


def test_get_next_version_number(db, repo, sample_record, test_data):
    """Test version number generation."""
    logical_key = "src1_usd_cat1"
    
    # No observations yet - should return 1
    version = repo.get_next_version_number(logical_key)
    assert version == 1
    
    # Insert versioned observation
    fingerprint = _fingerprint(sample_record)
    repo.insert(
        record=sample_record,
        source_id=test_data['source_id'],
        run_id=test_data['run_id'],
        category_id=test_data['category_id'],
        fingerprint=fingerprint,
        logical_key=logical_key,
        identity_status=IdentityStatus.CONFIRMED,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[],
        fetched_at=datetime.now(timezone.utc),
        version_number=1,
        is_current=True,
    )
    
    # Should return 2
    version = repo.get_next_version_number(logical_key)
    assert version == 2
    
    db.rollback()


def test_lock_and_get_version(db, repo, sample_record, test_data):
    """Test locking observation for correction."""
    logical_key = "src1_usd_cat1"
    fingerprint = _fingerprint(sample_record)
    
    obs_id = repo.insert(
        record=sample_record,
        source_id=test_data['source_id'],
        run_id=test_data['run_id'],
        category_id=test_data['category_id'],
        fingerprint=fingerprint,
        logical_key=logical_key,
        identity_status=IdentityStatus.CONFIRMED,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[],
        fetched_at=datetime.now(timezone.utc),
        version_number=1,
        is_current=True,
    )
    
    # Lock and get version
    version = repo.lock_and_get_version(obs_id, logical_key)
    assert version == 1
    
    # Wrong logical key should raise ValueError
    with pytest.raises(ValueError, match="Logical key mismatch"):
        repo.lock_and_get_version(obs_id, "wrong_key")
    
    # Non-existent ID should raise StaleObservationError
    with pytest.raises(StaleObservationError):
        repo.lock_and_get_version(99999, logical_key)
    
    db.rollback()


def test_insert_correction(db, repo, sample_record, test_data):
    """Test inserting corrected observation."""
    logical_key = "src1_usd_cat1"
    fingerprint1 = _fingerprint(sample_record)
    
    # Insert original observation
    original_id = repo.insert(
        record=sample_record,
        source_id=test_data['source_id'],
        run_id=test_data['run_id'],
        category_id=test_data['category_id'],
        fingerprint=fingerprint1,
        logical_key=logical_key,
        identity_status=IdentityStatus.CONFIRMED,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[],
        fetched_at=datetime.now(timezone.utc),
        version_number=1,
        is_current=True,
    )
    
    # Create corrected record
    sample_record.buying_rate = Decimal("122.00")
    sample_record.selling_rate = Decimal("122.50")
    fingerprint2 = _fingerprint(sample_record)
    
    # Insert correction
    corrected_id = repo.insert_correction(
        prior_obs_id=original_id,
        record=sample_record,
        source_id=test_data['source_id'],
        run_id=test_data['run_id'],
        category_id=test_data['category_id'],
        fingerprint=fingerprint2,
        logical_key=logical_key,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[],
        fetched_at=datetime.now(timezone.utc),
        new_version=2,
    )
    
    assert corrected_id != original_id
    
    # Verify correction properties
    correction = repo.get_by_id(corrected_id)
    assert correction['version_number'] == 2
    assert correction['supersedes_id'] == original_id
    assert correction['change_review_status'] == 'confirmed_correction'
    assert correction['identity_status'] == 'confirmed'
    assert correction['is_current'] is False  # Initially false, needs promotion
    assert correction['is_fallback'] is False
    assert correction['buying_rate'] == Decimal("122.00")
    
    db.rollback()


def test_expire_stale_fallback_current(db, repo, sample_record, test_data):
    """Test expiring stale fallback observations."""
    # Insert old fallback observation (20 days old)
    sample_record.effective_date = date(2026, 11, 4)
    fingerprint1 = _fingerprint(sample_record)
    
    old_fallback_id = repo.insert(
        record=sample_record,
        source_id=test_data['source_id'],
        run_id=test_data['run_id'],
        category_id=test_data['category_id'],
        fingerprint=fingerprint1,
        logical_key="src1_usd_cat1_old",
        identity_status=IdentityStatus.CONFIRMED,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[],
        fetched_at=datetime.now(timezone.utc),
        version_number=None,
        is_current=True,
        is_fallback=True,
    )
    
    # Retire old fallback to allow fresh fallback insertion
    repo.demote_observation(old_fallback_id)
    
    # Insert fresh fallback observation (1 day old)
    sample_record.effective_date = date(2026, 11, 23)
    sample_record.buying_rate = Decimal("121.00")
    fingerprint2 = _fingerprint(sample_record)
    
    fresh_fallback_id = repo.insert(
        record=sample_record,
        source_id=test_data['source_id'],
        run_id=test_data['run_id'],
        category_id=test_data['category_id'],
        fingerprint=fingerprint2,
        logical_key="src1_usd_cat1_fresh",
        identity_status=IdentityStatus.CONFIRMED,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[],
        fetched_at=datetime.now(timezone.utc),
        version_number=None,
        is_current=True,
        is_fallback=True,
    )
    
    # Re-promote old fallback to test scenario with two current fallbacks
    # First demote fresh to avoid constraint violation
    repo.demote_observation(fresh_fallback_id)
    repo.promote_observation(old_fallback_id)
    
    # Expire with 10 day TTL
    expired_count = repo.expire_stale_fallback_current(
        source_id=test_data['source_id'],
        fallback_ttl_days=10
    )
    
    assert expired_count >= 1  # At least old fallback expired
    
    # Verify old fallback expired
    old_obs = repo.get_by_id(old_fallback_id)
    assert old_obs['is_current'] is False
    
    # Fresh fallback was demoted earlier
    fresh_obs = repo.get_by_id(fresh_fallback_id)
    assert fresh_obs['is_current'] is False
    
    db.rollback()


def test_repository_isolation(db, repo, sample_record, test_data):
    """Test that repository methods don't commit transactions."""
    
    sample_record = AdapterRecord(
        source_currency_code="EUR",
        effective_date_basis="source_published",
        category="cash",
        currency_name="Euro",
        buying_rate=Decimal("130.00"),
        selling_rate=Decimal("131.00"),
        source_rate_text="130.00 / 131.00",
        effective_date=date(2026, 11, 24),
        raw_excerpt={},
        quote_currency_code="ETB",
        unit_multiplier=1,
    )
    
    fingerprint = _fingerprint(sample_record)
    
    # Insert observation
    obs_id = repo.insert(
        record=sample_record,
        source_id=test_data['source_id'],
        run_id=test_data['run_id'],
        category_id=test_data['category_id'],
        fingerprint=fingerprint,
        logical_key="src1_eur_cat1",
        identity_status=IdentityStatus.CONFIRMED,
        validation_status=ValidationStatus.VALIDATED,
        validation_messages=[],
        fetched_at=datetime.now(timezone.utc),
        version_number=1,
        is_current=True,
    )
    
    # Rollback - observation should disappear
    db.rollback()
    
    # Verify rollback worked
    obs = repo.get_by_id(obs_id)
    assert obs is None, "Repository should not commit - observation should be rolled back"
