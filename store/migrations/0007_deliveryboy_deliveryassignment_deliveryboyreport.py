# Generated by Django 4.2.7 on 2025-03-06 05:18

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('store', '0006_order_stripe_charge_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='DeliveryBoy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('phone', models.CharField(max_length=15)),
                ('address', models.TextField()),
                ('is_available', models.BooleanField(default=True)),
                ('is_approved', models.BooleanField(default=False)),
                ('total_deliveries', models.PositiveIntegerField(default=0)),
                ('rating', models.DecimalField(decimal_places=2, default=5.0, max_digits=3)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': 'Delivery Boys',
            },
        ),
        migrations.CreateModel(
            name='DeliveryAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('assigned', 'Assigned'), ('picked_up', 'Picked Up'), ('in_transit', 'In Transit'), ('delivered', 'Delivered'), ('failed', 'Failed')], default='assigned', max_length=20)),
                ('assigned_at', models.DateTimeField(auto_now_add=True)),
                ('picked_up_at', models.DateTimeField(blank=True, null=True)),
                ('delivered_at', models.DateTimeField(blank=True, null=True)),
                ('delivery_notes', models.TextField(blank=True)),
                ('delivery_boy', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assignments', to='store.deliveryboy')),
                ('order', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='delivery_assignment', to='store.order')),
            ],
        ),
        migrations.CreateModel(
            name='DeliveryBoyReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('orders_delivered', models.PositiveIntegerField(default=0)),
                ('on_time_deliveries', models.PositiveIntegerField(default=0)),
                ('total_distance', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('delivery_boy', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reports', to='store.deliveryboy')),
            ],
            options={
                'unique_together': {('delivery_boy', 'date')},
            },
        ),
    ]
