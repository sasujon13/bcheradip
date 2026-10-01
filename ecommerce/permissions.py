from rest_framework.permissions import BasePermission


class IsCommerceAdmin(BasePermission):
    message = 'Commerce administrator access is required.'

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))

