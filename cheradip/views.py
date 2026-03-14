from django.shortcuts import render
from rest_framework import generics, status, viewsets, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from .models import (
    Item,
    Customer,
    OrderDetail,
    Transaction,
    Notification,
    Country,
    Location,
    JsonData,
)
from .serializers import (
    ItemSerializer,
    CustomerSignupSerializer,
    CustomerUpdateSerializer,
    CustomerSerializer,
    NotificationSerializer,
    CountrySerializer,
    CountryListSerializer,
)
from rest_framework.permissions import AllowAny
from .permissions import IsSuperUserOrStaff, PublicAccess
from .location import Bangladesh
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import check_password
from django.views.decorators.csrf import csrf_exempt
import logging, random, string, json, requests, os, re, csv, time
from urllib import parse as urllib_parse
from urllib.parse import quote
from rest_framework.decorators import action
from django.conf import settings
from django.db.models import Q
from django.db.models.expressions import RawSQL
from django.db.utils import ProgrammingError, OperationalError

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


# ==============================================================================
# COUNTRY VIEWSET
# ==============================================================================

class CountryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Country model with search, autocomplete, and geolocation detection.
    
    Endpoints:
    - GET /api/countries/ - List all countries (lightweight, unpaginated)
    - GET /api/countries/{country_code}/ - Get single country (full details)
    - GET /api/countries/?search=bang - Search countries
    - GET /api/countries/?featured=true - Get featured countries
    - GET /api/countries/detect/ - Detect country from IP
    """
    queryset = Country.objects.filter(is_active=True)
    serializer_class = CountrySerializer
    lookup_field = 'country_code'
    pagination_class = None  # Return full list for dropdowns/options
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['country_name', 'country_name_native', 'country_code', 'phone_code']
    ordering_fields = ['display_order', 'country_name']
    ordering = ['display_order', 'country_name']
    
    def get_serializer_class(self):
        """Use lightweight serializer for list, full for detail"""
        if self.action == 'list':
            return CountryListSerializer
        return CountrySerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        # Avoid loading datetime columns (MySQL/PyMySQL can return them as str → 'utcoffset' error)
        queryset = queryset.defer('created_at', 'updated_at')

        # Filter by featured
        featured = self.request.query_params.get('featured')
        if featured and featured.lower() == 'true':
            queryset = queryset.filter(is_featured=True)
        
        # Filter by continent
        continent = self.request.query_params.get('continent')
        if continent:
            queryset = queryset.filter(continent__iexact=continent)
        
        # Custom search parameter
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(country_name__icontains=search) |
                Q(country_name_native__icontains=search) |
                Q(country_code__iexact=search) |
                Q(phone_code__icontains=search)
            )
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def detect(self, request):
        """
        Detect user's country based on IP address.
        Uses multiple fallback services for reliability.
        """
        # Get client IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        
        # Skip detection for localhost
        if ip in ['127.0.0.1', 'localhost', '::1']:
            # Return Bangladesh as default for localhost
            try:
                country = Country.objects.defer('created_at', 'updated_at').get(country_code='BD')
                serializer = CountrySerializer(country)
                return Response({
                    'detected': True,
                    'ip': ip,
                    'country': serializer.data,
                    'source': 'default'
                })
            except Country.DoesNotExist:
                return Response({
                    'detected': False,
                    'ip': ip,
                    'error': 'Default country not found'
                })
        
        # Try multiple geolocation services
        country_code = None
        source = None
        
        # Service 1: ipapi.co
        try:
            response = requests.get(f'https://ipapi.co/{ip}/country/', timeout=5)
            if response.status_code == 200:
                country_code = response.text.strip().upper()
                source = 'ipapi.co'
        except:
            pass
        
        # Service 2: ip-api.com (fallback)
        if not country_code:
            try:
                response = requests.get(f'http://ip-api.com/json/{ip}?fields=countryCode', timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    country_code = data.get('countryCode', '').upper()
                    source = 'ip-api.com'
            except:
                pass
        
        # Return detected country
        if country_code:
            try:
                country = Country.objects.defer('created_at', 'updated_at').get(country_code=country_code)
                serializer = CountrySerializer(country)
                return Response({
                    'detected': True,
                    'ip': ip,
                    'country': serializer.data,
                    'source': source
                })
            except Country.DoesNotExist:
                return Response({
                    'detected': False,
                    'ip': ip,
                    'country_code': country_code,
                    'error': 'Country not in database'
                })
        
        # Fallback to default (Bangladesh)
        try:
            country = Country.objects.defer('created_at', 'updated_at').get(country_code='BD')
            serializer = CountrySerializer(country)
            return Response({
                'detected': False,
                'ip': ip,
                'country': serializer.data,
                'source': 'default',
                'error': 'Could not detect country'
            })
        except Country.DoesNotExist:
            return Response({
                'detected': False,
                'ip': ip,
                'error': 'Detection failed and no default country'
            })
    
    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Get featured countries for quick selection"""
        countries = Country.objects.filter(is_active=True, is_featured=True).order_by('display_order').defer('created_at', 'updated_at')
        serializer = CountryListSerializer(countries, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_continent(self, request):
        """Get countries grouped by continent"""
        continents = Country.objects.filter(is_active=True).values_list('continent', flat=True).distinct()
        result = {}
        for continent in continents:
            if continent:
                countries = Country.objects.filter(is_active=True, continent=continent).order_by('country_name').defer('created_at', 'updated_at')
                result[continent] = CountryListSerializer(countries, many=True).data
        return Response(result)


class AllCountriesView(APIView):
    """GET /api/country/ - Return all active countries as array (for <option> dropdowns)."""
    def get(self, request):
        countries = Country.objects.filter(is_active=True).order_by('display_order', 'country_name').defer('created_at', 'updated_at')
        serializer = CountryListSerializer(countries, many=True)
        return Response(serializer.data)


class LocationDivisionsView(APIView):
    """
    GET /api/locations/divisions/?country_code=BD
    Returns distinct division names from cheradip_location for the given country.
    """
    permission_classes = [PublicAccess]
    authentication_classes = []

    def get(self, request):
        country_code = (request.query_params.get('country_code') or '').strip().upper()
        if not country_code:
            return Response([], status=status.HTTP_200_OK)
        qs = Location.objects.filter(country_id=country_code).exclude(
            division__isnull=True
        ).exclude(division='').values_list('division', flat=True).distinct().order_by('division')
        return Response(list(qs))


class LocationDistrictsView(APIView):
    """
    GET /api/locations/districts/?country_code=BD&division=Dhaka
    Returns distinct district names from cheradip_location for the given country and division.
    """
    permission_classes = [PublicAccess]
    authentication_classes = []

    def get(self, request):
        country_code = (request.query_params.get('country_code') or '').strip().upper()
        division = (request.query_params.get('division') or '').strip()
        if not country_code or not division:
            return Response([], status=status.HTTP_200_OK)
        qs = Location.objects.filter(
            country_id=country_code, division=division
        ).exclude(district__isnull=True).exclude(district='').values_list(
            'district', flat=True
        ).distinct().order_by('district')
        return Response(list(qs))


class LocationThanasView(APIView):
    """
    GET /api/locations/thanas/?country_code=BD&division=Dhaka&district=Dhaka
    Returns distinct thana names from cheradip_location for the given country, division, district.
    """
    permission_classes = [PublicAccess]
    authentication_classes = []

    def get(self, request):
        country_code = (request.query_params.get('country_code') or '').strip().upper()
        division = (request.query_params.get('division') or '').strip()
        district = (request.query_params.get('district') or '').strip()
        if not country_code or not division or not district:
            return Response([], status=status.HTTP_200_OK)
        qs = Location.objects.filter(
            country_id=country_code, division=division, district=district
        ).exclude(thana__isnull=True).exclude(thana='').values_list(
            'thana', flat=True
        ).distinct().order_by('thana')
        return Response(list(qs))


# ==============================================================================
# JOB DB VIEWSETS (cheradip_job – NTRCA merit/vacancy/recommend, institutes, banbeis, token)
# ==============================================================================

from .models import (
    Merit5, Merit6, Merit7,
    Vacancy5, Vacancy6, Vacancy7,
    Recommend5, Recommend6, Recommend7,
    Banbeis, Institutes, Token,
)
from .serializers import (
    Merit5Serializer, Merit6Serializer, Merit7Serializer,
    Vacancy5Serializer, Vacancy6Serializer, Vacancy7Serializer,
    Recommend5Serializer, Recommend6Serializer, Recommend7Serializer,
    BanbeisSerializer, InstitutesSerializer, TokenSerializer,
)
from rest_framework.pagination import PageNumberPagination


class JobListPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 500


class _MeritViewSetMixin:
    """Filter merit list by query param code= (designation code)."""
    pagination_class = JobListPagination
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = super().get_queryset()
        code = self.request.query_params.get('code')
        if code is not None and code != '':
            qs = qs.filter(Code=code)
        return qs.order_by('SL')


class Merit5ViewSet(_MeritViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Merit5.objects.all()
    serializer_class = Merit5Serializer


class Merit6ViewSet(_MeritViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Merit6.objects.all()
    serializer_class = Merit6Serializer


class Merit7ViewSet(_MeritViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Merit7.objects.all()
    serializer_class = Merit7Serializer


class _VacancyViewSetMixin:
    pagination_class = JobListPagination
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = super().get_queryset()
        designation = self.request.query_params.get('designation')
        if designation:
            qs = qs.filter(Designation__iexact=designation)
        subject = self.request.query_params.get('subject')
        if subject:
            qs = qs.filter(Subject__iexact=subject)
        districts = self.request.query_params.getlist('district')
        if districts:
            qs = qs.filter(District__in=districts)
        return qs


class Vacancy5ViewSet(_VacancyViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Vacancy5.objects.all()
    serializer_class = Vacancy5Serializer


class Vacancy6ViewSet(_VacancyViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Vacancy6.objects.all()
    serializer_class = Vacancy6Serializer


class Vacancy7ViewSet(_VacancyViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Vacancy7.objects.all()
    serializer_class = Vacancy7Serializer


class _RecommendViewSetMixin:
    pagination_class = JobListPagination
    permission_classes = [AllowAny]


class Recommend5ViewSet(_RecommendViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Recommend5.objects.all()
    serializer_class = Recommend5Serializer


class Recommend6ViewSet(_RecommendViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Recommend6.objects.all()
    serializer_class = Recommend6Serializer


class Recommend7ViewSet(_RecommendViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Recommend7.objects.all()
    serializer_class = Recommend7Serializer


class BanbeisViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Banbeis.objects.all()
    serializer_class = BanbeisSerializer
    pagination_class = JobListPagination
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = super().get_queryset()
        eiin = self.request.query_params.get('eiin')
        if eiin is not None and str(eiin).strip() != '':
            try:
                eiin_int = int(str(eiin).strip())
                qs = qs.filter(EIIN=eiin_int)
            except (ValueError, TypeError):
                pass
        return qs


class InstitutesViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Institutes.objects.all()
    serializer_class = InstitutesSerializer
    pagination_class = JobListPagination
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = [
        'instituteName', 'instituteNameBn', 'eiinNo', 'districtName', 'thanaName',
        'mobile', 'mobileAlternate', 'divisionName', 'divisionNameBn', 'districtNameBn',
        'thanaNameBn', 'instituteTypeName', 'instituteTypeNameBn', 'mouzaName', 'mouzaNameBn', 'email'
    ]

    def get_queryset(self):
        qs = super().get_queryset()
        # Optional search query param ?q= – match if any of these fields contains the term
        q = self.request.query_params.get('q')
        if q and str(q).strip():
            q = str(q).strip()
            q_any = (
                Q(eiinNo__icontains=q) |
                Q(mobile__icontains=q) |
                Q(mobileAlternate__icontains=q) |
                Q(instituteName__icontains=q) |
                Q(instituteNameBn__icontains=q) |
                Q(divisionName__icontains=q) |
                Q(divisionNameBn__icontains=q) |
                Q(districtName__icontains=q) |
                Q(districtNameBn__icontains=q) |
                Q(thanaName__icontains=q) |
                Q(thanaNameBn__icontains=q) |
                Q(instituteTypeName__icontains=q) |
                Q(instituteTypeNameBn__icontains=q) |
                Q(mouzaName__icontains=q) |
                Q(mouzaNameBn__icontains=q) |
                Q(email__icontains=q)
            )
            if q.isdigit():
                q_any = q_any | Q(id=int(q)) | Q(year=int(q))
            q_lower = q.lower()
            if q_lower in ('true', 'govt', 'government', 'yes', '1'):
                q_any = q_any | Q(isGovt=True)
            elif q_lower in ('false', 'non govt', 'no', '0'):
                q_any = q_any | Q(isGovt=False)
            qs = qs.filter(q_any)
        # Filter by type/division/district/thana (e.g. from institute filter UI)
        for param, field in [
            ('instituteTypeName', 'instituteTypeName'),
            ('divisionName', 'divisionName'),
            ('districtName', 'districtName'),
            ('thanaName', 'thanaName'),
        ]:
            values = self.request.query_params.getlist(param)
            values = [v.strip() for v in values if v and str(v).strip()]
            if values:
                qs = qs.filter(**{f'{field}__in': values})
        return qs

    @action(detail=False, url_path='unique_types', methods=['get'])
    def unique_types(self, request):
        """GET /api/institutes/unique_types/ – return all unique instituteTypeName from cheradip_institutes."""
        values = (
            Institutes.objects
            .values_list('instituteTypeName', flat=True)
            .distinct()
            .order_by('instituteTypeName')
        )
        # Exclude null/blank, return as list
        types = [v for v in values if v and str(v).strip()]
        return Response(types)

    @action(detail=False, url_path='unique_divisions', methods=['get'])
    def unique_divisions(self, request):
        """GET /api/institutes/unique_divisions/ – return all unique divisionName from cheradip_institutes."""
        values = (
            Institutes.objects
            .values_list('divisionName', flat=True)
            .distinct()
            .order_by('divisionName')
        )
        divisions = [v for v in values if v and str(v).strip()]
        return Response(divisions)

    @action(detail=False, url_path='unique_districts', methods=['get'])
    def unique_districts(self, request):
        """GET /api/institutes/unique_districts/?divisionName=Rangpur – unique districtName for that divisionName."""
        division_names = request.query_params.getlist('divisionName')
        division_names = [d.strip() for d in division_names if d and str(d).strip()]
        qs = Institutes.objects.all()
        if division_names:
            qs = qs.filter(divisionName__in=division_names)
        values = qs.values_list('districtName', flat=True).distinct().order_by('districtName')
        districts = [v for v in values if v and str(v).strip()]
        return Response(districts)

    @action(detail=False, url_path='unique_thanas', methods=['get'])
    def unique_thanas(self, request):
        """GET /api/institutes/unique_thanas/?districtName=Dinajpur – unique thanaName for that districtName."""
        district_names = request.query_params.getlist('districtName')
        district_names = [d.strip() for d in district_names if d and str(d).strip()]
        qs = Institutes.objects.all()
        if district_names:
            qs = qs.filter(districtName__in=district_names)
        values = qs.values_list('thanaName', flat=True).distinct().order_by('thanaName')
        thanas = [v for v in values if v and str(v).strip()]
        return Response(thanas)


class InstituteDetailView(APIView):
    """GET /api/institute/?eiin=XXX – return one institute (Institutes or Banbeis by EIIN) for unlock details."""
    permission_classes = [AllowAny]

    def get(self, request):
        eiin = request.query_params.get('eiin')
        if not eiin:
            return Response({}, status=status.HTTP_400_BAD_REQUEST)
        eiin_str = str(eiin).strip()
        # Try Institutes first (PK eiinNo) – routed to job DB
        try:
            inst = Institutes.objects.get(eiinNo=eiin_str)
            serializer = InstitutesSerializer(inst)
            return Response({'results': [serializer.data]})
        except Institutes.DoesNotExist:
            pass
        # Fallback: Banbeis by EIIN (bigint) – routed to job DB
        try:
            eiin_int = int(eiin_str)
            banbeis = Banbeis.objects.filter(EIIN=eiin_int).first()
            if banbeis:
                serializer = BanbeisSerializer(banbeis)
                return Response({'results': [serializer.data]})
        except (ValueError, TypeError):
            pass
        return Response({}, status=status.HTTP_404_NOT_FOUND)


SITEMAP_URLS_PER_FILE = 50000  # Sitemap spec limit

# XSL so browsers render sitemap XML as a readable page (removes "no style information" message)
SITEMAP_XSL = '''<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform" xmlns:sm="http://www.sitemaps.org/schemas/sitemap/0.9">
  <xsl:output method="html" doctype-system="about:legacy-compat" encoding="UTF-8"/>
  <xsl:template match="/">
    <html>
      <head><meta charset="UTF-8"/><title>Sitemap</title>
        <style>
          body { font-family: system-ui, sans-serif; margin: 1rem 2rem; background: #f5f5f5; }
          h1 { color: #333; }
          table { border-collapse: collapse; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
          th, td { padding: .5rem .75rem; text-align: left; border-bottom: 1px solid #eee; }
          th { background: #1976d2; color: #fff; }
          a { color: #1976d2; }
          tr:hover { background: #f9f9f9; }
        </style>
      </head>
      <body>
        <h1>Sitemap</h1>
        <xsl:choose>
          <xsl:when test="sm:sitemapindex">
            <table><tr><th>#</th><th>Sitemap</th></tr>
              <xsl:for-each select="sm:sitemapindex/sm:sitemap">
                <tr><td><xsl:value-of select="position()"/></td>
                  <td><a><xsl:attribute name="href"><xsl:value-of select="sm:loc"/></xsl:attribute><xsl:value-of select="sm:loc"/></a></td></tr>
              </xsl:for-each>
            </table>
          </xsl:when>
          <xsl:otherwise>
            <table><tr><th>#</th><th>URL</th></tr>
              <xsl:for-each select="sm:urlset/sm:url">
                <tr><td><xsl:value-of select="position()"/></td>
                  <td><a><xsl:attribute name="href"><xsl:value-of select="sm:loc"/></xsl:attribute><xsl:value-of select="sm:loc"/></a></td></tr>
              </xsl:for-each>
            </table>
          </xsl:otherwise>
        </xsl:choose>
      </body>
    </html>
  </xsl:template>
</xsl:stylesheet>'''


def _sitemap_base_url(request):
    """Base URL for sitemap. Set SITEMAP_BASE_URL in settings for production (e.g. https://cheradip.com)."""
    base = getattr(settings, 'SITEMAP_BASE_URL', None)
    if base:
        return base.rstrip('/')
    # Local dev: point to Angular app so sitemap URLs are openable (default 4200)
    if getattr(settings, 'DEBUG', False):
        return 'http://localhost:4200'
    return request.build_absolute_uri('/').rstrip('/') or 'https://cheradip.com'


def _sitemap_static_pages(base_url):
    """Yield <url> lines for all navigable app routes (fcheradip), in hierarchical order."""
    # Grouped so sitemap is easy to scan; comments mark sections.
    sections = [
        ('Home', ['index']),
        ('Products / Shop', ['packages', 'books', 'cart', 'choice', 'order']),
        ('User / Account', ['about_us', 'faqs', 'live_chat', 'login', 'auth', 'admin', 'profile', 'password', 'mobile', 'myorder']),
        ('NTRCA', ['ntrca', 'institute', 'institutes', 'vacant7', 'vacant5', 'vacant6', 'merit7', 'merit5', 'merit6', 'recommend7', 'recommend5', 'recommend6']),
        ('Student', ['student', 'student/dashboard', 'student/liveexam', 'student/archive', 'student/report', 'student/stats', 'student/leaderboard', 'student/tutor']),
        ('Question Bank', ['question']),
        ('Other', ['scrape']),
    ]
    for label, paths in sections:
        yield f'  <!-- {label} -->'
        for path in paths:
            loc = f'{base_url}/{path}' if path else base_url
            yield f'  <url><loc>{loc}</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>'


def _sitemap_slug_for_url(slug):
    """Encode slug for URL in sitemap: keep Bengali/Unicode as literal; encode space, %, &, etc."""
    if not slug:
        return slug
    return slug.replace('%', '%25').replace('&', '%26').replace(' ', '%20')


def _sitemap_institute_url_entries(base_url):
    """Yield <url>...</url> lines for all institutes: EIIN-only, EIIN-English name, EIIN-Bengali name.
    Bengali and other Unicode appear as literal characters in the XML (UTF-8) so they display correctly."""
    for inst in Institutes.objects.all().values('eiinNo', 'instituteName', 'instituteNameBn').iterator(chunk_size=5000):
        eiin = (inst.get('eiinNo') or '').strip()
        if not eiin:
            continue
        name_en = (inst.get('instituteName') or '').strip()
        name_bn = (inst.get('instituteNameBn') or '').strip()
        yield f'  <url><loc>{base_url}/institutes/{_sitemap_slug_for_url(eiin)}</loc><changefreq>weekly</changefreq></url>'
        if name_en:
            slug_en = f"{eiin}-{name_en}"
            yield f'  <url><loc>{base_url}/institutes/{_sitemap_slug_for_url(slug_en)}</loc><changefreq>weekly</changefreq></url>'
        if name_bn:
            slug_bn = f"{eiin}-{name_bn}"
            yield f'  <url><loc>{base_url}/institutes/{_sitemap_slug_for_url(slug_bn)}</loc><changefreq>weekly</changefreq></url>'


def sitemap_xsl(request):
    """Serve XSL stylesheet so browsers render sitemap XML as a readable page."""
    return HttpResponse(SITEMAP_XSL.encode('utf-8'), content_type='application/xml; charset=utf-8')


def sitemap_pages(request):
    """Serve sitemap_pages.xml: all static app URLs from fcheradip (hierarchical)."""
    base = _sitemap_base_url(request)
    url_lines = list(_sitemap_static_pages(base))
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<?xml-stylesheet type="text/xsl" href="sitemap.xsl"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + '\n'.join(url_lines) + '\n'
        '</urlset>'
    )
    return HttpResponse(xml.encode('utf-8'), content_type='application/xml; charset=utf-8')


def sitemap_institutes(request):
    """Serve sitemap index at sitemap.xml: pages first, then institute parts (111k+ URLs)."""
    base = _sitemap_base_url(request)
    # Hierarchy: 1) App pages, 2) Institute detail URLs (3 parts)
    index_lines = [
        f'  <sitemap><loc>{base}/sitemap_pages.xml</loc></sitemap>',
        f'  <sitemap><loc>{base}/sitemap_institutes_1.xml</loc></sitemap>',
        f'  <sitemap><loc>{base}/sitemap_institutes_2.xml</loc></sitemap>',
        f'  <sitemap><loc>{base}/sitemap_institutes_3.xml</loc></sitemap>',
    ]
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<?xml-stylesheet type="text/xsl" href="sitemap.xsl"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + '\n'.join(index_lines) + '\n'
        '</sitemapindex>'
    )
    return HttpResponse(xml.encode('utf-8'), content_type='application/xml; charset=utf-8')


def sitemap_institutes_part(request, page):
    """Serve one sitemap part (page 1, 2, or 3) with up to 50,000 institute URLs."""
    if page not in (1, 2, 3):
        return HttpResponse(status=404)
    base = _sitemap_base_url(request)
    skip = (page - 1) * SITEMAP_URLS_PER_FILE
    take = SITEMAP_URLS_PER_FILE
    url_lines = []
    try:
        for line in _sitemap_institute_url_entries(base):
            if skip > 0:
                skip -= 1
                continue
            url_lines.append(line)
            if len(url_lines) >= take:
                break
    except Exception as e:
        logger.warning("Sitemap part %s generation failed: %s", page, e)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<?xml-stylesheet type="text/xsl" href="sitemap.xsl"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + '\n'.join(url_lines) + '\n'
        '</urlset>'
    )
    return HttpResponse(xml.encode('utf-8'), content_type='application/xml; charset=utf-8')


class TokenViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Token.objects.all()
    serializer_class = TokenSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = super().get_queryset()
        token_val = self.request.query_params.get('token')
        if token_val is not None and token_val != '':
            try:
                qs = qs.filter(Token=int(token_val))
            except (ValueError, TypeError):
                qs = qs.none()
        return qs

    def list(self, request, *args, **kwargs):
        token_val = request.query_params.get('token')
        if token_val is not None and token_val != '':
            # Validate single token: return one result + success/counter for back.ts and vacant6
            qs = self.get_queryset()
            obj = qs.first()
            try:
                counter_int = int(obj.Counter) if obj and obj.Counter not in (None, '') else 0
            except (ValueError, TypeError):
                counter_int = 0
            status_ok = getattr(obj, 'Status', 0) == 0 if obj else False
            success = bool(obj and status_ok and counter_int > 0)
            serializer = self.get_serializer(qs, many=True)
            data = {
                'count': 1 if obj else 0,
                'results': serializer.data,
                'success': success,
                'counter': counter_int if success else 0,
            }
            return Response(data)
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='update_status')
    def update_status(self, request, pk=None):
        """Set Status=1 (used) for this token. Body: { \"Status\": 1 }."""
        token_obj = self.get_object()
        token_obj.Status = 1
        token_obj.save(update_fields=['Status'])
        return Response({'success': True})

    def create(self, request, *args, **kwargs):
        """Use one token unlock: POST { token, eiin }. Decrements Counter, returns { success, remaining }."""
        token_val = request.data.get('token')
        eiin = request.data.get('eiin')
        if not token_val:
            return Response({'success': False, 'remaining': 0}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token_int = int(token_val)
        except (ValueError, TypeError):
            return Response({'success': False, 'remaining': 0}, status=status.HTTP_400_BAD_REQUEST)
        obj = Token.objects.filter(Token=token_int).first()
        if not obj:
            return Response({'success': False, 'remaining': 0})
        try:
            counter_int = int(obj.Counter) if obj.Counter not in (None, '') else 0
        except (ValueError, TypeError):
            counter_int = 0
        if getattr(obj, 'Status', 0) != 0 or counter_int <= 0:
            return Response({'success': False, 'remaining': 0})
        counter_int -= 1
        obj.Counter = str(counter_int)
        obj.save(update_fields=['Counter'])
        return Response({'success': True, 'remaining': counter_int})


class ItemListCreateView(generics.ListCreateAPIView):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer

    def get_permissions(self):
        if self.request.method in ['GET', 'HEAD', 'OPTIONS']:
            return [PublicAccess()]
        else:
            return [IsSuperUserOrStaff()]
            
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)

        # Update image URLs to include 'manage' prefix
        for item_data in response.data:
            if 'image' in item_data and item_data['image']:
                item_data['image'] = f'{settings.HOST_URL}/manage/media/{item_data["image"].split("/media/")[-1]}'

        return response

@api_view(['GET'])
@permission_classes([IsSuperUserOrStaff])
def item_list(request):
    items = Item.objects.all()
    serializer = ItemSerializer(items, many=True)
    return Response(serializer.data) 


class CustomerCreateView(APIView):
    """
    Signup: create one Customer row in cheradip_customers for Student, Teacher, or Job Seeker.
    Same table and same endpoint for all account types.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def _get(self, raw, key, default=None):
        v = raw.get(key, default)
        return v[0] if isinstance(v, (list, tuple)) and len(v) else v

    @staticmethod
    def _normalize_acctype(value):
        """Normalize acctype to model choice: Student, Teacher, JobSeeker."""
        if not value or not str(value).strip():
            return 'Student'
        v = str(value).strip()
        if v == 'Job Seeker':
            return 'JobSeeker'
        return v

    @staticmethod
    def _date_to_iso(value):
        """Accept DD/MM/YYYY or YYYY-MM-DD; return YYYY-MM-DD for serializer, or None if invalid/empty."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        s = str(value).strip()
        if not s:
            return None
        # Already ISO (YYYY-MM-DD)
        if len(s) == 10 and s[4] == '-' and s[7] == '-':
            return s
        # DD/MM/YYYY
        parts = s.split('/')
        if len(parts) == 3:
            try:
                d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                if 1 <= d <= 31 and 1 <= m <= 12 and 1900 <= y <= 2100:
                    return f'{y:04d}-{m:02d}-{d:02d}'
            except (ValueError, TypeError):
                pass
        return None

    def post(self, request, *args, **kwargs):
        raw = request.data
        acctype = self._normalize_acctype(self._get(raw, 'acctype', 'Student'))
        country_code = self._get(raw, 'country_code') or self._get(raw, 'countryCode') or 'US'
        date_of_birth = self._date_to_iso(self._get(raw, 'date_of_birth'))
        user_data = {
            'acctype': acctype,  # Student | Teacher | JobSeeker
            'fullName': self._get(raw, 'fullName', ''),
            'username': self._get(raw, 'username', ''),
            'password': self._get(raw, 'password', ''),
            'country_code': country_code,
            'date_of_birth': date_of_birth,
            'class_name': self._get(raw, 'class_name'),
            'group': self._get(raw, 'group'),
            'department': self._get(raw, 'department'),
            'teacher_level': self._get(raw, 'teacher_level'),
            'teacher_subject_code': self._get(raw, 'teacher_subject_code'),
            'teacher_department_code': self._get(raw, 'teacher_department_code'),
            'teacher_department_name': self._get(raw, 'teacher_department_name'),
            'gender': self._get(raw, 'gender', 'Male'),
            'email': self._get(raw, 'email'),
        }
        serializer = CustomerSignupSerializer(data=user_data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            serializer.save()
            if acctype == 'Teacher':
                tcode = self._get(raw, 'teacher_department_code', '')
                tname = self._get(raw, 'teacher_department_name', '')
                if (tcode or '').strip().upper() == 'OTHER' and (tname or '').strip():
                    _append_department_to_json((tname or '').strip(), None)
        except Exception as e:
            logger.exception('Signup save failed: %s', e)
            err_msg = 'Signup failed. Please try again.'
            if getattr(settings, 'DEBUG', False):
                err_msg = str(e)
            return Response({'detail': err_msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        token = self.generate_unique_key()
        return Response({'authToken': token}, status=status.HTTP_200_OK)

    def generate_unique_key(self):
        length = 40
        characters = string.ascii_letters + string.digits
        return ''.join(random.choice(characters) for _ in range(length))


class SignupProfileView(APIView):
    """
    GET /api/signup_profile/?username=xxx&acctype=Teacher|Student|JobSeeker
    Returns profile data from Customer table. Password is never returned.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        username = request.query_params.get('username')
        acctype = (request.query_params.get('acctype') or '').strip()
        if not username:
            return Response({'detail': 'username is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            q = Customer.objects.filter(username=username)
            if acctype and acctype in ('Teacher', 'Student', 'JobSeeker'):
                q = q.filter(acctype=acctype)
            obj = q.first()
            if not obj:
                return Response({'detail': 'Profile not found for this username and account type.'}, status=status.HTTP_404_NOT_FOUND)
            data = {
                'acctype': obj.acctype,
                'fullName': obj.fullName,
                'username': obj.username,
                'date_of_birth': obj.date_of_birth.isoformat() if obj.date_of_birth else None,
                'class_name': getattr(obj, 'class_name', None),
                'group': obj.group,
                'department': getattr(obj, 'department', None),
                'teacher_level': getattr(obj, 'teacher_level', None),
                'teacher_subject_code': getattr(obj, 'teacher_subject_code', None),
                'teacher_department_code': getattr(obj, 'teacher_department_code', None),
                'teacher_department_name': getattr(obj, 'teacher_department_name', None),
                'gender': obj.gender,
                'email': obj.email,
                'country_code': getattr(obj, 'country_code', None),
                'division': obj.division,
                'district': obj.district,
                'thana': obj.thana,
                'union': obj.union,
                'village': obj.village,
                'date_joined': obj.date_joined.isoformat() if obj.date_joined else None,
            }
            return Response(data, status=status.HTTP_200_OK)
        except Customer.DoesNotExist:
            return Response({'detail': 'Profile not found for this username and account type.'}, status=status.HTTP_404_NOT_FOUND)


class CustomerRetrieveView(APIView):
    """Login: authenticate against Customer only. Optional country_code filter on username lookup."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        username = request.data.get('username')
        password = request.data.get('password')
        raw_country = request.data.get('countryCode') or request.data.get('country_code')
        if hasattr(raw_country, 'get'):
            country_code = (raw_country.get('country_code') or raw_country.get('countryCode') or '').strip().upper() or None
        else:
            country_code = (str(raw_country).strip().upper() or None) if raw_country else None
        if not username or not password:
            return Response({'error': 'Username and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        user = None
        try:
            if country_code:
                user = Customer.objects.filter(username=username, country_code=country_code).first()
                if user and not user.check_password(password):
                    user = None
            else:
                user = authenticate(request, username=username, password=password)
        except (ProgrammingError, OperationalError):
            user = None
        if user is not None:
            acctype = getattr(user, 'acctype', None)
            fullName = getattr(user, 'fullName', None)
            group = getattr(user, 'group', None)
            gender = getattr(user, 'gender', None)
            division = getattr(user, 'division', None)
            district = getattr(user, 'district', None)
            thana = getattr(user, 'thana', None)
            union = getattr(user, 'union', None)
            village = getattr(user, 'village', None)
            token = self.generate_unique_key()
            return Response({
                'authToken': token,
                'acctype': acctype,
                'fullName': fullName,
                'username': user.username,
                'group': group,
                'gender': gender,
                'division': division,
                'district': district,
                'thana': thana,
                'union': union,
                'village': village,
            }, status=status.HTTP_200_OK)

        return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

    def generate_unique_key(self):
        length = 40
        characters = string.ascii_letters + string.digits
        return ''.join(random.choice(characters) for _ in range(length))

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            customer_data = {
                'username': request.user.username,
                'fullName': getattr(request.user, 'fullName', getattr(request.user, 'full_name', '')),
            }
            return Response(customer_data, status=status.HTTP_200_OK)
        return Response({'error': 'Not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)



class CustomerUpdateView(APIView):
    def post(self, request, *args, **kwargs):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        serializer = CustomerUpdateSerializer(user, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        token = self.generate_unique_key()
        return Response({'authToken': token, 'token': token}, status=status.HTTP_200_OK)

    def generate_unique_key(self):
        length = 40
        characters = string.ascii_letters + string.digits
        return ''.join(random.choice(characters) for _ in range(length))

class CustomerResetView(APIView):
    def post(self, request, *args, **kwargs):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            serializer = CustomerSerializer(user, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response({'message': 'Password reset successfully'}, status=status.HTTP_200_OK)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """List notifications for the header marquee. GET /api/notification/. Returns last 10 by id (newest first)."""
    serializer_class = NotificationSerializer
    pagination_class = None

    def get_queryset(self):
        return Notification.objects.all().order_by('-id')[:10]


class MobileNumberExistsView(APIView):
    """Check username (mobile) in Customer table. Optional country_code filter. Returns exists and found_in='customer' when found."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        username = request.query_params.get('username')
        country_code = (request.query_params.get('countryCode') or request.query_params.get('country_code') or '').strip().upper() or None

        if not username:
            return Response({'exists': False}, status=status.HTTP_200_OK)
        q = Q(username=username)
        if country_code:
            q &= Q(country_code=country_code)
        if Customer.objects.filter(q).exists():
            return Response({'exists': True, 'found_in': 'customer'}, status=status.HTTP_200_OK)
        return Response({'exists': False}, status=status.HTTP_200_OK)


class PasswordExistsView(APIView):
    """Check username+password in Customer table. Optional country_code filter."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        username = request.query_params.get('username')
        password = request.query_params.get('password')
        country_code = (request.query_params.get('countryCode') or request.query_params.get('country_code') or '').strip().upper() or None

        if not username or not password:
            return Response({'exists': False}, status=status.HTTP_200_OK)
        q = Q(username=username)
        if country_code:
            q &= Q(country_code=country_code)
        try:
            customer = Customer.objects.filter(q).first()
            if customer and customer.check_password(password):
                return Response({'exists': True}, status=status.HTTP_200_OK)
        except (ProgrammingError, OperationalError):
            pass
        return Response({'exists': False}, status=status.HTTP_200_OK)
    

@csrf_exempt
def save_json_data(request):
    """Store JSON payload in JsonData; optionally link/update Transaction by trxid+paidFrom."""
    if request.method != 'POST':
        return JsonResponse({'message': 'Invalid request method'}, status=405)
    try:
        body = json.loads(request.body.decode('utf-8'))
        trxid = body.pop('trxid', None)
        paidFrom = body.pop('paidFrom', None)
        username = body.get('username', None)
        transaction = None
        if trxid and paidFrom:
            try:
                transaction = Transaction.objects.get(trxid=trxid, paidFrom=paidFrom)
            except Transaction.DoesNotExist:
                pass
        if transaction and username and transaction.username != username:
            transaction.username = username
            transaction.save(update_fields=['username'])
        JsonData.objects.create(
            data=body,
            data_type='order_submission',
            description=username or trxid or 'save_json_data',
        )
        return JsonResponse({'message': 'Data saved successfully'}, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
def run_scraper(request):
    """Proxy scraper: fetch paginated API (from frontend config), return combined JSON."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        import time
        body = json.loads(request.body.decode('utf-8'))
        base_url = (body.get('base_url') or '').strip()
        params = body.get('params') or {}
        headers = body.get('headers') or {}
        page_param = (body.get('page_param') or 'page').strip() or 'page'
        delay_seconds = float(body.get('delay_seconds') or 1)
        delay_seconds = max(0, min(10, delay_seconds))
        chapter_name = body.get('chapter_name') or 'scraped_data'

        if not base_url:
            return JsonResponse({'error': 'base_url is required'}, status=400)

        # Normalize params: ensure page_param is not in params yet for first request
        req_params = dict(params) if isinstance(params, dict) else {}
        if not isinstance(params, dict):
            req_params = {}
            for item in params if isinstance(params, list) else []:
                k = item.get('key') or item.get('name')
                v = item.get('value')
                if k:
                    req_params[k] = v

        all_data = []
        page = 1
        while True:
            req_params[page_param] = page
            resp = requests.get(base_url, headers=headers, params=req_params, timeout=30)
            if resp.status_code != 200:
                return JsonResponse({
                    'error': f'HTTP {resp.status_code} at page {page}',
                    'data': all_data,
                    'chapter_name': chapter_name
                }, status=200)
            try:
                data = resp.json()
            except Exception:
                return JsonResponse({
                    'error': f'Non-JSON response at page {page}',
                    'data': all_data,
                    'chapter_name': chapter_name
                }, status=200)
            if data is None or (isinstance(data, list) and len(data) == 0) or (isinstance(data, dict) and not data):
                break
            all_data.append(data)
            time.sleep(delay_seconds)
            page += 1
            if page > 500:
                break

        return JsonResponse({'data': all_data, 'chapter_name': chapter_name})
    except json.JSONDecodeError as e:
        return JsonResponse({'error': f'Invalid JSON: {e}'}, status=400)
    except Exception as e:
        logger.exception('run_scraper failed')
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def run_scraper_page(request):
    """POST: fetch a single page. Returns { data, has_more } for progress bar."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        import time
        body = json.loads(request.body.decode('utf-8'))
        base_url = (body.get('base_url') or '').strip()
        params = body.get('params') or {}
        headers = body.get('headers') or {}
        page_param = (body.get('page_param') or 'page').strip() or 'page'
        page_number = int(body.get('page_number') or 1)
        delay_seconds = float(body.get('delay_seconds') or 1)
        delay_seconds = max(0, min(10, delay_seconds))

        if not base_url:
            return JsonResponse({'error': 'base_url is required'}, status=400)

        req_params = dict(params) if isinstance(params, dict) else {}
        if not isinstance(params, dict):
            req_params = {}
            for item in params if isinstance(params, list) else []:
                k = item.get('key') or item.get('name')
                v = item.get('value')
                if k:
                    req_params[k] = v
        req_params[page_param] = page_number

        if page_number > 1:
            time.sleep(delay_seconds)

        resp = requests.get(base_url, headers=headers, params=req_params, timeout=30)
        if resp.status_code != 200:
            return JsonResponse({'error': f'HTTP {resp.status_code}', 'data': None, 'has_more': False})

        try:
            data = resp.json()
        except Exception:
            return JsonResponse({'error': 'Non-JSON response', 'data': None, 'has_more': False})

        has_more = data is not None and (
            (isinstance(data, list) and len(data) > 0) or
            (isinstance(data, dict) and bool(data))
        )
        return JsonResponse({'data': data, 'has_more': has_more})
    except json.JSONDecodeError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        logger.exception('run_scraper_page failed')
        return JsonResponse({'error': str(e)}, status=500)


def _scraper_desktop_path():
    """Return user's Desktop directory (Windows: USERPROFILE\\Desktop, else ~/Desktop). Works on any computer."""
    home = os.environ.get('USERPROFILE') or os.environ.get('HOME') or os.path.expanduser('~')
    return os.path.join(home, 'Desktop')


def _scraper_root_config_path():
    """Path to project config file that stores custom scraper root (one line). Enables different root per computer."""
    return os.path.join(settings.BASE_DIR, 'scraper_root.txt')


def _scraper_get_root_override():
    """Return custom root folder from config file, or None to use default Desktop."""
    path = _scraper_root_config_path()
    if not os.path.isfile(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            line = (f.read() or '').strip()
        if line:
            return line
    except Exception:
        pass
    return None


def _scraper_base_path():
    """Scraper folder: {root}/Scraper. Root = custom from scraper_root.txt or Desktop. Creates folder if not exists."""
    root_override = _scraper_get_root_override()
    if root_override:
        base = os.path.join(root_override, 'Scraper')
    else:
        base = os.path.join(_scraper_desktop_path(), 'Scraper')
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        pass
    return base


def _scraper_site_dir(website, group):
    """Return directory path Desktop/Scraper/{website}/{group}/. Creates Scraper and subdirs if needed. Group is uppercase (HSC, JSC)."""
    root = _scraper_base_path()
    safe_website = re.sub(r'[^\w\-]', '', (website or 'daricomma').strip()).lower() or 'daricomma'
    safe_group = (re.sub(r'[^\w\-]', '', (group or 'default').strip()) or 'default').upper()
    dir_path = os.path.join(root, safe_website, safe_group)
    try:
        os.makedirs(dir_path, exist_ok=True)
    except Exception:
        pass
    return dir_path


def _scraper_helper_json():
    """Path to Scraper/helper.json. Default: {root}/Scraper/helper.json (e.g. C:\\Users\\sasha\\Desktop\\Scraper\\helper.json).
    Tries: 1) SCRAPER_HELPER_JSON env (exact path), 2) {root}/Scraper/helper.json, 3) project BASE_DIR/helper.json."""
    env_path = (os.environ.get('SCRAPER_HELPER_JSON') or '').strip()
    if env_path and os.path.isfile(env_path):
        return os.path.normpath(env_path)
    path = os.path.normpath(os.path.join(_scraper_base_path(), 'helper.json'))
    if os.path.isfile(path):
        return path
    fallback = os.path.normpath(os.path.join(settings.BASE_DIR, 'helper.json'))
    if os.path.isfile(fallback):
        return fallback
    return path


def _scraper_api_txt():
    """Path to Desktop/Scraper/api.txt – one API URL per line (script-compatible). Do not clear on start; clear only when all tasks done."""
    return os.path.join(_scraper_base_path(), 'api.txt')


def _scraper_load_seen_apis(api_base_prefix=None):
    """Load already-used API URLs from Desktop/Scraper/api.txt. Do not clear file on new run (same as script)."""
    seen = set()
    path = _scraper_api_txt()
    if not os.path.isfile(path):
        return seen
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                url = line.strip()
                if not url or url.startswith('#'):
                    continue
                if api_base_prefix is None or url.startswith(api_base_prefix):
                    seen.add(url)
    except Exception:
        pass
    return seen


def _scraper_add_api_to_file(api_url, api_base_prefix=None):
    """Append one API URL to Desktop/Scraper/api.txt (script add_api_to_file)."""
    if not api_url or not isinstance(api_url, str):
        return
    api_url = api_url.strip()
    if api_base_prefix and not api_url.startswith(api_base_prefix):
        return
    try:
        _scraper_base_path()
        with open(_scraper_api_txt(), 'a', encoding='utf-8') as f:
            f.write(api_url + '\n')
    except Exception:
        pass


def _scraper_clear_api_file():
    """Remove all URLs from Desktop/Scraper/api.txt – call only after all tasks completed (script clear_api_file)."""
    try:
        _scraper_base_path()
        open(_scraper_api_txt(), 'w', encoding='utf-8').close()
    except Exception:
        pass


def _normalize_library_for_response(lib):
    """Ensure library dict has camelCase keys so frontend (loginUrl, apiBaseUrl, etc.) always receives them.
    Accepts both camelCase and snake_case keys from helper.json."""
    if not isinstance(lib, dict):
        return lib
    # (camelCase_key, snake_case_alias_or_same)
    key_map = [
        ('loginUrl', 'login_url'), ('username',), ('password',), ('groups',),
        ('apiBaseUrl', 'api_base_url'), ('apiUrlTemplate', 'api_url_template'),
        ('bearerToken', 'bearer_token'), ('questionPerPage', 'question_per_page'),
    ]
    out = {}
    for names in key_map:
        camel = names[0]
        val = None
        for key in names:
            if key in lib:
                val = lib[key]
                break
        if val is not None:
            out[camel] = val
        elif camel == 'groups':
            out[camel] = []
        elif camel == 'questionPerPage':
            out[camel] = 200
        else:
            out[camel] = ''
    if not isinstance(out.get('groups'), list):
        out['groups'] = [{'name': 'Default', 'urls': []}]
    return out


def _default_libraries():
    """Default library entries per site (daricomma, other). HSC group includes the 4 chapter URLs."""
    _HSC_CHAPTER_URLS = [
        'https://daricomma.com/academic/HSC%20-%20ICT/chapter/default&page=1',
        'https://daricomma.com/academic/HSC%20-%20%E0%A6%89%E0%A6%9A%E0%A7%8D%E0%A6%9A%E0%A6%A4%E0%A6%B0%20%E0%A6%97%E0%A6%A3%E0%A6%BF%E0%A6%A4%20%E0%A7%A7%E0%A6%AE%20%E0%A6%AA%E0%A6%A4%E0%A7%8D%E0%A6%B0/chapter/default&page=1',
        'https://daricomma.com/academic/HSC%20-%20%E0%A6%89%E0%A7%8E%E0%A6%AA%E0%A6%BE%E0%A6%A6%E0%A6%A8%20%E0%A6%AC%E0%A7%8D%E0%A6%AF%E0%A6%AC%E0%A6%B8%E0%A7%8D%E0%A6%A5%E0%A6%BE%E0%A6%AA%E0%A6%A8%E0%A6%BE%20%E0%A6%93%20%E0%A6%AC%E0%A6%BF%E0%A6%AA%E0%A6%A3%E0%A6%A8%20%E0%A7%A8%E0%A7%9F%20%E0%A6%AA%E0%A6%A4%E0%A7%8D%E0%A6%B0/chapter/default&page=1',
        'https://daricomma.com/academic/HSC%20-%20%E0%A6%85%E0%A6%B0%E0%A7%8D%E0%A6%A5%E0%A6%A8%E0%A7%80%E0%A6%A4%E0%A6%BF%20%E0%A7%A8%E0%A7%9F%20%E0%A6%AA%E0%A6%A4%E0%A7%8D%E0%A6%B0/chapter/default&page=1',
    ]
    _base = {
        'loginUrl': '',
        'username': '',
        'password': '',
        'groups': [{'name': 'Default', 'urls': []}],
        'apiBaseUrl': '',
        'apiUrlTemplate': '',
        'bearerToken': '',
        'questionPerPage': 200,
    }
    return {
        'daricomma': {
            'loginUrl': 'https://www.daricomma.com/sign-in',
            'username': '',
            'password': '',
            'groups': [{'name': 'HSC', 'urls': _HSC_CHAPTER_URLS}],
            'apiBaseUrl': 'https://api.daricomma.com/v2/question/',
            'apiUrlTemplate': 'https://api.daricomma.com/v2/question/7e93e529-3405-40ad-b003-895dacf21e9f',
            'bearerToken': '',
            'questionPerPage': 200,
        },
        'chorcha': {**_base},
        'eprosnobank': {**_base},
        'livemcq': {**_base},
        'other': {**_base},
    }


@csrf_exempt
def scraper_helper(request):
    """GET: return { lastSite, libraries: { daricomma: {...}, other: {...} } }. POST: save body { lastSite, libraries }."""
    if request.method == 'GET':
        try:
            _scraper_base_path()
            defaults = _default_libraries()
            with open(_scraper_helper_json(), 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Migrate old format { groups } to new format
            if 'libraries' not in data:
                groups = data.get('groups') if isinstance(data.get('groups'), list) else []
                data = {
                    'lastSite': data.get('lastSite', 'daricomma'),
                    'libraries': {
                        'daricomma': {**defaults['daricomma'], 'groups': groups or defaults['daricomma']['groups']},
                        'other': defaults['other'],
                    },
                }
            last_site = (data.get('lastSite') or 'daricomma').strip().lower() or 'daricomma'
            if last_site not in defaults:
                last_site = 'daricomma'
            libs_raw = data.get('libraries') or {}
            # Normalize keys to lowercase so frontend (sitePreset='daricomma') always finds the library
            libs = {}
            for k, v in libs_raw.items():
                if isinstance(v, dict):
                    libs[str(k).lower()] = v
            for key in defaults:
                if key not in libs or not isinstance(libs[key], dict):
                    libs[key] = defaults[key]
                else:
                    for k, v in defaults[key].items():
                        if k not in libs[key]:
                            libs[key][k] = v
            # If daricomma HSC group has no URLs, fill with default 4 chapter URLs
            if libs.get('daricomma') and isinstance(libs['daricomma'].get('groups'), list) and libs['daricomma']['groups']:
                first = libs['daricomma']['groups'][0]
                if isinstance(first, dict) and first.get('name') == 'HSC' and not (first.get('urls') or []):
                    first['urls'] = list(defaults['daricomma']['groups'][0]['urls'])
            # Normalize each library to camelCase so frontend always gets loginUrl, apiBaseUrl, bearerToken, apiUrlTemplate
            libs = {k: _normalize_library_for_response(v) for k, v in libs.items()}
            return JsonResponse({'lastSite': last_site, 'libraries': libs})
        except FileNotFoundError:
            return JsonResponse({'lastSite': 'daricomma', 'libraries': _default_libraries()})
        except Exception as e:
            logger.exception('scraper_helper GET failed')
            return JsonResponse({'error': str(e), 'lastSite': 'daricomma', 'libraries': _default_libraries()})
    if request.method == 'POST':
        try:
            body = json.loads(request.body.decode('utf-8'))
            last_site = (body.get('lastSite') or 'daricomma').strip() or 'daricomma'
            libraries = body.get('libraries')
            if not isinstance(libraries, dict):
                return JsonResponse({'error': 'libraries must be an object'}, status=400)
            defaults = _default_libraries()
            for key in defaults:
                if key not in libraries or not isinstance(libraries[key], dict):
                    libraries[key] = defaults[key]
            _scraper_base_path()
            with open(_scraper_helper_json(), 'w', encoding='utf-8') as f:
                json.dump({'lastSite': last_site, 'libraries': libraries}, f, ensure_ascii=False, indent=2)
            return JsonResponse({'ok': True})
        except (json.JSONDecodeError, TypeError) as e:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.exception('scraper_helper POST failed')
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
def scraper_clear_api_file(request):
    """POST: Clear Scrape/api.txt (call only after all tasks completed – same as script clear_api_file())."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        _scraper_clear_api_file()
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def scraper_root_get(request):
    """GET: Return current scraper root folder (custom or default Desktop). Used so UI can show and change it."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    root = _scraper_get_root_override()
    if not root:
        root = _scraper_desktop_path()
    return JsonResponse({'path': root})


@csrf_exempt
def scraper_default_root_get(request):
    """GET: Return default Desktop path for this machine. Use for 'Use default (Desktop)' button."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    return JsonResponse({'path': _scraper_desktop_path()})


@csrf_exempt
def scraper_root_post(request):
    """POST: Set custom scraper root folder. Body: { path: "C:\\Users\\...\\Desktop" }. Creates scraper_root.txt in project."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        body = json.loads(request.body.decode('utf-8'))
        path = (body.get('path') or '').strip()
        if not path:
            config_path = _scraper_root_config_path()
            if os.path.isfile(config_path):
                try:
                    os.remove(config_path)
                except Exception:
                    pass
            return JsonResponse({'ok': True})
        config_path = _scraper_root_config_path()
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(path)
        return JsonResponse({'ok': True})
    except (json.JSONDecodeError, TypeError) as e:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def _scraper_safe_request(url, headers=None, params=None, max_retry=5, timeout=30):
    """Fetch URL with retries (matches script safe_request)."""
    headers = headers or {}
    params = params or {}
    for attempt in range(max_retry):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=timeout)
            if resp.status_code == 200:
                return resp
            _scraper_progress('API error {}, retrying...'.format(resp.status_code))
        except Exception as e:
            _scraper_progress('Network error: {}, retrying...'.format(e))
        if attempt < max_retry - 1:
            time.sleep(3)
    return None


def _scraper_parse_academic_url(url):
    """Parse daricomma academic URL; return (subject_from_url, chapter_no, chapter_slug)."""
    try:
        if '/academic/' not in url or '/chapter/' not in url:
            return ('', '', '')
        parts = url.split('/chapter/', 1)
        if len(parts) != 2:
            return ('', '', '')
        subject_encoded = parts[0].rstrip('/').split('/academic/')[-1]
        rest = parts[1].split('&')[0].split('?')[0]
        subject_from_url = urllib_parse.unquote(subject_encoded)
        chapter_slug = urllib_parse.unquote(rest)
        chapter_no = _scraper_extract_chapter_no_from_slug(chapter_slug)
        return (subject_from_url, chapter_no, chapter_slug)
    except Exception:
        return ('', '', '')


def _scraper_extract_chapter_no_from_slug(chapter_slug):
    """Extract chapter number from URL slug (e.g. অধ্যায়-০১ঃ or 1.)."""
    if not chapter_slug or not isinstance(chapter_slug, str):
        return ''
    s = chapter_slug.strip()
    if 'অধ্যায়' in s:
        parts = s.split(None, 1)
        return parts[0].strip() if parts else (s.split()[0] if s.split() else '')
    m = re.match(r'^(\d+\.)', s)
    return m.group(1) if m else ''


def _scraper_extract_chapter_no_from_option_text(level2_text):
    """Get ChapterNo from Level2 dropdown option text (e.g. 'অধ্যায়-০১ঃ ম্যাট্রিক্স' or '1. Text Book')."""
    if not level2_text or not isinstance(level2_text, str):
        return ''
    s = level2_text.strip()
    if 'অধ্যায়' in s:
        parts = s.split(None, 1)
        return parts[0].strip() if parts else (s.split()[0] if s.split() else '')
    m = re.match(r'^(\d+\.)', s)
    return m.group(1) if m else ''


def _scraper_sanitize_filename(name):
    r"""Sanitize for file paths (matches script: replace / and \ with -)."""
    if not name:
        return ''
    return name.replace('/', '-').replace('\\', '-').strip()


@csrf_exempt
def scraper_fetch_and_save(request):
    """POST { group, base_url, params, headers, filename } - Fetch from API (with pagination, retry, dedupe) and save. Returns all questions in data."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        body = json.loads(request.body.decode('utf-8'))
        group = (body.get('group') or '').strip()
        website = (body.get('website') or body.get('site') or 'daricomma').strip()
        base_url = (body.get('base_url') or '').strip()
        params = body.get('params') or {}
        headers = body.get('headers') or {}
        filename = (body.get('filename') or 'data').strip()
        level1_name = (body.get('level1_name') or body.get('level1') or '').strip()
        level2_label = (body.get('level2_label') or body.get('level2') or '').strip()
        chapter_no = (body.get('chapter_no') or '').strip()
        session_id = (body.get('session_id') or '').strip()
        if not group or not base_url:
            return JsonResponse({'error': 'group and base_url are required'}, status=400)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    if session_id and session_id in _scraper_aborted_sessions:
        return JsonResponse({'ok': False, 'error': 'Scraper stopped', 'data': []})
    dir_path = _scraper_site_dir(website, group)
    filename = _scraper_sanitize_filename(filename) or 'data'
    if not filename.endswith('.json'):
        filename = filename + '.json'
    file_path = os.path.join(dir_path, filename)
    if isinstance(params, dict):
        req_params = dict(params)
    else:
        req_params = {}
        for item in params if isinstance(params, list) else []:
            k = item.get('key') or item.get('name')
            v = item.get('value')
            if k:
                req_params[k] = v
    chapter_id = req_params.get('chapter_id', '')
    per_page = int(req_params.get('questionPerPage') or 200)
    if per_page <= 0:
        per_page = 200
    # Script: use Bearer token from the same browser session (localStorage) so API returns questions
    request_headers = dict(headers) if isinstance(headers, dict) else {}
    request_headers.setdefault('Accept', 'application/json')
    request_headers.setdefault('User-Agent', 'Mozilla/5.0')
    if session_id:
        driver = _scraper_sessions.get(session_id)
        if driver:
            try:
                local_storage = driver.execute_script('return window.localStorage;')
                if isinstance(local_storage, dict):
                    access_token = None
                    for k, v in local_storage.items():
                        if 'token' in (k or '').lower():
                            access_token = v
                            break
                    if access_token:
                        request_headers['Authorization'] = 'Bearer %s' % (access_token,)
                        _scraper_progress('Using token from session browser for API request.')
            except Exception:
                pass
    try:
        _scraper_progress('Fetching API: {}?chapter_id={} (paginated)'.format(
            base_url.rstrip('/'), chapter_id[:36] if chapter_id else ''))
        max_fetch_retries = 5
        wait_between_retries_sec = 10
        all_questions = []
        for fetch_attempt in range(max_fetch_retries):
            if session_id and session_id in _scraper_aborted_sessions:
                _scraper_progress('Scraper stopped by user.')
                return JsonResponse({'ok': False, 'error': 'Scraper stopped', 'data': []})
            all_questions = []
            seen_ids = set()
            total_questions = None
            page = 1
            page_retry = 0
            max_page_retry = 3
            while True:
                if session_id and session_id in _scraper_aborted_sessions:
                    _scraper_progress('Scraper stopped by user.')
                    return JsonResponse({'ok': False, 'error': 'Scraper stopped', 'data': []})
                # Like script: only page and questionPerPage (no chapter_id/subject in request)
                page_params = {'page': page, 'questionPerPage': per_page}
                resp = _scraper_safe_request(base_url, headers=request_headers, params=page_params, timeout=45)
                if not resp:
                    if page > 1 and page_retry < max_page_retry:
                        page_retry += 1
                        _scraper_progress('Page {} request failed, retrying ({}/{})...'.format(page, page_retry, max_page_retry))
                        time.sleep(2)
                        continue
                    break
                page_retry = 0
                try:
                    raw = resp.json()
                except Exception:
                    break
                data = raw.get('data', raw) if isinstance(raw, dict) else raw
                if total_questions is None and isinstance(raw, dict):
                    total_questions = raw.get('total') or raw.get('totalQuestions')
                if total_questions is None and isinstance(data, dict):
                    total_questions = data.get('total') or data.get('totalQuestions')
                # Parse questions like script: data.questions or raw.questions or data if list; fallbacks for other APIs
                questions = None
                if isinstance(data, dict):
                    questions = data.get('questions') or data.get('results') or data.get('items')
                if not questions and isinstance(raw, dict):
                    questions = raw.get('questions') or raw.get('results') or raw.get('items')
                if questions is None and isinstance(data, list):
                    questions = data
                if not questions:
                    questions = []
                if not questions:
                    break
                for q in questions:
                    if not isinstance(q, dict):
                        continue
                    qid = q.get('id')
                    if qid and qid not in seen_ids:
                        all_questions.append(q)
                        seen_ids.add(qid)
                _scraper_progress('Fetched page {}, {} questions (total so far {})'.format(page, len(questions), len(all_questions)))
                # Script: only break when no questions; otherwise continue to next page
                if len(questions) < per_page:
                    break
                page += 1
            if all_questions:
                break
            if session_id and session_id in _scraper_aborted_sessions:
                _scraper_progress('Scraper stopped by user.')
                return JsonResponse({'ok': False, 'error': 'Scraper stopped', 'data': []})
            if fetch_attempt < max_fetch_retries - 1:
                _scraper_progress('No questions returned, retrying ({}/{}) in {}s...'.format(
                    fetch_attempt + 2, max_fetch_retries, wait_between_retries_sec))
                for _ in range(wait_between_retries_sec):
                    if session_id and session_id in _scraper_aborted_sessions:
                        return JsonResponse({'ok': False, 'error': 'Scraper stopped', 'data': []})
                    time.sleep(1)
        if all_questions:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(all_questions, f, ensure_ascii=False, indent=2)
            _scraper_progress('Saved {} questions to {}'.format(len(all_questions), file_path))
            if level1_name or level2_label:
                csv_path = file_path.replace('.json', '.csv') if file_path.endswith('.json') else (file_path + '.csv')
                csv_header = ['ID', 'Subject', 'ChapterNo', 'Chapter', 'Topic', 'Question', 'Option 1', 'Option 2', 'Option 3', 'Option 4',
                              'Answer', 'Explanation', 'Question Type', 'Level', 'Subsources']
                with open(csv_path, 'w', newline='', encoding='utf-8-sig') as cf:
                    writer = csv.writer(cf)
                    writer.writerow(csv_header)
                    for idx, q in enumerate(all_questions, start=1):
                        if not isinstance(q, dict):
                            continue
                        options = q.get('option') or []
                        correct_index = q.get('mcq_solution_index')
                        correct_answer = options[correct_index] if isinstance(correct_index, int) and 0 <= correct_index < len(options) else ''
                        expl = _scraper_extract_text(q.get('answer_text')) or _scraper_extract_text(q.get('explanation_text'))
                        writer.writerow([
                            idx, level1_name, chapter_no, level2_label, _scraper_format_topics(q),
                            _scraper_extract_text(q.get('question_text')),
                            options[0] if len(options) > 0 else '', options[1] if len(options) > 1 else '',
                            options[2] if len(options) > 2 else '', options[3] if len(options) > 3 else '',
                            correct_answer, expl,
                            (q.get('question_type') or {}).get('name', ''),
                            (q.get('question_level') or {}).get('name', ''),
                            _scraper_format_subsources(q)
                        ])
                _scraper_progress('Saved chapter CSV: {}'.format(csv_path))
            _scraper_add_api_to_file(base_url.split('?')[0].strip())
            return JsonResponse({'ok': True, 'path': file_path, 'data': all_questions})
        empty_data = {'error': 'No data (after {} attempts)'.format(max_fetch_retries), 'data': [], 'chapter_id': chapter_id}
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(empty_data, f, ensure_ascii=False, indent=2)
        _scraper_progress('Saved (no data after {} retries) to {}'.format(max_fetch_retries, file_path))
        return JsonResponse({'ok': True, 'path': file_path, 'data': [], 'error': 'No questions returned (tried {} times)'.format(max_fetch_retries)})
    except Exception as e:
        logger.exception('scraper_fetch_and_save failed')
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump({'error': str(e), 'data': []}, f, ensure_ascii=False, indent=2)
            _scraper_progress('Saved (error) to {}'.format(file_path))
            return JsonResponse({'ok': True, 'path': file_path, 'data': [], 'error': str(e)})
        except Exception:
            return JsonResponse({'error': str(e), 'path': None, 'data': None}, status=500)


def _scraper_extract_text(editor_obj):
    """Extract plain text from editor JSON (blocks[].text)."""
    if not isinstance(editor_obj, dict):
        return ''
    blocks = editor_obj.get('blocks') or []
    return '\n'.join(block.get('text', '') for block in blocks if isinstance(block, dict))


def _scraper_format_topics(q):
    """Format topic names for CSV."""
    topic_names = []
    topics = q.get('topic')
    if isinstance(topics, list):
        for t in topics:
            if isinstance(t, dict) and t.get('name'):
                topic_names.append('"{}"'.format(t['name']))
    elif isinstance(topics, dict) and topics.get('name'):
        topic_names.append('"{}"'.format(topics['name']))
    return ', '.join(topic_names)


def _scraper_format_subsources(q):
    """Format question_subsources for CSV."""
    out = []
    for sub in (q.get('question_subsources') or []):
        if not isinstance(sub, dict):
            continue
        sub_source = sub.get('sub_source') or {}
        year_obj = sub.get('year') or {}
        short_name = sub_source.get('name', '')
        year_name = year_obj.get('name', '')
        if short_name and year_name:
            formatted = short_name + "'" + (year_name[-2:] if len(year_name) >= 2 else year_name)
            out.append('"{}"'.format(formatted))
    return ', '.join(out)


def _scraper_subject_file_has_questions(json_path):
    """Return True if json_path exists and contains at least one question (so we don't skip based on empty failed-run files)."""
    if not os.path.isfile(json_path):
        return False
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            content = json.load(f)
        if isinstance(content, list):
            return len(content) > 0
        if isinstance(content, dict):
            data = content.get('data', content)
            if isinstance(data, list):
                return len(data) > 0
            qs = content.get('questions')
            if not qs and isinstance(data, dict):
                qs = data.get('questions')
            return isinstance(qs, list) and len(qs) > 0
    except Exception:
        pass
    return False


@csrf_exempt
def scraper_file_exists(request):
    """GET ?group=...&filename=...&website=... (base name). Returns { exists: true } only if both .json and .csv exist AND json has at least one question (avoids skip from empty failed runs). Also returns path for UI."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    group = (request.GET.get('group') or '').strip()
    filename = (request.GET.get('filename') or '').strip()
    website = (request.GET.get('website') or request.GET.get('site') or 'daricomma').strip()
    if not group or not filename:
        return JsonResponse({'error': 'group and filename are required'}, status=400)
    safe_name = re.sub(r'[^\w\-]', '_', _scraper_sanitize_filename(filename) or filename).strip('_') or 'data'
    dir_path = _scraper_site_dir(website, group)
    json_path = os.path.join(dir_path, safe_name + '.json')
    csv_path = os.path.join(dir_path, safe_name + '.csv')
    files_exist = os.path.isfile(json_path) and os.path.isfile(csv_path)
    has_questions = _scraper_subject_file_has_questions(json_path)
    exists = files_exist and has_questions
    return JsonResponse({'exists': exists, 'path': dir_path})


@csrf_exempt
def scraper_save_subject(request):
    """POST { group, level1_name, questions: [...] }. Writes level1_name.json and level1_name.csv (same format as Python script)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        body = json.loads(request.body.decode('utf-8'))
        group = (body.get('group') or '').strip()
        website = (body.get('website') or body.get('site') or 'daricomma').strip()
        level1_name = (body.get('level1_name') or '').strip()
        questions = body.get('questions')
        if not isinstance(questions, list):
            questions = []
        if not group or not level1_name:
            return JsonResponse({'error': 'group and level1_name are required'}, status=400)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    safe_name = re.sub(r'[^\w\-]', '_', _scraper_sanitize_filename(level1_name) or level1_name).strip('_') or 'subject'
    dir_path = _scraper_site_dir(website, group)
    json_path = os.path.join(dir_path, safe_name + '.json')
    csv_path = os.path.join(dir_path, safe_name + '.csv')
    try:
        # JSON: copy without internal fields (same as script)
        json_questions = []
        for q in questions:
            if isinstance(q, dict):
                qcopy = {k: v for k, v in q.items() if k not in ('_chapter', '_chapter_no', '_level1')}
                json_questions.append(qcopy)
            else:
                json_questions.append(q)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_questions, f, ensure_ascii=False, indent=2)
        csv_header = ['ID', 'Subject', 'ChapterNo', 'Chapter', 'Topic', 'Question', 'Option 1', 'Option 2', 'Option 3', 'Option 4',
                      'Answer', 'Explanation', 'Question Type', 'Level', 'Subsources']
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(csv_header)
            for idx, q in enumerate(questions, start=1):
                if not isinstance(q, dict):
                    continue
                level1 = q.get('_level1', level1_name)
                chapter_no = q.get('_chapter_no', '')
                chapter = q.get('_chapter', '')
                options = q.get('option') or []
                correct_index = q.get('mcq_solution_index')
                correct_answer = options[correct_index] if isinstance(correct_index, int) and 0 <= correct_index < len(options) else ''
                expl = _scraper_extract_text(q.get('answer_text')) or _scraper_extract_text(q.get('explanation_text'))
                qtype = (q.get('question_type') or {}).get('name', '')
                qlevel = (q.get('question_level') or {}).get('name', '')
                writer.writerow([
                    idx, level1, chapter_no, chapter, _scraper_format_topics(q),
                    _scraper_extract_text(q.get('question_text')),
                    options[0] if len(options) > 0 else '', options[1] if len(options) > 1 else '',
                    options[2] if len(options) > 2 else '', options[3] if len(options) > 3 else '',
                    correct_answer, expl, qtype, qlevel, _scraper_format_subsources(q)
                ])
        _scraper_progress('Saved subject files: {}'.format(safe_name))
        return JsonResponse({'ok': True, 'path_json': json_path, 'path_csv': csv_path})
    except Exception as e:
        logger.exception('scraper_save_subject failed')
        return JsonResponse({'error': str(e)}, status=500)


# Persistent Selenium sessions for scraper (session_id -> driver). Headed browser for "Load website".
_scraper_sessions = {}
_scraper_aborted_sessions = set()  # session_ids for which user clicked Stop; in-flight fetch_and_save will exit
_SCRAPER_SESSION_TIMEOUT = 3600  # 1 hour


def _scraper_progress(msg):
    """Log and print scraper progress so it appears in the terminal (e.g. runserver)."""
    logger.info('[Scraper] %s', msg)
    try:
        print('[Scraper]', msg, flush=True)
    except Exception:
        pass


def _get_selenium_driver(headed=False, enable_performance_log=False):
    """Return Chrome WebDriver. headed=True shows the browser window. enable_performance_log=True for capturing API URLs from network."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        opts = Options()
        if not headed:
            opts.add_argument('--headless')
        opts.add_argument('--no-sandbox')
        opts.add_argument('--disable-dev-shm-usage')
        opts.add_argument('--disable-gpu')
        opts.add_argument('--disable-software-rasterizer')
        if enable_performance_log:
            opts.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
        try:
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=opts)
        except Exception:
            driver = webdriver.Chrome(options=opts)
        if enable_performance_log:
            try:
                driver.execute_cdp_cmd('Network.enable', {})
            except Exception:
                pass
        return driver
    except Exception as e:
        logger.warning('Selenium/Chrome not available: %s', e)
        return None


@csrf_exempt
def scraper_load_website(request):
    """POST { url, headless?: bool } - Open Chrome (headed or headless) and load URL. Returns session_id."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        body = json.loads(request.body.decode('utf-8'))
        url = (body.get('url') or '').strip()
        headless = bool(body.get('headless'))
        if not url:
            return JsonResponse({'error': 'url is required'}, status=400)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    _scraper_progress('Opening browser (headless={})...'.format(headless))
    driver = _get_selenium_driver(headed=not headless, enable_performance_log=True)
    if not driver:
        return JsonResponse({'error': 'Selenium/Chrome not available. Install Chrome and: pip install selenium webdriver-manager'})
    try:
        import time
        import uuid
        _scraper_progress('Loading URL: {}'.format(url[:80] + ('...' if len(url) > 80 else '')))
        driver.get(url)
        wait_sec = 4 if headless else 2
        _scraper_progress('Waiting {}s for page load...'.format(wait_sec))
        time.sleep(wait_sec)
        session_id = str(uuid.uuid4())
        _scraper_sessions[session_id] = driver
        _scraper_progress('Session created: {}'.format(session_id[:8]))
        return JsonResponse({'session_id': session_id, 'url': url})
    except Exception as e:
        _scraper_progress('Load failed: {}'.format(e))
        try:
            driver.quit()
        except Exception:
            pass
        return JsonResponse({'error': str(e)})


@csrf_exempt
def scraper_navigate(request):
    """POST { session_id, url } - Navigate the session browser to url."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        body = json.loads(request.body.decode('utf-8'))
        session_id = (body.get('session_id') or '').strip()
        url = (body.get('url') or '').strip()
        if not session_id or not url:
            return JsonResponse({'error': 'session_id and url are required'}, status=400)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    driver = _scraper_sessions.get(session_id)
    if not driver:
        return JsonResponse({'error': 'Session not found.'}, status=400)
    try:
        import time
        _scraper_progress('Navigating to: {}'.format(url[:70] + ('...' if len(url) > 70 else '')))
        driver.get(url)
        _scraper_progress('Waiting 4s for page load...')
        time.sleep(4)
        # If the site (e.g. Daricomma) redirects to a placeholder route, force the target URL again
        current = (driver.current_url or '')
        if '[subjectName]' in current or '[chapterId]' in current:
            _scraper_progress('Redirect detected; re-navigating to target URL...')
            driver.get(url)
            time.sleep(2)
        _scraper_progress('Navigate done.')
        return JsonResponse({'ok': True, 'url': url})
    except Exception as e:
        _scraper_progress('Navigate failed: {}'.format(e))
        return JsonResponse({'error': str(e)})


@csrf_exempt
def scraper_daricomma_login(request):
    """POST { session_id, login_url, username, password } - Navigate to login, fill form, submit."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        body = json.loads(request.body.decode('utf-8'))
        session_id = (body.get('session_id') or '').strip()
        login_url = (body.get('login_url') or '').strip()
        username = (body.get('username') or '').strip()
        password = (body.get('password') or '').strip()
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    if not session_id or not login_url:
        return JsonResponse({'error': 'session_id and login_url are required'}, status=400)
    driver = _scraper_sessions.get(session_id)
    if not driver:
        return JsonResponse({'error': 'Session not found.'}, status=400)
    try:
        import time
        from selenium.webdriver.common.by import By
        _scraper_progress('Loading login page...')
        driver.get(login_url)
        _scraper_progress('Waiting 4s for login form...')
        time.sleep(4)
        username_el = None
        pwd_el = None
        _scraper_progress('Looking for username/email field...')
        for sel in ['input[name="email"]', 'input[name="username"]', 'input[type="email"]', 'input#email', 'input#username']:
            try:
                username_el = driver.find_element(By.CSS_SELECTOR, sel)
                break
            except Exception:
                continue
        if not username_el:
            _scraper_progress('Trying Mantine form (first form text + password)...')
            # Daricomma sign-in uses Mantine: first field is mobile (type=text), second is password
            # Scope to first form (login tab) so we don't hit register form fields
            try:
                forms = driver.find_elements(By.CSS_SELECTOR, 'form')
                if forms:
                    form = forms[0]
                    username_el = form.find_element(By.CSS_SELECTOR, 'input[type="text"]')
                    pwd_el = form.find_element(By.CSS_SELECTOR, 'input[type="password"]')
            except Exception:
                pass
        if not username_el:
            return JsonResponse({'error': 'Could not find email/username field.'})
        if not pwd_el:
            try:
                pwd_el = driver.find_element(By.CSS_SELECTOR, 'input[name="password"], input[type="password"], input#password')
            except Exception:
                if username_el:
                    try:
                        form = username_el.find_element(By.XPATH, './ancestor::form[1]')
                        pwd_el = form.find_element(By.CSS_SELECTOR, 'input[type="password"]')
                    except Exception:
                        pass
        if not pwd_el:
            return JsonResponse({'error': 'Could not find password field.'})
        _scraper_progress('Filling username and password...')
        username_el.clear()
        username_el.send_keys(username)
        pwd_el.clear()
        pwd_el.send_keys(password)
        _scraper_progress('Submitting login form...')
        try:
            form = pwd_el.find_element(By.XPATH, './ancestor::form')
            form.submit()
        except Exception:
            for el in driver.find_elements(By.CSS_SELECTOR, 'button[type="submit"], input[type="submit"]'):
                try:
                    el.click()
                    break
                except Exception:
                    continue
        _scraper_progress('Waiting 3s after submit...')
        time.sleep(3)
        _scraper_progress('Login done.')
        return JsonResponse({'ok': True})
    except Exception as e:
        logger.exception('scraper_daricomma_login failed')
        return JsonResponse({'error': str(e)})


def _mantine_options(driver, combobox_index, previous_selections):
    """Get options from Mantine Select by index (0=first, 1=second). previous_selections for level 2."""
    import time
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    roots = driver.find_elements(By.CSS_SELECTOR, '.mantine-Select-root')
    if combobox_index >= len(roots):
        return []
    for i, val in enumerate(previous_selections):
        roots = driver.find_elements(By.CSS_SELECTOR, '.mantine-Select-root')
        if i >= len(roots):
            break
        try:
            cb = roots[i].find_element(By.CSS_SELECTOR, '[role="combobox"]')
            cb.click()
            time.sleep(0.9)
            listboxes = driver.find_elements(By.CSS_SELECTOR, '[role="listbox"]')
            options_to_use = []
            for lb in listboxes:
                try:
                    if lb.is_displayed():
                        options_to_use = lb.find_elements(By.CSS_SELECTOR, '[role="option"]')
                        break
                except Exception:
                    pass
            if not options_to_use:
                options_to_use = driver.find_elements(By.CSS_SELECTOR, '[role="listbox"] [role="option"]')
            for opt in options_to_use:
                ov = (opt.get_attribute('data-value') or opt.get_attribute('value') or '').strip()
                ot = (opt.text or '').strip()
                if ov == str(val).strip() or ot == str(val).strip():
                    opt.click()
                    break
            time.sleep(0.8)
        except Exception:
            try:
                driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            except Exception:
                pass
        time.sleep(0.6)
    # After selecting Level1 (for Level2 dropdown), wait longer for API to populate options (script: wait_after_select=4)
    wait_after_selections = 4.0 if (combobox_index == 1 and previous_selections) else 1.5
    time.sleep(wait_after_selections)
    roots = driver.find_elements(By.CSS_SELECTOR, '.mantine-Select-root')
    if combobox_index >= len(roots):
        return []
    try:
        root = roots[combobox_index]
        combobox_el = root.find_element(By.CSS_SELECTOR, '[role="combobox"]')
        combobox_el.click()
        time.sleep(1.2)
        listbox_els = driver.find_elements(By.CSS_SELECTOR, '[role="listbox"]')
        active_listbox = None
        for lb in listbox_els:
            try:
                if lb.is_displayed():
                    active_listbox = lb
                    break
            except Exception:
                pass
        if active_listbox is None:
            active_listbox = driver
        option_selector = '[role="listbox"] [role="option"]' if active_listbox == driver else '[role="option"]'
        try:
            option_els = active_listbox.find_elements(By.CSS_SELECTOR, option_selector)
        except Exception:
            option_els = driver.find_elements(By.CSS_SELECTOR, '[role="listbox"] [role="option"]')
        opts = []
        # Script get_all_options: open dropdown, collect option text/value, close – no selecting each option
        for opt in (option_els or []):
            try:
                driver.execute_script('arguments[0].scrollIntoView({block: "nearest"});', opt)
                time.sleep(0.03)
            except Exception:
                pass
            text = (opt.text or '').strip()
            v = opt.get_attribute('data-value') or opt.get_attribute('value') or text
            opts.append({'value': v or text, 'text': text or v})
        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        return opts
    except Exception:
        try:
            driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        except Exception:
            pass
        return []


@csrf_exempt
def scraper_capture_mantine(request):
    """POST { session_id, combobox_index (0|1), previous_selections: [] } - Get Mantine Select options."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        body = json.loads(request.body.decode('utf-8'))
        session_id = (body.get('session_id') or '').strip()
        combobox_index = int(body.get('combobox_index') or 0)
        previous_selections = body.get('previous_selections') or []
        if not session_id:
            return JsonResponse({'error': 'session_id is required'}, status=400)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    driver = _scraper_sessions.get(session_id)
    if not driver:
        return JsonResponse({'error': 'Session not found.', 'options': []})
    try:
        _scraper_progress('Capturing Mantine options (combobox_index={})...'.format(combobox_index))
        opts = _mantine_options(driver, combobox_index, previous_selections)
        _scraper_progress('Got {} options.'.format(len(opts)))
        return JsonResponse({'options': opts})
    except Exception as e:
        _scraper_progress('Capture failed: {}'.format(e))
        logger.exception('scraper_capture_mantine failed')
        return JsonResponse({'error': str(e), 'options': []})


def _scraper_wait_for_chapter_url(driver, timeout=12, poll_interval=0.5):
    """After Level2 selection, wait until URL contains /academic/ and /chapter/ with non-empty chapter part (script: timeout=12)."""
    start = time.time()
    while (time.time() - start) < timeout:
        url = (driver.current_url or '').strip()
        if '/academic/' in url and '/chapter/' in url:
            parts = url.split('/chapter/', 1)
            if len(parts) == 2:
                rest = (parts[1].split('&')[0].split('?')[0] or '').strip()
                if rest:
                    return True
        time.sleep(poll_interval)
    return False


def _scraper_capture_question_api_url(driver, prefix, wait_after=1.5):
    """Capture the first request URL starting with prefix from performance log (script: wait_after=1.5)."""
    time.sleep(wait_after)
    try:
        logs = driver.get_log('performance')
    except Exception:
        return None
    for entry in logs:
        try:
            msg = json.loads(entry.get('message', '{}'))
            event = msg.get('message') or msg
            method = event.get('method')
            if method not in ('Network.requestWillBeSent', 'Network.responseReceived'):
                continue
            params = event.get('params') or {}
            req_url = ''
            if method == 'Network.requestWillBeSent':
                req_url = (params.get('request') or {}).get('url') or ''
            else:
                req_url = (params.get('response') or {}).get('url') or ''
            if req_url.startswith(prefix):
                return req_url.split('?')[0].strip()
        except Exception:
            continue
    return None


@csrf_exempt
def scraper_capture_question_url(request):
    """POST { session_id, level1_value, level2_value, level1_label?, level2_label?, api_base_prefix? } - Select Level1 & Level2 by visible text (script: uses option text). Wait for chapter URL, capture question API URL. Returns { url }."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        body = json.loads(request.body.decode('utf-8'))
        session_id = (body.get('session_id') or '').strip()
        level1_value = (body.get('level1_value') or body.get('level1') or '').strip()
        level2_value = (body.get('level2_value') or body.get('level2') or '').strip()
        level1_label = (body.get('level1_label') or '').strip()
        level2_label = (body.get('level2_label') or '').strip()
        api_base_prefix = (body.get('api_base_prefix') or 'https://api.daricomma.com/v2/question/').strip()
        if not session_id:
            return JsonResponse({'error': 'session_id is required'}, status=400)
        # Script selects by visible text (option text); prefer label when provided
        level1_selection = level1_label or level1_value
        level2_selection = level2_label or level2_value
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    driver = _scraper_sessions.get(session_id)
    if not driver:
        return JsonResponse({'error': 'Session not found.', 'url': ''})
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        _scraper_progress('Capturing question API URL for chapter...')
        # Apply Level1 then Level2 selection by visible text (script: select_mantine_option uses option_text)
        for i, val in enumerate([level1_selection, level2_selection]):
            if not val:
                continue
            roots = driver.find_elements(By.CSS_SELECTOR, '.mantine-Select-root')
            if i >= len(roots):
                break
            try:
                cb = roots[i].find_element(By.CSS_SELECTOR, '[role="combobox"]')
                cb.click()
                time.sleep(0.9)
                listboxes = driver.find_elements(By.CSS_SELECTOR, '[role="listbox"]')
                options_to_use = []
                for lb in listboxes:
                    try:
                        if lb.is_displayed():
                            options_to_use = lb.find_elements(By.CSS_SELECTOR, '[role="option"]')
                            break
                    except Exception:
                        pass
                if not options_to_use:
                    options_to_use = driver.find_elements(By.CSS_SELECTOR, '[role="listbox"] [role="option"]')
                for opt in options_to_use:
                    ov = (opt.get_attribute('data-value') or opt.get_attribute('value') or '').strip()
                    ot = (opt.text or '').strip()
                    if ov == str(val).strip() or ot == str(val).strip():
                        opt.click()
                        break
                time.sleep(0.8)
            except Exception:
                try:
                    driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                except Exception:
                    pass
            time.sleep(0.6)
        time.sleep(1.0)
        _scraper_wait_for_chapter_url(driver, timeout=12)
        captured = _scraper_capture_question_api_url(driver, prefix=api_base_prefix, wait_after=1.5)
        if captured:
            _scraper_progress('Captured API URL: {}...'.format(captured[:60]))
            return JsonResponse({'url': captured})
        return JsonResponse({'url': '', 'error': 'No question API URL found in network log'})
    except Exception as e:
        _scraper_progress('Capture question URL failed: {}'.format(e))
        logger.exception('scraper_capture_question_url failed')
        return JsonResponse({'error': str(e), 'url': ''})


@csrf_exempt
def scraper_capture_dropdown(request):
    """POST { session_id, level, previous_selections: [] } - Get options for level (1-based). Applies previous selections first."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        body = json.loads(request.body.decode('utf-8'))
        session_id = (body.get('session_id') or '').strip()
        level = int(body.get('level') or 1)
        previous_selections = body.get('previous_selections') or []
        if not session_id:
            return JsonResponse({'error': 'session_id is required'}, status=400)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    driver = _scraper_sessions.get(session_id)
    if not driver:
        return JsonResponse({'error': 'Session not found. Load website again.', 'options': []})
    try:
        import time
        from selenium.webdriver.support.ui import Select
        from selenium.webdriver.common.by import By
        selects = driver.find_elements(By.CSS_SELECTOR, 'select')
        if level < 1 or level > len(selects):
            return JsonResponse({'options': [], 'message': 'No select at this level.'})
        # Apply previous selections so level 2+ options are correct
        for i, val in enumerate(previous_selections):
            if i >= len(selects):
                break
            try:
                Select(selects[i]).select_by_value(val)
                time.sleep(0.5)
            except Exception:
                pass
        time.sleep(0.5)
        selects = driver.find_elements(By.CSS_SELECTOR, 'select')
        if level > len(selects):
            return JsonResponse({'options': []})
        sel = selects[level - 1]
        opts = []
        for opt in sel.find_elements(By.TAG_NAME, 'option'):
            v = opt.get_attribute('value')
            if v is None:
                v = ''
            text = (opt.text or '').strip() or v
            opts.append({'value': v, 'text': text})
        return JsonResponse({'options': opts})
    except Exception as e:
        logger.exception('scraper_capture_dropdown failed')
        return JsonResponse({'error': str(e), 'options': []})


@csrf_exempt
def scraper_close_session(request):
    """POST { session_id } - Close browser and remove session."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        body = json.loads(request.body.decode('utf-8'))
        session_id = (body.get('session_id') or '').strip()
    except Exception:
        session_id = ''
    if session_id:
        _scraper_aborted_sessions.add(session_id)
        driver = _scraper_sessions.pop(session_id, None)
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
    return JsonResponse({'ok': True})


@csrf_exempt
def scraper_discover_dropdowns(request):
    """GET ?url=... - Open page with Selenium, find all <select>, return groups (one per dropdown)."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    url = (request.GET.get('url') or '').strip()
    if not url:
        return JsonResponse({'error': 'url is required'}, status=400)
    driver = _get_selenium_driver()
    if not driver:
        return JsonResponse({
            'error': 'Selenium/Chrome not available. Install: 1) Chrome browser, 2) pip install selenium webdriver-manager. Or use "Capture by your activity" above instead.',
            'groups': []
        })
    try:
        import time
        driver.get(url)
        time.sleep(2)
        try:
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.common.by import By
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
            time.sleep(2)
        except Exception:
            pass
        selects = driver.find_elements('css selector', 'select')
        groups = []
        for i, sel in enumerate(selects):
            name = sel.get_attribute('name') or sel.get_attribute('id') or ('Dropdown_%d' % (i + 1))
            opts = []
            for opt in sel.find_elements('tag name', 'option'):
                v = opt.get_attribute('value')
                if v is None:
                    v = ''
                text = (opt.text or '').strip() or v
                opts.append({'value': v, 'text': text})
            groups.append({'name': name, 'options': opts})
        if not groups:
            return JsonResponse({
                'groups': [],
                'message': 'No native <select> dropdowns found on this page. Many sites use custom dropdowns (divs). Use "Capture by your activity" to add options manually.'
            })
        return JsonResponse({'groups': groups})
    except Exception as e:
        logger.exception('scraper_discover_dropdowns failed')
        return JsonResponse({'error': str(e), 'groups': []})
    finally:
        try:
            driver.quit()
        except Exception:
            pass


@csrf_exempt
def scraper_dynamic_dropdown(request):
    """POST { url, level_index, selections: [] } - Open page, set prior selects, return options for level level_index."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        body = json.loads(request.body.decode('utf-8'))
        url = (body.get('url') or '').strip()
        level_index = int(body.get('level_index') or 0)
        selections = body.get('selections') or []
        if not url:
            return JsonResponse({'error': 'url is required'}, status=400)
    except (json.JSONDecodeError, TypeError) as e:
        return JsonResponse({'error': str(e)}, status=400)
    driver = _get_selenium_driver()
    if not driver:
        return JsonResponse({'error': 'Selenium/Chrome not available.', 'options': []})
    try:
        driver.get(url)
        import time
        time.sleep(2)
        selects = driver.find_elements('css selector', 'select')
        if level_index <= 0 or level_index > len(selects):
            return JsonResponse({'options': []})
        try:
            from selenium.webdriver.support.ui import Select
            for i, val in enumerate(selections):
                if i >= len(selects):
                    break
                Select(selects[i]).select_by_value(val)
                time.sleep(0.6)
        except Exception:
            pass
        time.sleep(0.8)
        selects = driver.find_elements('css selector', 'select')
        sel = selects[level_index - 1] if level_index <= len(selects) else None
        if not sel:
            return JsonResponse({'options': []})
        opts = []
        for opt in sel.find_elements('tag name', 'option'):
            v = opt.get_attribute('value')
            if v is None:
                v = ''
            text = (opt.text or '').strip() or v
            opts.append({'value': v, 'text': text})
        return JsonResponse({'options': opts})
    except Exception as e:
        logger.exception('scraper_dynamic_dropdown failed')
        return JsonResponse({'error': str(e), 'options': []})
    finally:
        try:
            driver.quit()
        except Exception:
            pass


class PasswordUpdateView(APIView):
    def post(self, request, *args, **kwargs):
        username = request.data.get('username')
        password = request.data.get('password')
        newpassword = request.data.get('newpassword')
        
        try:
            user = Customer.objects.get(username=username)
            
            # Verify old password
            if user.password.startswith('pbkdf2_') or user.password.startswith('argon2'):
                password_valid = user.check_password(password)
            else:
                # Legacy: compare plain text
                password_valid = (user.password == password)
            
            if password_valid:
                # Set new hashed password
                user.set_password(newpassword)
                user.save()
                token = self.generate_unique_key()
                return Response({'authToken': token, 'message': 'Password updated successfully'}, status=status.HTTP_200_OK)
            else:
                return Response({'error': 'Invalid current password'}, status=status.HTTP_401_UNAUTHORIZED)
        except Customer.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        

    def generate_unique_key(self):
        length = 40
        characters = string.ascii_letters + string.digits
        key = ''.join(random.choice(characters) for _ in range(length))
        return key 



class MobileUpdateView(APIView):
    def post(self, request, *args, **kwargs):
        username = request.data.get('username')
        newusername = request.data.get('newusername')
        password = request.data.get('password')
        
        try:
            user = Customer.objects.get(username=username)
            
            # Verify password
            if user.password.startswith('pbkdf2_') or user.password.startswith('argon2'):
                password_valid = user.check_password(password)
            else:
                # Legacy: compare plain text
                password_valid = (user.password == password)
            
            if password_valid:
                # Check if new username already exists
                if Customer.objects.filter(username=newusername).exclude(pk=user.pk).exists():
                    return Response({'error': 'Mobile number already exists'}, status=status.HTTP_400_BAD_REQUEST)
                
                user.username = newusername
                user.save()
                token = self.generate_unique_key()
                return Response({'authToken': token, 'message': 'Mobile number updated successfully'}, status=status.HTTP_200_OK)
            else:
                return Response({'error': 'Invalid password'}, status=status.HTTP_401_UNAUTHORIZED)
        except Customer.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        

    def generate_unique_key(self):
        length = 40
        characters = string.ascii_letters + string.digits
        key = ''.join(random.choice(characters) for _ in range(length))
        return key 


# ==============================================================================
# VERIFICATION VIEWS (Email + WhatsApp)
# ==============================================================================

class SendVerificationCodeView(APIView):
    """Send verification code via Telegram/Email/WhatsApp"""
    permission_classes = [PublicAccess]

    def post(self, request):
        username = request.data.get('username')
        if not username:
            return Response({'error': 'Phone number is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            customer = Customer.objects.get(username=username)
        except Customer.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        from .verification_service import send_verification_code
        result = send_verification_code(customer, purpose='verification')
        if result['success']:
            response_data = {
                'message': result.get('message', 'Verification code sent'),
                'method': result.get('method', 'unknown'),
                'expires_in': 600,
            }
            if result.get('requires_linking'):
                response_data['requires_linking'] = True
                response_data['bot_username'] = result.get('bot_username')
            return Response(response_data, status=status.HTTP_200_OK)
        return Response({
            'error': result['message'],
            'method': result.get('method'),
            'requires_linking': result.get('requires_linking', False),
            'bot_username': result.get('bot_username'),
        }, status=status.HTTP_400_BAD_REQUEST)


class VerifyCodeView(APIView):
    """Verify the verification code"""
    permission_classes = [PublicAccess]

    def post(self, request):
        username = request.data.get('username')
        code = request.data.get('code')
        if not username or not code:
            return Response({'error': 'Phone number and code are required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            customer = Customer.objects.get(username=username)
        except Customer.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        from .verification_service import verify_code
        result = verify_code(customer, code)
        if result['success']:
            return Response({'message': result['message'], 'verified': True}, status=status.HTTP_200_OK)
        return Response({'error': result['message'], 'verified': False}, status=status.HTTP_400_BAD_REQUEST)


class SendPasswordResetCodeView(APIView):
    """Send password reset code via Email (primary) or WhatsApp (fallback)"""
    permission_classes = [PublicAccess]
    authentication_classes = []

    def post(self, request):
        username = request.data.get('username')
        email = request.data.get('email')
        if not username:
            return Response({'success': False, 'error': 'Phone number is required', 'message': 'Phone number is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            customer = Customer.objects.get(username=username)
        except Customer.DoesNotExist:
            return Response({'success': False, 'error': 'User not found', 'message': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        if email:
            from .verification_service import send_verification_to_email
            result = send_verification_to_email(customer, email, purpose='password_reset')
        else:
            from .verification_service import send_verification_code
            result = send_verification_code(customer, purpose='password_reset')
        if result['success']:
            return Response({
                'success': True,
                'message': result.get('message', 'Password reset code sent'),
                'method': result.get('method'),
                'expires_in': 600,
            }, status=status.HTTP_200_OK)
        return Response({
            'success': False,
            'message': result.get('message', 'Failed to send code'),
            'error': result.get('message'),
            'method': result.get('method'),
            'needs_email': result.get('needs_email', False),
            'needs_activation': result.get('needs_activation', False),
        }, status=status.HTTP_400_BAD_REQUEST)


class ResetPasswordWithCodeView(APIView):
    """Reset password using verification code"""
    permission_classes = [PublicAccess]

    def post(self, request):
        username = request.data.get('username')
        code = request.data.get('code')
        new_password = request.data.get('new_password')
        save_email = request.data.get('save_email')
        if not username or not code or not new_password:
            return Response({'error': 'Phone number, code, and new password are required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            customer = Customer.objects.get(username=username)
        except Customer.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        from .verification_service import verify_code
        result = verify_code(customer, code)
        if not result['success']:
            return Response({'error': result['message']}, status=status.HTTP_400_BAD_REQUEST)
        customer.set_password(new_password)
        if save_email:
            customer.email = save_email
        customer.save()
        return Response({'message': 'Password reset successfully'}, status=status.HTTP_200_OK)


class UpdateEmailView(APIView):
    """Allow user to add/update their email"""
    permission_classes = [PublicAccess]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        email = request.data.get('email')
        if not username or not password or not email:
            return Response({'error': 'Phone number, password, and email are required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            customer = Customer.objects.get(username=username)
        except Customer.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        if not customer.check_password(password):
            return Response({'error': 'Invalid password'}, status=status.HTTP_401_UNAUTHORIZED)
        if Customer.objects.filter(email=email).exclude(pk=customer.pk).exists():
            return Response({'error': 'This email is already registered'}, status=status.HTTP_400_BAD_REQUEST)
        customer.email = email
        customer.save(update_fields=['email'])
        return Response({'message': 'Email updated successfully'}, status=status.HTTP_200_OK)


class UpdateWhatsAppApiKeyView(APIView):
    """Allow user to save their CallMeBot API key for free WhatsApp notifications"""
    permission_classes = [PublicAccess]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        whatsapp_apikey = request.data.get('whatsapp_apikey')
        if not username or not password or not whatsapp_apikey:
            return Response({'error': 'Phone number, password, and WhatsApp API key are required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            customer = Customer.objects.get(username=username)
        except Customer.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        if not customer.check_password(password):
            return Response({'error': 'Invalid password'}, status=status.HTTP_401_UNAUTHORIZED)
        if hasattr(customer, 'whatsapp_apikey'):
            customer.whatsapp_apikey = whatsapp_apikey
            customer.save(update_fields=['whatsapp_apikey'])
        return Response({'message': 'WhatsApp API key saved successfully'}, status=status.HTTP_200_OK)


class GenerateDefaultPasswordView(APIView):
    """Generate default password preview (for frontend display)"""
    permission_classes = [PublicAccess]

    def post(self, request):
        full_name = request.data.get('fullName', '')
        year_of_birth = request.data.get('year_of_birth')
        if not full_name or not year_of_birth:
            return Response({'error': 'Full name and year of birth are required'}, status=status.HTTP_400_BAD_REQUEST)
        name_part = full_name[:3].strip()
        if len(name_part) > 0:
            name_part = name_part[0].upper() + name_part[1:].lower()
        default_password = f"{name_part}@{year_of_birth}"
        return Response({'default_password': default_password}, status=status.HTTP_200_OK)


# ----- Removed: view_order, view_ordered, view_canceled, update_shipped_status, move_*_orders, get_shipped_status -----
# ----- Removed: GroupViewSet, SubjectViewSet, ChapterViewSet, TopicViewSet, InstituteViewSet, YearViewSet, McqIctViewSet,
#      SubjectQuestionTablesView, SubjectQuestionDataView, GetGroupsByClassView, GetDepartmentsView, GetClassInfoView -----


def _university_departments_json_path():
    """Path to departments.json (university departments list for Teacher signup)."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'departments.json')


def _append_department_to_json(dept_name, faculty=None):
    """Append a department to departments.json (e.g. from signup 'Others')."""
    if not dept_name or len(dept_name) > 200:
        return
    path = _university_departments_json_path()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {'departments': []}
    departments = data.get('departments', [])
    if any((d.get('dept_name') or '').strip().lower() == dept_name.lower() for d in departments):
        return
    departments.append({
        'dept_code': 'CUSTOM_' + str(len(departments) + 1),
        'dept_name': dept_name,
        'faculty': faculty
    })
    data['departments'] = departments
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError as e:
        logger.warning('Could not write departments.json: %s', e)


class UniversityDepartmentsView(APIView):
    """
    GET: Return university departments from departments.json (all aspects of knowledge, worldwide).
    Used for Teacher signup when Level = University. Not from database.
    POST: Append a new department (when user selects "Others" and enters name); adds to departments.json.
    """
    permission_classes = [PublicAccess]
    authentication_classes = []

    def get(self, request):
        path = _university_departments_json_path()
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            departments = data.get('departments', [])
            # Sort by dept_name ascending (Others is added by frontend at the end)
            departments = sorted(departments, key=lambda d: (d.get('dept_name') or '').strip().lower())
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning('University departments JSON not found or invalid: %s', e)
            departments = []
        return Response({'departments': departments, 'count': len(departments)}, status=status.HTTP_200_OK)

    def post(self, request):
        """Append a department to departments.json (e.g. when user chose 'Others' and entered a name)."""
        dept_name = (request.data.get('dept_name') or request.data.get('department_name') or '').strip()
        if not dept_name or len(dept_name) > 200:
            return Response(
                {'error': 'dept_name is required and must be 1–200 characters'},
                status=status.HTTP_400_BAD_REQUEST
            )
        path = _university_departments_json_path()
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {'departments': []}
        departments = data.get('departments', [])
        faculty = (request.data.get('faculty') or '').strip() or None
        dept_code = (request.data.get('dept_code') or '').strip()
        if not dept_code:
            dept_code = 'CUSTOM_' + str(len(departments) + 1)
        if any(d.get('dept_name', '').strip().lower() == dept_name.lower() for d in departments):
            return Response({'departments': data.get('departments', []), 'count': len(departments)}, status=status.HTTP_200_OK)
        departments.append({
            'dept_code': dept_code[:20],
            'dept_name': dept_name,
            'faculty': faculty
        })
        data['departments'] = departments
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.warning('Could not write departments.json: %s', e)
            return Response({'error': 'Could not save department'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({'departments': departments, 'count': len(departments)}, status=status.HTTP_201_CREATED)
