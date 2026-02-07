from django.shortcuts import render, get_object_or_404
from rest_framework import generics, status, viewsets, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from .models import (Institutes, Token, Item, Merit, Merit5, Merit6, Banbeis, Recommend, Recommend5, Recommend6, 
                     Vacancy, Vacancy5, Vacancy6, Customer, CheradipUser, CheradipTeacher, Order, OrderDetail, Transaction, Ordered, Canceled,
                     Notification, Group, Subject, Chapter, Topic, Mcq_ict, Institute, Year, Country, Location,
                     ClassLevel, ClassGroupMapping, Department)
from .serializers import (InstitutesSerializer, TokenSerializer, RecommendSerializer, Recommend5Serializer, 
                         Recommend6Serializer, BanbeisSerializer, MeritSerializer, Merit5Serializer, Merit6Serializer, 
                         VacancySerializer, Vacancy5Serializer, Vacancy6Serializer, ItemSerializer, CustomerSerializer, 
                         CheradipUserSerializer, CheradipTeacherSerializer, CustomerUpdateSerializer, OrderSerializer, NotificationSerializer, GroupSerializer, 
                         SubjectSerializer, ChapterSerializer, TopicSerializer, McqIctSerializer, InstituteSerializer, 
                         YearSerializer, CountrySerializer, CountryListSerializer)
