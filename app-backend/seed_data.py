from datetime import datetime, timedelta, timezone

from app.auth import hash_password
from app.db import Base, SessionLocal, engine
from app.models import Lot, Product, Shop, User

Base.metadata.create_all(bind=engine)
db = SessionLocal()
user = db.query(User).filter_by(email="demo@sobracero.local").first()
if not user:
    user = User(email="demo@sobracero.local", password_hash=hash_password("password123"), is_admin=True)
    db.add(user); db.flush()
shop = Shop(owner_id=user.id, name="Fresh Corner", description="Rescue good food near you", latitude=4.711, longitude=-74.072)
db.add(shop); db.flush()
product = Product(shop_id=shop.id, name="Bakery box", description="A selection from today's bakery")
db.add(product); db.flush()
for index, hours in enumerate((24, 36, 72), 1):
    db.add(Lot(shop_id=shop.id, product_id=product.id, title=f"Rescue box {index}", description="Fresh surplus food", quantity=10, original_price_cents=2000, discount_percent=50, expires_at=datetime.now(timezone.utc) + timedelta(hours=hours)))
db.commit(); db.close()
print("Seed complete: demo@sobracero.local / password123")
