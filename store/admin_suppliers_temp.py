@login_required
@user_passes_test(is_admin)
def admin_suppliers(request):
    suppliers = Supplier.objects.all().order_by('-created_at')
    
    for supplier in suppliers:
        # Calculate total products
        supplier.total_products = supplier.products.count()
        
        # Calculate response rate
        total_requests = supplier.restockrequest_set.count()
        completed_requests = supplier.restockrequest_set.filter(status='completed').count()
        supplier.response_rate = (completed_requests / total_requests * 100) if total_requests > 0 else 0
        
        # Get recent activity
        supplier.recent_activity = supplier.activities.first()
        
        # Get pending restock requests
        supplier.pending_requests = supplier.restockrequest_set.filter(status='pending').count()
    
    context = {
        'suppliers': suppliers,
        'title': 'Manage Suppliers'
    }
    
    return render(request, 'store/admin/suppliers.html', context)
