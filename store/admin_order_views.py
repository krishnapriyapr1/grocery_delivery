from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db import transaction
import json
from django.utils import timezone
from datetime import timedelta
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

from .models import Order, OrderItem, DeliveryBoy, DeliveryAssignment
from .utils import is_admin, send_notification
from .decorators import admin_required
from django.db.models import Sum, F

@admin_required
def admin_orders(request):
    orders = Order.objects.all()
    
    # Get status filter from query parameters
    status = request.GET.get('status')
    if status and status != 'all':
        orders = orders.filter(status=status)
    
    # Order by most recent first
    orders = orders.order_by('-created_at')
    
    context = {
        'orders': orders,
        'status': status  # Pass the current status to template
    }
    return render(request, 'store/admin/orders.html', context)

@admin_required
def admin_view_order_details(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order_items = OrderItem.objects.filter(order=order)
    # Only get approved and available delivery boys
    delivery_boys = DeliveryBoy.objects.filter(is_approved=True, is_available=True)
    
    context = {
        'order': order,
        'order_items': order_items,
        'delivery_boys': delivery_boys
    }
    
    # If it's an AJAX request, return JSON response
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('store/admin/order_details_modal.html', context)
        return JsonResponse({'html': html})
    
    # Otherwise render the full page
    return render(request, 'store/admin/order_details.html', context)

@admin_required
@require_http_methods(["POST"])
def update_order_status(request, order_id):
    try:
        order = get_object_or_404(Order, id=order_id)
        new_status = request.POST.get('status')
        
        if new_status not in ['processing', 'shipped', 'delivered', 'cancelled']:
            return JsonResponse({
                'success': False,
                'error': 'Invalid status'
            })
        
        # Check if order can be updated to shipped status
        if new_status == 'shipped' and not hasattr(order, 'delivery_assignment'):
            return JsonResponse({
                'success': False,
                'error': 'Cannot mark as shipped without delivery assignment'
            })
            
        order.status = new_status
        order.save()
        
        # Update delivery assignment status if needed
        if new_status == 'delivered' and hasattr(order, 'delivery_assignment'):
            order.delivery_assignment.status = 'delivered'
            order.delivery_assignment.delivered_at = timezone.now()
            order.delivery_assignment.save()
            
            # Make delivery boy available again
            delivery_boy = order.delivery_assignment.delivery_boy
            delivery_boy.is_available = True
            delivery_boy.save()
            
        # Send notification to customer
        message = f'Your order #{order.id} has been marked as {new_status}'
        send_notification(order.user, 'Order Status Updated', message)
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        print(f"Error in update_order_status: {str(e)}")  # Debug logging
        return JsonResponse({'success': False, 'error': str(e)})

@admin_required
@require_http_methods(["POST"])
def assign_delivery(request):
    try:
        order_id = request.POST.get('order_id')
        delivery_boy_id = request.POST.get('delivery_boy_id')
        
        if not order_id or not delivery_boy_id:
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameters'
            })
        
        with transaction.atomic():
            # Get order and delivery boy with select_for_update to prevent race conditions
            order = Order.objects.select_for_update().get(id=order_id)
            delivery_boy = DeliveryBoy.objects.select_for_update().get(id=delivery_boy_id)
            
            # Check if order already has delivery assignment
            if hasattr(order, 'delivery_assignment'):
                return JsonResponse({
                    'success': False,
                    'error': 'Order already has a delivery assignment'
                })
            
            # Check if delivery boy is available and approved
            if not delivery_boy.is_available or not delivery_boy.is_approved:
                return JsonResponse({
                    'success': False,
                    'error': 'Selected delivery boy is not available'
                })
            
            # Create delivery assignment
            assignment = DeliveryAssignment.objects.create(
                order=order,
                delivery_boy=delivery_boy,
                status='assigned',
                assigned_at=timezone.now()
            )
            
            # Update delivery boy availability
            delivery_boy.is_available = False
            delivery_boy.save()
            
            # Update order status if it's still pending
            if order.status == 'pending':
                order.status = 'processing'
                order.save()
            
            try:
                # Send notification to delivery boy
                send_notification(
                    delivery_boy.user,
                    'New Delivery Assignment',
                    f'You have been assigned to deliver order #{order.id}'
                )
            except Exception as notification_error:
                # Log notification error but don't fail the assignment
                print(f"Error sending notification: {str(notification_error)}")
            
            return JsonResponse({'success': True})
            
    except Exception as e:
        print(f"Error in assign_delivery: {str(e)}")  # Debug log
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while assigning the delivery. Please try again.'
        })

