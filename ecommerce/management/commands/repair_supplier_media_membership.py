import json
from django.core.management.base import BaseCommand
from ecommerce.source_media_repair import repair_media_membership

class Command(BaseCommand):
    def add_arguments(self,parser):parser.add_argument('--apply',action='store_true')
    def handle(self,*args,**options):self.stdout.write(json.dumps(repair_media_membership(apply=options['apply'])))
