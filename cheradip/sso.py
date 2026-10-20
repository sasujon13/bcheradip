"""Secure first-party session bridge. Legacy Bearer clients remain supported."""
from urllib.parse import urlsplit
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

COOKIE = '__Secure-cheradip_session'
HOSTS = {'cheradip.com', 'www.cheradip.com', 'ai.cheradip.com', 'tutor.cheradip.com',
         'agent.cheradip.com', 'ailt.cheradip.com', 'ecommerce.cheradip.com'}


def trusted_request(request):
    origin = request.META.get('HTTP_ORIGIN')
    if origin:
        parsed = urlsplit(origin)
        return parsed.scheme == 'https' and parsed.netloc in HOSTS
    return request.method in {'GET', 'HEAD', 'OPTIONS'}


class SharedSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.get_host().split(':')[0] in HOSTS and request.is_secure():
            payload = getattr(response, 'data', None)
            token = payload.get('authToken') if isinstance(payload, dict) else None
            if token and 200 <= response.status_code < 300:
                response.set_cookie(COOKIE, token, max_age=30 * 86400, domain='.cheradip.com',
                                    secure=True, httponly=True, samesite='Lax')
        return response


@csrf_exempt
def session_bridge(request):
    from .views import BearerTokenAuthentication
    from .models import CustomerToken
    if request.method == 'POST':
        if not trusted_request(request):
            return JsonResponse({'error': 'Untrusted origin.'}, status=403)
        auth = BearerTokenAuthentication().authenticate(request)
        if auth:
            CustomerToken.objects.filter(key=auth[1]).delete()
        response = JsonResponse({'loggedIn': False})
        # An old tab may still hold A's token while the shared cookie belongs to B.
        # Revoke the explicit account, never silently log out the other account.
        if not auth or request.COOKIES.get(COOKIE) in (None, auth[1]):
            response.delete_cookie(COOKIE, domain='.cheradip.com', samesite='Lax')
        return response
    if request.method != 'GET' or not trusted_request(request):
        return JsonResponse({'error': 'Method or origin not allowed.'}, status=403)
    cookie_only = request.GET.get('cookie_only') == '1'
    if cookie_only:
        request.META.pop('HTTP_AUTHORIZATION', None)
    auth = BearerTokenAuthentication().authenticate(request)
    if not auth:
        return JsonResponse({'loggedIn': False, 'sharedSessionPresent': bool(request.COOKIES.get(COOKIE))})
    user, token = auth
    return JsonResponse({'loggedIn': True, 'authToken': token, 'username': user.username,
                         'fullName': user.fullName, 'acctype': user.acctype})
