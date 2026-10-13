import bcrypt


class BcryptPasswordHasher:
    """Hash passwords with bcrypt while preserving existing bcrypt hashes."""

    def hash(self, password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")

    def verify(self, password: str, password_hash: str) -> bool:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
