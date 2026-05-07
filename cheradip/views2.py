"""Bangladesh location dropdowns (divisions, districts, thanas). Used by signup/profile."""
from rest_framework.views import APIView
from rest_framework.response import Response
from .location import Bangladesh


class DivisionsView(APIView):
    def get(self, request):
        divisions = list(Bangladesh.keys())
        return Response(divisions)


class DistrictsView(APIView):
    def get(self, request):
        division = request.query_params.get('division')
        if division in Bangladesh:
            districts = list(Bangladesh[division].keys())
            return Response(districts)
        return Response([])


class ThanasView(APIView):
    def get(self, request):
        division = request.query_params.get('division')
        district = request.query_params.get('district')
        if division in Bangladesh and district in Bangladesh[division]:
            thanas = Bangladesh[division][district]
            return Response(thanas)
        return Response([])
