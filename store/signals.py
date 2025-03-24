from django.db.models.signals import post_save, pre_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from django.db.models import Sum
from .models import UserProfile, Order, Coupon
from .views import send_coupon_email

# @receiver(post_save, sender=User)
# def create_user_profile(sender, instance, created, **kwargs):
#     if created:
#         UserProfile.objects.create(user=instance)

# @receiver(post_save, sender=User)
# def save_user_profile(sender, instance, **kwargs):
#     try:
#         instance.userprofile.save()
#     except UserProfile.DoesNotExist:
#         UserProfile.objects.create(user=instance)

@receiver(pre_save, sender=Order)
def handle_order_status_change(sender, instance, **kwargs):
    """
    Signal to handle order status changes and trigger coupon emails
    when appropriate
    """
    try:
        if instance.pk:  # If this is an existing order being updated
            old_order = Order.objects.get(pk=instance.pk)
            
            # Check if status is being changed to delivered
            if old_order.status != 'delivered' and instance.status == 'delivered':
                # Calculate total purchases in last 30 days for this user
                thirty_days_ago = timezone.now() - timedelta(days=30)
                
                monthly_orders = Order.objects.filter(
                    user=instance.user,
                    created_at__gte=thirty_days_ago,
                    status='delivered'  # Only count delivered orders
                )
                
                # Include the current order that's being marked as delivered
                monthly_total = monthly_orders.aggregate(
                    total=Sum('total_amount'))['total'] or 0
                monthly_total += instance.total_amount
                
                # Check if user already has an active coupon
                has_active_coupon = Coupon.objects.filter(
                    user=instance.user,
                    is_used=False,
                    valid_to__gte=timezone.now()
                ).exists()
                
                print(f"User {instance.user.email} monthly total: ₹{monthly_total}")
                print(f"Has active coupon: {has_active_coupon}")
                
                if monthly_total >= 1000 and not has_active_coupon:
                    # Generate coupon code
                    coupon_code = f"REWARD{instance.user.id}{timezone.now().strftime('%m%y%d')}"
                    
                    # Calculate discount (10% of monthly total, max ₹500)
                    discount_amount = min(monthly_total * Decimal('0.10'), 500)
                    
                    # Set expiry date (30 days from now)
                    valid_to = timezone.now() + timedelta(days=30)
                    
                    try:
                        # Create the coupon
                        coupon = Coupon.objects.create(
                            code=coupon_code,
                            user=instance.user,
                            discount_amount=discount_amount,
                            valid_from=timezone.now(),
                            valid_to=valid_to,
                            is_active=True,
                            minimum_spend=Decimal('100')
                        )
                        
                        # Send the email
                        if send_coupon_email(instance.user.email, coupon_code, 
                                          discount_amount, valid_to):
                            print(f"Sent reward coupon to {instance.user.email}")
                        else:
                            # If email fails, delete the coupon
                            coupon.delete()
                            print(f"Failed to send coupon email to {instance.user.email}")
                            
                    except Exception as e:
                        print(f"Error creating/sending coupon: {str(e)}")
                        # Clean up any partially created coupon
                        Coupon.objects.filter(code=coupon_code).delete()
                        
    except Exception as e:
        print(f"Error in order status change signal: {str(e)}")
