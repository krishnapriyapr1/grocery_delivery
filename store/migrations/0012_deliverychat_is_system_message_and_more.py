# Generated by Django 4.2.7 on 2025-03-21 06:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0011_add_quick_messages'),
    ]

    operations = [
        migrations.AddField(
            model_name='deliverychat',
            name='is_system_message',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='deliverychat',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
