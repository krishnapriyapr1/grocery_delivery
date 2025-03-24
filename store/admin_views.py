from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.db.models import Count, Q, Sum, Avg, F
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.contrib import messages
import json
from .models import Supplier, Product, RestockRequest, SupplierMessage, OrderItem, SupplierActivity, Notification
from .decorators import is_admin
from django.db import models

@login_required
@user_passes_test(is_admin)
def supplier_details(request, supplier_id):
    supplier = get_object_or_404(Supplier, id=supplier_id)
    
    # Get performance metrics
    total_products = supplier.products.count()
    total_restock_requests = RestockRequest.objects.filter(supplier=supplier).count()
    completed_requests = RestockRequest.objects.filter(supplier=supplier, status='completed').count()
    response_rate = (completed_requests / total_restock_requests * 100) if total_restock_requests > 0 else 0
    
    # Get supplier's products with their current stock levels
    products = supplier.products.all().select_related('category').order_by('name')
    
    # Get message history
    messages = SupplierMessage.objects.filter(supplier=supplier).order_by('-created_at')[:20]
    
    # Get recent activities (restock requests and messages)
    restock_activities = RestockRequest.objects.filter(supplier=supplier).order_by('-created_at')[:5]
    message_activities = SupplierMessage.objects.filter(supplier=supplier).order_by('-created_at')[:5]
    
    # Get all restock requests for the table
    restock_requests = RestockRequest.objects.filter(supplier=supplier).select_related('product').order_by('-created_at')
    
    # Get pending restock requests
    pending_restock_requests = restock_requests.filter(status='pending')
    
    # Calculate total sales
    total_sales = OrderItem.objects.filter(
        product__supplier=supplier
    ).aggregate(
        total=Sum(F('quantity') * F('price'))
    )['total'] or 0
    
    # Calculate average response time (in hours)
    completed_requests_with_time = RestockRequest.objects.filter(
        supplier=supplier, 
        status='completed'
    ).annotate(
        response_time=F('updated_at') - F('created_at')
    )
    avg_response_time = completed_requests_with_time.aggregate(
        avg_time=Avg('response_time')
    )['avg_time']
    
    # Get unread messages count
    unread_messages_count = SupplierMessage.objects.filter(
        supplier=supplier,
        is_from_admin=False,
        read=False
    ).count()
    
    # Combine and sort activities
    recent_activities = []
    for restock in restock_activities:
        recent_activities.append({
            'date': restock.created_at,
            'description': f'Restock requested for {restock.product.name} - {restock.quantity} units'
        })
    
    for message in message_activities:
        recent_activities.append({
            'date': message.created_at,
            'description': 'Message ' + ('sent' if message.is_from_admin else 'received')
        })
    
    # Sort activities by date
    recent_activities.sort(key=lambda x: x['date'], reverse=True)
    recent_activities = recent_activities[:5]  # Keep only 5 most recent
    
    context = {
        'supplier': supplier,
        'total_products': total_products,
        'total_restock_requests': total_restock_requests,
        'response_rate': round(response_rate, 1),
        'recent_activities': recent_activities,
        'unread_messages_count': unread_messages_count,
        'products': products,
        'restock_requests': restock_requests,
        'pending_restock_requests': pending_restock_requests,
        'messages': messages,
        'total_sales': total_sales,
        'avg_response_time': avg_response_time,
        'section': 'suppliers'
    }
    
    return render(request, 'store/admin/supplier_details.html', context)

@login_required
@user_passes_test(is_admin)
def stock_management(request):
    """View for managing stock levels and restock requests."""
    products = Product.objects.select_related('supplier', 'category').all()
    suppliers = Supplier.objects.filter(is_approved=True).order_by('name')
    low_stock_products = products.filter(stock__lte=F('reorder_level'))
    
    # Get all restock requests
    restock_requests = RestockRequest.objects.select_related('product', 'supplier').all()
    
    context = {
        'products': products,
        'suppliers': suppliers,
        'low_stock_products': low_stock_products,
        'total_products': products.count(),
        'low_stock_count': low_stock_products.count(),
        'restock_requests': restock_requests,
    }
    
    return render(request, 'store/admin/stock_management.html', context)

