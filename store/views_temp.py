@login_required
@user_passes_test(lambda u: u.is_superuser)
def edit_category(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    if request.method == 'GET':
        form = CategoryForm(instance=category)
        return render(request, 'store/admin/edit_category.html', {
            'form': form,
            'category': category,
            'title': 'Edit Category'
        })
    elif request.method == 'POST':
        form = CategoryForm(request.POST, request.FILES, instance=category)
        try:
            if form.is_valid():
                form.save()
                messages.success(request, 'Category updated successfully!')
            else:
                messages.error(request, 'Please check the form data and try again.')
                return render(request, 'store/admin/edit_category.html', {
                    'form': form,
                    'category': category,
                    'title': 'Edit Category'
                })
        except Exception as e:
            messages.error(request, f'Error updating category: {str(e)}')
    return redirect('admin_categories')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def delete_category(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    if request.method == 'POST':
        try:
            category.delete()
            messages.success(request, 'Category deleted successfully!')
        except Exception as e:
            messages.error(request, f'Error deleting category: {str(e)}')
    return redirect('admin_categories')
