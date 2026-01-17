"""Утилиты для Document Processing Agent."""

from utils.security import (
    validate_email,
    validate_password,
    sanitize_html,
    sanitize_filename,
    mask_sensitive_data,
    RateLimiter,
    login_rate_limiter,
    setup_secure_logging,
)

from utils.auth import (
    require_auth,
    authenticate,
    logout,
    show_user_menu,
    get_current_user,
    create_admin_user,
    check_first_run,
)

__all__ = [
    # Security
    'validate_email',
    'validate_password',
    'sanitize_html',
    'sanitize_filename',
    'mask_sensitive_data',
    'RateLimiter',
    'login_rate_limiter',
    'setup_secure_logging',
    # Auth
    'require_auth',
    'authenticate',
    'logout',
    'show_user_menu',
    'get_current_user',
    'create_admin_user',
    'check_first_run',
]