@admin_required
def admin_monthly_sales_report(request):
    # Get current month's data
    today = timezone.now()
    first_day = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day = (first_day + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
    
    # Get orders for current month
    orders = Order.objects.filter(
        created_at__range=(first_day, last_day),
        status__in=['delivered', 'shipped', 'processing']  # Only count non-cancelled orders
    )
    
    # Calculate metrics
    total_sales = orders.aggregate(
        total=Sum(F('total_amount'))
    )['total'] or 0
    
    total_orders = orders.count()
    avg_order_value = total_sales / total_orders if total_orders > 0 else 0
    
    # Get top selling products
    top_products = OrderItem.objects.filter(
        order__in=orders
    ).values(
        'product__name'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_sales=Sum(F('quantity') * F('price'))
    ).order_by('-total_sales')[:5]
    
    # Get sales by category
    category_sales = OrderItem.objects.filter(
        order__in=orders
    ).values(
        'product__category__name'
    ).annotate(
        total_sales=Sum(F('quantity') * F('price'))
    ).order_by('-total_sales')
    
    context = {
        'month': today.strftime('%B %Y'),
        'total_sales': total_sales,
        'total_orders': total_orders,
        'avg_order_value': avg_order_value,
        'top_products': top_products,
        'category_sales': category_sales,
    }
    
    print(f"Debug - Total Sales: {total_sales}, Total Orders: {total_orders}")  # Debug log
    
    return render(request, 'store/admin/monthly_sales_report.html', context)

@admin_required
def download_monthly_sales_report(request):
    # Get current month's data
    today = timezone.now()
    first_day = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day = (first_day + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
    
    # Get orders for current month
    orders = Order.objects.filter(
        created_at__range=(first_day, last_day),
        status__in=['delivered', 'shipped', 'processing']  # Only count non-cancelled orders
    )
    
    # Calculate metrics
    total_sales = orders.aggregate(
        total=Sum(F('total_amount'))
    )['total'] or 0
    
    total_orders = orders.count()
    avg_order_value = total_sales / total_orders if total_orders > 0 else 0
    
    # Get top selling products
    top_products = OrderItem.objects.filter(
        order__in=orders
    ).values(
        'product__name'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_sales=Sum(F('quantity') * F('price'))
    ).order_by('-total_sales')[:5]
    
    # Get sales by category
    category_sales = OrderItem.objects.filter(
        order__in=orders
    ).values(
        'product__category__name'
    ).annotate(
        total_sales=Sum(F('quantity') * F('price'))
    ).order_by('-total_sales')
    
    # Create PDF
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="sales_report_{today.strftime("%B_%Y")}.pdf"'
    
    # Create the PDF object
    doc = SimpleDocTemplate(response, pagesize=letter)
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30
    )
    
    # Add title
    elements.append(Paragraph(f'Monthly Sales Report - {today.strftime("%B %Y")}', title_style))
    
    # Add summary statistics
    elements.append(Paragraph('Summary Statistics', styles['Heading2']))
    elements.append(Spacer(1, 12))
    
    summary_data = [
        ['Metric', 'Value'],
        ['Total Sales', f'₹{total_sales:,.2f}'],
        ['Total Orders', str(total_orders)],
        ['Average Order Value', f'₹{avg_order_value:,.2f}'],
    ]
    
    summary_table = Table(summary_data, colWidths=[200, 200])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))
    
    # Add top products
    elements.append(Paragraph('Top Selling Products', styles['Heading2']))
    elements.append(Spacer(1, 12))
    
    products_data = [['Product', 'Quantity Sold', 'Total Sales']]
    for product in top_products:
        products_data.append([
            product['product__name'],
            str(product['total_quantity']),
            f'₹{product["total_sales"]:,.2f}'
        ])
    
    products_table = Table(products_data, colWidths=[200, 100, 100])
    products_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(products_table)
    elements.append(Spacer(1, 20))
    
    # Add category sales
    elements.append(Paragraph('Sales by Category', styles['Heading2']))
    elements.append(Spacer(1, 12))
    
    category_data = [['Category', 'Total Sales']]
    for category in category_sales:
        category_data.append([
            category['product__category__name'] or 'Uncategorized',
            f'₹{category["total_sales"]:,.2f}'
        ])
    
    category_table = Table(category_data, colWidths=[200, 200])
    category_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(category_table)
    
    # Build PDF
    doc.build(elements)
    return response
