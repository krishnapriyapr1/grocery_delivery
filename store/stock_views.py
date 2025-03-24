from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.contrib import messages
from .models import Product, RestockRequest, Notification, Supplier
from .decorators import is_admin
from django.views.decorators.http import require_POST
import json

@login_required
@user_passes_test(is_admin)
def admin_stock(request):
    """View for managing stock levels and inventory."""
    product_id = request.GET.get('product_id')
    product = None
    if product_id:
        product = get_object_or_404(Product, id=product_id)
    
    products = Product.objects.select_related('category', 'supplier').all()
    low_stock_products = products.filter(stock__lte=3)
    suppliers = Supplier.objects.filter(is_approved=True)
    
    context = {
        'products': products,
        'low_stock_products': low_stock_products,
        'suppliers': suppliers,
        'title': 'Stock Management'
    }
    
    # If a product was selected, add it to context for modal
    if product:
        context['show_restock_modal'] = True
        context['restock_product'] = product
    
    return render(request, 'store/admin/stock_management.html', context)

@login_required
@user_passes_test(is_admin)
@require_POST
def restock_product(request, product_id):
    """Handle product restock requests with custom quantity."""
    try:
        product = get_object_or_404(Product, id=product_id)
        quantity = int(request.POST.get('quantity', 0))
        notes = request.POST.get('notes', '')

        if quantity <= 0:
            return JsonResponse({
                'success': False,
                'message': 'Please enter a valid quantity greater than 0'
            })

        if not product.supplier:
            return JsonResponse({
                'success': False,
                'message': 'This product has no assigned supplier'
            })

        # Create restock request
        restock_request = RestockRequest.objects.create(
            product=product,
            supplier=product.supplier,
            quantity=quantity,
            notes=notes
        )

        # Create notification for supplier
        Notification.objects.create(
            recipient=product.supplier.user,
            type='restock_request',  
            title=f'New Restock Request: {product.name}',
            message=f'A restock request for {quantity} units of {product.name} has been submitted.'
        )

        return JsonResponse({
            'success': True,
            'message': f'Restock request for {quantity} units of {product.name} has been sent to the supplier.'
        })

    except ValueError:
        return JsonResponse({
            'success': False,
            'message': 'Invalid quantity provided'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        })

@login_required
@user_passes_test(is_admin)
@require_POST
def assign_supplier(request):
    """Assign a supplier to a product."""
    try:
        data = request.POST
        product_id = data.get('product_id')
        supplier_id = data.get('supplier_id')

        if not product_id or not supplier_id:
            return JsonResponse({
                'success': False,
                'message': 'Product ID and Supplier ID are required'
            })

        product = get_object_or_404(Product, id=product_id)
        supplier = get_object_or_404(Supplier, id=supplier_id)

        # Update product's supplier
        product.supplier = supplier
        product.save()

        # Create notification for supplier
        Notification.objects.create(
            recipient=supplier.user,
            type='approval',  
            title=f'New Product Assignment: {product.name}',
            message=f'You have been assigned as the supplier for {product.name}.'
        )

        return JsonResponse({
            'success': True,
            'message': f'{supplier.name} has been assigned as the supplier for {product.name}'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        })

@login_required
@user_passes_test(is_admin)
@require_POST
def update_reorder_level(request, product_id):
    """Update the reorder level for a product."""
    try:
        product = get_object_or_404(Product, id=product_id)
        reorder_level = int(request.POST.get('reorder_level', 0))

        if reorder_level < 0:
            return JsonResponse({
                'success': False,
                'message': 'Reorder level must be 0 or greater'
            })

        product.reorder_level = reorder_level
        product.save()

        return JsonResponse({
            'success': True,
            'message': f'Reorder level for {product.name} has been updated to {reorder_level}'
        })

    except ValueError:
        return JsonResponse({
            'success': False,
            'message': 'Invalid reorder level provided'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        })
