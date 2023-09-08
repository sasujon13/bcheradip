from django.contrib.auth.backends import ModelBackend
from cheradip.models import Customer
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

class CustomBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            user = Customer.objects.get(username=username)
            return user
        except Customer.DoesNotExist:
            return None
        
        # if user.check_password(password):
        # if Customer.objects.get(password=password):
        #     return user

    def get_user(self, user_id):
        logger.debug(user_id)
        try:
            return Customer.objects.get(pk=user_id)
        except Customer.DoesNotExist:
            return None
