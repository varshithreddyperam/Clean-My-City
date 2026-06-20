import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import credentials, auth

# Security scheme for FastAPI
security = HTTPBearer()

# Track initialization status
firebase_initialized = False

# Attempt to initialize Firebase Admin SDK
firebase_creds_path = os.getenv("FIREBASE_CREDENTIALS")
if firebase_creds_path and os.path.exists(firebase_creds_path):
    try:
        cred = credentials.Certificate(firebase_creds_path)
        firebase_admin.initialize_app(cred)
        firebase_initialized = True
        print("[Auth] Firebase Admin SDK successfully initialized.")
    except Exception as e:
        print(f"[Auth] Firebase Admin initialization warning: {e}. Falling back to Developer Mode.")
else:
    print("[Auth] No FIREBASE_CREDENTIALS path supplied or file not found. Running in Developer Mode with Mock Auth.")

async def get_current_user(auth_cred: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Dependency injection helper to verify the token in the Authorization header.
    Supports live Firebase ID Token verification and Developer mock mode tokens.
    """
    token = auth_cred.credentials

    # Developer/Mock Token Support
    if token.startswith("mock_token_"):
        # Returns the username from token e.g. mock_token_alice -> alice
        username = token.replace("mock_token_", "").strip().lower()
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Mock token must contain a valid username suffix"
            )
        return username

    # Live Firebase ID Token verification
    if firebase_initialized:
        try:
            decoded_token = auth.verify_id_token(token)
            # Use uid or email prefix as username
            uid = decoded_token.get("uid")
            email = decoded_token.get("email", "")
            username = email.split("@")[0] if email else uid
            return username.lower()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid Firebase ID Token: {str(e)}"
            )
    else:
        # If firebase not set up, treat any token as the username directly for convenience
        return token.strip().lower()
