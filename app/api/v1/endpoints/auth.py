from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import deps
from app.database.session import get_db
from app.database.models.user import User
from app.schemas.auth import (
    Token,
    TwoFactorSetupResponse,
    TwoFactorVerifyRequest,
    TwoFactorLoginRequest,
    PasswordChangeRequest,
)
from app.schemas.msg import Msg
from app.services.auth_service import AuthService

router = APIRouter()


@router.post(
    "/login",
    response_model=Token,
    summary="Logowanie użytkownika",
    responses={400: {"description": "Niepoprawny login lub hasło"}, 401: {"description": "Użytkownik nieaktywny"}},
)
async def login_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Logowanie OAuth2 (pobranie tokena dostępu).
    
    - Jeśli użytkownik ma włączone 2FA, zwraca tymczasowy token z flagą `is_2fa_required=True`.
    - Jeśli 2FA jest wyłączone, zwraca pełny token dostępu.
    """
    user = await AuthService.authenticate_user(
        db, form_data.username, form_data.password
    )
    if not user:
        raise HTTPException(status_code=400, detail="Niepoprawny login lub hasło")

    return AuthService.create_login_token(user)


@router.post(
    "/2fa/setup",
    response_model=TwoFactorSetupResponse,
    summary="Konfiguracja 2FA",
    responses={401: {"description": "Brak autoryzacji"}},
)
async def setup_2fa(
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Rozpoczęcie konfiguracji 2FA dla zalogowanego użytkownika.
    
    Generuje nowy sekret TOTP i zwraca:
    - **secret**: Surowy klucz sekretny.
    - **qr_code_url**: URL do generowania kodu QR (provisioning URI).
    - **qr_code_image**: Obraz kodu QR w formacie Base64.
    """
    return await AuthService.setup_2fa(db, current_user)


@router.post(
    "/2fa/verify",
    response_model=Msg,
    summary="Weryfikacja i włączenie 2FA",
    responses={
        400: {"description": "Niepoprawny kod lub brak inicjalizacji 2FA"},
        401: {"description": "Brak autoryzacji"},
    },
)
async def verify_2fa_setup(
    body: TwoFactorVerifyRequest,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Weryfikacja kodu w celu WŁĄCZENIA 2FA.
    
    Wymaga podania poprawnego kodu z aplikacji uwierzytelniającej, 
    aby potwierdzić konfigurację i aktywować 2FA na koncie.
    """
    success = await AuthService.verify_and_enable_2fa(db, current_user, body.code)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid code")

    return {"message": "2FA włączone pomyślnie"}


@router.post(
    "/2fa/login",
    response_model=Token,
    summary="Logowanie 2FA (drugi etap)",
    responses={
        400: {"description": "Niepoprawny kod lub 2FA nieaktywne"},
        401: {"description": "Niepoprawny token lub użytkownik nie znaleziony"},
    },
)
async def login_2fa(
    body: TwoFactorLoginRequest, db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Dokończenie logowania kodem 2FA.
    
    Wymaga:
    - **token**: Tymczasowy token dostępu otrzymany z endpointu `/login`.
    - **code**: Kod TOTP z aplikacji uwierzytelniającej.
    
    Zwraca pełny token dostępu (access token) w przypadku sukcesu.
    """
    return await AuthService.login_2fa(db, body.token, body.code)


@router.post(
    "/change-password",
    response_model=Msg,
    summary="Zmiana hasła",
    responses={
        400: {"description": "Niepoprawne obecne hasło"},
        401: {"description": "Brak autoryzacji"},
    },
)
async def change_password(
    body: PasswordChangeRequest,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Zmiana hasła zalogowanego użytkownika.
    
    Wymaga:
    - **old_password**: Obecne hasło do weryfikacji.
    - **new_password**: Nowe hasło (min. 8 znaków).
    - **confirm_password**: Potwierdzenie nowego hasła (musi pasować).
    """
    await AuthService.change_password(
        db, current_user, body.old_password, body.new_password
    )
    return {"message": "Hasło zmienione pomyślnie"}

