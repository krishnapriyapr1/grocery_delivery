from django.db import migrations
from django.conf import settings

def create_default_site(apps, schema_editor):
    Site = apps.get_model('sites', 'Site')
    Site.objects.update_or_create(
        id=settings.SITE_ID,
        defaults={
            'domain': 'localhost:8000',
            'name': 'Fresh Mart'
        }
    )

class Migration(migrations.Migration):
    dependencies = [
        ('store', '0001_initial'),
        ('sites', '0002_alter_domain_unique'),
    ]

    operations = [
        migrations.RunPython(create_default_site),
    ] 