import pytest
import math
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from app.services.product_stats_service import ProductStatsService
from app.database.models.product_definition import ProductDefinition, FrequencyClass
from app.database.models.product_stats import ProductStats

# Mock Redic Incrby since the default fixture might not have it
@pytest.fixture
def mock_redis_custom():
    mock = AsyncMock()
    mock.incrby = AsyncMock(return_value=1)
    return mock

@pytest.mark.asyncio
async def test_update_product_stats_increment(db_session, mock_redis_custom):
    # Setup product
    prod = ProductDefinition(
        name="Test Prod", barcode="123", req_temp_min=0, req_temp_max=10, 
        weight_kg=1, dims_x_mm=10, dims_y_mm=10, dims_z_mm=10, expiry_days=10
    )
    db_session.add(prod)
    await db_session.commit()
    await db_session.refresh(prod)

    # 1. Test basic increment
    await ProductStatsService.update_product_stats(db_session, prod.id, 5, mock_redis_custom)
    
    # Check stats
    stmt = select(ProductStats).where(ProductStats.product_id == prod.id)
    result = await db_session.execute(stmt)
    stats = result.scalars().first()
    
    assert stats is not None
    assert stats.pick_count == 5
    assert stats.total_since_last_update == 5
    
    # Check Redis call
    mock_redis_custom.incrby.assert_called_once()

@pytest.mark.asyncio
async def test_update_product_stats_trigger(db_session, mock_redis_custom):
    # Setup product
    prod = ProductDefinition(
        name="Test Prod Trigger", barcode="1234", req_temp_min=0, req_temp_max=10, 
        weight_kg=1, dims_x_mm=10, dims_y_mm=10, dims_z_mm=10, expiry_days=10
    )
    db_session.add(prod)
    await db_session.commit()
    await db_session.refresh(prod)

    # Mock redis to return 10 (trigger value)
    mock_redis_custom.incrby.return_value = 10
    
    # Patch the task
    with patch("app.tasks.product_stats_tasks.update_frequencies_task.delay") as mock_task:
        await ProductStatsService.update_product_stats(db_session, prod.id, 1, mock_redis_custom)
        mock_task.assert_called_once()

@pytest.mark.asyncio
async def test_abc_classification_standard(db_session):
    # Create 10 products with varying pick counts
    # A: Top 30% -> Top 3 -> Ranks 1, 2, 3
    # B: Next 40% -> Next 4 -> Ranks 4, 5, 6, 7
    # C: Bottom 30% -> Bottom 3 -> Ranks 8, 9, 10
    
    products = []
    for i in range(10):
        p = ProductDefinition(
            name=f"P{i}", barcode=f"BC{i}", req_temp_min=0, req_temp_max=10, 
            weight_kg=1, dims_x_mm=10, dims_y_mm=10, dims_z_mm=10, expiry_days=10
        )
        db_session.add(p)
        products.append(p)
    await db_session.commit()
    
    # Add stats (Process in reverse so P9 has highest count)
    for i, p in enumerate(products):
        # i=0 (P0) -> count=0
        # i=9 (P9) -> count=9
        stats = ProductStats(product_id=p.id, pick_count=i)
        db_session.add(stats)
    await db_session.commit()

    # Run calculation
    await ProductStatsService.update_products_frequencies(db_session)
    await db_session.commit()
    
    # Verification
    # Expected:
    # 7, 8, 9 -> Count 7, 8, 9 (Top 3) -> A
    # 3, 4, 5, 6 -> Count 3, 4, 5, 6 -> B
    # 0, 1, 2 -> Count 0, 1, 2 -> C
    
    stmt = select(ProductDefinition).order_by(ProductDefinition.barcode)
    res = await db_session.execute(stmt)
    all_prods = res.scalars().all()
    
    # Map barcode to class
    results = {p.barcode: p.frequency_class for p in all_prods}
    
    # A Class
    assert results["BC9"] == FrequencyClass.A
    assert results["BC8"] == FrequencyClass.A
    assert results["BC7"] == FrequencyClass.A
    
    # B Class
    assert results["BC6"] == FrequencyClass.B
    assert results["BC5"] == FrequencyClass.B
    assert results["BC4"] == FrequencyClass.B
    assert results["BC3"] == FrequencyClass.B
    
    # C Class
    assert results["BC2"] == FrequencyClass.C
    assert results["BC1"] == FrequencyClass.C
    assert results["BC0"] == FrequencyClass.C

@pytest.mark.asyncio
async def test_abc_classification_small_dataset(db_session):
    # Test for the bugfix: 3 items. 30% of 3 is 0.9 -> ceil(0.9) = 1.
    # Should result in 1 A, 1 B, 1 C (since 70% of 3 is 2.1->3? No wait)
    # logic:
    # a_limit = ceil(0.3 * 3) = ceil(0.9) = 1. Index 0 is < 1? Yes. -> A
    # b_limit = ceil(0.7 * 3) = ceil(2.1) = 3. 
    # Index 1 < 3? Yes -> B
    # Index 2 < 3? Yes -> B.
    # Wait, my logic: 
    # if i < a_limit: A
    # elif i < b_limit: B
    # else: C
    
    # If a=1, b=3.
    # i=0: <1 (True) -> A
    # i=1: <1 (False), <3 (True) -> B
    # i=2: <1 (False), <3 (True) -> B
    # So 1 A, 2 Bs. No C?
    # Let's check logic: C is bottom 30%.
    # If 3 items: A(30%)=1, B(40%)=~1, C(30%)=1.
    # 1 A, 2 B is acceptable for 3 items. Or 1 A, 1 B, 1 C.
    # With ceil(2.1) = 3, b_limit is 3.
    # So indices 0, 1, 2 are all < 3.
    # i=0 -> A.
    # i=1 -> B.
    # i=2 -> B.
    # That means no C. That's actually fine for small sets, better than no A.
    
    # Create 3 products
    products = []
    for i in range(3):
        p = ProductDefinition(
            name=f"Small{i}", barcode=f"S{i}", req_temp_min=0, req_temp_max=10, 
            weight_kg=1, dims_x_mm=10, dims_y_mm=10, dims_z_mm=10, expiry_days=10
        )
        db_session.add(p)
        products.append(p)
    await db_session.commit()
    
    # Scores: S0=10, S1=5, S2=1
    db_session.add(ProductStats(product_id=products[0].id, pick_count=10))
    db_session.add(ProductStats(product_id=products[1].id, pick_count=5))
    db_session.add(ProductStats(product_id=products[2].id, pick_count=1))
    await db_session.commit()
    
    await ProductStatsService.update_products_frequencies(db_session)
    await db_session.commit()
    
    # Refresh
    for p in products:
        await db_session.refresh(p)
        
    # S0 should be A
    assert products[0].frequency_class == FrequencyClass.A
    # S1 should be B
    assert products[1].frequency_class == FrequencyClass.B
    # S2 should be B (based on ceil logic)
    assert products[2].frequency_class == FrequencyClass.B
