from django.shortcuts import render, get_object_or_404
from rest_framework import generics, status, viewsets, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from .models import (Institutes, Token, Item, Merit, Merit5, Merit6, Banbeis, Recommend, Recommend5, Recommend6, 
                     Vacancy, Vacancy5, Vacancy6, Customer, Order, OrderDetail, Transaction, Ordered, Canceled,
                     Notification, Group, Subject, Chapter, Topic, Mcq_ict, Institute, Year, Country, Location,
                     ClassLevel, ClassGroupMapping, Department)
from .serializers import (InstitutesSerializer, TokenSerializer, RecommendSerializer, Recommend5Serializer, 
                         Recommend6Serializer, BanbeisSerializer, MeritSerializer, Merit5Serializer, Merit6Serializer, 
                         VacancySerializer, Vacancy5Serializer, Vacancy6Serializer, ItemSerializer, 
                         CustomerSignupSerializer, CustomerUpdateSerializer, OrderSerializer, NotificationSerializer, GroupSerializer, 
                         SubjectSerializer, ChapterSerializer, TopicSerializer, McqIctSerializer, InstituteSerializer, 
                         YearSerializer, CountrySerializer, CountryListSerializer)
from rest_framework.permissions import AllowAny
from .permissions import IsSuperUserOrStaff, PublicAccess
from .location import Bangladesh
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import check_password
from django.views.decorators.csrf import csrf_exempt
import logging, random, string, json, requests, os, re, csv, time
from urllib import parse as urllib_parse
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


class LevelsByCountryView(APIView):
    """
    GET /api/levels_by_country/?country_code=BD
    Returns unique Level/Class values from cheradip_subject for the given country, with level_tr.
    Level column may contain comma-separated values (e.g. 'SSC,JSC,PSC'); we split and return unique list
    ordered by class_level ascending. Each item has level, level_tr, and label = "level (level_tr)".
    Used by signup to populate Class (Student) and Level (Teacher) dropdowns.
    """
    permission_classes = [PublicAccess]
    authentication_classes = []

    DEFAULT_CLASS_FOR_UNKNOWN = 999

    def get(self, request):
        country_code = (request.query_params.get('country_code') or '').strip().upper()
        if not country_code:
            return Response({'levels': [], 'error': 'country_code is required'}, status=status.HTTP_400_BAD_REQUEST)

        from django.db import connection
        table = 'cheradip_subject'
        # level_name -> (min_class_level, level_tr to show)
        level_info = {}
        with connection.cursor() as cur:
            cur.execute(
                f"SELECT level, level_tr, class_level FROM {table} WHERE country_id = %s AND level IS NOT NULL AND TRIM(COALESCE(level, '')) != ''",
                [country_code]
            )
            for (level_str, level_tr_str, class_level) in cur.fetchall():
                if not level_str:
                    continue
                s = (class_level or '').strip()
                if not s:
                    cl = self.DEFAULT_CLASS_FOR_UNKNOWN
                elif s.isdigit():
                    cl = int(s)
                elif s == '9-10':
                    cl = 9
                elif s == '11-12':
                    cl = 11
                elif s == '13-16':
                    cl = 13
                else:
                    cl = self.DEFAULT_CLASS_FOR_UNKNOWN
                level_parts = [p.strip() for p in level_str.split(',') if p.strip()]
                level_tr_parts = [p.strip() for p in (level_tr_str or '').split(',') if p.strip()] if level_tr_str else []
                for i, part in enumerate(level_parts):
                    tr = level_tr_parts[i] if i < len(level_tr_parts) else (level_tr_parts[0] if level_tr_parts else None)
                    if part not in level_info or cl < level_info[part][0]:
                        level_info[part] = (cl, tr)

        # Order levels by relevant class ascending (class_level), then by level name
        def sort_key(item):
            level_name = item[0]
            min_cl = item[1][0]
            return (min_cl, level_name)

        levels = []
        for lev, (min_cl, level_tr) in sorted(level_info.items(), key=sort_key):
            label = f"{lev} ({level_tr})" if level_tr else lev
            levels.append({'level': lev, 'level_tr': level_tr or '', 'label': label})
        if not any(item['level'] == 'University' for item in levels):
            levels.append({'level': 'University', 'level_tr': 'University', 'label': 'University (University)'})

        return Response({'levels': levels, 'country_code': country_code})


# Class number to display name for Student signup (Class Zero, Class One, ...)
CLASS_LEVEL_LABELS = {
    0: 'Zero', 1: 'One', 2: 'Two', 3: 'Three', 4: 'Four', 5: 'Five', 6: 'Six',
    7: 'Seven', 8: 'Eight', 9: 'Nine', 10: 'Ten', 11: 'Eleven', 12: 'Twelve',
    13: 'Thirteen', 14: 'Fourteen', 15: 'Fifteen', 16: 'Sixteen',
}
CLASSES_WITH_GROUPS = {9, 10, 11, 12}  # Show Group dropdown for these


