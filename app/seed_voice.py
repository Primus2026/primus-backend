import asyncio
from app.database.session import SessionLocal
from app.database.models.product_definition import ProductDefinition

async def seed():
    async with SessionLocal() as db:
        prod = ProductDefinition(
            name="Mleko 3,2%",
            barcode="5901234567890",
            req_temp_min=2.0,
            req_temp_max=6.0,
            weight_kg=1.0,
            dims_x_mm=100,
            dims_y_mm=100,
            dims_z_mm=200,
            expiry_days=14
        )
        db.add(prod)
        try:
            await db.commit()
            print("Seeded 'Mleko 3,2%' (5901234567890)")
        except Exception as e:
            print(f"Seed failed (maybe exists): {e}")

if __name__ == "__main__":
    asyncio.run(seed())
