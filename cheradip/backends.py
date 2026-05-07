from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Get the custom user model
User = get_user_model()

class CustomBackend(ModelBackend):
    """
    Custom authentication backend that authenticates using username (mobile number)
    and password. Handles both hashed passwords (new users) and plain text passwords (legacy users).
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
            
        try:
            user = User.objects.get(username=username)
            
            # Check if password is hashed (starts with pbkdf2_ or other hash algorithms)
            if user.password.startswith('pbkdf2_') or user.password.startswith('argon2'):
                # Use Django's built-in password checker for hashed passwords
                if user.check_password(password):
                    return user
            else:
                # Legacy: compare plain text passwords (for existing data migration)
                # TODO: Migrate all users to hashed passwords
                if user.password == password:
                    # Migrate to hashed password on successful login
                    user.set_password(password)
                    user.save(update_fields=['password'])
                    return user
            
            return None
        except User.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return None

    def get_user(self, user_id):
        logger.debug(user_id)
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
