from rest_framework.throttling import SimpleRateThrottle


class CommerceThrottle(SimpleRateThrottle):
    scope = 'commerce'
    rate = '120/hour'

    def get_cache_key(self, request, view):
        identity = f'user:{request.user.pk}' if request.user.is_authenticated else f'ip:{self.get_ident(request)}'
        return self.cache_format % {'scope': f'{self.scope}:{type(view).__name__}', 'ident': identity}


class TrackingThrottle(CommerceThrottle):
    rate = '600/hour'


class ReviewThrottle(CommerceThrottle):
    rate = '30/hour'