from .permissions import IsSuperUserOrStaff, PublicAccess
from .location import Bangladesh
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.contrib.auth import authenticate
from django.views.decorators.csrf import csrf_exempt
import logging, random, string, json, requests, os
from rest_framework.decorators import action
from django.conf import settings
from django.db.models import Q
from django.db.models.expressions import RawSQL

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
        # Avoid loading datetime columns on list (MySQL can return them as str → is_aware fails)
        if self.action == 'list':
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
                country = Country.objects.get(country_code='BD')
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
                country = Country.objects.get(country_code=country_code)
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
            country = Country.objects.get(country_code='BD')
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
        countries = Country.objects.filter(is_active=True, is_featured=True).order_by('display_order')
        serializer = CountryListSerializer(countries, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_continent(self, request):
        """Get countries grouped by continent"""
        continents = Country.objects.filter(is_active=True).values_list('continent', flat=True).distinct()
        result = {}
        for continent in continents:
            if continent:
                countries = Country.objects.filter(is_active=True, continent=continent).order_by('country_name')
                result[continent] = CountryListSerializer(countries, many=True).data
        return Response(result)


class AllCountriesView(APIView):
    """GET /api/country/ - Return all active countries as array (for <option> dropdowns)."""
    def get(self, request):
        countries = Country.objects.filter(is_active=True).order_by('display_order', 'country_name')
        serializer = CountryListSerializer(countries, many=True)
        return Response(serializer.data)


class LevelsByCountryView(APIView):
    """
    GET /api/levels_by_country/?country_code=BD
    Returns unique Level/Class values from cheradip_subject for the given country.
    Level column may contain comma-separated values (e.g. 'SSC,JSC,PSC'); we split and return unique sorted list.
    Used by signup to populate Class (Student) and Level (Teacher) dropdowns.
    """
    permission_classes = [PublicAccess]
    authentication_classes = []

    # Display order for levels (PSC, JSC, SSC, HSC, University)
    LEVEL_ORDER = ('PSC', 'JSC', 'SSC', 'HSC', 'University')

    def get(self, request):
        country_code = (request.query_params.get('country_code') or '').strip().upper()
        if not country_code:
            return Response({'levels': [], 'error': 'country_code is required'}, status=status.HTTP_400_BAD_REQUEST)

        from django.db import connection
        table = 'cheradip_subject'
        levels_set = set()
        with connection.cursor() as cur:
            cur.execute(
                f"SELECT DISTINCT level FROM {table} WHERE country_id = %s AND level IS NOT NULL AND TRIM(COALESCE(level, '')) != ''",
                [country_code]
            )
            for (level_str,) in cur.fetchall():
                if level_str:
                    for part in level_str.replace(',', ' ').split():
                        levels_set.add(part.strip())

        # Sort by LEVEL_ORDER (excluding University), then any extras alphabetically, then University last
        order_without_uni = ('PSC', 'JSC', 'SSC', 'HSC')
        ordered = [l for l in order_without_uni if l in levels_set]
        extras = sorted(levels_set - set(self.LEVEL_ORDER))
        levels = ordered + extras
        if 'University' not in levels:
            levels.append('University')

        return Response({'levels': levels, 'country_code': country_code})


class SubjectsByCountryLevelView(APIView):
    """
    GET /api/subjects_by_country_level/?country_code=BD&level=HSC
    Returns subjects from cheradip_subject for the given country and level (for Teacher signup).
    Level matches exact or comma-separated (e.g. level LIKE '%HSC%').
    """
    permission_classes = [PublicAccess]
    authentication_classes = []

    def get(self, request):
        country_code = (request.query_params.get('country_code') or '').strip().upper()
        level = (request.query_params.get('level') or '').strip()
        if not country_code or not level:
            return Response(
                {'subjects': [], 'error': 'country_code and level are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from django.db import connection
        table = 'cheradip_subject'
        # Match level: exact or as part of comma-separated (e.g. "SSC,JSC" for level "SSC")
        with connection.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, subject_code, subject_name, subject_name_tr
                FROM {table}
                WHERE country_id = %s AND level IS NOT NULL AND TRIM(COALESCE(level, '')) != ''
                  AND (level = %s OR level LIKE %s OR level LIKE %s OR level LIKE %s)
                ORDER BY subject_code
                """,
                [country_code, level, f'%{level},%', f'{level},%', f'%,{level}']
            )
            rows = cur.fetchall()

        subjects = [
            {'id': r[0], 'subject_code': r[1], 'subject_name': r[2] or '', 'subject_name_tr': r[3] or ''}
            for r in rows
        ]
        return Response({'subjects': subjects, 'country_code': country_code, 'level': level})


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

        # Resolve to Group model by group_name for group_code and group_name_bn
        groups_qs = Group.objects.filter(group_name__in=group_names).order_by('group_code')
        serializer = GroupSerializer(groups_qs, many=True)
        groups_data = []
        for i, g in enumerate(groups_qs):
            row = dict(serializer.data[i]) if i < len(serializer.data) else {'group_code': g.group_code, 'group_name': g.group_name}
            row['group_name_bn'] = getattr(g, 'group_name_bn', None) or ''
            groups_data.append(row)

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
    def post(self, request, *args, **kwargs):
        serializer = CustomerSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            # Also save to cheradip_teacher (Teacher) or cheradip_users (Student/Job Seeker)
            def _get(d, key, default=None):
                v = d.get(key, default)
                return v[0] if isinstance(v, (list, tuple)) and len(v) else v
            raw = request.data
            acctype = _get(raw, 'acctype', 'Student')
            if acctype == 'Teacher':
                user_data = {
                    'fullName': _get(raw, 'fullName', ''),
                    'username': _get(raw, 'username', ''),
                    'password': _get(raw, 'password', ''),
                    'date_of_birth': _get(raw, 'date_of_birth'),
                    'teacher_level': _get(raw, 'teacher_level'),
                    'teacher_subject_code': _get(raw, 'teacher_subject_code'),
                    'teacher_department_code': _get(raw, 'teacher_department_code'),
                    'teacher_department_name': _get(raw, 'teacher_department_name'),
                    'gender': _get(raw, 'gender', 'Male'),
                    'email': _get(raw, 'email'),
                    'country_code': _get(raw, 'country_code') or _get(raw, 'countryCode') or 'US',
                }
                user_serializer = CheradipTeacherSerializer(data=user_data)
            else:
                user_data = {
                    'acctype': acctype if acctype in ('Student', 'JobSeeker') else 'Student',
                    'fullName': _get(raw, 'fullName', ''),
                    'username': _get(raw, 'username', ''),
                    'password': _get(raw, 'password', ''),
                    'date_of_birth': _get(raw, 'date_of_birth'),
                    'class_name': _get(raw, 'class_name'),
                    'group': _get(raw, 'group'),
                    'department': _get(raw, 'department'),
                    'gender': _get(raw, 'gender', 'Male'),
                    'email': _get(raw, 'email'),
                    'country_code': _get(raw, 'country_code') or _get(raw, 'countryCode') or 'US',
                }
                user_serializer = CheradipUserSerializer(data=user_data)
            if user_serializer.is_valid():
                try:
                    user_serializer.save()
                    if acctype == 'Teacher':
                        tcode = _get(raw, 'teacher_department_code', '')
                        tname = _get(raw, 'teacher_department_name', '')
                        if (tcode or '').strip().upper() == 'OTHER' and (tname or '').strip():
                            _append_department_to_json((tname or '').strip(), None)
                except Exception as e:
                    logger.warning('Signup table save failed (non-blocking): %s', e)
            token = self.generate_unique_key()
            return Response({'authToken': token}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def generate_unique_key(self):
            length = 40
            characters = string.ascii_letters + string.digits
            key = ''.join(random.choice(characters) for _ in range(length))
            return key 

class CustomerRetrieveView(APIView):
    def post(self, request, *args, **kwargs):
            username = request.data.get('username')
            password = request.data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                if hasattr(user, 'acctype'):acctype = user.acctype
                else:acctype = None
                if hasattr(user, 'fullName'):fullName = user.fullName
                else:fullName = None
                if hasattr(user, 'group'):group = user.group
                else:group = None
                if hasattr(user, 'gender'):gender = user.gender
                else:gender = None
                if hasattr(user, 'division'):division = user.division
                else:division = None 
                if hasattr(user, 'district'): district = user.district
                else:district = None
                if hasattr(user, 'thana'):thana = user.thana
                else:thana = None
                if hasattr(user, 'union'):union = user.union
                else:union = None
                if hasattr(user, 'village'):village = user.village
                else:village = None
                token = self.generate_unique_key()
                return Response({'authToken': token, 'acctype': acctype, 'fullName': fullName, 'group': group, 'gender': gender, 'division': division, 'district': district, 'thana': thana, 'union': union, 'village': village}, status=status.HTTP_200_OK)
            else:
                return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)


    def generate_unique_key(self):
            length = 40
            characters = string.ascii_letters + string.digits
            key = ''.join(random.choice(characters) for _ in range(length))
            return key 
    

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            customer_data = {
                'username': request.user.username, 
                'fullName': request.user.full_name,  
            }
            return Response(customer_data, status=status.HTTP_200_OK)
        else:
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
        if user is not None:
            serializer = CustomerUpdateSerializer(user, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                token = self.generate_unique_key()
                return Response({'authToken': token}, status=status.HTTP_200_OK)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def generate_unique_key(self):
            length = 40
            characters = string.ascii_letters + string.digits
            key = ''.join(random.choice(characters) for _ in range(length))
            return key 

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
    def get(self, request, *args, **kwargs):
        username = request.query_params.get('username')
        
        try:
            exists = Customer.objects.filter(username=username).exists()
        except Customer.DoesNotExist:
            exists = False
        
        return Response({'exists': exists}, status=status.HTTP_200_OK)


class PasswordExistsView(APIView):
    def get(self, request, *args, **kwargs):
        username = request.query_params.get('username')
        password = request.query_params.get('password')
        
        try:
            customer = Customer.objects.get(username=username)
            # Use check_password for both hashed and plain text passwords
            if customer.password.startswith('pbkdf2_') or customer.password.startswith('argon2'):
                exists = customer.check_password(password)
            else:
                # Legacy: compare plain text
                exists = (customer.password == password)
        except Customer.DoesNotExist:
            exists = False
        return Response({'exists': exists}, status=status.HTTP_200_OK)
    

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
            from django.db.models import Q
            from functools import reduce
            from operator import or_
            q = reduce(or_, [Q(groups__contains=[c]) for c in group_codes], Q())
            queryset = queryset.filter(q)
        
        if subject_code:
            queryset = queryset.filter(subject_code=subject_code)
        
        return queryset.order_by('id')


class ChapterViewSet(viewsets.ModelViewSet):
    serializer_class = ChapterSerializer
    
    def get_queryset(self):
        queryset = Chapter.objects.all().select_related('subject')
        subject_codes = self.request.query_params.getlist('subjects')
        chapter_no = self.request.query_params.get('chapter_no')
        
        if subject_codes:
            queryset = queryset.filter(subject__subject_code__in=subject_codes)
        
        if chapter_no:
            queryset = queryset.filter(chapter_no=chapter_no)
        
        return queryset.order_by('subject__subject_code', 'chapter_no')


class TopicViewSet(viewsets.ModelViewSet):
    serializer_class = TopicSerializer
    
    def get_queryset(self):
        queryset = Topic.objects.all().select_related('chapter', 'chapter__subject')
        chapter_ids = self.request.query_params.getlist('chapters')
        topic_no = self.request.query_params.get('topic_no')
        
        if chapter_ids:
            queryset = queryset.filter(chapter_id__in=chapter_ids)
        
        if topic_no:
            queryset = queryset.filter(topic_no=topic_no)
        
        return queryset.order_by('chapter__subject__subject_code', 'chapter__chapter_no', 'topic_no')


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
    queryset = Mcq_ict.objects.all().select_related('subject', 'chapter', 'topic').prefetch_related(
        'institutes', 'years'
    )
    
    def get_queryset(self):
        queryset = Mcq_ict.objects.all().select_related(
            'subject', 'chapter', 'topic'
        ).prefetch_related('institutes', 'years')
        
        # Filter by subject code(s)
        subject_codes = self.request.query_params.getlist('subject')
        if subject_codes:
            queryset = queryset.filter(subject__subject_code__in=subject_codes)
        
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
        
        # Filter by group code(s) (subject.groups overlaps requested codes)
        group_codes = self.request.query_params.getlist('group')
        if group_codes:
            from django.db.models import Q
            from functools import reduce
            from operator import or_
            q = reduce(or_, [Q(subject__groups__contains=[c]) for c in group_codes], Q())
            queryset = queryset.filter(q).distinct()
        
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
        subject_counts = queryset.values('subject__subject_code', 'subject__subject_name').annotate(
            count=Count('qid')
        ).order_by('subject__subject_code')
        
        for item in subject_counts:
            stats['by_subject'][item['subject__subject_code']] = {
                'name': item['subject__subject_name'],
                'count': item['count']
            }
        
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


class GetGroupsByClassView(APIView):
    """Get available groups for a specific class (9-10, 11-12)"""
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
        
        # Get group mappings for this class
        mappings = ClassGroupMapping.objects.filter(class_level=class_level)
        all_group_codes = set()
        for mapping in mappings:
            all_group_codes.update(mapping.get_group_list())
        
        # Get group details
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
