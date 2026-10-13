from rest_framework.permissions import BasePermission


class IsCommerceAdmin(BasePermission):
    message = 'Commerce administrator access is required.'

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated or not user.is_staff:
            return False
        if user.is_superuser:
            return True
        model = getattr(view, 'permission_model', None) or getattr(view, 'queryset', None)
        if model is not None and not isinstance(model, type):
            model = getattr(model, 'model', None)
        if model is None:
            return False
        requirements = getattr(view, 'permission_requirements', {}).get(request.method)
        if requirements is not None:
            return all(
                user.has_perm(f'{required_model._meta.app_label}.{required_action}_{required_model._meta.model_name}')
                for required_model, required_action in requirements
            )
        action = 'view' if request.method in {'GET', 'HEAD', 'OPTIONS'} else (
            'add' if request.method == 'POST' and getattr(view, 'action', '') == 'create' else 'change'
        )
        if request.method == 'DELETE':
            action = 'delete'
        return user.has_perm(f'{model._meta.app_label}.{action}_{model._meta.model_name}')

