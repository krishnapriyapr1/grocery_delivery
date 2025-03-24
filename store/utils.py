from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.contrib.auth.models import User
from .models import Notification

def is_admin(user):
    return user.is_staff or user.is_superuser

def send_notification(user, title, message, notification_type='info'):
    """
    Send a notification to a user through both the in-app notification system
    and email (if configured).
    """
    # Create in-app notification
    Notification.objects.create(
        recipient=user,
        title=title,
        message=message,
        type=notification_type
    )
    
    # Send email notification if email settings are configured
    if settings.EMAIL_HOST:
        try:
            send_mail(
                subject=title,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True
            )
        except Exception as e:
            print(f"Failed to send email notification: {str(e)}")

def send_email_notification(subject, template, context, recipient_list):
    """
    Send HTML email using a template
    """
    html_message = render_to_string(template, context)
    plain_message = strip_tags(html_message)
    
    send_mail(
        subject=subject,
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipient_list,
        html_message=html_message
    )

def send_order_confirmation(order):
    """
    Send order confirmation notification to customer
    """
    title = f'Order #{order.id} Confirmation'
    message = f'Thank you for your order! Your order #{order.id} has been received and is being processed.'
    send_notification(order.user, title, message, 'order_confirmation')

    context = {
        'order': order,
        'items': order.items.all(),
    }
    send_email_notification(
        subject=f'Order Confirmation - #{order.id}',
        template='emails/order_confirmation.html',
        context=context,
        recipient_list=[order.email]
    )

def send_order_status_update(order):
    """
    Send order status update notification to customer
    """
    title = f'Order #{order.id} Status Update'
    message = f'Your order #{order.id} has been updated to: {order.status}'
    send_notification(order.user, title, message, 'order_status')

    context = {
        'order': order,
        'status': order.get_status_display(),
    }
    send_email_notification(
        subject=f'Order Status Update - #{order.id}',
        template='emails/order_status_update.html',
        context=context,
        recipient_list=[order.email]
    )

def send_supplier_approval(supplier):
    """
    Send approval notification to supplier
    """
    context = {
        'supplier': supplier,
    }
    send_email_notification(
        subject='Supplier Account Approved',
        template='emails/supplier_approval.html',
        context=context,
        recipient_list=[supplier.user.email]
    )

def send_restock_request(restock_request):
    """
    Send restock request notification to supplier
    """
    context = {
        'restock_request': restock_request,
        'product': restock_request.product,
        'supplier': restock_request.supplier,
    }
    send_email_notification(
        subject=f'Restock Request - {restock_request.product.name}',
        template='emails/restock_request.html',
        context=context,
        recipient_list=[restock_request.supplier.user.email]
    )

def send_low_stock_alert(product):
    """
    Send low stock alert to admin and supplier
    """
    context = {
        'product': product,
        'supplier': product.supplier,
    }
    admin_emails = [admin.email for admin in User.objects.filter(is_staff=True)]
    send_email_notification(
        subject=f'Low Stock Alert - {product.name}',
        template='emails/low_stock_alert.html',
        context=context,
        recipient_list=admin_emails + [product.supplier.user.email]
    ) 