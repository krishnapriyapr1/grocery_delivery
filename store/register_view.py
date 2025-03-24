def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Update existing user profile
            user.userprofile.phone = form.cleaned_data.get('phone', '')
            user.userprofile.address = form.cleaned_data.get('address', '')
            user.userprofile.save()
            messages.success(request, 'Registration successful! Please login.')
            return redirect('login')
    else:
        form = UserRegistrationForm()
    
    return render(request, 'store/register.html', {'form': form})
