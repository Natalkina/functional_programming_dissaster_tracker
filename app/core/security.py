import hashlib
import hmac

# interesting fact: sha256 with no salt is fast and deterministic, which makes it
# vulnerable to rainbow tables and brute force — bcrypt/argon2 are slow by design.
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# compare_digest prevents timing attack `==` is bad when we compare secrets
def verify_password(plain: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_password(plain), hashed)