class ClassesByCountryView(APIView):
    """
    GET /api/classes_by_country/?country_code=BD
    Returns distinct class_level from cheradip_subject for the given country, ordered ascending.
    Each item: value (class number), label (e.g. "Class Zero", "Class One"), has_groups (true for 9,10,11,12).
    Used for Student signup Class dropdown.
    """
    permission_classes = [PublicAccess]
    authentication_classes = []

    def get(self, request):
        country_code = (request.query_params.get('country_code') or '').strip().upper()
        if not country_code:
            return Response({'classes': [], 'error': 'country_code is required'}, status=status.HTTP_400_BAD_REQUEST)
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT TRIM(class_level) FROM cheradip_subject
                WHERE country_id = %s AND class_level IS NOT NULL AND TRIM(class_level) != ''
                """,
                [country_code]
            )
            rows = cur.fetchall()
        distinct_class = set((r[0].strip() for r in rows if r[0] and r[0].strip()))
        # Always include Class Zero through Class Eight so dropdown is complete
        single_classes = [str(i) for i in range(0, 9)]
        classes = []
        for c in single_classes:
            n = int(c)
            label_name = CLASS_LEVEL_LABELS.get(n)
            label = f"Class {label_name}" if label_name is not None else f"Class {n}"
            classes.append({
                'value': c,
                'label': label,
                'has_groups': False,
            })
        if '9-10' in distinct_class:
            classes.append({'value': '9-10', 'label': 'Class 9-10', 'has_groups': True})
        if '11-12' in distinct_class:
            classes.append({'value': '11-12', 'label': 'Class 11-12', 'has_groups': True})
        classes.append({
            'value': '13-16',
            'label': 'Degree / University',
            'has_groups': False,
        })
        return Response({'classes': classes, 'country_code': country_code})


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


class SubjectsByCountryLevelView(APIView):
    """
    GET /api/subjects_by_country_level/?country_code=BD&level=HSC
    GET /api/subjects_by_country_level/?country_code=BD&level=SSC,JSC
    Returns subjects from cheradip_subject for the given country and level(s) (for Teacher signup).
    Level may be comma-separated (e.g. SSC,JSC); subjects matching ANY of those levels are returned.
    Each level matches exact or as part of comma-separated in DB (e.g. level LIKE '%SSC%').
    """
    permission_classes = [PublicAccess]
    authentication_classes = []

    def get(self, request):
        country_code = (request.query_params.get('country_code') or '').strip().upper()
        level_param = (request.query_params.get('level') or '').strip()
        if not country_code or not level_param:
            return Response(
                {'subjects': [], 'error': 'country_code and level are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Support comma-separated levels: retrieve subjects for all of them
        level_parts = [p.strip() for p in level_param.split(',') if p.strip()]
        if not level_parts:
            return Response({'subjects': [], 'country_code': country_code, 'level': level_param})

        from django.db import connection
        table = 'cheradip_subject'
        # Broad SQL match so subjects load; then filter in Python so "প্রাথমিক" does NOT match "প্রাক-প্রাথমিক"
        per_part = '(level = %s OR level LIKE %s)'
        level_conditions = ' OR '.join([per_part] * len(level_parts))
        params = [country_code]
        for part in level_parts:
            params.extend([part, f'%{part}%'])

        with connection.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, subject_code, subject_name, subject_translated, level
                FROM {table}
                WHERE country_id = %s AND level IS NOT NULL AND TRIM(COALESCE(level, '')) != ''
                  AND ({level_conditions})
                """,
                params
            )
            rows = cur.fetchall()

        # Keep only rows where each selected part appears as a whole token (comma-separated), not substring
        def level_matches(level_str, parts):
            if not level_str or not parts:
                return False
            tokens = [t.strip() for t in level_str.split(',') if t.strip()]
            return any(p in tokens for p in parts)

        selected_parts = set(level_parts)
        subjects = []
        for r in rows:
            level_val = (r[4] or '').strip()
            if level_matches(level_val, selected_parts):
                subjects.append({'id': r[0], 'subject_code': r[1], 'subject_name': r[2] or '', 'subject_name_tr': r[3] or ''})
        return Response({'subjects': subjects, 'country_code': country_code, 'level': level_param})


