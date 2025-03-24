from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.contrib import messages
from .models import Product, RestockRequest, Supplier, SupplierMessage, SupplierActivity, Notification
from django.contrib.auth.models import User

def is_supplier(user):
    return hasattr(user, 'supplier')

@login_required
@user_passes_test(is_supplier)
def supplier_dashboard(request):
    supplier = request.user.supplier
    products = Product.objects.filter(supplier=supplier)
    restock_requests = RestockRequest.objects.filter(supplier=supplier)
    
    # Get unread messages count
    unread_messages_count = SupplierMessage.objects.filter(
        supplier=supplier,
        read=False
    ).count()
    
    # Get recent products
    recent_products = products.order_by('-created_at')[:5]
    
    # Get recent restock requests
    recent_restock_requests = restock_requests.select_related('product').order_by('-created_at')[:5]
    
    context = {
        'supplier': supplier,
        'total_products': products.count(),
        'approved_products': products.filter(approval_status='approved').count(),
        'pending_approvals': products.filter(approval_status='pending').count(),
        'pending_restocks': restock_requests.filter(status='pending').count(),
        'unread_messages_count': unread_messages_count,
        'recent_products': recent_products,
        'recent_restock_requests': recent_restock_requests,
        'recent_activities': SupplierActivity.objects.filter(supplier=supplier).order_by('-created_at')[:5]
    }
    
    return render(request, 'store/supplier/dashboard.html', context)

@login_required
@user_passes_test(is_supplier)
def supplier_restock_requests(request):
    supplier = request.user.supplier
    
    # Get all restock requests for this supplier
    restock_requests = RestockRequest.objects.filter(
        supplier=supplier
    ).select_related(
        'product',
        'requested_by'
    ).order_by('-created_at')
    
    # Count pending requests
    pending_count = restock_requests.filter(status='pending').count()
    
    context = {
        'restock_requests': restock_requests,
        'pending_restock_requests': pending_count,
        'supplier': supplier,
    }
    
    return render(request, 'store/supplier/restock_requests.html', context)

@login_required
@user_passes_test(is_supplier)
def update_restock_request(request, request_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

    supplier = request.user.supplier
    restock_request = get_object_or_404(RestockRequest, id=request_id, supplier=supplier)
    action = request.POST.get('action')
    
    try:
        if action == 'complete':
            # Get and validate stock quantity
            try:
                stock_quantity = int(request.POST.get('stock_quantity', '0'))
                if stock_quantity <= 0:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Please enter a valid quantity greater than 0'
                    })
            except ValueError:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Invalid quantity value'
                })
                
            # Update product stock
            product = restock_request.product
            product.stock += stock_quantity
            product.save()
            
            # Update restock request status
            restock_request.status = 'completed'
            restock_request.save()
            
            # Create notification for admin
            Notification.objects.create(
                recipient=User.objects.filter(is_superuser=True).first(),
                type='stock_update',
                title='Stock Updated',
                message=f'Supplier {supplier.name} has updated stock for {product.name}. Added {stock_quantity} units.'
            )
            
            # Create activity log
            SupplierActivity.objects.create(
                supplier=supplier,
                activity_type='stock_update',
                description=f'Updated stock for {product.name} (+{stock_quantity} units)'
            )
            
            return JsonResponse({
                'status': 'success',
                'message': f'Successfully updated stock for {product.name}'
            })
            
        elif action == 'reject':
            reason = request.POST.get('reason', '').strip()
            if not reason:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Please provide a reason for rejection'
                })
                
            restock_request.status = 'rejected'
            restock_request.notes = f"Rejected: {reason}"
            restock_request.save()
            
            # Create notification for admin
            Notification.objects.create(
                recipient=User.objects.filter(is_superuser=True).first(),
                type='restock_rejected',
                title='Restock Request Rejected',
                message=f'Supplier {supplier.name} has rejected restock request for {restock_request.product.name}. Reason: {reason}'
            )
            
            # Create activity log
            SupplierActivity.objects.create(
                supplier=supplier,
                activity_type='restock_rejected',
                description=f'Rejected restock request for {restock_request.product.name}. Reason: {reason}'
            )
            
            return JsonResponse({
                'status': 'success',
                'message': f'Restock request for {restock_request.product.name} has been rejected'
            })
        
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid action'
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'An error occurred: {str(e)}'
        })
