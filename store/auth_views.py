from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, 'Welcome back!')
            
            # Check user type and redirect accordingly
            if user.is_superuser or user.is_staff:
                return redirect('/store-admin/')  # Use absolute path to ensure correct redirect
            elif hasattr(user, 'supplier'):
                return redirect('supplier_dashboard')
            elif hasattr(user, 'deliveryboy'):
                return redirect('delivery_dashboard')
            else:
                return redirect('home')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/login.html')

def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('login')
