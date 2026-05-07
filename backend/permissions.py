from rest_framework.permissions import BasePermission, SAFE_METHODS

class IsSuperUserOrStaff(BasePermission):
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and (request.user.is_superuser or request.user.is_staff)


class PublicAccess(BasePermission):

    def has_permission(self, request, view):
        return request.method in SAFE_METHODS
