import asyncio
import sys
import os
from sqlalchemy import select, delete
from datetime import datetime

# Ensure app is in pythonpath
sys.path.append("/app")

from app.database.session import SessionLocal
from app.services.alert_service import AlertService
from app.database.models.alert import Alert, AlertType
from app.schemas.alert import AlertCreate

async def setup_data(db):
    print("Setting up test alerts...")
    
    # 1. Active Unread (Unsent)
    alert1 = Alert(
        alert_type=AlertType.TEMP,
        message="Test Alert 1 (Active, Unread)",
        is_resolved=False,
        is_sent=False,
        created_at=datetime.now()
    )
    
    # 2. Active Read (Sent)
    alert2 = Alert(
        alert_type=AlertType.TEMP,
        message="Test Alert 2 (Active, Read)",
        is_resolved=False,
        is_sent=True,
        created_at=datetime.now()
    )
    
    # 3. Resolved
    alert3 = Alert(
        alert_type=AlertType.TEMP,
        message="Test Alert 3 (Resolved)",
        is_resolved=True,
        is_sent=True,
        created_at=datetime.now()
    )
    
    db.add_all([alert1, alert2, alert3])
    await db.commit()
    return [alert1, alert2, alert3]

async def verify():
    async with SessionLocal() as db:
        alerts = await setup_data(db)
        
        try:
            print("\n--- Verifying Filters ---")
            
            # Test 1: Active Alerts (is_resolved=False)
            print("1. Testing is_resolved=False...")
            results = await AlertService.get_alerts(db, is_resolved=False)
            count = len([a for a in results if a.message.startswith("Test Alert")])
            print(f"Found {count} test alerts (Expected 2)")
            if count != 2:
                raise Exception("Failed is_resolved=False check")

            # Test 2: Resolved Alerts (is_resolved=True)
            print("2. Testing is_resolved=True...")
            results = await AlertService.get_alerts(db, is_resolved=True)
            count = len([a for a in results if a.message.startswith("Test Alert")])
            print(f"Found {count} test alerts (Expected 1)")
            if count != 1:
                raise Exception("Failed is_resolved=True check")

            # Test 3: Unsent Alerts (is_sent=False)
            print("3. Testing is_sent=False...")
            results = await AlertService.get_alerts(db, is_sent=False)
            count = len([a for a in results if a.message.startswith("Test Alert")])
            print(f"Found {count} test alerts (Expected 1)")
            if count != 1:
                raise Exception("Failed is_sent=False check")
                
            print("\nSUCCESS: All filters verified!")
            
        finally:
            print("\nCleaning up...")
            for a in alerts:
                await db.delete(a)
            await db.commit()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(verify())