@login_required
@user_passes_test(is_admin)
@require_POST
@csrf_exempt
def toggle_supplier_status(request, supplier_id):
    try:
        supplier = get_object_or_404(Supplier, id=supplier_id)
        data = json.loads(request.body)
        approve = bool(data.get('approve'))
        
        # Update supplier status
        supplier.is_approved = approve
        supplier.save()
        
        # Create notification for supplier
        Notification.objects.create(
            recipient=supplier.user,
            type='approval',
            title='Supplier Status Update',
            message=f'Your supplier account has been {"approved" if approve else "suspended"}.'
        )
        
        # Create activity log
        activity_desc = 'approved' if approve else 'suspended'
        SupplierActivity.objects.create(
            supplier=supplier,
            activity_type='approval_status',
            description=f'Supplier {activity_desc} by admin'
        )
        
        messages.success(request, f'Supplier successfully {activity_desc}')
        
        return JsonResponse({
            'success': True,
            'message': f'Supplier successfully {activity_desc}',
            'is_approved': supplier.is_approved
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid request data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
@user_passes_test(is_admin)
@require_POST
def create_restock_request(request, product_id):
    """Create a new restock request for a product"""
    try:
        quantity = request.POST.get('quantity')
        supplier_id = request.POST.get('supplier_id')
        notes = request.POST.get('notes', '')

        if not quantity:
            return JsonResponse({
                'status': 'error',
                'message': 'Quantity is required'
            })
            
        if not supplier_id:
            return JsonResponse({
                'status': 'error',
                'message': 'Supplier is required'
            })

        try:
            quantity = int(quantity)
            if quantity <= 0:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Quantity must be greater than 0'
                })
        except ValueError:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid quantity value'
            })

        product = get_object_or_404(Product, id=product_id)
        supplier = get_object_or_404(Supplier, id=supplier_id)
        
        if not supplier.is_approved:
            return JsonResponse({
                'status': 'error',
                'message': f'Supplier {supplier.name} is not approved'
            })
            
        # Check if there's already a pending restock request for this product and supplier
        if RestockRequest.objects.filter(
            product=product,
            supplier=supplier,
            status='pending'
        ).exists():
            return JsonResponse({
                'status': 'error',
                'message': f'There is already a pending restock request for {product.name} with supplier {supplier.name}'
            })
        
        # Create restock request
        restock_request = RestockRequest.objects.create(
            product=product,
            supplier=supplier,
            quantity=quantity,
            notes=notes,
            status='pending',
            requested_by=request.user  # Add this line to track who made the request
        )
        
        # Update product's supplier if not set
        if not product.supplier:
            product.supplier = supplier
            product.save()

        # Create notification for supplier
        Notification.objects.create(
            recipient=supplier.user,
            type='restock_request',
            title='New Restock Request',
            message=f'A restock request has been created for {product.name}. Quantity: {quantity}'
        )
        
        # Create supplier activity
        SupplierActivity.objects.create(
            supplier=supplier,
            activity_type='restock_request',
            description=f'New restock request for {product.name} (Quantity: {quantity})'
        )

        return JsonResponse({
            'status': 'success',
            'message': f'Restock request for {quantity} units of {product.name} has been sent to {supplier.name}'
        })

    except Product.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Product not found'
        })
    except Supplier.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Supplier not found'
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'An error occurred: {str(e)}'
        })

@login_required
@user_passes_test(is_admin)
def manage_product_approvals(request):
    # Get all pending products
    pending_products = Product.objects.filter(approval_status='pending').select_related('supplier', 'category')
    
    # Get approved and rejected products for reference
    approved_products = Product.objects.filter(approval_status='approved').count()
    rejected_products = Product.objects.filter(approval_status='rejected').count()
    
    context = {
        'pending_products': pending_products,
        'approved_count': approved_products,
        'rejected_count': rejected_products,
        'title': 'Product Approvals'
    }
    
    return render(request, 'store/admin/product_approvals.html', context)

@login_required
@user_passes_test(is_admin)
@require_POST
def update_product_approval(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    status = request.POST.get('status')
    
    if status in ['approved', 'rejected']:
        product.approval_status = status
        product.save()
        
        # Create notification for supplier
        notification = Notification.objects.create(
            recipient=product.supplier.user,
            type='approval',
            title=f'Product {status.title()}',
            message=f'Your product "{product.name}" has been {status}.'
        )
        
        # Create supplier activity
        SupplierActivity.objects.create(
            supplier=product.supplier,
            activity_type='approval_status',
            description=f'Product "{product.name}" was {status}.'
        )
        
        messages.success(request, f'Product "{product.name}" has been {status}.')
    else:
        messages.error(request, 'Invalid approval status.')
    
    return redirect('manage_product_approvals')

@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    # Get pending products count
    pending_products_count = Product.objects.filter(approval_status='pending').count()
    
    # Get total orders count
    total_orders = Order.objects.count()
    
    # Calculate total revenue
    total_revenue = OrderItem.objects.aggregate(
        revenue=Sum(F('price') * F('quantity'))
    )['revenue'] or 0
    
    context = {
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'pending_products_count': pending_products_count,
        'title': 'Admin Dashboard'
    }
    
    return render(request, 'store/admin/admin_dashboard.html', context)
