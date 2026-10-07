from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.auth import verify_password
from app.db import Base
from app.models import Lot, Product, Shop, User
from seed_data import DEMO_EMAIL, DEMO_PASSWORD, LEGACY_DEMO_EMAIL, seed_demo_data


def test_seed_is_idempotent_and_migrates_legacy_demo_email() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as db:
        seed_demo_data(db)
        user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
        assert user is not None
        user.email = LEGACY_DEMO_EMAIL
        db.commit()

        seed_demo_data(db)

        user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
        assert user is not None
        assert user.is_admin
        assert verify_password(DEMO_PASSWORD, user.password_hash)
        assert db.scalar(select(func.count(Shop.id))) == 1
        assert db.scalar(select(func.count(Product.id))) == 1
        assert db.scalar(select(func.count(Lot.id))) == 3

    engine.dispose()
