from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import DeliveryBoyRegistrationForm

def delivery_register(request):
    if request.method == 'POST':
        form = DeliveryBoyRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()  # This will create both User and DeliveryBoy
            messages.success(request, 'Registration successful! Please wait for admin approval.')
            return redirect('delivery_login')
    else:
        form = DeliveryBoyRegistrationForm()
    
    return render(request, 'store/delivery/register.html', {'form': form})