class GroupsByCountryLevelView(APIView):
    """
    GET /api/groups_by_country_level/?country_code=BD&level=HSC
    Returns unique groups from cheradip_subject.groups for the given country and level (for Student signup).
    Parses JSON/longtext groups column and resolves to Group model (group_code, group_name) where possible.
    """
    permission_classes = [PublicAccess]
    authentication_classes = []

    def get(self, request):
        country_code = (request.query_params.get('country_code') or '').strip().upper()
        level = (request.query_params.get('level') or '').strip()
        if not country_code or not level:
            return Response(
                {'groups': [], 'error': 'country_code and level are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from django.db import connection
        import json
        table = 'cheradip_subject'
        with connection.cursor() as cur:
            cur.execute(
                f"""
                SELECT groups FROM {table}
                WHERE country_id = %s AND level IS NOT NULL AND TRIM(COALESCE(level, '')) != ''
                  AND (level = %s OR level LIKE %s OR level LIKE %s OR level LIKE %s)
                """,
                [country_code, level, f'%{level},%', f'{level},%', f'%,{level}']
            )
            rows = cur.fetchall()

        group_names = set()
        for (groups_raw,) in rows:
            if not groups_raw:
                continue
            try:
                if isinstance(groups_raw, str):
                    parsed = json.loads(groups_raw)
                else:
                    parsed = groups_raw if isinstance(groups_raw, (list, tuple)) else []
                for g in parsed:
                    if g and isinstance(g, str):
                        group_names.add(g.strip())
            except (TypeError, ValueError, json.JSONDecodeError):
                pass

        # Fallback: SSC rows in cheradip_subject often have groups=[]. For BD+SSC or BD+HSC use default groups when none found.
        if not group_names and level in ('SSC', 'HSC'):
            default_bd_groups = [
                'Science', 'Humanities', 'Business Studies', 'Islamic Studies',
                'Home Science', 'Music',
            ]
            group_names = set(default_bd_groups)

        # Return groups from cheradip_subject.groups only (no Group table lookup; no group_name_bn column)
        groups_data = [
            {'group_code': name[:30], 'group_name': name}
            for name in sorted(group_names) if name
        ]
        return Response({'groups': groups_data, 'country_code': country_code, 'level': level})


# ==============================================================================
# INSTITUTE VIEWSETS
# ==============================================================================

class InstitutesViewSet(viewsets.ModelViewSet):
    serializer_class = InstitutesSerializer

    def get_queryset(self):
        search_query = self.request.query_params.get('q', '')
        eiinNo = self.request.query_params.get('eiinNo')
        divisionName = self.request.query_params.getlist('divisionName')
        districtName = self.request.query_params.getlist('districtName')
        thanaName = self.request.query_params.getlist('thanaName')
        instituteTypeName = self.request.query_params.getlist('instituteTypeName')
        instituteName = self.request.query_params.getlist('instituteName')
        instituteNameBn = self.request.query_params.getlist('instituteNameBn')
        mouzaName = self.request.query_params.getlist('mouzaName')
        mouzaNameBn = self.request.query_params.getlist('mouzaNameBn')
        thanaNameBn = self.request.query_params.getlist('thanaNameBn')
        districtNameBn = self.request.query_params.getlist('districtNameBn')
        isGovt = self.request.query_params.getlist('isGovt')

        queryset = Institutes.objects.all()

        if isGovt:
            queryset = queryset.filter(isGovt__in=isGovt)
        if instituteTypeName:
            queryset = queryset.filter(instituteTypeName__in=instituteTypeName)
        if divisionName:
            queryset = queryset.filter(divisionName__in=divisionName)
        if districtName:
            queryset = queryset.filter(districtName__in=districtName)
        if thanaName:
            queryset = queryset.filter(thanaName__in=thanaName)
        if eiinNo:
            queryset = queryset.filter(eiinNo=eiinNo)
        if instituteName:
            queryset = queryset.filter(instituteName__in=instituteName)
        if instituteNameBn:
            queryset = queryset.filter(instituteNameBn__in=instituteNameBn)

        if search_query:
            exact_match_qs = queryset.annotate(
                relevance=RawSQL(
                    """
                    (MATCH(instituteName) AGAINST (%s IN NATURAL LANGUAGE MODE) +
                     MATCH(instituteNameBn) AGAINST (%s IN NATURAL LANGUAGE MODE) +
                     MATCH(eiinNo) AGAINST (%s IN NATURAL LANGUAGE MODE) +
                     MATCH(mouzaName) AGAINST (%s IN NATURAL LANGUAGE MODE) +
                     MATCH(thanaName) AGAINST (%s IN NATURAL LANGUAGE MODE) +
                     MATCH(districtName) AGAINST (%s IN NATURAL LANGUAGE MODE) +
                     MATCH(mouzaNameBn) AGAINST (%s IN NATURAL LANGUAGE MODE) +
                     MATCH(thanaNameBn) AGAINST (%s IN NATURAL LANGUAGE MODE) +
                     MATCH(districtNameBn) AGAINST (%s IN NATURAL LANGUAGE MODE))
                    """,
                    (search_query, search_query, search_query, search_query, search_query, search_query, search_query, search_query, search_query)
                )
            ).filter(relevance__gt=0).order_by('-relevance')
    
            if exact_match_qs.exists():
                return exact_match_qs
    
            queryset = queryset.filter(
                Q(instituteName__icontains=search_query) |
                Q(instituteNameBn__icontains=search_query) |
                Q(mouzaName__icontains=search_query) |
                Q(thanaName__icontains=search_query) |
                Q(districtName__icontains=search_query) |
                Q(mouzaNameBn__icontains=search_query) |
                Q(thanaNameBn__icontains=search_query) |
                Q(districtNameBn__icontains=search_query) |
                Q(eiinNo__icontains=search_query)
            ).order_by('instituteName')
    
            return queryset

        return queryset


    # ✅ Custom endpoints
    @action(detail=False, methods=['get'])
    def unique_types(self, request):
        types = Institutes.objects.values_list('instituteTypeName', flat=True).distinct().order_by('instituteTypeName')
        return Response(types)
        
    @action(detail=False, methods=['get'])
    def unique_divisions(self, request):
        divisions = Institutes.objects.values_list('divisionName', flat=True).distinct().order_by('divisionName')
        return Response(divisions)

    @action(detail=False, methods=['get'])
    def unique_districts(self, request):
        divisions = request.query_params.getlist('divisionName')
        if not divisions:
            return Response({"error": "divisionName parameter is required"}, status=400)
    
        districts = Institutes.objects.filter(
            divisionName__in=divisions
        ).values_list('districtName', flat=True).distinct().order_by('districtName')
    
        return Response(districts)

    @action(detail=False, methods=['get'])
    def unique_thanas(self, request):
        districts = request.query_params.getlist('districtName')
        if not districts:
            return Response({"error": "district parameter is required"}, status=400)
    
        thanas = Institutes.objects.filter(districtName__in=districts).values_list(
            'thanaName', flat=True
        ).distinct().order_by('thanaName')
    
        return Response(thanas)


class TokenViewSet(viewsets.ModelViewSet):
    serializer_class = TokenSerializer
    queryset = Token.objects.all()
    lookup_field = 'pk'

    def get_queryset(self):
        # Only filter by query param for list or retrieve
        if self.action == 'list':
            token = self.request.query_params.get('token')
            if token:
                return Token.objects.filter(Token=token)
            return Token.objects.none()
        return Token.objects.all()

    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        try:
            token_obj = self.get_object()
            token_obj.Status = 1
            token_obj.save()
            return Response({"success": True, "Status": token_obj.Status})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        
class BanbeisViewSet(viewsets.ModelViewSet):
    serializer_class = BanbeisSerializer

    def get_queryset(self):
        eiin = self.request.query_params.get('eiin')

        # if not eiin:
        #     return Banbeis.objects.none()

        queryset = Banbeis.objects.all()

        if eiin:
            queryset = queryset.filter(EIIN=eiin)

        return queryset


class RecommendViewSet(viewsets.ModelViewSet):
    serializer_class = RecommendSerializer

    def get_queryset(self):
        code = self.request.query_params.get('code')
        districts = self.request.query_params.getlist('district')
        thanas = self.request.query_params.getlist('thana')

        if not code:
            return Recommend.objects.none()

        queryset = Recommend.objects.all()

        if code:
            queryset = queryset.filter(Code=code)
        if districts:
            queryset = queryset.filter(District__in=districts)
        if thanas:
            queryset = queryset.filter(Thana__in=thanas)

        return queryset

    # ✅ Custom endpoints
    @action(detail=False, methods=['get'])
    def unique_districts(self, request):
        districts = Recommend.objects.values_list('District', flat=True).distinct().order_by('District')
        return Response(districts)

    @action(detail=False, methods=['get'])
    def unique_thanas(self, request):
        districts = request.query_params.getlist('district')
        if not districts:
            return Response({"error": "district parameter is required"}, status=400)
    
        thanas = Recommend.objects.filter(District__in=districts).values_list(
            'Thana', flat=True
        ).distinct().order_by('Thana')
    
        return Response(thanas)



class Recommend5ViewSet(viewsets.ModelViewSet):
    serializer_class = Recommend5Serializer

    def get_queryset(self):
        code = self.request.query_params.get('code')
        districts = self.request.query_params.getlist('district')
        thanas = self.request.query_params.getlist('thana')

        if not code:
            return Recommend5.objects.none()

        queryset = Recommend5.objects.all()

        if code:
            queryset = queryset.filter(Code=code)
        if districts:
            queryset = queryset.filter(District__in=districts)
        if thanas:
            queryset = queryset.filter(Thana__in=thanas)

        return queryset

    # ✅ Custom endpoints
    @action(detail=False, methods=['get'])
    def unique_districts(self, request):
        districts = Recommend5.objects.values_list('District', flat=True).distinct().order_by('District')
        return Response(districts)

    @action(detail=False, methods=['get'])
    def unique_thanas(self, request):
        districts = request.query_params.getlist('district')
        if not districts:
            return Response({"error": "district parameter is required"}, status=400)
    
        thanas = Recommend5.objects.filter(District__in=districts).values_list(
            'Thana', flat=True
        ).distinct().order_by('Thana')
    
        return Response(thanas)


class Recommend6ViewSet(viewsets.ModelViewSet):
    serializer_class = Recommend6Serializer

    def get_queryset(self):
        code = self.request.query_params.get('code')
        districts = self.request.query_params.getlist('district')
        thanas = self.request.query_params.getlist('thana')

        if not code:
            return Recommend6.objects.none()

        queryset = Recommend6.objects.all()

        if code:
            queryset = queryset.filter(Code=code)
        if districts:
            queryset = queryset.filter(District__in=districts)
        if thanas:
            queryset = queryset.filter(Thana__in=thanas)

        return queryset

    # ✅ Custom endpoints
    @action(detail=False, methods=['get'])
    def unique_districts(self, request):
        districts = Recommend6.objects.values_list('District', flat=True).distinct().order_by('District')
        return Response(districts)

    @action(detail=False, methods=['get'])
    def unique_thanas(self, request):
        districts = request.query_params.getlist('district')
        if not districts:
            return Response({"error": "district parameter is required"}, status=400)
    
        thanas = Recommend6.objects.filter(District__in=districts).values_list(
            'Thana', flat=True
        ).distinct().order_by('Thana')
    
        return Response(thanas)


class VacancyViewSet(viewsets.ModelViewSet):
    serializer_class = VacancySerializer

    def get_queryset(self):
        subject = self.request.query_params.get('subject')
        designation = self.request.query_params.get('designation')
        districts = self.request.query_params.getlist('district')

        if not subject and not designation and not districts:
            return Vacancy.objects.none()

        queryset = Vacancy.objects.all()

        if subject:
            queryset = queryset.filter(Subject=subject)
        if designation:
            queryset = queryset.filter(Designation=designation)
        if districts:
            queryset = queryset.filter(District__in=districts)

        return queryset


class Vacancy5ViewSet(viewsets.ModelViewSet):
    serializer_class = Vacancy5Serializer

    def get_queryset(self):
        subject = self.request.query_params.get('subject')
        designation = self.request.query_params.get('designation')
        districts = self.request.query_params.getlist('district')

        if not subject and not designation and not districts:
            return Vacancy5.objects.none()

        queryset = Vacancy5.objects.all()

        if subject:
            queryset = queryset.filter(Subject=subject)
        if designation:
            queryset = queryset.filter(Designation=designation)
        if districts:
            queryset = queryset.filter(District__in=districts)

        return queryset


class Vacancy6ViewSet(viewsets.ModelViewSet):
    serializer_class = Vacancy6Serializer

    def get_queryset(self):
        subject = self.request.query_params.get('subject')
        designation = self.request.query_params.get('designation')
        districts = self.request.query_params.getlist('district')

        if not subject and not designation and not districts:
            return Vacancy6.objects.none()

        queryset = Vacancy6.objects.all()

        if subject:
            queryset = queryset.filter(Subject=subject)
        if designation:
            queryset = queryset.filter(Designation=designation)
        if districts:
            queryset = queryset.filter(District__in=districts)

        return queryset


class MeritViewSet(viewsets.ModelViewSet):
    serializer_class = MeritSerializer

    def get_queryset(self):
        code = self.request.query_params.get('code')
        batch = self.request.query_params.get('batch')
        roll = self.request.query_params.getlist('roll')
        subject = self.request.query_params.getlist('subject')

        if not code:
            return Merit.objects.none()

        queryset = Merit.objects.all()
        if subject:
            queryset = queryset.filter(Subject=subject)
        if roll:
            queryset = queryset.filter(Roll=roll)
        if batch:
            queryset = queryset.filter(Batch=batch)
        if code:
            queryset = queryset.filter(Code=code)

        return queryset


class Merit5ViewSet(viewsets.ModelViewSet):
    serializer_class = Merit5Serializer

    def get_queryset(self):
        code = self.request.query_params.get('code')
        batch = self.request.query_params.get('batch')
        roll = self.request.query_params.getlist('roll')
        subject = self.request.query_params.getlist('subject')

        if not code:
            return Merit5.objects.none()

        queryset = Merit5.objects.all()

        if subject:
            queryset = queryset.filter(Subject=subject)
        if roll:
            queryset = queryset.filter(Roll=roll)
        if batch:
            queryset = queryset.filter(Batch=batch)
        if code:
            queryset = queryset.filter(Code=code)

        return queryset


class Merit6ViewSet(viewsets.ModelViewSet):
    serializer_class = Merit6Serializer

    def get_queryset(self):
        code = self.request.query_params.get('code')
        batch = self.request.query_params.get('batch')
        roll = self.request.query_params.getlist('roll')
        subject = self.request.query_params.getlist('subject')

        if not code:
            return Merit6.objects.none()

        queryset = Merit6.objects.all()

        if subject:
            queryset = queryset.filter(Subject=subject)
        if roll:
            queryset = queryset.filter(Roll=roll)
        if batch:
            queryset = queryset.filter(Batch=batch)
        if code:
            queryset = queryset.filter(Code=code)

        return queryset


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



class OrderRetrieveView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    lookup_field = 'username'

    def get_object(self):
        username = self.kwargs['username']
        try:
            return Order.objects.filter(username=username)
        except Order.DoesNotExist:
            raise Http404

    def get(self, request, *args, **kwargs):
        instances = self.get_object()
        if instances.exists():
            serializer = self.get_serializer(instances, many=True)
            return Response(serializer.data)
        else:
            return Response("0 orders")
        

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
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
    if request.method == 'POST':
        try:
            json_data = json.loads(request.body.decode('utf-8'))
            order_details_data = json_data.pop('orderDetails', [])
            trxid = json_data.pop('trxid', None)
            paidFrom = json_data.pop('paidFrom', None)
            username = json_data.get('username', None)
            
            try:
                transaction = Transaction.objects.get(trxid=trxid, paidFrom=paidFrom)
            except Transaction.DoesNotExist:
                transaction = None
            
            if transaction:
                if username != transaction.username:
                    
                    new_order = Order(**json_data)
                    new_order.save()
                    new_order.transaction.add(transaction)
                    
                    for detail_data in order_details_data:
                        logger.debug(detail_data)
                        order_detail = OrderDetail.objects.create(**detail_data)
                        new_order.orderDetails.add(order_detail)
                        
                    transaction.username = username 
                    transaction.save()

                    return JsonResponse({'message': 'Order Created Successfully'})
                else:
                    return JsonResponse({'message': 'You already have an Order with this TrxId!'})
            else:
                return JsonResponse({'error': 'Your TrxId / Account has not been found! Please Check your TrxId and Account Number, Or Contact Us'})

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    else:
        return JsonResponse({'message': 'Invalid request method'}, status=405)


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
    """Sanitize for file paths (matches script: replace / and \ with -)."""
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



def view_order(request, pk):
    order = get_object_or_404(Order, pk=pk)
    # Render the 'view_order.html' template with the order details
    return render(request, 'cheradip/view_order.html', {'order': order})


def view_ordered(request, pk):
    order = get_object_or_404(Ordered, pk=pk)
    # Render the 'view_order.html' template with the order details
    return render(request, 'cheradip/view_order.html', {'order': order})


def view_canceled(request, pk):
    order = get_object_or_404(Canceled, pk=pk)
    # Render the 'view_order.html' template with the order details
    return render(request, 'cheradip/view_order.html', {'order': order})


def update_shipped_status(request, order_id, is_shipped):
    try:
        # Get the Order instance by order_id
        order = get_object_or_404(Order, id=order_id)

        # Convert the 'is_shipped' string to a boolean
        is_shipped = is_shipped.lower() == 'true'

        # Update the 'shipped' field in the database
        order.shipped = is_shipped
        order.save()

        # Assuming the update was successful
        response_data = {"updated": True}
        return JsonResponse(response_data)
    except Exception as e:
        # Handle any exceptions or errors
        response_data = {"error": str(e)}
        return JsonResponse(response_data, status=500)
    

def move_completed_orders(request, pk):
    completed_orders = Order.objects.filter(shipped=True, pk=pk)

    for new_order in completed_orders:
        order = Ordered.objects.create(
            id=new_order.id,
            division=new_order.division,
            district=new_order.district,
            thana=new_order.thana,
            paymentMethod=new_order.paymentMethod,
            username=new_order.username,
            fullName=new_order.fullName,
            gender=new_order.gender,
            union=new_order.union,
            village=new_order.village,
            altMobileNo=new_order.altMobileNo,
            shipped=new_order.shipped,
        )

        order.orderDetails.set(new_order.orderDetails.all())
        order.transaction.set(new_order.transaction.all())

        for order_detail in order.orderDetails.all():
            try:
                item = Item.objects.get(id=order_detail.id)  # Retrieve the correct Item
                item.in_stock -= order_detail.Quantity 
                item.save()
            except Item.DoesNotExist:
                # Print or log the problematic OrderDetail
                print(f"Item not found for OrderDetail: {order_detail.Name}")


        new_order.delete()

        message = "Completed Orders moved successfully"
        return HttpResponse(message)
    message = "Sorry! First check the Shipping Status and then Move again!"
    return HttpResponse(message)

def move_canceled_orders(request, pk):
    canceled_orders = Order.objects.filter(pk=pk)

    for new_order in canceled_orders:
        order = Canceled.objects.create(
            id=new_order.id,
            division=new_order.division,
            district=new_order.district,
            thana=new_order.thana,
            paymentMethod=new_order.paymentMethod,
            username=new_order.username,
            fullName=new_order.fullName,
            gender=new_order.gender,
            union=new_order.union,
            village=new_order.village,
            altMobileNo=new_order.altMobileNo,
            shipped=new_order.shipped,
        )

        order.orderDetails.set(new_order.orderDetails.all())
        order.transaction.set(new_order.transaction.all())

        new_order.delete()

        message = "Canceled Orders moved successfully"
        return HttpResponse(message)
    message = "Sorry! First check the Shipping Status and then Move again!"
    return HttpResponse(message)


def retrieve_canceled_orders(request, pk):
    canceled_orders = Canceled.objects.filter(pk=pk)

    for new_order in canceled_orders:
        order = Order.objects.create(
            id=new_order.id,
            division=new_order.division,
            district=new_order.district,
            thana=new_order.thana,
            paymentMethod=new_order.paymentMethod,
            username=new_order.username,
            fullName=new_order.fullName,
            gender=new_order.gender,
            union=new_order.union,
            village=new_order.village,
            altMobileNo=new_order.altMobileNo,
            shipped=new_order.shipped,
        )

        order.orderDetails.set(new_order.orderDetails.all())
        order.transaction.set(new_order.transaction.all())

        new_order.delete()

        message = "Canceled Ordered retrieved successfully"
        return HttpResponseRedirect('/admin/cheradip/canceled/')
    message = "Sorry! Canceled Ordered failed to retrieve!"
    return HttpResponse(message)


def retrieve_ordered_orders(request, pk):
    ordered_orders = Ordered.objects.filter(pk=pk)

    for new_order in ordered_orders:
        order = Order.objects.create(
            id=new_order.id,
            division=new_order.division,
            district=new_order.district,
            thana=new_order.thana,
            paymentMethod=new_order.paymentMethod,
            username=new_order.username,
            fullName=new_order.fullName,
            gender=new_order.gender,
            union=new_order.union,
            village=new_order.village,
            altMobileNo=new_order.altMobileNo,
            shipped=new_order.shipped,
        )

        # Transfer many-to-many relations
        order.orderDetails.set(new_order.orderDetails.all())
        order.transaction.set(new_order.transaction.all())
        
        for order_detail in order.orderDetails.all():
            try:
                item = Item.objects.get(id=order_detail.id)  # Retrieve the correct Item
                item.in_stock += order_detail.Quantity 
                item.save()
            except Item.DoesNotExist:
                # Print or log the problematic OrderDetail
                print(f"Item not found for OrderDetail: {order_detail.Name}")

        new_order.delete()

        message = "Ordered Orders retrieved successfully"
        return HttpResponseRedirect('/admin/cheradip/ordered/')
    message = "Sorry! Ordered Orders failed retrieve!"
    return HttpResponse(message)



def get_shipped_status(request, order_id):
    try:
        # Fetch the Order record by its ID
        new_order = Order.objects.get(pk=order_id)
        shipped = new_order.shipped
        return JsonResponse({'shipped': shipped})
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)


# MCQ and Related Model ViewSets
class GroupViewSet(viewsets.ModelViewSet):
    serializer_class = GroupSerializer
    queryset = Group.objects.all().order_by('group_code')
    
    def get_queryset(self):
        queryset = Group.objects.all()
        group_code = self.request.query_params.get('group_code')
        if group_code:
            queryset = queryset.filter(group_code=group_code)
        return queryset.order_by('group_code')


class SubjectViewSet(viewsets.ModelViewSet):
    serializer_class = SubjectSerializer
    
    def get_queryset(self):
        queryset = Subject.objects.all()
        group_codes = self.request.query_params.getlist('groups')
        subject_code = self.request.query_params.get('subject_code')
        
        if group_codes:
            queryset = queryset.filter(groups__group_code__in=group_codes).distinct()
        
        if subject_code:
            queryset = queryset.filter(subject_code=subject_code)
        
        return queryset.order_by('subject_code')


class ChapterViewSet(viewsets.ModelViewSet):
    serializer_class = ChapterSerializer
    
    def get_queryset(self):
        queryset = Chapter.objects.all()
        subject_codes = self.request.query_params.getlist('subjects')
        chapter_no = self.request.query_params.get('chapter_no')
        if subject_codes:
            queryset = queryset.filter(subject_code__in=subject_codes)
        if chapter_no:
            queryset = queryset.filter(chapter_no=chapter_no)
        return queryset.order_by('subject_code', 'chapter_no')


class TopicViewSet(viewsets.ModelViewSet):
    serializer_class = TopicSerializer
    
    def get_queryset(self):
        queryset = Topic.objects.all().select_related('chapter')
        chapter_ids = self.request.query_params.getlist('chapters')
        topic_no = self.request.query_params.get('topic_no')
        
        if chapter_ids:
            queryset = queryset.filter(chapter_id__in=chapter_ids)
        
        if topic_no:
            queryset = queryset.filter(topic_no=topic_no)
        
        return queryset.order_by('chapter__subject_code', 'chapter__chapter_no', 'topic_no')


class InstituteViewSet(viewsets.ModelViewSet):
    serializer_class = InstituteSerializer
    queryset = Institute.objects.all().order_by('institute_code')
    
    def get_queryset(self):
        queryset = Institute.objects.all()
        institute_code = self.request.query_params.get('institute_code')
        institute_type = self.request.query_params.getlist('institute_type')
        
        if institute_code:
            queryset = queryset.filter(institute_code=institute_code)
        
        if institute_type:
            queryset = queryset.filter(institute_type__in=institute_type)
        
        return queryset.order_by('institute_code')


class YearViewSet(viewsets.ModelViewSet):
    serializer_class = YearSerializer
    queryset = Year.objects.all().order_by('year_code')
    
    def get_queryset(self):
        queryset = Year.objects.all()
        year_code = self.request.query_params.get('year_code')
        institute_ids = self.request.query_params.getlist('institutes')
        
        if year_code:
            queryset = queryset.filter(year_code=year_code)
        
        # Filter years by institutes if provided
        if institute_ids:
            queryset = queryset.filter(questions__institutes__institute_code__in=institute_ids).distinct()
        
        return queryset.order_by('year_code')


class McqIctViewSet(viewsets.ModelViewSet):
    serializer_class = McqIctSerializer
    queryset = Mcq_ict.objects.all().select_related('chapter', 'topic').prefetch_related(
        'institutes', 'years'
    )

    def get_queryset(self):
        queryset = Mcq_ict.objects.all().select_related(
            'chapter', 'topic'
        ).prefetch_related('institutes', 'years')
        subject_codes = self.request.query_params.getlist('subject')
        if subject_codes:
            queryset = queryset.filter(subject_code__in=subject_codes)
        
        # Filter by chapter
        chapter_nos = self.request.query_params.getlist('chapter')
        if chapter_nos:
            queryset = queryset.filter(chapter__chapter_no__in=chapter_nos)
        
        # Filter by topic
        topic_nos = self.request.query_params.getlist('topic')
        if topic_nos:
            queryset = queryset.filter(topic__topic_no__in=topic_nos)
        
        # Filter by institute code(s)
        institute_codes = self.request.query_params.getlist('institute')
        if institute_codes:
            queryset = queryset.filter(institutes__institute_code__in=institute_codes).distinct()
        
        # Filter by year code(s)
        year_codes = self.request.query_params.getlist('year')
        if year_codes:
            queryset = queryset.filter(years__year_code__in=year_codes).distinct()
        
        # Filter by question ID
        qid = self.request.query_params.get('qid')
        if qid:
            queryset = queryset.filter(qid=qid)
        
        # Search by question text
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(question__icontains=search) |
                Q(uddipok__icontains=search) |
                Q(explanation__icontains=search) |
                Q(option1__icontains=search) |
                Q(option2__icontains=search) |
                Q(option3__icontains=search) |
                Q(option4__icontains=search)
            )
        
        # Filter by group code(s): subject_code in Subject rows whose groups JSON contains any requested code
        group_codes = self.request.query_params.getlist('group')
        if group_codes:
            codes_in_groups = set()
            for c in group_codes:
                codes_in_groups.update(
                    Subject.objects.filter(groups__contains=[c]).values_list('subject_code', flat=True)
                )
            if codes_in_groups:
                queryset = queryset.filter(subject_code__in=codes_in_groups)
        return queryset.order_by('qid')
    
    def get_serializer_context(self):
        """Add request to serializer context for building absolute URLs"""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get statistics about questions"""
        queryset = self.get_queryset()
        
        stats = {
            'total_questions': queryset.count(),
            'by_subject': {},
            'by_chapter': {},
            'by_year': {},
            'by_institute_type': {}
        }
        
        # Count by subject
        from django.db.models import Count
        subject_counts = queryset.values('subject_code').annotate(
            count=Count('qid')
        ).order_by('subject_code')
        for item in subject_counts:
            code = item['subject_code']
            subj = Subject.objects.filter(subject_code=code).first()
            name = (subj.subject_translated or subj.subject_name or code) if subj else code
            stats['by_subject'][code] = {'name': name, 'count': item['count']}
        
        # Count by year
        year_counts = queryset.values('years__year_code', 'years__year_name').annotate(
            count=Count('qid', distinct=True)
        ).order_by('years__year_code')
        
        for item in year_counts:
            if item['years__year_code']:
                stats['by_year'][item['years__year_code']] = {
                    'name': item['years__year_name'],
                    'count': item['count']
                }
        
        return Response(stats)


# ==============================================================================
# WHATSAPP VERIFICATION VIEWS
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
                'expires_in': 600  # 10 minutes
            }
            # For Telegram, include bot info if linking required
            if result.get('requires_linking'):
                response_data['requires_linking'] = True
                response_data['bot_username'] = result.get('bot_username')
            return Response(response_data, status=status.HTTP_200_OK)
        else:
            return Response({
                'error': result['message'],
                'method': result.get('method'),
                'requires_linking': result.get('requires_linking', False),
                'bot_username': result.get('bot_username')
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
            return Response({
                'message': result['message'],
                'verified': True
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'error': result['message'],
                'verified': False
            }, status=status.HTTP_400_BAD_REQUEST)


class SendPasswordResetCodeView(APIView):
    """Send password reset code via Email (primary) or WhatsApp (fallback)"""
    permission_classes = [PublicAccess]
    authentication_classes = []  # Allow unauthenticated requests
    
    def post(self, request):
        print("=" * 60)
        print("PASSWORD RESET CODE REQUEST RECEIVED")
        print("=" * 60)
        print(f"Request data: {request.data}")
        print(f"Request META: {dict(request.META)}")
        
        username = request.data.get('username')
        email = request.data.get('email')  # Optional: user can provide email during reset
        
        print(f"Extracted - username: {username}, email: {email}")
        logger.info(f"Password reset request - username: {username}, email provided: {bool(email)}")
        
        if not username:
            return Response({'success': False, 'error': 'Phone number is required', 'message': 'Phone number is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            customer = Customer.objects.get(username=username)
            logger.info(f"Customer found: {customer.username}, has email: {bool(customer.email)}")
        except Customer.DoesNotExist:
            logger.error(f"Customer not found: {username}")
            return Response({'success': False, 'error': 'User not found', 'message': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # If user provided email, use that email (even if customer has a saved email)
        if email:
            logger.info(f"Using provided email: {email}")
            from .verification_service import send_verification_to_email
            result = send_verification_to_email(customer, email, purpose='password_reset')
            
            if result['success']:
                # Store pending email for later verification
                request.session['pending_email'] = email
                request.session['pending_username'] = username
        else:
            # Use customer's saved email or WhatsApp
            logger.info(f"Using customer's saved email or WhatsApp")
            from .verification_service import send_verification_code
            result = send_verification_code(customer, purpose='password_reset')
        
        logger.info(f"Verification result: success={result.get('success')}, method={result.get('method')}, message={result.get('message')}")
        
        if result['success']:
            response_data = {
                'success': True,
                'message': result.get('message', 'Password reset code sent'),
                'method': result.get('method'),
                'expires_in': 600
            }
            return Response(response_data, status=status.HTTP_200_OK)
        else:
            response_data = {
                'success': False,
                'message': result.get('message', 'Failed to send code'),
                'error': result.get('message'),
                'method': result.get('method'),
                'needs_email': result.get('needs_email', False),
                'needs_activation': result.get('needs_activation', False),
            }
            if result.get('activation_instructions'):
                response_data['activation_instructions'] = result['activation_instructions']
            logger.error(f"Failed to send code: {response_data}")
            return Response(response_data, status=status.HTTP_400_BAD_REQUEST)


class ResetPasswordWithCodeView(APIView):
    """Reset password using verification code"""
    permission_classes = [PublicAccess]
    
    def post(self, request):
        username = request.data.get('username')
        code = request.data.get('code')
        new_password = request.data.get('new_password')
        save_email = request.data.get('save_email')  # Optional: save the email used for verification
        
        if not username or not code or not new_password:
            return Response({
                'error': 'Phone number, code, and new password are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            customer = Customer.objects.get(username=username)
        except Customer.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        
        from .verification_service import verify_code
        result = verify_code(customer, code)
        
        if not result['success']:
            return Response({
                'error': result['message']
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Code verified, update password
        customer.set_password(new_password)
        
        # If user wants to save the email they used for verification
        if save_email:
            customer.email = save_email
        
        customer.save()
        
        return Response({
            'message': 'Password reset successfully'
        }, status=status.HTTP_200_OK)


class UpdateEmailView(APIView):
    """Allow user to add/update their email"""
    permission_classes = [PublicAccess]
    
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        email = request.data.get('email')
        
        if not username or not password or not email:
            return Response({
                'error': 'Phone number, password, and email are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            customer = Customer.objects.get(username=username)
        except Customer.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Verify password
        if not customer.check_password(password):
            return Response({'error': 'Invalid password'}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Check if email already in use
        if Customer.objects.filter(email=email).exclude(pk=customer.pk).exists():
            return Response({'error': 'This email is already registered'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Update email
        customer.email = email
        customer.save(update_fields=['email'])
        
        return Response({
            'message': 'Email updated successfully'
        }, status=status.HTTP_200_OK)


class UpdateWhatsAppApiKeyView(APIView):
    """Allow user to save their CallMeBot API key for free WhatsApp notifications"""
    permission_classes = [PublicAccess]
    
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        whatsapp_apikey = request.data.get('whatsapp_apikey')
        
        if not username or not password or not whatsapp_apikey:
            return Response({
                'error': 'Phone number, password, and WhatsApp API key are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            customer = Customer.objects.get(username=username)
        except Customer.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Verify password
        if not customer.check_password(password):
            return Response({'error': 'Invalid password'}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Save WhatsApp API key
        customer.whatsapp_apikey = whatsapp_apikey
        customer.save(update_fields=['whatsapp_apikey'])
        
        return Response({
            'message': 'WhatsApp API key saved successfully'
        }, status=status.HTTP_200_OK)


class GenerateDefaultPasswordView(APIView):
    """Generate default password preview (for frontend display)"""
    permission_classes = [PublicAccess]
    
    def post(self, request):
        full_name = request.data.get('fullName', '')
        year_of_birth = request.data.get('year_of_birth')
        
        if not full_name or not year_of_birth:
            return Response({
                'error': 'Full name and year of birth are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Generate default password: First 3 letters of name + @ + year
        name_part = full_name[:3].strip()
        if len(name_part) > 0:
            name_part = name_part[0].upper() + name_part[1:].lower()
        
        default_password = f"{name_part}@{year_of_birth}"
        
        return Response({
            'default_password': default_password
        }, status=status.HTTP_200_OK)


def _subject_question_table_name(level_tr, class_level, subject_translated):
    from .models import subject_question_table_name
    return subject_question_table_name(level_tr, class_level, subject_translated)


def _allowed_question_table(name):
    """Allow only table names that match cheradip_ + alphanumeric/underscore (no SQL injection)."""
    import re
    return isinstance(name, str) and bool(re.match(r'^cheradip_[a-z0-9_]+$', name.strip().lower()))


class SubjectQuestionTablesView(APIView):
    """GET: List question table names from cheradip_subject (level_tr, class_level, subject_translated)."""
    permission_classes = [PublicAccess]
    authentication_classes = []

    def get(self, request):
        # One table per (class_level, subject_translated); use first row (by id) for level_tr.
        seen_key = set()
        tables = []
        for row in Subject.objects.order_by('id').values_list('level_tr', 'class_level', 'subject_translated'):
            level_tr = row[0] or ''
            class_level = row[1] or ''
            subject_translated = row[2] or ''
            key = (class_level, subject_translated)
            if key in seen_key:
                continue
            seen_key.add(key)
            name = _subject_question_table_name(level_tr, class_level, subject_translated)
            tables.append({
                'table_name': name,
                'level_tr': level_tr,
                'class_level': class_level,
                'subject_translated': subject_translated,
            })
        return Response({'tables': tables})


class SubjectQuestionDataView(APIView):
    """GET: Return rows from a subject question table. Query param: table_name (e.g. cheradip_pre_primary_0_story_book)."""
    permission_classes = [PublicAccess]
    authentication_classes = []

    def get(self, request):
        table_name_param = (request.query_params.get('table_name') or '').strip()
        if not table_name_param:
            return Response({'error': 'table_name is required'}, status=status.HTTP_400_BAD_REQUEST)
        if not _allowed_question_table(table_name_param):
            return Response({'error': 'Invalid table_name'}, status=status.HTTP_400_BAD_REQUEST)
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute(f"SELECT id, subject, chapter_no, chapter, topic, question, option_1, option_2, option_3, option_4, answer, explanation, explanation2, explanation3, type, level, subsource, created_at, updated_at, updated_by FROM `{table_name_param}` ORDER BY id")
            columns = [col[0] for col in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]
        return Response({'table_name': table_name_param, 'questions': rows})


class GetGroupsByClassView(APIView):
    """Get available groups for a specific class (9-10, 11-12). Returns exactly groups from Group/ClassGroupMapping, else none."""
    permission_classes = [PublicAccess]
    authentication_classes = []
    
    def get(self, request):
        class_code = request.query_params.get('class_code')
        
        if not class_code:
            return Response({'error': 'class_code parameter is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            class_level = ClassLevel.objects.get(class_code=class_code, is_active=True)
        except ClassLevel.DoesNotExist:
            return Response({'error': 'Class not found'}, status=status.HTTP_404_NOT_FOUND)
        
        if not class_level.has_groups:
            return Response({'groups': [], 'message': 'This class does not have groups'}, status=status.HTTP_200_OK)
        
        mappings = ClassGroupMapping.objects.filter(class_level=class_level)
        all_group_codes = set()
        for mapping in mappings:
            codes = [c.strip() for c in mapping.group_codes.split(',') if c.strip()]
            all_group_codes.update(codes)
        
        groups = Group.objects.filter(group_code__in=all_group_codes).order_by('group_code')
        from .serializers import GroupSerializer
        serializer = GroupSerializer(groups, many=True)
        
        return Response({
            'class_code': class_code,
            'class_name': class_level.class_name,
            'groups': serializer.data
        }, status=status.HTTP_200_OK)


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


class GetDepartmentsView(APIView):
    """Get all university departments for Class 13-16 (from database)."""
    permission_classes = [PublicAccess]
    authentication_classes = []
    
    def get(self, request):
        faculty = request.query_params.get('faculty')  # Optional filter by faculty
        
        departments = Department.objects.filter(is_active=True)
        if faculty:
            departments = departments.filter(faculty__icontains=faculty)
        
        departments = departments.order_by('display_order', 'dept_name')
        
        from .serializers import DepartmentSerializer
        serializer = DepartmentSerializer(departments, many=True)
        
        return Response({
            'departments': serializer.data,
            'count': len(serializer.data)
        }, status=status.HTTP_200_OK)


class GetClassInfoView(APIView):
    """Get class information including whether it has groups/departments"""
    permission_classes = [PublicAccess]
    authentication_classes = []
    
    def get(self, request):
        class_code = request.query_params.get('class_code')
        
        if not class_code:
            return Response({'error': 'class_code parameter is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            class_level = ClassLevel.objects.get(class_code=class_code, is_active=True)
        except ClassLevel.DoesNotExist:
            return Response({'error': 'Class not found'}, status=status.HTTP_404_NOT_FOUND)
        
        from .serializers import ClassLevelSerializer
        serializer = ClassLevelSerializer(class_level)
        
        return Response(serializer.data, status=status.HTTP_200_OK)
