@login_required
@user_passes_test(is_admin)
def admin_products(request):
    # Get all products with related category and supplier info
    products = Product.objects.all().select_related('category', 'supplier')
    # Get all categories
    categories = Category.objects.all()
    
    context = {
        'products': products,
        'categories': categories,
        'title': 'Products Management'
    }
    return render(request, 'store/admin/products.html', context)
