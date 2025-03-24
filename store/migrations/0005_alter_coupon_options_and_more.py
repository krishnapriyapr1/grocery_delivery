# Generated by Django 4.2.7 on 2025-03-02 17:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0004_suppliermessage_supplieractivity_coupon'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='coupon',
            options={'ordering': ['-created_at']},
        ),
        migrations.RenameField(
            model_name='coupon',
            old_name='valid_until',
            new_name='valid_to',
        ),
        migrations.RemoveField(
            model_name='coupon',
            name='discount_percentage',
        ),
        migrations.AddField(
            model_name='coupon',
            name='discount_amount',
            field=models.DecimalField(decimal_places=2, default=100, max_digits=10),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='coupon',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name='coupon',
            name='code',
            field=models.CharField(max_length=50, unique=True),
        ),
    ]
