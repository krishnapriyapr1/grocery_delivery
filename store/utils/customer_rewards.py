from django.db import connection
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from ..models import Order, Coupon
import uuid
from datetime import timedelta

def generate_unique_code():
    """Generate a unique coupon code"""
    return f"VIP{uuid.uuid4().hex[:8].upper()}"

def get_high_value_customers(min_spend=1000, days=30):
    """
    Identify high-value customers who have spent more than min_spend in the last days
    Returns a list of tuples (user_id, total_spend)
    """
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                u.id,
                u.email,
                u.username,
                COALESCE(SUM(o.total_amount), 0) as total_spend,
                COUNT(o.id) as order_count
            FROM 
                auth_user u
                LEFT JOIN store_order o ON u.id = o.user_id
            WHERE 
                o.created_at >= %s
                AND o.created_at <= %s
                AND o.status = 'delivered'
            GROUP BY 
                u.id, u.email, u.username
            HAVING 
                COALESCE(SUM(o.total_amount), 0) >= %s
        """, [start_date, end_date, min_spend])
        
        return cursor.fetchall()

def create_customer_coupon(user_id, total_spend):
    """Create a personalized coupon based on spending"""
    # Calculate discount percentage based on spending
    if total_spend >= 5000:
        discount = 20
    elif total_spend >= 3000:
        discount = 15
    else:
        discount = 10
        
    # Create coupon valid for 7 days
    valid_from = timezone.now()
    valid_until = valid_from + timedelta(days=7)
    
    try:
        coupon = Coupon.objects.create(
            code=generate_unique_code(),
            user_id=user_id,
            discount_percentage=discount,
            valid_from=valid_from,
            valid_until=valid_until,
            minimum_spend=total_spend * 0.5  # Set minimum spend to 50% of their previous spending
        )
        print(f"Created coupon {coupon.code} for user {user_id} with {discount}% discount")  # Debug log
        return coupon
    except Exception as e:
        print(f"Error creating coupon: {str(e)}")  # Debug log
        raise

def send_reward_email(user_email, username, coupon, total_spend):
    """Send personalized email with coupon code"""
    try:
        subject = f'Thank you for shopping with Fresh Mart! Here\'s your reward'
        
        context = {
            'username': username,
            'coupon_code': coupon.code,
            'discount': coupon.discount_percentage,
            'valid_until': coupon.valid_until.strftime('%B %d, %Y'),
            'minimum_spend': coupon.minimum_spend,
            'total_spend': total_spend
        }
        
        html_message = render_to_string('store/emails/reward_email.html', context)
        plain_message = f"""
        Dear {username},

        Thank you for being a valued customer! You've spent ₹{total_spend} with us recently.
        
        Here's your reward: {coupon.discount_percentage}% OFF your next purchase!
        
        Use code: {coupon.code}
        Valid until: {coupon.valid_until.strftime('%B %d, %Y')}
        Minimum spend: ₹{coupon.minimum_spend}
        
        Shop now at Fresh Mart!
        """
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user_email],
            html_message=html_message,
            fail_silently=False
        )
        print(f"Sent reward email to {user_email}")  # Debug log
    except Exception as e:
        print(f"Error sending reward email: {str(e)}")  # Debug log
        raise

def process_customer_rewards():
    """Main function to process customer rewards"""
    high_value_customers = get_high_value_customers()
    
    for user_id, email, username, total_spend, order_count in high_value_customers:
        try:
            # Create personalized coupon
            coupon = create_customer_coupon(user_id, total_spend)
            
            # Send email with coupon
            send_reward_email(email, username, coupon, total_spend)
            
        except Exception as e:
            print(f"Error processing rewards for user {username}: {str(e)}")
            continue
            
    return len(high_value_customers) 