from django.core.management.base import BaseCommand
from store.utils.customer_rewards import process_customer_rewards
from django.utils import timezone

class Command(BaseCommand):
    help = 'Identifies high-value customers and sends them reward coupons'

    def add_arguments(self, parser):
        parser.add_argument(
            '--min-spend',
            type=int,
            default=1000,
            help='Minimum spend amount to qualify (default: 1000)'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days to look back (default: 30)'
        )

    def handle(self, *args, **options):
        start_time = timezone.now()
        self.stdout.write(
            self.style.SUCCESS(f'Starting customer rewards processing at {start_time}')
        )

        try:
            customers_processed = process_customer_rewards(
                min_spend=options['min_spend'],
                days=options['days']
            )
            
            end_time = timezone.now()
            duration = end_time - start_time
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully processed {customers_processed} customers in {duration.total_seconds():.2f} seconds'
                )
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error processing customer rewards: {str(e)}')
            ) 