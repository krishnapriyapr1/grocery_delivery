from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import UserRegistrationForm
from .models import UserProfile

def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Get or create user profile
            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.phone = form.cleaned_data.get('phone', '')
            profile.address = form.cleaned_data.get('address', '')
            profile.save()
            messages.success(request, 'Registration successful! Please login.')
            return redirect('login')
    else:
        form = UserRegistrationForm()
    
    return render(request, 'store/register.html', {'form': form})
