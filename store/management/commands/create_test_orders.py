from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from store.models import Order
from decimal import Decimal
import random

class Command(BaseCommand):
    help = 'Creates test orders for reward system testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            help='Username to create orders for'
        )

    def handle(self, *args, **options):
        username = options['user']
        
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'User {username} does not exist')
            )
            return

        # Create 5 delivered orders in the last 30 days
        amounts = [500, 600, 700, 800, 900]  # Will sum to 3500
        
        for amount in amounts:
            days_ago = random.randint(1, 25)
            order_date = timezone.now() - timezone.timedelta(days=days_ago)
            
            order = Order.objects.create(
                user=user,
                name=user.get_full_name() or user.username,
                email=user.email,
                phone='1234567890',
                address='Test Address',
                city='Test City',
                postal_code='12345',
                payment_method='cod',
                payment_status='completed',
                total_amount=Decimal(str(amount)),
                status='delivered',
                created_at=order_date
            )
            
            self.stdout.write(
                self.style.SUCCESS(f'Created order #{order.id} for {amount} rupees')
            )
        
        total_spent = sum(amounts)
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created 5 orders for {username} totaling ₹{total_spent}'
            )
        ) 