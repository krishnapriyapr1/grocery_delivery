from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import redirect
from functools import wraps
from .utils import is_admin

def is_admin(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        return redirect('store:login')
    return _wrapped_view

def admin_required(view_func):
    """
    Decorator for views that checks that the user is logged in and is an admin,
    redirecting to the login page if necessary.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not is_admin(request.user):
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def delivery_boy_required(view_func):
    """
    Decorator for views that checks that the user is logged in and is a delivery boy,
    redirecting to the login page if necessary.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        try:
            if not request.user.delivery_boy.is_approved:
                return redirect('home')
        except:
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return _wrapped_view
