from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Count, Avg
from django.utils import timezone
from datetime import timedelta
from django.contrib import messages

from .models import DeliveryBoy, DeliveryAssignment, DeliveryBoyReport
from .decorators import admin_required
from .utils import send_notification

@admin_required
def admin_delivery_management(request):
    view_type = request.GET.get('view', 'active')
    
    # Get all delivery boys
    if view_type == 'pending':
        delivery_boys = DeliveryBoy.objects.filter(is_approved=False, is_rejected=False).order_by('-created_at')
    else:
        delivery_boys = DeliveryBoy.objects.filter(is_approved=True).order_by('-created_at')
    
    # Get pending delivery boys count for badge
    pending_delivery_boys = DeliveryBoy.objects.filter(is_approved=False, is_rejected=False)
    
    # Get active deliveries
    active_deliveries = DeliveryAssignment.objects.filter(
        status__in=['assigned', 'picked_up', 'in_transit']
    ).select_related('order', 'delivery_boy')
    
    context = {
        'delivery_boys': delivery_boys,
        'pending_delivery_boys': pending_delivery_boys,
        'active_deliveries': active_deliveries,
        'view': view_type
    }
    
    return render(request, 'store/admin/delivery_management.html', context)

@admin_required
def delivery_boy_performance(request, delivery_boy_id):
    delivery_boy = get_object_or_404(DeliveryBoy, id=delivery_boy_id)
    
    # Get last 30 days of reports
    start_date = timezone.now() - timedelta(days=30)
    reports = DeliveryBoyReport.objects.filter(
        delivery_boy=delivery_boy,
        date__gte=start_date
    ).order_by('-date')
    
    # Calculate performance metrics
    total_deliveries = DeliveryAssignment.objects.filter(
        delivery_boy=delivery_boy,
        status='delivered'
    ).count()
    
    avg_rating = DeliveryAssignment.objects.filter(
        delivery_boy=delivery_boy,
        status='delivered',
        rating__isnull=False
    ).aggregate(Avg('rating'))['rating__avg'] or 0
    
    on_time_deliveries = DeliveryAssignment.objects.filter(
        delivery_boy=delivery_boy,
        status='delivered',
        delivered_at__lte=timezone.now()
    ).count()
    
    context = {
        'delivery_boy': delivery_boy,
        'reports': reports,
        'total_deliveries': total_deliveries,
        'avg_rating': round(avg_rating, 2),
        'on_time_deliveries': on_time_deliveries
    }
    
    return render(request, 'store/admin/delivery_boy_performance.html', context)

@admin_required
def manage_delivery_boy(request, action, delivery_boy_id):
    delivery_boy = get_object_or_404(DeliveryBoy, id=delivery_boy_id)
    
    if action == 'approve':
        delivery_boy.is_approved = True
        delivery_boy.is_rejected = False
        delivery_boy.save()
        
        # Send notification to delivery boy
        message = 'Your account has been approved. You can now start accepting deliveries.'
        send_notification(delivery_boy.user, 'Account Approved', message)
        messages.success(request, f'Delivery boy {delivery_boy.name} has been approved.')
        
    elif action == 'reject':
        delivery_boy.is_approved = False
        delivery_boy.is_rejected = True
        delivery_boy.save()
        
        # Send notification to delivery boy
        message = 'Your account has been rejected. Please contact support for more information.'
        send_notification(delivery_boy.user, 'Account Rejected', message)
        messages.warning(request, f'Delivery boy {delivery_boy.name} has been rejected.')
        
    elif action == 'toggle-availability':
        delivery_boy.is_available = not delivery_boy.is_available
        delivery_boy.save()
        return JsonResponse({'success': True})  # Keep JSON response only for AJAX toggle
    
    # Redirect back to the appropriate view
    return redirect('admin_delivery_management') if action in ['approve', 'reject'] else JsonResponse({'success': True})
