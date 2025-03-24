from django.core.management.base import BaseCommand
from store.models import Category

class Command(BaseCommand):
    help = 'Generate slugs for categories that do not have them'

    def handle(self, *args, **kwargs):
        categories = Category.objects.all()
        for category in categories:
            if not category.slug:
                category.save()  # This will trigger the save method which generates the slug
                self.stdout.write(self.style.SUCCESS(f'Generated slug for category: {category.name}'))
