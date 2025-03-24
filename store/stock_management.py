from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.contrib import messages
from .models import Product, RestockRequest, Notification, Supplier
from .decorators import is_admin
from django.contrib.auth.models import User

@login_required
@user_passes_test(is_admin)
def admin_stock(request):
    """View for managing stock levels and inventory."""
    products = Product.objects.select_related('category', 'supplier').all()
    low_stock_products = products.filter(stock__lte=3)
    suppliers = Supplier.objects.filter(is_approved=True)
    
    context = {
        'products': products,
        'low_stock_products': low_stock_products,
        'suppliers': suppliers,
        'title': 'Stock Management'
    }
    return render(request, 'store/admin/stock_management.html', context)
