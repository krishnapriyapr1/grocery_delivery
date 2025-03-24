from .models import Product

def admin_context(request):
    """Add admin-related context variables to all templates."""
    context = {}
    if request.user.is_authenticated and request.user.is_staff:
        context['pending_products_count'] = Product.objects.filter(approval_status='pending').count()
    return context
