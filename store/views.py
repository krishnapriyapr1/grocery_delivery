from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.db.models import Q, Sum, Count, F, Avg
from django.contrib.auth.models import User
from django.templatetags.static import static
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.core.mail import send_mail, EmailMessage
from django.conf import settings
from django.template.loader import render_to_string
from django.db import transaction
from datetime import datetime, timedelta
from decimal import Decimal
import json
import random
import stripe
from .models import *
from .forms import SupplierRegistrationForm, DeliveryBoyRegistrationForm

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

from .models import Category, Product, Cart, CartItem, Order, OrderItem, UserProfile, Supplier, RestockRequest, Notification, SupplierActivity, SupplierMessage, Coupon, DeliveryBoy, DeliveryAssignment, DeliveryBoyReport, DeliveryChat, QuickMessage
from .forms import UserRegistrationForm, UserProfileForm, OrderForm, SearchForm, ProductForm, SupplierRegistrationForm, CategoryForm, DeliveryBoyRegistrationForm
from .utils import (
    send_order_confirmation,
    send_order_status_update,
    send_supplier_approval,
    send_restock_request,
    send_low_stock_alert
)

def is_admin(user):
    return user.is_staff

def is_supplier(user):
    return hasattr(user, 'supplier')

def home(request):
    # Get categories
    categories = Category.objects.all()[:6]  # Get first 6 categories
    
    # Get featured products that are available
    featured_products = Product.objects.filter(
        featured=True,
        is_available=True,
        approval_status='approved'
    ).select_related('supplier')[:4]  # Get first 4 featured products
    
    context = {
        'categories': categories,
        'featured_products': featured_products,
    }
    return render(request, 'store/home.html', context)

def product_list(request):
    products = Product.objects.filter(is_available=True)
    categories = Category.objects.all()
    search_form = SearchForm(request.GET)
    
    if search_form.is_valid():
        query = search_form.cleaned_data.get('query')
        category = search_form.cleaned_data.get('category')
        
        if query:
            products = products.filter(
                Q(name__icontains=query) |
                Q(description__icontains=query)
            )
        
        if category:
            products = products.filter(category__name=category)
    
    context = {
        'products': products,
        'categories': categories,
        'search_form': search_form,
        'title': 'All Products'
    }
    return render(request, 'store/product_list.html', context)

def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_available=True)
    related_products = Product.objects.filter(category=product.category).exclude(id=product_id)[:4]
    context = {
        'product': product,
        'related_products': related_products
    }
    return render(request, 'store/product_detail.html', context)

@login_required
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    cart, created = Cart.objects.get_or_create(user=request.user)
    print(f"Cart ID: {cart.id}, Created: {created}")  # Debugging output
    
    # Check if the item is already in cart
    cart_item, item_created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        defaults={'quantity': 1}
    )
    print(f"Cart Item: {cart_item}, Item Created: {item_created}")  # Debugging output
    
    # If item already exists, increment quantity
    if not item_created:
        cart_item.quantity += 1
        cart_item.save()
        print(f"Updated Cart Item Quantity: {cart_item.quantity}")  # Debugging output
    
    messages.success(request, f'{product.name} has been added to your cart.')
    return redirect('product_list')

@login_required
def view_cart(request):
    cart = Cart.objects.filter(user=request.user).first()
    cart_items = []
    total = 0
    
    if cart:
        cart_items = cart.items.all()
        total = cart.get_total()
    
    context = {
        'cart_items': cart_items,
        'total': total
    }
    return render(request, 'store/cart.html', context)

@login_required
def update_cart(request, item_id):
    try:
        cart_item = CartItem.objects.get(id=item_id, cart__user=request.user)
        
        if request.method == 'POST':
            action = request.POST.get('action')
            
            if action == 'increase':
                cart_item.quantity += 1
            elif action == 'decrease':
                if cart_item.quantity > 1:
                    cart_item.quantity -= 1
                else:
                    cart_item.delete()
                    messages.success(request, 'Item removed from cart.')
                    return redirect('cart')
            
            cart_item.save()
            messages.success(request, 'Cart updated successfully.')
    except CartItem.DoesNotExist:
        messages.error(request, 'Item not found in your cart.')
    
    return redirect('cart')

@login_required
def remove_from_cart(request, item_id):
    try:
        cart_item = CartItem.objects.get(id=item_id, cart__user=request.user)
        cart_item.delete()
        messages.success(request, 'Item removed from cart.')
    except CartItem.DoesNotExist:
        messages.error(request, 'Item not found in cart.')
    
    return redirect('cart')

@login_required
def remove_from_cart_ajax(request, item_id):
    if request.method == 'POST':
        try:
            cart = Cart.objects.get(user=request.user)
            cart_item = CartItem.objects.get(id=item_id, cart=cart)
            cart_item.delete()
            
            return JsonResponse({
                'success': True,
                'message': 'Item removed from cart.',
                'cart_total': str(cart.get_total())
            })
        except (Cart.DoesNotExist, CartItem.DoesNotExist):
            return JsonResponse({
                'success': False,
                'error': 'Item not found in cart.'
            })
    return JsonResponse({
        'success': False,
        'error': 'Invalid request method.'
    })

@login_required
def add_to_cart_ajax(request):
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        quantity = int(request.POST.get('quantity', 1))
        
        try:
            product = Product.objects.get(id=product_id)
            cart, _ = Cart.objects.get_or_create(user=request.user)
            
            # Check if item already exists in cart
            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                product=product,
                defaults={'quantity': quantity}
            )
            
            if not created:
                # If item exists, update the quantity instead of adding
                cart_item.quantity = quantity
                cart_item.save()
            
            return JsonResponse({
                'success': True,
                'message': f'{product.name} added to cart.',
                'cart_item_id': cart_item.id,
                'quantity': cart_item.quantity
            })
            
        except Product.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Product not found.'})
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Invalid quantity.'})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

@login_required
def update_cart_ajax(request, item_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            action = data.get('action')
            
            cart = Cart.objects.get(user=request.user)
            cart_item = CartItem.objects.get(id=item_id, cart=cart)
            
            if action == 'increase':
                cart_item.quantity += 1
            elif action == 'decrease':
                if cart_item.quantity > 1:
                    cart_item.quantity -= 1
                else:
                    cart_item.delete()
                    return JsonResponse({
                        'success': True,
                        'removed': True,
                        'cart_total': str(cart.get_total())
                    })
            
            cart_item.save()
            
            # Calculate the new totals
            item_total = cart_item.quantity * cart_item.product.price
            cart_total = cart.get_total()
            
            return JsonResponse({
                'success': True,
                'quantity': cart_item.quantity,
                'total': str(item_total),
                'cart_total': str(cart_total)
            })
            
        except CartItem.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Cart item not found.'})
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON data.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})

def get_delivery_time(postal_code):
    """
    Calculate delivery time based on postal code distance
    Returns minutes to add for delivery estimate
    """
    # Convert postal code to first 3 digits to determine zone
    zone = postal_code[:3] if postal_code else '000'
    
    # Delivery times based on zones (in minutes)
    delivery_times = {
        # Nearby zones: 30 minutes
        '560': 30,  # Bangalore central
        '561': 35,  # Bangalore north
        '562': 35,  # Bangalore south
        # Medium distance: 40 minutes
        '563': 40,  # Bangalore east
        '564': 40,  # Bangalore west
        # Far zones: 50 minutes
        '565': 50,  # Outer Bangalore
        '566': 50
    }
    
    # Get base delivery time, default to 45 minutes
    minutes = delivery_times.get(zone, 45)
    
    # Round up to nearest 5 minutes for cleaner times
    return ((minutes + 4) // 5) * 5

def check_monthly_purchases_and_send_coupon(user):
    """
    Check if user's total purchases in current month exceed ₹1000
    and send a coupon if they do
    """
    try:
        # Get the current month's first and last day
        today = timezone.now()
        month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if today.month == 12:
            next_month = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month = today.replace(month=today.month + 1, day=1)
        month_end = next_month - timedelta(seconds=1)

        # Calculate total purchases for the month including current order
        monthly_orders = Order.objects.filter(
            user=user,
            created_at__gte=month_start,
            created_at__lte=month_end,
            status__in=['pending', 'processing', 'shipped', 'delivered']
        )
        
        monthly_total = monthly_orders.aggregate(total=Sum('total_amount'))['total'] or 0
        order_count = monthly_orders.count()

        print(f"Monthly stats for {user.email}:")
        print(f"- Total amount: ₹{monthly_total}")
        print(f"- Order count: {order_count}")
        print(f"- Time period: {month_start} to {month_end}")

        # Check if user already received a coupon this month
        existing_coupon = Coupon.objects.filter(
            user=user,
            is_used=False,
            valid_to__gte=timezone.now()
        ).first()  # Get the actual coupon object instead of just checking existence

        if existing_coupon:
            print(f"User already has valid coupon: {existing_coupon.code} (valid until {existing_coupon.valid_to})")
            return False

        if monthly_total >= 1000:
            # Generate coupon code
            coupon_code = f"REWARD{user.id}{today.strftime('%m%y')}"
            
            # Calculate discount (10% of monthly purchases, max ₹500)
            discount_amount = min(monthly_total * Decimal('0.10'), 500)
            
            # Set expiry date (end of next month)
            expiry_date = month_end + timedelta(days=30)

            try:
                # Create coupon
                coupon = Coupon.objects.create(
                    code=coupon_code,
                    user=user,
                    discount_amount=discount_amount,
                    valid_from=today,
                    valid_to=expiry_date,
                    is_active=True,
                    minimum_spend=Decimal('100')  # Minimum spend to use coupon
                )

                print(f"Created coupon: {coupon_code} for ₹{discount_amount}")

                # Send coupon email
                if send_coupon_email(user.email, coupon_code, discount_amount, expiry_date):
                    print(f"Reward coupon sent to {user.email} for monthly purchases of ₹{monthly_total}")
                    return True
                else:
                    # If email fails, delete the coupon so we can try again later
                    coupon.delete()
                    print(f"Deleted coupon {coupon_code} due to email failure")
                    return False

            except Exception as e:
                print(f"Error creating/sending coupon: {str(e)}")
                # Attempt to clean up any partially created coupon
                Coupon.objects.filter(code=coupon_code).delete()
                raise  # Re-raise to be caught by outer try-except

    except Exception as e:
        print(f"Error in monthly purchase check for {user.email}: {str(e)}")
        from django.core.mail import mail_admins
        mail_admins(
            'Failed Monthly Purchase Check',
            f'Error checking monthly purchases for {user.email}.\nError: {str(e)}'
        )
    return False

def send_coupon_email(email, coupon_code, discount_amount, expiry_date):
    """
    Send a coupon email to the user
    """
    try:
        subject = 'Your Fresh Mart Discount Coupon!'
        from_email = settings.DEFAULT_FROM_EMAIL
        to_email = [email]
        
        # Render the email template with context
        html_content = render_to_string('store/emails/coupon_email.html', {
            'coupon_code': coupon_code,
            'discount_amount': discount_amount,
            'expiry_date': expiry_date
        })
        
        # Create and send the email
        msg = EmailMessage(subject, html_content, from_email, to_email)
        msg.content_subtype = "html"  # Main content is now HTML
        msg.send()
        
        print(f"Coupon email sent successfully to {email}")  # Debug log
        return True
        
    except Exception as e:
        print(f"Error sending coupon email to {email}: {str(e)}")  # More detailed error logging
        from django.core.mail import mail_admins
        mail_admins(
            'Failed to Send Coupon Email',
            f'Error sending coupon email to {email}.\nError: {str(e)}\nCoupon Code: {coupon_code}'
        )
        return False

@login_required
def checkout(request):
    try:
        cart = Cart.objects.get(user=request.user)
        cart_items = cart.items.all().select_related('product')
        
        if not cart_items.exists():
            messages.error(request, 'Your cart is empty')
            return redirect('cart')
        
        # Validate stock availability before processing
        stock_errors = []
        for item in cart_items:
            if item.quantity > item.product.stock:
                stock_errors.append(
                    f'Only {item.product.stock} units available for {item.product.name}'
                )
        
        if stock_errors:
            for error in stock_errors:
                messages.error(request, error)
            return redirect('cart')
        
        if request.method == 'POST':
            try:
                with transaction.atomic():
                    # Create order
                    order = Order.objects.create(
                        user=request.user,
                        name=request.POST.get('name'),
                        email=request.POST.get('email'),
                        phone=request.POST.get('phone'),
                        address=request.POST.get('address'),
                        city=request.POST.get('city'),
                        postal_code=request.POST.get('postal_code'),
                        payment_method=request.POST.get('payment_method'),
                        total_amount=cart.get_total()
                    )
                    
                    # Create order items and update stock
                    for item in cart_items:
                        OrderItem.objects.create(
                            order=order,
                            product=item.product,
                            quantity=item.quantity,
                            price=item.product.price
                        )
                        
                        Product.objects.filter(id=item.product.id).update(
                            stock=F('stock') - item.quantity
                        )
                    
                    # Clear the cart after successful order
                    cart.delete()
                    
                    # Send order confirmation email
                    try:
                        subject = f'Order Confirmation - Order #{order.id}'
                        html_content = render_to_string('store/emails/order_confirmation_email.html', {
                            'order': order
                        })
                        
                        msg = EmailMessage(subject, html_content, settings.DEFAULT_FROM_EMAIL, [order.email])
                        msg.content_subtype = "html"
                        msg.send()
                        
                        print(f"Order confirmation email sent to {order.email}")
                        
                        # Check monthly purchases and send reward coupon if eligible
                        coupon_sent = check_monthly_purchases_and_send_coupon(request.user)
                        if coupon_sent:
                            messages.success(request, "You've earned a reward coupon! Check your email.")
                        
                    except Exception as e:
                        print(f"Error sending order confirmation email: {str(e)}")
                    
                    messages.success(request, 'Order placed successfully!')
                    return redirect('order_confirmation', order_id=order.id)
                    
            except Exception as e:
                messages.error(request, f'Error processing order: {str(e)}')
                return redirect('cart')
        
        context = {
            'cart': cart,
            'cart_items': cart_items,
            'total': cart.get_total(),
        }
        return render(request, 'store/checkout.html', context)
        
    except Cart.DoesNotExist:
        messages.error(request, 'Your cart is empty')
        return redirect('shop')
    except Exception as e:
        messages.error(request, f'An error occurred: {str(e)}')
        return redirect('cart')

@login_required
def order_confirmation(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'store/order_confirmation.html', {'order': order})

@login_required
def order_tracking(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'store/order_tracking.html', {'order': order})

@login_required
def order_detail(request, order_id):
    try:
        if hasattr(request.user, 'deliveryboy'):
            order = Order.objects.get(
                id=order_id,
                delivery_assignment__delivery_boy=request.user.deliveryboy
            )
        else:
            order = Order.objects.get(id=order_id, user=request.user)
            
        return render(request, 'store/order_detail.html', {'order': order})
    except Order.DoesNotExist:
        messages.error(request, 'Order not found.')
        return redirect('home')

@login_required
def order_history(request):
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    
    # Add unread message counts for each order
    for order in orders:
        try:
            if hasattr(order, 'delivery_assignment') and order.delivery_assignment:
                order.unread_messages_count = DeliveryChat.objects.filter(
                    order=order,
                    customer=request.user,
                    is_from_customer=False,
                    is_read=False
                ).count()
            else:
                order.unread_messages_count = 0
        except Order.delivery_assignment.RelatedObjectDoesNotExist:
            order.unread_messages_count = 0
    
    context = {'orders': orders}
    return render(request, 'store/order_history.html', context)

@login_required
def my_orders(request):
    # Get all orders except delivered ones, ordered by most recent first
    active_orders = Order.objects.filter(
        user=request.user,
        status__in=['pending', 'processing', 'shipped']
    ).order_by('-created_at')
    
    # Get delivered orders separately
    delivered_orders = Order.objects.filter(
        user=request.user,
        status='delivered'
    ).order_by('-created_at')
    
    context = {
        'active_orders': active_orders,
        'delivered_orders': delivered_orders
    }
    return render(request, 'store/my_orders.html', context)

@login_required
@user_passes_test(is_admin)
def update_order_status(request, order_id):
    if request.method == 'POST':
        try:
            # Parse JSON data from request body
            data = json.loads(request.body)
            new_status = data.get('status')
            order = Order.objects.get(id=order_id)
            
            if new_status in dict(Order.STATUS_CHOICES):
                # Update the order status
                order.status = new_status
                order.save()
                
                return JsonResponse({
                    'success': True,
                    'message': f'Order status updated to {new_status}'
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Invalid status value'
                }, status=400)
                
        except Order.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Order not found'
            }, status=404)
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'Invalid JSON data'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)
    
    return JsonResponse({
        'success': False,
        'message': 'Invalid request method'
    }, status=400)

@login_required
@user_passes_test(is_admin)
def toggle_supplier_approval(request, supplier_id):
    if request.method == 'POST':
        supplier = get_object_or_404(Supplier, id=supplier_id)
        data = json.loads(request.body)
        approve = data.get('approve', False)
        
        supplier.is_approved = approve
        supplier.save()
        
        if approve:
            # Send approval email
            send_supplier_approval(supplier)
        
        # Log the activity
        action = "approved" if approve else "suspended"
        SupplierActivity.objects.create(
            supplier=supplier,
            description=f"Supplier was {action} by admin"
        )
        
        return JsonResponse({'success': True})
    return JsonResponse({'success': False})

@login_required
@user_passes_test(is_admin)
def admin_view_order_details(request, order_id):
    order = get_object_or_404(Order.objects.select_related('user'), id=order_id)
    order_items = OrderItem.objects.filter(order=order).select_related('product')
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('store/admin/order_details_modal.html', {
            'order': order,
            'order_items': order_items
        })
        return JsonResponse({'html': html})
    
    context = {
        'order': order,
        'order_items': order_items,
        'title': f'Order #{order.id} Details'
    }
    return render(request, 'store/admin/order_details.html', context)

@login_required
@user_passes_test(is_admin)
def view_supplier_details(request, supplier_id):
    supplier = get_object_or_404(Supplier, id=supplier_id)
    
    # Get restock requests
    restock_requests = RestockRequest.objects.filter(product__supplier=supplier)
    
    # Calculate response rate (completed restock requests / total requests)
    total_requests = restock_requests.count()
    completed_requests = restock_requests.filter(status='completed').count()
    response_rate = (completed_requests / total_requests * 100) if total_requests > 0 else 0
    
    # Get recent activities (last 10)
    recent_activities = SupplierActivity.objects.filter(supplier=supplier).order_by('-created_at')[:10]
    
    # Get messages
    messages = SupplierMessage.objects.filter(supplier=supplier).order_by('created_at')
    
    context = {
        'supplier': supplier,
        'restock_requests': restock_requests,
        'restock_requests_count': total_requests,
        'response_rate': round(response_rate, 1),
        'recent_activities': recent_activities,
        'messages': messages,
    }
    
    return render(request, 'store/admin/supplier_details.html', context)

@login_required
@user_passes_test(is_admin)
def admin_stock_management(request):
    """View for managing stock levels and inventory."""
    # Get all products with their suppliers
    all_products = Product.objects.all().select_related('supplier')
    
    # Get low stock products (stock <= 3)
    low_stock_products = all_products.filter(stock__lte=3)
    
    # Get pending restock requests
    pending_requests = RestockRequest.objects.filter(
        status='pending'
    ).select_related('product')
    
    # Create a map of product IDs to their pending requests
    pending_request_map = {req.product_id: req for req in pending_requests}
    
    # Add restock request information to all products
    for product in all_products:
        pending_request = pending_request_map.get(product.id)
        product._has_pending_restock = pending_request is not None
        if pending_request:
            product.latest_request_date = pending_request.created_at
            product.requested_quantity = pending_request.quantity
    
    # Split low stock products into requested and unrequested
    unrequested_items = [p for p in low_stock_products if not p.has_pending_restock]
    requested_items = [p for p in low_stock_products if p.has_pending_restock]
    
    # Get all suppliers for the assign supplier modal
    suppliers = Supplier.objects.filter(is_approved=True)
    
    context = {
        'unrequested_items': unrequested_items,
        'requested_items': requested_items,
        'all_products': all_products,
        'suppliers': suppliers,
    }
    return render(request, 'store/admin/stock_management.html', context)

@login_required
@user_passes_test(is_admin)
def restock_product(request, product_id):
    """Handle product restock requests."""
    if request.method != 'POST':
        return redirect('admin_stock')
    
    try:
        quantity = int(request.POST.get('quantity', 0))
        notes = request.POST.get('notes', '')
        
        if quantity <= 0:
            messages.error(request, 'Invalid quantity')
            return redirect('admin_stock')
        
        product = get_object_or_404(Product, id=product_id)
        
        if not product.supplier:
            messages.error(request, 'No supplier assigned to this product')
            return redirect('admin_stock')
        
        # Create restock request
        restock_request = RestockRequest.objects.create(
            product=product,
            supplier=product.supplier,
            quantity=quantity,
            notes=notes,
            status='pending'  # Set as pending for supplier approval
        )
        
        # Create notification for supplier
        Notification.objects.create(
            recipient=product.supplier.user,
            type='restock_request',
            title=f'New Restock Request: {product.name}',
            message=f'Admin has requested restock of {quantity} units for {product.name}'
        )
        
        # Record supplier activity
        SupplierActivity.objects.create(
            supplier=product.supplier,
            activity_type='restock_requested',
            description=f'Restock requested for {product.name} - {quantity} units'
        )
        
        messages.success(request, f'Restock request for {quantity} units of {product.name} has been sent to the supplier')
        return redirect('admin_stock')
        
    except Exception as e:
        messages.error(request, str(e))
        return redirect('admin_stock')

@login_required
@user_passes_test(is_admin)
def assign_supplier(request):
    """Assign a supplier to a product."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    try:
        product_id = request.POST.get('product_id')
        supplier_id = request.POST.get('supplier_id')
        
        if not product_id or not supplier_id:
            return JsonResponse({'success': False, 'error': 'Invalid product ID or supplier ID'})
        
        product = get_object_or_404(Product, id=product_id)
        supplier = get_object_or_404(Supplier, id=supplier_id)
        
        # Assign supplier to product
        product.supplier = supplier
        product.save()
        
        # Create notification for supplier
        Notification.objects.create(
            recipient=supplier.user,
            type='supplier_assignment',
            title=f'New Product Assignment',
            message=f'You have been assigned as the supplier for {product.name}'
        )
        
        # Record supplier activity
        SupplierActivity.objects.create(
            supplier=supplier,
            activity_type='product_assignment',
            description=f'Assigned as supplier for {product.name}'
        )
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@user_passes_test(is_admin)
def update_reorder_level(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        new_level = request.POST.get('reorder_level')
        
        if new_level and new_level.isdigit():
            product.reorder_level = int(new_level)
            product.save()
            messages.success(request, f'Reorder level updated for {product.name}')
        
    return redirect('admin_stock_management')

@login_required
@user_passes_test(is_admin)
def add_product(request):
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                product = form.save()
                messages.success(request, f'Product "{product.name}" has been added successfully!')
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'status': 'success',
                        'message': f'Product "{product.name}" has been added successfully!'
                    })
                return redirect('admin_dashboard')
            except Exception as e:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'status': 'error',
                        'message': str(e)
                    })
                messages.error(request, f'An error occurred while saving the product: {str(e)}')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'error',
                    'message': 'Please correct the errors in the form.',
                    'errors': dict(form.errors.items())
                })
            messages.error(request, 'Please correct the errors in the form.')
    else:
        form = ProductForm()
    
    return render(request, 'store/admin/product_form.html', {
        'form': form,
        'title': 'Add Product',
        'button_text': 'Add Product'
    })

@login_required
@user_passes_test(is_admin)
def edit_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, 'Product updated successfully!')
            return redirect('admin_dashboard')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ProductForm(instance=product)
    
    return render(request, 'store/admin/product_form.html', {
        'form': form,
        'product': product,
        'title': 'Edit Product',
        'button_text': 'Save Changes'
    })

@login_required
@user_passes_test(is_admin)
def delete_product(request, product_id):
    if request.method == 'POST':
        try:
            product = get_object_or_404(Product, id=product_id)
            product_name = product.name
            product.delete()
            
            messages.success(request, f'Product "{product_name}" has been deleted successfully.')
            return redirect('admin_dashboard')
                
        except Exception as e:
            messages.error(request, f'Error deleting product: {str(e)}')
            return redirect('admin_dashboard')
    
    messages.error(request, 'Invalid request method.')
    return redirect('admin_dashboard')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def add_category(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST, request.FILES)
        try:
            if form.is_valid():
                category = form.save()
                messages.success(request, 'Category added successfully!')
            else:
                messages.error(request, 'Please check the form data and try again.')
        except Exception as e:
            messages.error(request, f'Error adding category: {str(e)}')
    return redirect('admin_dashboard')

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

@login_required
@user_passes_test(lambda u: u.is_superuser)
def get_category_details(request, category_id):
    try:
        category = get_object_or_404(Category, id=category_id)
        data = {
            'id': category.id,
            'name': category.name,
            'description': category.description,
            'image': category.image.url if category.image else None
        }
        return JsonResponse(data)
    except Category.DoesNotExist:
        return JsonResponse({'error': 'Category not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    # Get existing dashboard data
    total_orders = Order.objects.count()
    total_products = Product.objects.count()
    total_users = User.objects.count()
    total_revenue = Order.objects.filter(status='delivered').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    recent_orders = Order.objects.order_by('-created_at')[:5]
    
    # Get active users (users with orders)
    active_users_count = User.objects.filter(order__isnull=False).distinct().count()
    
    # Get pending deliveries count
    pending_deliveries_count = Order.objects.filter(
        status__in=['processing', 'shipped']
    ).count()
    
    # Get unread messages count
    unread_messages_count = SupplierMessage.objects.filter(read=False, is_from_admin=False).count()
    
    return render(request, 'store/admin/dashboard.html', {
        'total_orders': total_orders,
        'total_products': total_products,
        'total_users': total_users,
        'total_revenue': total_revenue,
        'recent_orders': recent_orders,
        'unread_messages_count': unread_messages_count,
        'active_users_count': active_users_count,
        'pending_deliveries_count': pending_deliveries_count,
        'section': 'dashboard'
    })

@login_required
@user_passes_test(is_admin)
def admin_categories(request):
    if not request.user.is_superuser:
        return redirect('home')
        
    categories = Category.objects.prefetch_related('products').all()
    
    context = {
        'categories': categories,
    }
    
    return render(request, 'store/admin/categories.html', context)

@login_required
@user_passes_test(is_admin)
def admin_products(request):
    # Get all products with related category and supplier info
    products = Product.objects.all().select_related('category', 'supplier').prefetch_related('restock_requests')
    # Get all categories
    categories = Category.objects.all()
    
    context = {
        'products': products,
        'categories': categories,
        'title': 'Products Management'
    }
    return render(request, 'store/admin/products.html', context)

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

@login_required
@user_passes_test(is_admin)
def admin_stock(request):
    """View for managing stock levels and inventory."""
    products = Product.objects.select_related('category', 'supplier').all()
    low_stock_products = products.filter(stock__lte=3)
    
    context = {
        'products': products,
        'low_stock_products': low_stock_products,
        'title': 'Stock Management'
    }
    return render(request, 'store/admin/stock.html', context)

@login_required
@user_passes_test(is_admin)
def send_restock_request(request, product_id):
    """Handle restock requests for products."""
    if request.method == 'POST':
        try:
            product = Product.objects.get(id=product_id)
            quantity = int(request.POST.get('quantity', 0))
            
            if quantity <= 0:
                return JsonResponse({'success': False, 'error': 'Invalid quantity'})
            
            if not product.supplier:
                return JsonResponse({'success': False, 'error': 'No supplier assigned to this product'})
                
            # Create restock request
            restock_request = RestockRequest.objects.create(
                product=product,
                supplier=product.supplier,
                quantity=quantity,
                notes=f"Stock level is low ({product.stock} units). Please restock."
            )
            
            # Notify supplier
            Notification.objects.create(
                recipient=product.supplier.user,
                type='restock_request',
                title=f'Restock Request for {product.name}',
                message=f'A restock request for {quantity} units of {product.name} has been created.'
            )
            
            messages.success(request, f'Restock request sent for {product.name}')
            return redirect('admin_stock')
            
        except Product.DoesNotExist:
            messages.error(request, 'Product not found')
        except ValueError:
            messages.error(request, 'Invalid quantity value')
        except Exception as e:
            messages.error(request, f'An error occurred: {str(e)}')
        
        return redirect('admin_stock')
    
    return redirect('admin_stock')

def supplier_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Check if the user is a supplier
            try:
                supplier = Supplier.objects.get(user=user)
                if not supplier.is_approved:
                    messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
                    return render(request, 'store/supplier/login.html')
                login(request, user)
                return redirect('supplier_dashboard')
            except Supplier.DoesNotExist:
                messages.error(request, 'This login is only for suppliers.')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/supplier/login.html')

@login_required
def delivery_login(request):
    if request.user.is_authenticated:
        if hasattr(request.user, 'deliveryboy'):
            return redirect('delivery_dashboard')
        logout(request)  # Logout if not a delivery boy
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            try:
                delivery_boy = DeliveryBoy.objects.get(user=user)
                if not delivery_boy.is_approved:
                    messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
                else:
                    login(request, user)
                    return redirect('delivery_dashboard')
            except DeliveryBoy.DoesNotExist:
                messages.error(request, 'This login is only for delivery personnel.')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/delivery_login.html')

@user_passes_test(is_supplier)
def supplier_dashboard(request):
    if not hasattr(request.user, 'supplier'):
        return redirect('supplier_login')
    
    supplier = request.user.supplier
    products = Product.objects.filter(supplier=supplier)
    restock_requests = RestockRequest.objects.filter(supplier=supplier)
    
    # Get unread messages count
    unread_messages_count = SupplierMessage.objects.filter(
        supplier=supplier,
        read=False
    ).count()
    
    context = {
        'supplier': supplier,
        'total_products': products.count(),
        'pending_restock_requests': restock_requests.filter(status='pending').count(),
        'completed_restock_requests': restock_requests.filter(status='completed').count(),
        'unread_messages_count': unread_messages_count,
        'recent_activities': SupplierActivity.objects.filter(supplier=supplier).order_by('-created_at')[:5]
    }
    
    return render(request, 'store/supplier/dashboard.html', context)

@user_passes_test(is_supplier)
def supplier_restock_requests(request):
    supplier = request.user.supplier
    restock_requests = RestockRequest.objects.filter(supplier=supplier).order_by('-created_at')
    
    if request.method == 'POST':
        request_id = request.POST.get('request_id')
        action = request.POST.get('action')
        restock_request = get_object_or_404(RestockRequest, id=request_id, supplier=supplier)
        
        if action == 'complete':
            stock_quantity = int(request.POST.get('stock_quantity', 0))
            if stock_quantity > 0:
                # Update product stock
                product = restock_request.product
                product.stock += stock_quantity
                product.save()
                
                # Update restock request status
                restock_request.status = 'completed'
                restock_request.save()
                
                # Create notification for admin
                Notification.objects.create(
                    recipient=User.objects.filter(is_staff=True).first(),
                    type='stock_update',
                    title='Stock Updated',
                    message=f'Supplier has updated stock for {product.name}. Added {stock_quantity} units.'
                )
                
                messages.success(request, f'Successfully updated stock for {product.name}')
            else:
                messages.error(request, 'Please enter a valid quantity')
        
        elif action == 'reject':
            restock_request.status = 'rejected'
            restock_request.save()
            
            # Create notification for admin
            Notification.objects.create(
                recipient=User.objects.filter(is_staff=True).first(),
                type='stock_update',
                title='Restock Request Rejected',
                message=f'Supplier has rejected restock request for {restock_request.product.name}'
            )
            
            messages.info(request, f'Restock request for {restock_request.product.name} has been rejected')
    
    context = {
        'restock_requests': restock_requests,
        'title': 'Restock Requests'
    }
    return render(request, 'store/supplier/restock_requests.html', context)

@login_required
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(Notification, id=notification_id, recipient=request.user)
    notification.read = True
    notification.save()
    return JsonResponse({'status': 'success'})

@user_passes_test(is_supplier)
def supplier_products(request):
    supplier = request.user.supplier
    products = Product.objects.filter(supplier=supplier).select_related('category')
    
    # Add pending requests count to each product
    for product in products:
        product.pending_requests_count = product.restock_requests.filter(status='pending').count()
    
    context = {
        'products': products,
        'title': 'Manage Stock',
    }
    return render(request, 'store/supplier/products.html', context)

@login_required
@user_passes_test(is_supplier)
def update_stock(request, product_id):
    if request.method == 'POST':
        try:
            product = get_object_or_404(Product, id=product_id, supplier=request.user.supplier)
            quantity = request.POST.get('quantity')
            
            if quantity is not None:
                try:
                    quantity = int(quantity)
                    if quantity >= 0:
                        product.stock = quantity
                        product.save()
                        messages.success(request, f'Stock updated successfully for {product.name}')
                    else:
                        messages.error(request, 'Stock quantity cannot be negative')
                except ValueError:
                    messages.error(request, 'Please enter a valid number for stock quantity')
            else:
                messages.error(request, 'Stock quantity is required')
        except Product.DoesNotExist:
            messages.error(request, 'Product not found')
        except Exception as e:
            messages.error(request, f'Error updating stock: {str(e)}')
    
    return redirect('supplier_products')

def category_products(request, category_slug):
    category = get_object_or_404(Category, slug=category_slug)
    products = Product.objects.filter(category=category, is_available=True)
    context = {
        'category': category,
        'products': products,
    }
    return render(request, 'store/category_products.html', context)

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

def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Create user profile
            UserProfile.objects.create(
                user=user,
                phone=form.cleaned_data.get('phone', ''),
                address=form.cleaned_data.get('address', '')
            )
            messages.success(request, 'Registration successful! Please login.')
            return redirect('login')
    else:
        form = UserRegistrationForm()
    
    return render(request, 'store/register.html', {'form': form})

@login_required
def profile(request):
    # Get or create user profile
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        user_form = UserRegistrationForm(request.POST, instance=request.user)
        profile_form = UserProfileForm(request.POST, request.FILES, instance=profile)
        
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, 'Your profile has been updated.')
            return redirect('profile')
    else:
        user_form = UserRegistrationForm(instance=request.user)
        profile_form = UserProfileForm(instance=profile)
    
    # Get user's orders with related items
    orders = Order.objects.filter(user=request.user).prefetch_related(
        'items', 'items__product'
    ).order_by('-created_at')
    
    context = {
        'user_form': user_form,
        'profile_form': profile_form,
        'orders': orders,
        'title': 'My Profile'
    }
    return render(request, 'store/profile.html', context)

@login_required
@user_passes_test(is_admin)
def send_restock_request(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    
    if request.method == 'POST':
        # Check if there's already a pending restock request
        if RestockRequest.objects.filter(product=product, status='pending').exists():
            messages.warning(request, f'A restock request is already pending for {product.name}')
            return redirect('admin_products')
        
        if not product.supplier:
            messages.error(request, f'Cannot send restock request: No supplier assigned to {product.name}')
            return redirect('admin_products')
        
        quantity = int(request.POST.get('quantity', 10))
        
        restock_request = RestockRequest.objects.create(
            product=product,
            supplier=product.supplier,
            quantity=quantity,
            notes=f"Stock level is low ({product.stock} units). Please restock."
        )
        
        # Create notification for supplier
        Notification.objects.create(
            recipient=product.supplier.user,
            type='restock_request',
            title=f'New Restock Request for {product.name}',
            message=f'Stock level is low ({product.stock} units). Please review the restock request.'
        )
        
        messages.success(request, f'Restock request sent for {product.name}')
        return redirect('admin_products')
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
@user_passes_test(is_supplier)
def update_stock(request, product_id):
    if request.method == 'POST':
        try:
            product = get_object_or_404(Product, id=product_id, supplier=request.user.supplier)
            quantity = request.POST.get('quantity')
            
            if quantity is not None:
                try:
                    quantity = int(quantity)
                    if quantity >= 0:
                        product.stock = quantity
                        product.save()
                        messages.success(request, f'Stock updated successfully for {product.name}')
                    else:
                        messages.error(request, 'Stock quantity cannot be negative')
                except ValueError:
                    messages.error(request, 'Please enter a valid number for stock quantity')
            else:
                messages.error(request, 'Stock quantity is required')
        except Product.DoesNotExist:
            messages.error(request, 'Product not found')
        except Exception as e:
            messages.error(request, f'Error updating stock: {str(e)}')
    
    return redirect('supplier_products')

@login_required
@user_passes_test(is_admin)
def send_supplier_message(request, supplier_id):
    if request.method == 'POST':
        supplier = get_object_or_404(Supplier, id=supplier_id)
        message_content = request.POST.get('message')
        
        if message_content:
            SupplierMessage.objects.create(
                supplier=supplier,
                content=message_content,
                is_from_admin=True
            )
            
            # Create notification for supplier
            Notification.objects.create(
                recipient=supplier.user,
                type='message',
                title='New Message from Admin',
                message=f'You have received a new message from the admin.'
            )
            
            return JsonResponse({'success': True})
    return JsonResponse({'success': False})

@login_required
@user_passes_test(is_supplier)
def supplier_products(request):
    supplier = request.user.supplier
    products = Product.objects.filter(supplier=supplier).select_related('category')
    
    # Add pending requests count to each product
    for product in products:
        product.pending_requests_count = product.restock_requests.filter(status='pending').count()
    
    context = {
        'products': products,
        'title': 'Manage Stock',
    }
    return render(request, 'store/supplier/products.html', context)

def test_email(request):
    try:
        send_mail(
            'Test Email from Fresh Mart',
            'This is a test email to verify email settings.',
            settings.DEFAULT_FROM_EMAIL,
            [request.user.email],
            fail_silently=False,
        )
        return HttpResponse("Test email sent successfully! Check your inbox.")
    except Exception as e:
        return HttpResponse(f"Error sending email: {str(e)}")

@login_required
def apply_coupon(request):
    if request.method == 'POST':
        coupon_code = request.POST.get('coupon_code')
        cart = Cart.objects.filter(user=request.user).first()
        
        if not cart:
            messages.error(request, 'No active cart found.')
            return redirect('cart')
            
        try:
            # Validate coupon and apply discount
            coupon = Coupon.objects.get(
                code=coupon_code,
                is_active=True,
                valid_from__lte=timezone.now(),
                valid_to__gte=timezone.now()
            )
            
            # Apply discount to cart
            cart.discount = coupon.discount_amount
            cart.coupon = coupon
            cart.save()
            
            messages.success(request, f'Coupon applied successfully! You got ₹{coupon.discount_amount} off.')
            
        except Coupon.DoesNotExist:
            messages.error(request, 'Invalid or expired coupon code.')
        
        return redirect('cart')
    
    return redirect('cart')

def create_customer_coupon(user_id, total_spend):
    """Create a new coupon for the customer based on their spend"""
    user = User.objects.get(id=user_id)
    
    # Calculate discount (10% of spend, max ₹500)
    discount = min(total_spend * Decimal('0.10'), Decimal('500'))
    
    # Generate unique coupon code
    code = f"REWARD{user.id}{timezone.now().strftime('%m%y')}"
    
    # Set validity for 30 days
    valid_from = timezone.now()
    valid_to = valid_from + timedelta(days=30)

    # Create and return the coupon
    coupon = Coupon.objects.create(
        code=code,
        user=user,
        discount_amount=discount,
        valid_from=valid_from,
        valid_to=valid_to,
        is_active=True,
        minimum_spend=Decimal('100')  # Minimum spend to use coupon
    )
    return coupon

def send_reward_email(email, username, coupon, total_spend):
    """Send reward coupon email to customer"""
    subject = 'Your Fresh Mart Reward Coupon!'
    html_content = render_to_string('store/emails/reward_coupon_email.html', {
        'username': username,
        'coupon_code': coupon.code,
        'discount_amount': coupon.discount_amount,
        'valid_until': coupon.valid_to,
        'total_spend': total_spend
    })
    
    msg = EmailMessage(subject, html_content, settings.DEFAULT_FROM_EMAIL, [email])
    msg.content_subtype = "html"
    msg.send()
    print(f"Reward coupon email sent to {email}")  # Debug log

@login_required
@user_passes_test(is_supplier)
def request_restock(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id, supplier=request.user.supplier)
        
        if product.stock <= product.reorder_level:
            # Create restock request
            restock_request = RestockRequest.objects.create(
                product=product,
                supplier=request.user.supplier,
                quantity=max(product.reorder_level * 2 - product.stock, 10),  # Order enough to get above reorder level
                status='pending'
            )
            
            # Create notification for admin
            Notification.objects.create(
                recipient=User.objects.filter(is_staff=True).first(),
                type='restock_request',
                title=f'Restock Request for {product.name}',
                message=f'Supplier has requested restock for {product.name}. Current stock: {product.stock}'
            )
            
            messages.success(request, f'Restock request sent for {product.name}')
        else:
            messages.error(request, 'Product stock is above reorder level')
            
    return redirect('supplier_products')

@login_required
@user_passes_test(is_supplier)
def update_restock_request(request, request_id):
    restock_request = get_object_or_404(RestockRequest, id=request_id, supplier=request.user.supplier)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'complete':
            # Update restock request status
            restock_request.status = 'completed'
            restock_request.save()
            
            # Update product stock
            product = restock_request.product
            product.stock += restock_request.quantity
            product.save()
            
            # Create notification for admin
            Notification.objects.create(
                recipient=User.objects.filter(is_staff=True).first(),
                type='stock_update',
                title=f'Restock Request Completed - {product.name}',
                message=f'Supplier {request.user.supplier.name} has completed the restock request for {product.name}. New stock level: {product.stock}'
            )
            
            # Record supplier activity
            SupplierActivity.objects.create(
                supplier=request.user.supplier,
                description=f'Completed restock request for {product.name} (Added {restock_request.quantity} units)'
            )
            
            messages.success(request, f'Successfully restocked {product.name}. New stock level: {product.stock}')
            
        elif action == 'reject':
            restock_request.status = 'rejected'
            restock_request.save()
            
            # Create notification for admin
            Notification.objects.create(
                recipient=User.objects.filter(is_staff=True).first(),
                type='stock_update',
                title=f'Restock Request Rejected - {restock_request.product.name}',
                message=f'Supplier {request.user.supplier.name} has rejected the restock request for {restock_request.product.name}.'
            )
            
            # Record supplier activity
            SupplierActivity.objects.create(
                supplier=request.user.supplier,
                description=f'Rejected restock request for {restock_request.product.name}'
            )
            
            messages.warning(request, f'Restock request for {restock_request.product.name} has been rejected.')
    
    return redirect('supplier_restock_requests')

import stripe
import json
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse

stripe.api_key = settings.STRIPE_SECRET_KEY

@login_required
def payment_page(request):
    try:
        cart = Cart.objects.get(user=request.user)
        if not cart.items.exists():
            messages.error(request, 'Your cart is empty')
            return redirect('cart')
        
        # Get the actual total from cart
        total = cart.get_total()
        
        context = {
            'stripe_publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
            'total': total,
            'cart': cart
        }
        return render(request, 'store/payments.html', context)
    except Cart.DoesNotExist:
        messages.error(request, 'Your cart is empty')
        return redirect('cart')

@csrf_exempt
@login_required
def process_payment(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=400)
    
    try:
        # Parse the request data
        data = json.loads(request.body)
        token = data.get('token')
        amount = data.get('amount')
        
        if not token:
            return JsonResponse({'error': 'Payment token is required'}, status=400)
        
        # Get cart and verify amount
        try:
            cart = Cart.objects.get(user=request.user)
            cart_total = str(cart.get_total())
            
            # Compare the amounts as strings with 2 decimal places
            if format(float(amount), '.2f') != format(float(cart_total), '.2f'):
                return JsonResponse({
                    'error': f'Payment amount mismatch. Expected: {cart_total}, Got: {amount}'
                }, status=400)
            
            # Convert amount to cents for Stripe
            amount_in_cents = int(float(amount) * 100)
            
            try:
                # Create the charge on Stripe
                charge = stripe.Charge.create(
                    amount=amount_in_cents,
                    currency='inr',
                    source=token,
                    description=f'Order for {request.user.email}'
                )
                
                # Create order with minimal required fields
                order = Order.objects.create(
                    user=request.user,
                    name=request.user.get_full_name() or request.user.username,
                    email=request.user.email,
                    phone=request.user.userprofile.phone if hasattr(request.user, 'userprofile') else '',
                    address='',  # Will be updated in checkout
                    city='',     # Will be updated in checkout
                    postal_code='', # Will be updated in checkout
                    payment_method='card',
                    payment_status='completed',
                    total_amount=cart_total,
                    stripe_charge_id=charge.id
                )
                
                # Create order items and update stock
                for cart_item in cart.items.all():
                    OrderItem.objects.create(
                        order=order,
                        product=cart_item.product,
                        quantity=cart_item.quantity,
                        price=cart_item.product.price
                    )
                    
                    # Update product stock
                    product = cart_item.product
                    product.stock -= cart_item.quantity
                    product.save()
                
                # Clear the cart after successful order
                cart.delete()
                
                # Send confirmation email
                send_order_confirmation(order)  # Fixed: only pass the order object
                
                return JsonResponse({
                    'success': True,
                    'redirect_url': reverse('order_confirmation', args=[order.id])
                })
                
            except stripe.error.CardError as e:
                return JsonResponse({'error': e.error.message}, status=400)
            except stripe.error.StripeError as e:
                print(f"Stripe error: {str(e)}")  # Log the error
                return JsonResponse({'error': 'Payment processing failed'}, status=400)
                
        except Cart.DoesNotExist:
            return JsonResponse({'error': 'Cart not found'}, status=400)
            
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        print(f"Unexpected error: {str(e)}")  # Log the error
        return JsonResponse({'error': 'An unexpected error occurred'}, status=500)

# Update the checkout view
@login_required
def checkout(request):
    cart = Cart.objects.filter(user=request.user).first()
    if not cart or not cart.items.exists():
        messages.warning(request, 'Your cart is empty')
        return redirect('cart')
        
    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            # Store shipping details in session
            request.session['shipping_details'] = form.cleaned_data
            return redirect('payment')
    else:
        form = OrderForm()
        
    context = {
        'form': form,
        'cart': cart,
        'total': cart.get_total() if cart else 0
    }
    return render(request, 'store/checkout.html', context)

@login_required
@user_passes_test(is_admin)
def low_stock_management(request):
    # Get all products with stock level at or below reorder level
    low_stock_products = Product.objects.filter(
        stock__lte=3  # Using 3 as the reorder level
    ).select_related('category', 'supplier')
    
    context = {
        'low_stock_products': low_stock_products,
        'title': 'Low Stock Management'
    }
    return render(request, 'store/admin/low_stock_management.html', context)

@login_required
@user_passes_test(is_admin)
def admin_orders(request):
    if not request.user.is_superuser:
        return redirect('home')
        
    status_filter = request.GET.get('status', 'all')
    orders = Order.objects.select_related('user').order_by('-created_at')
    
    if status_filter != 'all':
        orders = orders.filter(status=status_filter)
    
    context = {
        'orders': orders,
        'current_status': status_filter
    }
    
    return render(request, 'store/admin/orders.html', context)

@login_required
@user_passes_test(is_admin)
def admin_view_order_details(request, order_id):
    order = get_object_or_404(Order.objects.select_related('user'), id=order_id)
    order_items = OrderItem.objects.filter(order=order).select_related('product')
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('store/admin/order_details_modal.html', {
            'order': order,
            'order_items': order_items
        })
        return JsonResponse({'html': html})
    
    context = {
        'order': order,
        'order_items': order_items
    }
    return render(request, 'store/admin/order_details.html', context)

@login_required
@user_passes_test(is_admin)
def update_order_status(request, order_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            status = data.get('status')
            
            order = Order.objects.get(id=order_id)
            
            if status not in [s[0] for s in Order.STATUS_CHOICES]:
                return JsonResponse({'success': False, 'error': 'Invalid status'})
            
            order.status = status
            order.save()
            
            # Send notification to customer
            Notification.objects.create(
                recipient=order.user,
                type='order_status',
                title=f'Order #{order.id} Status Updated',
                message=f'Your order status has been updated to: {status.title()}'
            )
            
            return JsonResponse({'success': True})
        except Order.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Order not found'})
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
            
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

# Delivery Boy Views
@login_required
def delivery_boy_dashboard(request):
    if not hasattr(request.user, 'deliveryboy'):
        return redirect('home')
    
    delivery_boy = request.user.deliveryboy
    current_assignments = DeliveryAssignment.objects.filter(
        delivery_boy=delivery_boy,
        status__in=['assigned', 'picked_up', 'in_transit']
    ).select_related('order')
    
    completed_deliveries = DeliveryAssignment.objects.filter(
        delivery_boy=delivery_boy,
        status='delivered'
    ).select_related('order').order_by('-delivered_at')[:10]
    
    today = timezone.now().date()
    today_report = DeliveryBoyReport.objects.filter(
        delivery_boy=delivery_boy,
        date=today
    ).first()
    
    username = request.user.username
    
    context = {
        'delivery_boy': delivery_boy,
        'username':username,
        'current_assignments': current_assignments,
        'completed_deliveries': completed_deliveries,
        'today_report': today_report
    }
    return render(request, 'store/delivery/dashboard.html', context)

@login_required
def update_delivery_status(request, assignment_id):
    if not hasattr(request.user, 'deliveryboy'):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    assignment = get_object_or_404(DeliveryAssignment, id=assignment_id, delivery_boy=request.user.deliveryboy)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        notes = request.POST.get('notes', '')
        
        if new_status in dict(DeliveryAssignment.STATUS_CHOICES):
            old_status = assignment.status
            assignment.status = new_status
            
            # Status-specific updates
            if new_status == 'picked_up':
                assignment.picked_up_at = timezone.now()
                customer_msg = f'Your order #{assignment.order.id} has been picked up by {assignment.delivery_boy.name}'
                admin_msg = f'Order #{assignment.order.id} picked up by {assignment.delivery_boy.name}'
            
            elif new_status == 'in_transit':
                customer_msg = f'Your order #{assignment.order.id} is on the way!'
                admin_msg = f'Order #{assignment.order.id} is in transit'
                
            elif new_status == 'delivered':
                assignment.delivered_at = timezone.now()
                assignment.delivery_boy.total_deliveries += 1
                assignment.delivery_boy.save()
                
                # Update order status
                assignment.order.status = 'delivered'
                assignment.order.save()
                
                # Update daily report
                report, _ = DeliveryBoyReport.objects.get_or_create(
                    delivery_boy=assignment.delivery_boy,
                    date=timezone.now().date()
                )
                report.orders_delivered += 1
                report.save()
                
                customer_msg = f'Your order #{assignment.order.id} has been delivered!'
                admin_msg = f'Order #{assignment.order.id} delivered by {assignment.delivery_boy.name}'
            
            else:
                customer_msg = f'Your order #{assignment.order.id} status has been updated to {new_status}'
                admin_msg = f'Order #{assignment.order.id} status updated to {new_status}'
            
            # Add notes if provided
            if notes:
                customer_msg += f'\nNote: {notes}'
                admin_msg += f'\nNote: {notes}'
            
            # Create notifications
            # For customer
            Notification.objects.create(
                recipient=assignment.order.user,
                type='order_status',
                title=f'Order #{assignment.order.id} Update',
                message=customer_msg
            )
            
            # For admin
            admin_users = User.objects.filter(is_superuser=True)
            for admin in admin_users:
                Notification.objects.create(
                    recipient=admin,
                    type='delivery_status',
                    title=f'Delivery Status Update',
                    message=admin_msg
                )
            
            assignment.save()
            
            return JsonResponse({
                'success': True,
                'message': f'Status updated to {new_status}',
                'customerNotified': True,
                'adminNotified': True
            })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

# Admin Delivery Management Views
@user_passes_test(lambda u: u.is_superuser)
def admin_delivery_management(request):
    view = request.GET.get('view', 'all')
    
    # Base querysets
    delivery_boys = DeliveryBoy.objects.all()
    pending_orders = Order.objects.filter(status='pending', delivery_assignment__isnull=True)
    active_deliveries = DeliveryAssignment.objects.filter(
        status__in=['assigned', 'picked_up', 'in_transit']
    ).select_related('delivery_boy', 'order')
    
    context = {
        'view': view,
        'delivery_boys': delivery_boys
    }
    
    if view == 'pending':
        # Show pending approval delivery boys
        context['pending_delivery_boys'] = delivery_boys.filter(is_approved=False)
        return render(request, 'store/admin/delivery_management_pending.html', context)
    
    elif view == 'active':
        # Show active deliveries
        context['active_deliveries'] = active_deliveries
        context['pending_orders'] = pending_orders
        return render(request, 'store/admin/delivery_management_active.html', context)
    
    else:
        # Show all delivery boys and their stats
        context.update({
            'approved_delivery_boys': delivery_boys.filter(is_approved=True),
            'pending_delivery_boys': delivery_boys.filter(is_approved=False),
            'active_deliveries': active_deliveries,
            'pending_orders': pending_orders
        })
        return render(request, 'store/admin/delivery_management.html', context)

@user_passes_test(lambda u: u.is_superuser)
def manage_delivery_boy(request, action, delivery_boy_id=None):
    if action == 'approve':
        delivery_boy = get_object_or_404(DeliveryBoy, id=delivery_boy_id)
        delivery_boy.is_approved = True
        delivery_boy.save()
        messages.success(request, f'Delivery boy {delivery_boy.name} has been approved')
    
    elif action == 'remove':
        delivery_boy = get_object_or_404(DeliveryBoy, id=delivery_boy_id)
        delivery_boy.user.delete()  # This will cascade delete the delivery boy profile
        messages.success(request, 'Delivery boy has been removed')
    
    return redirect('admin_delivery_management')

@user_passes_test(lambda u: u.is_superuser)
def assign_delivery(request):
    if request.method == 'POST':
        try:
            order_id = request.POST.get('order_id')
            delivery_boy_id = request.POST.get('delivery_boy_id')
            
            # Validate input
            if not order_id or not delivery_boy_id:
                return JsonResponse({
                    'success': False,
                    'error': 'Missing required fields'
                }, status=400)
            
            # Get order and delivery boy
            order = get_object_or_404(Order, id=order_id)
            delivery_boy = get_object_or_404(DeliveryBoy, id=delivery_boy_id)
            
            # Validate order status
            if order.status != 'pending':
                return JsonResponse({
                    'success': False,
                    'error': f'Order #{order.id} cannot be assigned (status: {order.status})'
                }, status=400)
            
            # Validate delivery boy
            if not delivery_boy.is_approved:
                return JsonResponse({
                    'success': False,
                    'error': f'{delivery_boy.name} is not approved for deliveries'
                }, status=400)
            
            if not delivery_boy.is_available:
                return JsonResponse({
                    'success': False,
                    'error': f'{delivery_boy.name} is not available'
                }, status=400)
            
            # Check if order already has an assignment
            if DeliveryAssignment.objects.filter(order=order).exists():
                return JsonResponse({
                    'success': False,
                    'error': f'Order #{order.id} already has a delivery assignment'
                }, status=400)
            
            # Create delivery assignment
            assignment = DeliveryAssignment.objects.create(
                order=order,
                delivery_boy=delivery_boy,
                status='assigned',
                assigned_at=timezone.now()
            )
            
            # Update order status
            order.status = 'shipped'
            order.save()
            
            # Create notification for delivery boy
            Notification.objects.create(
                recipient=delivery_boy.user,
                type='new_assignment',
                title='New Delivery Assignment',
                message=f'You have been assigned to deliver Order #{order.id} to {order.name}\nDelivery Address: {order.address}'
            )
            
            # Create notification for customer
            Notification.objects.create(
                recipient=order.user,
                type='order_status',
                title='Order Update',
                message=f'Your order #{order.id} has been assigned to our delivery partner {delivery_boy.name}'
            )
            
            messages.success(request, f'Order #{order.id} assigned to {delivery_boy.name}')
            
            return JsonResponse({
                'success': True,
                'message': f'Order #{order.id} successfully assigned to {delivery_boy.name}',
                'assignment': {
                    'id': assignment.id,
                    'status': assignment.status,
                    'assigned_at': assignment.assigned_at.strftime('%Y-%m-%d %H:%M:%S')
                }
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)

@user_passes_test(lambda u: u.is_superuser)
def delivery_boy_performance(request, delivery_boy_id):
    delivery_boy = get_object_or_404(DeliveryBoy, id=delivery_boy_id)
    reports = DeliveryBoyReport.objects.filter(delivery_boy=delivery_boy).order_by('-date')[:30]
    
    total_deliveries = delivery_boy.total_deliveries
    recent_deliveries = DeliveryAssignment.objects.filter(
        delivery_boy=delivery_boy,
        status='delivered'
    ).select_related('order').order_by('-delivered_at')[:20]
    
    context = {
        'delivery_boy': delivery_boy,
        'reports': reports,
        'total_deliveries': total_deliveries,
        'recent_deliveries': recent_deliveries
    }
    return render(request, 'store/admin/delivery_boy_performance.html', context)

@login_required
def toggle_availability(request):
    if not hasattr(request.user, 'deliveryboy'):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    delivery_boy = request.user.deliveryboy
    delivery_boy.is_available = not delivery_boy.is_available
    delivery_boy.save()
    
    return JsonResponse({
        'success': True,
        'is_available': delivery_boy.is_available
    })

def register_delivery_boy(request):
    if request.method == 'POST':
        form = DeliveryBoyRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            DeliveryBoy.objects.create(
                user=user,
                name=form.cleaned_data['name'],
                phone=form.cleaned_data['phone'],
                address=form.cleaned_data['address']
            )
            messages.success(request, 'Registration successful! Please wait for admin approval.')
            return redirect('login')
    else:
        form = DeliveryBoyRegistrationForm()
    return render(request, 'store/delivery/register.html', {'form': form})

@login_required
def delivery_chat(request, order_id):
    # Get the order and verify permissions
    if hasattr(request.user, 'deliveryboy'):
        # Delivery boy accessing the chat
        delivery_boy = request.user.deliveryboy
        order = get_object_or_404(Order, delivery_assignment__delivery_boy=delivery_boy, id=order_id)
        is_delivery_boy = True
    else:
        # Customer accessing the chat
        order = get_object_or_404(Order, user=request.user, id=order_id)
        is_delivery_boy = False

    if not order.delivery_assignment:
        return HttpResponseForbidden("Chat is only available after delivery assignment")

    # Handle message submission
    if request.method == 'POST':
        message = request.POST.get('message')
        is_quick_message = request.POST.get('is_quick_message') == 'true'
        
        if message:
            DeliveryChat.objects.create(
                order=order,
                customer=order.user,
                delivery_boy=order.delivery_assignment.delivery_boy,
                message=message,
                is_from_customer=not is_delivery_boy,
                is_quick_message=is_quick_message
            )

    # Get messages and mark them as read
    messages = DeliveryChat.objects.filter(order=order).order_by('created_at')
    
    # Mark messages as read based on who's viewing
    if is_delivery_boy:
        # Mark customer messages as read when delivery boy views them
        messages.filter(is_from_customer=True, is_read=False).update(is_read=True)
    else:
        # Mark delivery boy messages as read when customer views them
        messages.filter(is_from_customer=False, is_read=False).update(is_read=True)

    # Get appropriate quick messages based on user type
    quick_messages = QuickMessage.objects.filter(is_for_customer=not is_delivery_boy)

    # For HTMX requests, only return the messages partial
    if request.headers.get('HX-Request'):
        return render(request, 'store/partials/chat_messages.html', {
            'messages': messages,
            'is_delivery_boy': is_delivery_boy
        })

    return render(request, 'store/delivery_chat.html', {
        'order': order,
        'messages': messages,
        'quick_messages': quick_messages,
        'is_delivery_boy': is_delivery_boy
    })

@login_required
def get_unread_chat_count(request):
    if hasattr(request.user, 'deliveryboy'):
        count = DeliveryChat.objects.filter(
            delivery_assignment__delivery_boy=request.user.deliveryboy,
            is_read=False
        ).exclude(sender=request.user).count()
    else:
        count = DeliveryChat.objects.filter(
            customer=request.user,
            is_read=False
        ).exclude(sender=request.user).count()
    return JsonResponse({'count': count})

@login_required
def delivery_dashboard(request):
    try:
        delivery_boy = DeliveryBoy.objects.get(user=request.user)
        delivery_assignments = DeliveryAssignment.objects.filter(delivery_boy=delivery_boy)
        
        # Get counts for dashboard
        pending_count = delivery_assignments.filter(status='assigned').count()
        active_count = delivery_assignments.filter(status__in=['picked_up', 'in_transit']).count()
        completed_count = delivery_assignments.filter(status='delivered').count()
        
        # Get unread message count
        unread_messages = DeliveryChat.objects.filter(
            delivery_boy=delivery_boy,
            is_read=False,
            is_from_customer=True  # Only count messages from customers
        ).count()
        
        context = {
            'delivery_boy': delivery_boy,
            'delivery_assignments': delivery_assignments.order_by('-assigned_at')[:5],  # Show last 5 assignments
            'pending_count': pending_count,
            'active_count': active_count,
            'completed_count': completed_count,
            'unread_messages': unread_messages,
        }
        return render(request, 'store/delivery/dashboard.html', context)
    except DeliveryBoy.DoesNotExist:
        messages.error(request, 'You are not authorized to access this page.')
        return redirect('home')

@login_required
def update_delivery_status(request, order_id):
    if not hasattr(request.user, 'deliveryboy'):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)
    
    delivery_boy = request.user.deliveryboy
    assignment = get_object_or_404(
        DeliveryAssignment,
        order_id=order_id,
        delivery_boy=delivery_boy
    )
    
    status = request.POST.get('status')
    if status not in ['pending', 'in_progress', 'delivered', 'failed']:
        return JsonResponse({'error': 'Invalid status'}, status=400)
    
    assignment.status = status
    assignment.save()
    
    # If delivered, update order status and create a chat message
    if status == 'delivered':
        assignment.order.status = 'delivered'
        assignment.order.save()
        
        # Create system message for delivery confirmation
        DeliveryChat.objects.create(
            order=assignment.order,
            customer=assignment.order.user,
            delivery_boy=delivery_boy,
            message="Order has been delivered successfully!",
            is_from_customer=False,
            is_system_message=True
        )
    
    return JsonResponse({
        'status': 'success',
        'new_status': assignment.get_status_display()
    })

@login_required
def delivery_chat(request, order_id):
    # Get the order and verify permissions
    if hasattr(request.user, 'deliveryboy'):
        # Delivery boy accessing the chat
        delivery_boy = request.user.deliveryboy
        order = get_object_or_404(Order, delivery_assignment__delivery_boy=delivery_boy, id=order_id)
        is_delivery_boy = True
    else:
        # Customer accessing the chat
        order = get_object_or_404(Order, user=request.user, id=order_id)
        is_delivery_boy = False

    if not order.delivery_assignment:
        return HttpResponseForbidden("Chat is only available after delivery assignment")

    # Handle message submission
    if request.method == 'POST':
        message = request.POST.get('message')
        is_quick_message = request.POST.get('is_quick_message') == 'true'
        
        if message:
            DeliveryChat.objects.create(
                order=order,
                customer=order.user,
                delivery_boy=order.delivery_assignment.delivery_boy,
                message=message,
                is_from_customer=not is_delivery_boy,
                is_quick_message=is_quick_message
            )

    # Get messages and mark them as read
    messages = DeliveryChat.objects.filter(order=order).order_by('created_at')
    
    # Mark messages as read based on who's viewing
    if is_delivery_boy:
        # Mark customer messages as read when delivery boy views them
        messages.filter(is_from_customer=True, is_read=False).update(is_read=True)
    else:
        # Mark delivery boy messages as read when customer views them
        messages.filter(is_from_customer=False, is_read=False).update(is_read=True)

    # Get appropriate quick messages based on user type
    quick_messages = QuickMessage.objects.filter(is_for_customer=not is_delivery_boy)

    # For HTMX requests, only return the messages partial
    if request.headers.get('HX-Request'):
        return render(request, 'store/partials/chat_messages.html', {
            'messages': messages,
            'is_delivery_boy': is_delivery_boy
        })

    return render(request, 'store/delivery_chat.html', {
        'order': order,
        'messages': messages,
        'quick_messages': quick_messages,
        'is_delivery_boy': is_delivery_boy
    })

@login_required
@user_passes_test(is_admin)
def admin_monthly_sales_report(request):
    if not request.user.is_staff:
        return redirect('home')
    
    # Get the current date and first day of the month
    today = timezone.now()
    first_day = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Get all orders for the current month
    monthly_orders = Order.objects.filter(
        created_at__gte=first_day,
        created_at__lte=today,
        status='delivered'  # Only count delivered orders
    )
    
    # Calculate total sales
    total_sales = monthly_orders.aggregate(
        total_amount=Sum('total_amount'),
        total_orders=Count('id')
    )
    
    # Get sales by category
    category_sales = OrderItem.objects.filter(
        order__in=monthly_orders
    ).values(
        'product__category__name'
    ).annotate(
        total_sales=Sum(F('quantity') * F('price')),
        items_sold=Sum('quantity')
    ).order_by('-total_sales')
    
    # Get top selling products
    top_products = OrderItem.objects.filter(
        order__in=monthly_orders
    ).values(
        'product__name'
    ).annotate(
        total_sales=Sum(F('quantity') * F('price')),
        items_sold=Sum('quantity')
    ).order_by('-items_sold')[:5]
    
    context = {
        'total_sales': total_sales,
        'category_sales': category_sales,
        'top_products': top_products,
        'month': today.strftime('%B %Y')
    }
    
    return render(request, 'store/admin/monthly_sales_report.html', context)

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

@login_required
@user_passes_test(is_admin)
def download_monthly_sales_report(request):
    # Get the current date and first day of the month
    today = timezone.now()
    first_day = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Get all orders for the current month
    monthly_orders = Order.objects.filter(
        created_at__gte=first_day,
        created_at__lte=today,
        status='delivered'
    )
    
    # Calculate total sales
    total_sales = monthly_orders.aggregate(
        total_amount=Sum('total_amount'),
        total_orders=Count('id')
    )
    
    # Get sales by category
    category_sales = OrderItem.objects.filter(
        order__in=monthly_orders
    ).values(
        'product__category__name'
    ).annotate(
        total_sales=Sum(F('quantity') * F('price')),
        items_sold=Sum('quantity')
    ).order_by('-total_sales')
    
    # Get top selling products
    top_products = OrderItem.objects.filter(
        order__in=monthly_orders
    ).values(
        'product__name'
    ).annotate(
        total_sales=Sum(F('quantity') * F('price')),
        items_sold=Sum('quantity')
    ).order_by('-items_sold')[:5]
    
    # Create the PDF
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="monthly_sales_report_{today.strftime("%B_%Y")}.pdf"'
    
    # Create the PDF document
    doc = SimpleDocTemplate(response, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30
    )
    elements.append(Paragraph(f'Monthly Sales Report - {today.strftime("%B %Y")}', title_style))
    elements.append(Spacer(1, 20))
    
    # Summary Statistics
    elements.append(Paragraph('Summary Statistics', styles['Heading2']))
    elements.append(Spacer(1, 12))
    summary_data = [
        ['Total Sales', f'₹{total_sales["total_amount"] or 0:,.2f}'],
        ['Total Orders', str(total_sales["total_orders"] or 0)]
    ]
    summary_table = Table(summary_data, colWidths=[2*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))
    
    # Category Sales
    elements.append(Paragraph('Sales by Category', styles['Heading2']))
    elements.append(Spacer(1, 12))
    category_data = [['Category', 'Items Sold', 'Total Sales']]
    for category in category_sales:
        category_data.append([
            category['product__category__name'],
            str(category['items_sold']),
            f'₹{category["total_sales"]:,.2f}'
        ])
    category_table = Table(category_data, colWidths=[2.5*inch, 2*inch, 2*inch])
    category_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT')
    ]))
    elements.append(category_table)
    elements.append(Spacer(1, 20))
    
    # Top Products
    elements.append(Paragraph('Top Selling Products', styles['Heading2']))
    elements.append(Spacer(1, 12))
    products_data = [['Product', 'Items Sold', 'Total Sales']]
    for product in top_products:
        products_data.append([
            product['product__name'],
            str(product['items_sold']),
            f'₹{product["total_sales"]:,.2f}'
        ])
    products_table = Table(products_data, colWidths=[2.5*inch, 2*inch, 2*inch])
    products_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT')
    ]))
    elements.append(products_table)
    
    # Generate PDF
    doc.build(elements)
    return response

@login_required
@user_passes_test(is_admin)
def admin_messages(request):
    # Get all suppliers with messages
    messages = SupplierMessage.objects.all().order_by('created_at')
    
    # Group messages by supplier
    supplier_messages = {}
    for message in messages:
        if message.supplier not in supplier_messages:
            supplier_messages[message.supplier] = []
        supplier_messages[message.supplier].append(message)
    
    # Mark all messages as read
    messages.filter(read=False, is_from_admin=False).update(read=True)
    
    return render(request, 'store/admin/messages.html', {
        'supplier_messages': supplier_messages,
        'messages': messages,
        'section': 'messages'
    })

@login_required
@user_passes_test(is_supplier)
def supplier_messages(request):
    supplier = request.user.supplier
    message_list = SupplierMessage.objects.filter(supplier=supplier).order_by('created_at')
    
    if request.method == 'POST':
        content = request.POST.get('message')
        if content:
            # Create supplier's reply
            SupplierMessage.objects.create(
                supplier=supplier,
                content=content,
                is_from_admin=False
            )
            messages.success(request, 'Message sent successfully')
            return redirect('supplier_messages')
    
    # Mark all unread messages as read
    message_list.filter(read=False).update(read=True)
    
    return render(request, 'store/supplier/messages.html', {
        'messages': message_list
    })

def search(request):
    query = request.GET.get('q', '')
    if query:
        products = Product.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query)
        ).distinct()
    else:
        products = Product.objects.none()
    
    context = {
        'query': query,
        'products': products,
    }
    return render(request, 'store/search_results.html', context)

def supplier_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Check if the user is a supplier
            try:
                supplier = Supplier.objects.get(user=user)
                if not supplier.is_approved:
                    messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
                    return render(request, 'store/supplier/login.html')
                login(request, user)
                return redirect('supplier_dashboard')
            except Supplier.DoesNotExist:
                messages.error(request, 'This login is only for suppliers.')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/supplier/login.html')

def supplier_register(request):
    if request.method == 'POST':
        form = SupplierRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            supplier = Supplier.objects.create(
                user=user,
                name=form.cleaned_data['company_name'],
                address=form.cleaned_data['address'],
                phone=form.cleaned_data['phone']
            )
            messages.success(request, 'Registration successful! Please wait for admin approval.')
            return redirect('supplier_login')
    else:
        form = SupplierRegistrationForm()
    
    return render(request, 'store/supplier/register.html', {'form': form})

def search(request):
    query = request.GET.get('q', '')
    if query:
        products = Product.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query)
        ).distinct()
    else:
        products = Product.objects.none()
    
    context = {
        'query': query,
        'products': products,
    }
    return render(request, 'store/search_results.html', context)

def supplier_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Check if the user is a supplier
            try:
                supplier = Supplier.objects.get(user=user)
                if not supplier.is_approved:
                    messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
                    return render(request, 'store/supplier/login.html')
                login(request, user)
                return redirect('supplier_dashboard')
            except Supplier.DoesNotExist:
                messages.error(request, 'This login is only for suppliers.')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/supplier/login.html')

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, 'Welcome back!')
            
            # Check user type and redirect accordingly
            try:
                if hasattr(user, 'supplier'):
                    return redirect('supplier_dashboard')
                elif hasattr(user, 'deliveryboy'):
                    return redirect('delivery_dashboard')
                else:
                    return redirect('home')
            except:
                return redirect('home')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/login.html')

def supplier_register(request):
    if request.method == 'POST':
        form = SupplierRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            supplier = Supplier.objects.create(
                user=user,
                name=form.cleaned_data['company_name'],
                address=form.cleaned_data['address'],
                phone=form.cleaned_data['phone']
            )
            messages.success(request, 'Registration successful! Please wait for admin approval.')
            return redirect('supplier_login')
    else:
        form = SupplierRegistrationForm()
    
    return render(request, 'store/supplier/register.html', {'form': form})

def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('home')

def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Create user profile
            UserProfile.objects.create(
                user=user,
                phone=form.cleaned_data.get('phone', ''),
                address=form.cleaned_data.get('address', '')
            )
            messages.success(request, 'Registration successful! Please login.')
            return redirect('login')
    else:
        form = UserRegistrationForm()
    
    return render(request, 'store/register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, 'Welcome back!')
            
            # Check user type and redirect accordingly
            try:
                if hasattr(user, 'supplier'):
                    return redirect('supplier_dashboard')
                elif hasattr(user, 'deliveryboy'):
                    return redirect('delivery_dashboard')
                else:
                    return redirect('home')
            except:
                return redirect('home')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/login.html')

def delivery_register(request):
    if request.method == 'POST':
        form = DeliveryBoyRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            delivery_boy = DeliveryBoy.objects.create(
                user=user,
                phone=form.cleaned_data['phone'],
                address=form.cleaned_data['address'],
                vehicle_number=form.cleaned_data.get('vehicle_number', '')
            )
            messages.success(request, 'Registration successful! Please wait for admin approval.')
            return redirect('delivery_login')
    else:
        form = DeliveryBoyRegistrationForm()
    
    return render(request, 'store/delivery/register.html', {'form': form})

def delivery_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None and hasattr(user, 'deliveryboy'):
            login(request, user)
            return redirect('delivery_dashboard')
        else:
            messages.error(request, 'Invalid credentials or not a delivery person.')
    
    return render(request, 'store/delivery/login.html')

@login_required
def delivery_dashboard(request):
    try:
        delivery_boy = DeliveryBoy.objects.get(user=request.user)
        delivery_assignments = DeliveryAssignment.objects.filter(delivery_boy=delivery_boy)
        
        # Get counts for different statuses
        pending_count = delivery_assignments.filter(status='assigned').count()
        active_count = delivery_assignments.filter(status__in=['picked_up', 'in_transit']).count()
        completed_count = delivery_assignments.filter(status='delivered').count()
        
        # Get unread message count
        unread_messages = DeliveryChat.objects.filter(
            delivery_boy=delivery_boy,
            is_read=False,
            is_from_customer=True  # Only count messages from customers
        ).count()
        
        context = {
            'delivery_boy': delivery_boy,
            'delivery_assignments': delivery_assignments.order_by('-assigned_at')[:5],  # Show last 5 assignments
            'pending_count': pending_count,
            'active_count': active_count,
            'completed_count': completed_count,
            'unread_messages': unread_messages,
        }
        return render(request, 'store/delivery/dashboard.html', context)
    except DeliveryBoy.DoesNotExist:
        messages.error(request, 'You are not authorized to access this page.')
        return redirect('home')

@login_required
def delivery_orders(request):
    try:
        delivery_boy = DeliveryBoy.objects.get(user=request.user)
        delivery_assignments = DeliveryAssignment.objects.filter(delivery_boy=delivery_boy)
        
        # Filter assignments by status if provided
        status = request.GET.get('status')
        if status:
            delivery_assignments = delivery_assignments.filter(status=status)
        
        context = {
            'delivery_boy': delivery_boy,
            'delivery_assignments': delivery_assignments.order_by('-assigned_at'),
            'current_status': status
        }
        return render(request, 'store/delivery/orders.html', context)
    except DeliveryBoy.DoesNotExist:
        messages.error(request, 'You are not authorized to access this page.')
        return redirect('home')

@login_required
def toggle_delivery_availability(request):
    if request.method == 'POST':
        try:
            delivery_boy = DeliveryBoy.objects.get(user=request.user)
            delivery_boy.is_available = not delivery_boy.is_available
            delivery_boy.save()
            
            status = 'available' if delivery_boy.is_available else 'offline'
            messages.success(request, f'You are now {status}')
            
            return redirect('delivery_dashboard')
        except DeliveryBoy.DoesNotExist:
            messages.error(request, 'You are not authorized to perform this action.')
            return redirect('home')
    return redirect('delivery_dashboard')

@login_required
def delivery_login(request):
    if request.user.is_authenticated:
        try:
            delivery_boy = DeliveryBoy.objects.get(user=request.user)
            if not delivery_boy.is_approved:
                messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
                logout(request)
            else:
                return redirect('delivery_dashboard')
        except DeliveryBoy.DoesNotExist:
            messages.error(request, 'This login is only for delivery personnel.')
            logout(request)
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            try:
                delivery_boy = DeliveryBoy.objects.get(user=user)
                if not delivery_boy.is_approved:
                    messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
                else:
                    login(request, user)
                    return redirect('delivery_dashboard')
            except DeliveryBoy.DoesNotExist:
                messages.error(request, 'This login is only for delivery personnel.')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/delivery/login.html')

@login_required
def delivery_dashboard(request):
    try:
        delivery_boy = DeliveryBoy.objects.get(user=request.user)
        delivery_assignments = DeliveryAssignment.objects.filter(delivery_boy=delivery_boy)
        
        # Get counts for dashboard
        pending_count = delivery_assignments.filter(status='assigned').count()
        active_count = delivery_assignments.filter(status__in=['picked_up', 'in_transit']).count()
        completed_count = delivery_assignments.filter(status='delivered').count()
        
        # Get unread message count
        unread_messages = DeliveryChat.objects.filter(
            delivery_boy=delivery_boy,
            is_read=False,
            is_from_customer=True  # Only count messages from customers
        ).count()
        
        context = {
            'delivery_boy': delivery_boy,
            'delivery_assignments': delivery_assignments.order_by('-assigned_at')[:5],  # Show last 5 assignments
            'pending_count': pending_count,
            'active_count': active_count,
            'completed_count': completed_count,
            'unread_messages': unread_messages,
        }
        return render(request, 'store/delivery/dashboard.html', context)
    except DeliveryBoy.DoesNotExist:
        messages.error(request, 'You are not authorized to access this page.')
        return redirect('home')

@login_required
def update_delivery_status(request, order_id):
    if not hasattr(request.user, 'deliveryboy'):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)
    
    delivery_boy = request.user.deliveryboy
    assignment = get_object_or_404(
        DeliveryAssignment,
        order_id=order_id,
        delivery_boy=delivery_boy
    )
    
    status = request.POST.get('status')
    if status not in ['pending', 'in_progress', 'delivered', 'failed']:
        return JsonResponse({'error': 'Invalid status'}, status=400)
    
    assignment.status = status
    assignment.save()
    
    # If delivered, update order status and create a chat message
    if status == 'delivered':
        assignment.order.status = 'delivered'
        assignment.order.save()
        
        # Create system message for delivery confirmation
        DeliveryChat.objects.create(
            order=assignment.order,
            customer=assignment.order.user,
            delivery_boy=delivery_boy,
            message="Order has been delivered successfully!",
            is_from_customer=False,
            is_system_message=True
        )
    
    return JsonResponse({
        'status': 'success',
        'new_status': assignment.get_status_display()
    })

@login_required
def delivery_chat(request, order_id):
    # Get the order and verify permissions
    if hasattr(request.user, 'deliveryboy'):
        # Delivery boy accessing the chat
        delivery_boy = request.user.deliveryboy
        order = get_object_or_404(Order, delivery_assignment__delivery_boy=delivery_boy, id=order_id)
        is_delivery_boy = True
    else:
        # Customer accessing the chat
        order = get_object_or_404(Order, user=request.user, id=order_id)
        is_delivery_boy = False

    if not order.delivery_assignment:
        return HttpResponseForbidden("Chat is only available after delivery assignment")

    # Handle message submission
    if request.method == 'POST':
        message = request.POST.get('message')
        is_quick_message = request.POST.get('is_quick_message') == 'true'
        
        if message:
            DeliveryChat.objects.create(
                order=order,
                customer=order.user,
                delivery_boy=order.delivery_assignment.delivery_boy,
                message=message,
                is_from_customer=not is_delivery_boy,
                is_quick_message=is_quick_message
            )

    # Get messages and mark them as read
    messages = DeliveryChat.objects.filter(order=order).order_by('created_at')
    
    # Mark messages as read based on who's viewing
    if is_delivery_boy:
        # Mark customer messages as read when delivery boy views them
        messages.filter(is_from_customer=True, is_read=False).update(is_read=True)
    else:
        # Mark delivery boy messages as read when customer views them
        messages.filter(is_from_customer=False, is_read=False).update(is_read=True)

    # Get appropriate quick messages based on user type
    quick_messages = QuickMessage.objects.filter(is_for_customer=not is_delivery_boy)

    # For HTMX requests, only return the messages partial
    if request.headers.get('HX-Request'):
        return render(request, 'store/partials/chat_messages.html', {
            'messages': messages,
            'is_delivery_boy': is_delivery_boy
        })

    return render(request, 'store/delivery_chat.html', {
        'order': order,
        'messages': messages,
        'quick_messages': quick_messages,
        'is_delivery_boy': is_delivery_boy
    })

@login_required
@user_passes_test(is_admin)
def admin_monthly_sales_report(request):
    if not request.user.is_staff:
        return redirect('home')
    
    # Get the current date and first day of the month
    today = timezone.now()
    first_day = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Get all orders for the current month
    monthly_orders = Order.objects.filter(
        created_at__gte=first_day,
        created_at__lte=today,
        status='delivered'  # Only count delivered orders
    )
    
    # Calculate total sales
    total_sales = monthly_orders.aggregate(
        total_amount=Sum('total_amount'),
        total_orders=Count('id')
    )
    
    # Get sales by category
    category_sales = OrderItem.objects.filter(
        order__in=monthly_orders
    ).values(
        'product__category__name'
    ).annotate(
        total_sales=Sum(F('quantity') * F('price')),
        items_sold=Sum('quantity')
    ).order_by('-total_sales')
    
    # Get top selling products
    top_products = OrderItem.objects.filter(
        order__in=monthly_orders
    ).values(
        'product__name'
    ).annotate(
        total_sales=Sum(F('quantity') * F('price')),
        items_sold=Sum('quantity')
    ).order_by('-items_sold')[:5]
    
    context = {
        'total_sales': total_sales,
        'category_sales': category_sales,
        'top_products': top_products,
        'month': today.strftime('%B %Y')
    }
    
    return render(request, 'store/admin/monthly_sales_report.html', context)

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

@login_required
@user_passes_test(is_admin)
def download_monthly_sales_report(request):
    # Get the current date and first day of the month
    today = timezone.now()
    first_day = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Get all orders for the current month
    monthly_orders = Order.objects.filter(
        created_at__gte=first_day,
        created_at__lte=today,
        status='delivered'
    )
    
    # Calculate total sales
    total_sales = monthly_orders.aggregate(
        total_amount=Sum('total_amount'),
        total_orders=Count('id')
    )
    
    # Get sales by category
    category_sales = OrderItem.objects.filter(
        order__in=monthly_orders
    ).values(
        'product__category__name'
    ).annotate(
        total_sales=Sum(F('quantity') * F('price')),
        items_sold=Sum('quantity')
    ).order_by('-total_sales')
    
    # Get top selling products
    top_products = OrderItem.objects.filter(
        order__in=monthly_orders
    ).values(
        'product__name'
    ).annotate(
        total_sales=Sum(F('quantity') * F('price')),
        items_sold=Sum('quantity')
    ).order_by('-items_sold')[:5]
    
    # Create the PDF
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="monthly_sales_report_{today.strftime("%B_%Y")}.pdf"'
    
    # Create the PDF document
    doc = SimpleDocTemplate(response, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30
    )
    elements.append(Paragraph(f'Monthly Sales Report - {today.strftime("%B %Y")}', title_style))
    elements.append(Spacer(1, 20))
    
    # Summary Statistics
    elements.append(Paragraph('Summary Statistics', styles['Heading2']))
    elements.append(Spacer(1, 12))
    summary_data = [
        ['Total Sales', f'₹{total_sales["total_amount"] or 0:,.2f}'],
        ['Total Orders', str(total_sales["total_orders"] or 0)]
    ]
    summary_table = Table(summary_data, colWidths=[2*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))
    
    # Category Sales
    elements.append(Paragraph('Sales by Category', styles['Heading2']))
    elements.append(Spacer(1, 12))
    category_data = [['Category', 'Items Sold', 'Total Sales']]
    for category in category_sales:
        category_data.append([
            category['product__category__name'],
            str(category['items_sold']),
            f'₹{category["total_sales"]:,.2f}'
        ])
    category_table = Table(category_data, colWidths=[2.5*inch, 2*inch, 2*inch])
    category_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT')
    ]))
    elements.append(category_table)
    elements.append(Spacer(1, 20))
    
    # Top Products
    elements.append(Paragraph('Top Selling Products', styles['Heading2']))
    elements.append(Spacer(1, 12))
    products_data = [['Product', 'Items Sold', 'Total Sales']]
    for product in top_products:
        products_data.append([
            product['product__name'],
            str(product['items_sold']),
            f'₹{product["total_sales"]:,.2f}'
        ])
    products_table = Table(products_data, colWidths=[2.5*inch, 2*inch, 2*inch])
    products_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT')
    ]))
    elements.append(products_table)
    
    # Generate PDF
    doc.build(elements)
    return response

@login_required
@user_passes_test(is_admin)
def admin_messages(request):
    # Get all suppliers with messages
    messages = SupplierMessage.objects.all().order_by('created_at')
    
    # Group messages by supplier
    supplier_messages = {}
    for message in messages:
        if message.supplier not in supplier_messages:
            supplier_messages[message.supplier] = []
        supplier_messages[message.supplier].append(message)
    
    # Mark all messages as read
    messages.filter(read=False, is_from_admin=False).update(read=True)
    
    return render(request, 'store/admin/messages.html', {
        'supplier_messages': supplier_messages,
        'messages': messages,
        'section': 'messages'
    })

@login_required
@user_passes_test(is_supplier)
def supplier_messages(request):
    supplier = request.user.supplier
    message_list = SupplierMessage.objects.filter(supplier=supplier).order_by('created_at')
    
    if request.method == 'POST':
        content = request.POST.get('message')
        if content:
            # Create supplier's reply
            SupplierMessage.objects.create(
                supplier=supplier,
                content=content,
                is_from_admin=False
            )
            messages.success(request, 'Message sent successfully')
            return redirect('supplier_messages')
    
    # Mark all unread messages as read
    message_list.filter(read=False).update(read=True)
    
    return render(request, 'store/supplier/messages.html', {
        'messages': message_list
    })

def search(request):
    query = request.GET.get('q', '')
    if query:
        products = Product.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query)
        ).distinct()
    else:
        products = Product.objects.none()
    
    context = {
        'query': query,
        'products': products,
    }
    return render(request, 'store/search_results.html', context)

def supplier_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Check if the user is a supplier
            try:
                supplier = Supplier.objects.get(user=user)
                if not supplier.is_approved:
                    messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
                    return render(request, 'store/supplier/login.html')
                login(request, user)
                return redirect('supplier_dashboard')
            except Supplier.DoesNotExist:
                messages.error(request, 'This login is only for suppliers.')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/supplier/login.html')

def supplier_register(request):
    if request.method == 'POST':
        form = SupplierRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            supplier = Supplier.objects.create(
                user=user,
                name=form.cleaned_data['company_name'],
                address=form.cleaned_data['address'],
                phone=form.cleaned_data['phone']
            )
            messages.success(request, 'Registration successful! Please wait for admin approval.')
            return redirect('supplier_login')
    else:
        form = SupplierRegistrationForm()
    
    return render(request, 'store/supplier/register.html', {'form': form})

def search(request):
    query = request.GET.get('q', '')
    if query:
        products = Product.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query)
        ).distinct()
    else:
        products = Product.objects.none()
    
    context = {
        'query': query,
        'products': products,
    }
    return render(request, 'store/search_results.html', context)

def supplier_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Check if the user is a supplier
            try:
                supplier = Supplier.objects.get(user=user)
                if not supplier.is_approved:
                    messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
                    return render(request, 'store/supplier/login.html')
                login(request, user)
                return redirect('supplier_dashboard')
            except Supplier.DoesNotExist:
                messages.error(request, 'This login is only for suppliers.')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/supplier/login.html')

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, 'Welcome back!')
            
            # Check user type and redirect accordingly
            try:
                if hasattr(user, 'supplier'):
                    return redirect('supplier_dashboard')
                elif hasattr(user, 'deliveryboy'):
                    return redirect('delivery_dashboard')
                else:
                    return redirect('home')
            except:
                return redirect('home')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/login.html')

def supplier_register(request):
    if request.method == 'POST':
        form = SupplierRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            supplier = Supplier.objects.create(
                user=user,
                name=form.cleaned_data['company_name'],
                address=form.cleaned_data['address'],
                phone=form.cleaned_data['phone']
            )
            messages.success(request, 'Registration successful! Please wait for admin approval.')
            return redirect('supplier_login')
    else:
        form = SupplierRegistrationForm()
    
    return render(request, 'store/supplier/register.html', {'form': form})

def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('home')

def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Create user profile
            UserProfile.objects.create(
                user=user,
                phone=form.cleaned_data.get('phone', ''),
                address=form.cleaned_data.get('address', '')
            )
            messages.success(request, 'Registration successful! Please login.')
            return redirect('login')
    else:
        form = UserRegistrationForm()
    
    return render(request, 'store/register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, 'Welcome back!')
            
            # Check user type and redirect accordingly
            try:
                if hasattr(user, 'supplier'):
                    return redirect('supplier_dashboard')
                elif hasattr(user, 'deliveryboy'):
                    return redirect('delivery_dashboard')
                else:
                    return redirect('home')
            except:
                return redirect('home')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/login.html')

def delivery_register(request):
    if request.method == 'POST':
        form = DeliveryBoyRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            delivery_boy = DeliveryBoy.objects.create(
                user=user,
                phone=form.cleaned_data['phone'],
                address=form.cleaned_data['address'],
                vehicle_number=form.cleaned_data.get('vehicle_number', '')
            )
            messages.success(request, 'Registration successful! Please wait for admin approval.')
            return redirect('delivery_login')
    else:
        form = DeliveryBoyRegistrationForm()
    
    return render(request, 'store/delivery/register.html', {'form': form})

def delivery_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None and hasattr(user, 'deliveryboy'):
            login(request, user)
            return redirect('delivery_dashboard')
        else:
            messages.error(request, 'Invalid credentials or not a delivery person.')
    
    return render(request, 'store/delivery/login.html')

@login_required
def delivery_dashboard(request):
    try:
        delivery_boy = DeliveryBoy.objects.get(user=request.user)
        delivery_assignments = DeliveryAssignment.objects.filter(delivery_boy=delivery_boy)
        
        # Get counts for different statuses
        pending_count = delivery_assignments.filter(status='assigned').count()
        active_count = delivery_assignments.filter(status__in=['picked_up', 'in_transit']).count()
        completed_count = delivery_assignments.filter(status='delivered').count()
        
        # Get unread message count
        unread_messages = DeliveryChat.objects.filter(
            delivery_boy=delivery_boy,
            is_read=False,
            is_from_customer=True  # Only count messages from customers
        ).count()
        
        context = {
            'delivery_boy': delivery_boy,
            'delivery_assignments': delivery_assignments.order_by('-assigned_at')[:5],  # Show last 5 assignments
            'pending_count': pending_count,
            'active_count': active_count,
            'completed_count': completed_count,
            'unread_messages': unread_messages,
        }
        return render(request, 'store/delivery/dashboard.html', context)
    except DeliveryBoy.DoesNotExist:
        messages.error(request, 'You are not authorized to access this page.')
        return redirect('home')

@login_required
def delivery_orders(request):
    try:
        delivery_boy = DeliveryBoy.objects.get(user=request.user)
        delivery_assignments = DeliveryAssignment.objects.filter(delivery_boy=delivery_boy)
        
        # Filter assignments by status if provided
        status = request.GET.get('status')
        if status:
            delivery_assignments = delivery_assignments.filter(status=status)
        
        context = {
            'delivery_boy': delivery_boy,
            'delivery_assignments': delivery_assignments.order_by('-assigned_at'),
            'current_status': status
        }
        return render(request, 'store/delivery/orders.html', context)
    except DeliveryBoy.DoesNotExist:
        messages.error(request, 'You are not authorized to access this page.')
        return redirect('home')

@login_required
def toggle_delivery_availability(request):
    if request.method == 'POST':
        try:
            delivery_boy = DeliveryBoy.objects.get(user=request.user)
            delivery_boy.is_available = not delivery_boy.is_available
            delivery_boy.save()
            
            status = 'available' if delivery_boy.is_available else 'offline'
            messages.success(request, f'You are now {status}')
            
            return redirect('delivery_dashboard')
        except DeliveryBoy.DoesNotExist:
            messages.error(request, 'You are not authorized to perform this action.')
            return redirect('home')
    return redirect('delivery_dashboard')

@login_required
def delivery_login(request):
    if request.user.is_authenticated:
        try:
            delivery_boy = DeliveryBoy.objects.get(user=request.user)
            if not delivery_boy.is_approved:
                messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
                logout(request)
            else:
                return redirect('delivery_dashboard')
        except DeliveryBoy.DoesNotExist:
            messages.error(request, 'This login is only for delivery personnel.')
            logout(request)
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            try:
                delivery_boy = DeliveryBoy.objects.get(user=user)
                if not delivery_boy.is_approved:
                    messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
                else:
                    login(request, user)
                    return redirect('delivery_dashboard')
            except DeliveryBoy.DoesNotExist:
                messages.error(request, 'This login is only for delivery personnel.')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/delivery/login.html')

@login_required
def delivery_dashboard(request):
    try:
        delivery_boy = DeliveryBoy.objects.get(user=request.user)
        delivery_assignments = DeliveryAssignment.objects.filter(delivery_boy=delivery_boy)
        
        # Get counts for dashboard
        pending_count = delivery_assignments.filter(status='assigned').count()
        active_count = delivery_assignments.filter(status__in=['picked_up', 'in_transit']).count()
        completed_count = delivery_assignments.filter(status='delivered').count()
        
        # Get unread message count
        unread_messages = DeliveryChat.objects.filter(
            delivery_boy=delivery_boy,
            is_read=False,
            is_from_customer=True  # Only count messages from customers
        ).count()
        
        context = {
            'delivery_boy': delivery_boy,
            'delivery_assignments': delivery_assignments.order_by('-assigned_at')[:5],  # Show last 5 assignments
            'pending_count': pending_count,
            'active_count': active_count,
            'completed_count': completed_count,
            'unread_messages': unread_messages,
        }
        return render(request, 'store/delivery/dashboard.html', context)
    except DeliveryBoy.DoesNotExist:
        messages.error(request, 'You are not authorized to access this page.')
        return redirect('home')

@login_required
def update_delivery_status(request, order_id):
    if not hasattr(request.user, 'deliveryboy'):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)
    
    delivery_boy = request.user.deliveryboy
    assignment = get_object_or_404(
        DeliveryAssignment,
        order_id=order_id,
        delivery_boy=delivery_boy
    )
    
    status = request.POST.get('status')
    if status not in ['pending', 'in_progress', 'delivered', 'failed']:
        return JsonResponse({'error': 'Invalid status'}, status=400)
    
    assignment.status = status
    assignment.save()
    
    # If delivered, update order status and create a chat message
    if status == 'delivered':
        assignment.order.status = 'delivered'
        assignment.order.save()
        
        # Create system message for delivery confirmation
        DeliveryChat.objects.create(
            order=assignment.order,
            customer=assignment.order.user,
            delivery_boy=delivery_boy,
            message="Order has been delivered successfully!",
            is_from_customer=False,
            is_system_message=True
        )
    
    return JsonResponse({
        'status': 'success',
        'new_status': assignment.get_status_display()
    })

@login_required
def delivery_chat(request, order_id):
    # Get the order and verify permissions
    if hasattr(request.user, 'deliveryboy'):
        # Delivery boy accessing the chat
        delivery_boy = request.user.deliveryboy
        order = get_object_or_404(Order, delivery_assignment__delivery_boy=delivery_boy, id=order_id)
        is_delivery_boy = True
    else:
        # Customer accessing the chat
        order = get_object_or_404(Order, user=request.user, id=order_id)
        is_delivery_boy = False

    if not order.delivery_assignment:
        return HttpResponseForbidden("Chat is only available after delivery assignment")

    # Handle message submission
    if request.method == 'POST':
        message = request.POST.get('message')
        is_quick_message = request.POST.get('is_quick_message') == 'true'
        
        if message:
            DeliveryChat.objects.create(
                order=order,
                customer=order.user,
                delivery_boy=order.delivery_assignment.delivery_boy,
                message=message,
                is_from_customer=not is_delivery_boy,
                is_quick_message=is_quick_message
            )

    # Get messages and mark them as read
    messages = DeliveryChat.objects.filter(order=order).order_by('created_at')
    
    # Mark messages as read based on who's viewing
    if is_delivery_boy:
        # Mark customer messages as read when delivery boy views them
        messages.filter(is_from_customer=True, is_read=False).update(is_read=True)
    else:
        # Mark delivery boy messages as read when customer views them
        messages.filter(is_from_customer=False, is_read=False).update(is_read=True)

    # Get appropriate quick messages based on user type
    quick_messages = QuickMessage.objects.filter(is_for_customer=not is_delivery_boy)

    # For HTMX requests, only return the messages partial
    if request.headers.get('HX-Request'):
        return render(request, 'store/partials/chat_messages.html', {
            'messages': messages,
            'is_delivery_boy': is_delivery_boy
        })

    return render(request, 'store/delivery_chat.html', {
        'order': order,
        'messages': messages,
        'quick_messages': quick_messages,
        'is_delivery_boy': is_delivery_boy
    })

@login_required
@user_passes_test(is_admin)
def admin_monthly_sales_report(request):
    if not request.user.is_staff:
        return redirect('home')
    
    # Get the current date and first day of the month
    today = timezone.now()
    first_day = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Get all orders for the current month
    monthly_orders = Order.objects.filter(
        created_at__gte=first_day,
        created_at__lte=today,
        status='delivered'  # Only count delivered orders
    )
    
    # Calculate total sales
    total_sales = monthly_orders.aggregate(
        total_amount=Sum('total_amount'),
        total_orders=Count('id')
    )
    
    # Get sales by category
    category_sales = OrderItem.objects.filter(
        order__in=monthly_orders
    ).values(
        'product__category__name'
    ).annotate(
        total_sales=Sum(F('quantity') * F('price')),
        items_sold=Sum('quantity')
    ).order_by('-total_sales')
    
    # Get top selling products
    top_products = OrderItem.objects.filter(
        order__in=monthly_orders
    ).values(
        'product__name'
    ).annotate(
        total_sales=Sum(F('quantity') * F('price')),
        items_sold=Sum('quantity')
    ).order_by('-items_sold')[:5]
    
    context = {
        'total_sales': total_sales,
        'category_sales': category_sales,
        'top_products': top_products,
        'month': today.strftime('%B %Y')
    }
    
    return render(request, 'store/admin/monthly_sales_report.html', context)

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

@login_required
@user_passes_test(is_admin)
def download_monthly_sales_report(request):
    # Get the current date and first day of the month
    today = timezone.now()
    first_day = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Get all orders for the current month
    monthly_orders = Order.objects.filter(
        created_at__gte=first_day,
        created_at__lte=today,
        status='delivered'
    )
    
    # Calculate total sales
    total_sales = monthly_orders.aggregate(
        total_amount=Sum('total_amount'),
        total_orders=Count('id')
    )
    
    # Get sales by category
    category_sales = OrderItem.objects.filter(
        order__in=monthly_orders
    ).values(
        'product__category__name'
    ).annotate(
        total_sales=Sum(F('quantity') * F('price')),
        items_sold=Sum('quantity')
    ).order_by('-total_sales')
    
    # Get top selling products
    top_products = OrderItem.objects.filter(
        order__in=monthly_orders
    ).values(
        'product__name'
    ).annotate(
        total_sales=Sum(F('quantity') * F('price')),
        items_sold=Sum('quantity')
    ).order_by('-items_sold')[:5]
    
    # Create the PDF
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="monthly_sales_report_{today.strftime("%B_%Y")}.pdf"'
    
    # Create the PDF document
    doc = SimpleDocTemplate(response, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30
    )
    elements.append(Paragraph(f'Monthly Sales Report - {today.strftime("%B %Y")}', title_style))
    elements.append(Spacer(1, 20))
    
    # Summary Statistics
    elements.append(Paragraph('Summary Statistics', styles['Heading2']))
    elements.append(Spacer(1, 12))
    summary_data = [
        ['Total Sales', f'₹{total_sales["total_amount"] or 0:,.2f}'],
        ['Total Orders', str(total_sales["total_orders"] or 0)]
    ]
    summary_table = Table(summary_data, colWidths=[2*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))
    
    # Category Sales
    elements.append(Paragraph('Sales by Category', styles['Heading2']))
    elements.append(Spacer(1, 12))
    category_data = [['Category', 'Items Sold', 'Total Sales']]
    for category in category_sales:
        category_data.append([
            category['product__category__name'],
            str(category['items_sold']),
            f'₹{category["total_sales"]:,.2f}'
        ])
    category_table = Table(category_data, colWidths=[2.5*inch, 2*inch, 2*inch])
    category_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT')
    ]))
    elements.append(category_table)
    elements.append(Spacer(1, 20))
    
    # Top Products
    elements.append(Paragraph('Top Selling Products', styles['Heading2']))
    elements.append(Spacer(1, 12))
    products_data = [['Product', 'Items Sold', 'Total Sales']]
    for product in top_products:
        products_data.append([
            product['product__name'],
            str(product['items_sold']),
            f'₹{product["total_sales"]:,.2f}'
        ])
    products_table = Table(products_data, colWidths=[2.5*inch, 2*inch, 2*inch])
    products_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT')
    ]))
    elements.append(products_table)
    
    # Generate PDF
    doc.build(elements)
    return response

@login_required
@user_passes_test(is_admin)
def admin_messages(request):
    # Get all suppliers with messages
    messages = SupplierMessage.objects.all().order_by('created_at')
    
    # Group messages by supplier
    supplier_messages = {}
    for message in messages:
        if message.supplier not in supplier_messages:
            supplier_messages[message.supplier] = []
        supplier_messages[message.supplier].append(message)
    
    # Mark all messages as read
    messages.filter(read=False, is_from_admin=False).update(read=True)
    
    return render(request, 'store/admin/messages.html', {
        'supplier_messages': supplier_messages,
        'messages': messages,
        'section': 'messages'
    })

@login_required
@user_passes_test(is_supplier)
def supplier_messages(request):
    supplier = request.user.supplier
    message_list = SupplierMessage.objects.filter(supplier=supplier).order_by('created_at')
    
    if request.method == 'POST':
        content = request.POST.get('message')
        if content:
            # Create supplier's reply
            SupplierMessage.objects.create(
                supplier=supplier,
                content=content,
                is_from_admin=False
            )
            messages.success(request, 'Message sent successfully')
            return redirect('supplier_messages')
    
    # Mark all unread messages as read
    message_list.filter(read=False).update(read=True)
    
    return render(request, 'store/supplier/messages.html', {
        'messages': message_list
    })

def search(request):
    query = request.GET.get('q', '')
    if query:
        products = Product.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query)
        ).distinct()
    else:
        products = Product.objects.none()
    
    context = {
        'query': query,
        'products': products,
    }
    return render(request, 'store/search_results.html', context)

def supplier_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Check if the user is a supplier
            try:
                supplier = Supplier.objects.get(user=user)
                if not supplier.is_approved:
                    messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
                    return render(request, 'store/supplier/login.html')
                login(request, user)
                return redirect('supplier_dashboard')
            except Supplier.DoesNotExist:
                messages.error(request, 'This login is only for suppliers.')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/supplier/login.html')

def supplier_register(request):
    if request.method == 'POST':
        form = SupplierRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            supplier = Supplier.objects.create(
                user=user,
                name=form.cleaned_data['company_name'],
                address=form.cleaned_data['address'],
                phone=form.cleaned_data['phone']
            )
            messages.success(request, 'Registration successful! Please wait for admin approval.')
            return redirect('supplier_login')
    else:
        form = SupplierRegistrationForm()
    
    return render(request, 'store/supplier/register.html', {'form': form})

def search(request):
    query = request.GET.get('q', '')
    if query:
        products = Product.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query)
        ).distinct()
    else:
        products = Product.objects.none()
    
    context = {
        'query': query,
        'products': products,
    }
    return render(request, 'store/search_results.html', context)

def supplier_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Check if the user is a supplier
            try:
                supplier = Supplier.objects.get(user=user)
                if not supplier.is_approved:
                    messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
                    return render(request, 'store/supplier/login.html')
                login(request, user)
                return redirect('supplier_dashboard')
            except Supplier.DoesNotExist:
                messages.error(request, 'This login is only for suppliers.')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/supplier/login.html')

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, 'Welcome back!')
            
            # Check user type and redirect accordingly
            try:
                if hasattr(user, 'supplier'):
                    return redirect('supplier_dashboard')
                elif hasattr(user, 'deliveryboy'):
                    return redirect('delivery_dashboard')
                else:
                    return redirect('home')
            except:
                return redirect('home')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/login.html')

def supplier_register(request):
    if request.method == 'POST':
        form = SupplierRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            supplier = Supplier.objects.create(
                user=user,
                name=form.cleaned_data['company_name'],
                address=form.cleaned_data['address'],
                phone=form.cleaned_data['phone']
            )
            messages.success(request, 'Registration successful! Please wait for admin approval.')
            return redirect('supplier_login')
    else:
        form = SupplierRegistrationForm()
    
    return render(request, 'store/supplier/register.html', {'form': form})

def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('home')

def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Create user profile
            UserProfile.objects.create(
                user=user,
                phone=form.cleaned_data.get('phone', ''),
                address=form.cleaned_data.get('address', '')
            )
            messages.success(request, 'Registration successful! Please login.')
            return redirect('login')
    else:
        form = UserRegistrationForm()
    
    return render(request, 'store/register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, 'Welcome back!')
            
            # Check user type and redirect accordingly
            try:
                if hasattr(user, 'supplier'):
                    return redirect('supplier_dashboard')
                elif hasattr(user, 'deliveryboy'):
                    return redirect('delivery_dashboard')
                else:
                    return redirect('home')
            except:
                return redirect('home')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/login.html')

def delivery_register(request):
    if request.method == 'POST':
        form = DeliveryBoyRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            delivery_boy = DeliveryBoy.objects.create(
                user=user,
                phone=form.cleaned_data['phone'],
                address=form.cleaned_data['address'],
                vehicle_number=form.cleaned_data.get('vehicle_number', '')
            )
            messages.success(request, 'Registration successful! Please wait for admin approval.')
            return redirect('delivery_login')
    else:
        form = DeliveryBoyRegistrationForm()
    
    return render(request, 'store/delivery/register.html', {'form': form})

def delivery_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None and hasattr(user, 'deliveryboy'):
            login(request, user)
            return redirect('delivery_dashboard')
        else:
            messages.error(request, 'Invalid credentials or not a delivery person.')
    
    return render(request, 'store/delivery/login.html')

@login_required
def delivery_dashboard(request):
    try:
        delivery_boy = DeliveryBoy.objects.get(user=request.user)
        delivery_assignments = DeliveryAssignment.objects.filter(delivery_boy=delivery_boy)
        
        # Get counts for different statuses
        pending_count = delivery_assignments.filter(status='assigned').count()
        active_count = delivery_assignments.filter(status__in=['picked_up', 'in_transit']).count()
        completed_count = delivery_assignments.filter(status='delivered').count()
        
        # Get unread message count
        unread_messages = DeliveryChat.objects.filter(
            delivery_boy=delivery_boy,
            is_read=False,
            is_from_customer=True  # Only count messages from customers
        ).count()
        
        context = {
            'delivery_boy': delivery_boy,
            'delivery_assignments': delivery_assignments.order_by('-assigned_at')[:5],  # Show last 5 assignments
            'pending_count': pending_count,
            'active_count': active_count,
            'completed_count': completed_count,
            'unread_messages': unread_messages,
        }
        return render(request, 'store/delivery/dashboard.html', context)
    except DeliveryBoy.DoesNotExist:
        messages.error(request, 'You are not authorized to access this page.')
        return redirect('home')

@login_required
def delivery_orders(request):
    try:
        delivery_boy = DeliveryBoy.objects.get(user=request.user)
        delivery_assignments = DeliveryAssignment.objects.filter(delivery_boy=delivery_boy)
        
        # Filter assignments by status if provided
        status = request.GET.get('status')
        if status:
            delivery_assignments = delivery_assignments.filter(status=status)
        
        context = {
            'delivery_boy': delivery_boy,
            'delivery_assignments': delivery_assignments.order_by('-assigned_at'),
            'current_status': status
        }
        return render(request, 'store/delivery/orders.html', context)
    except DeliveryBoy.DoesNotExist:
        messages.error(request, 'You are not authorized to access this page.')
        return redirect('home')

@login_required
def toggle_delivery_availability(request):
    if request.method == 'POST':
        try:
            delivery_boy = DeliveryBoy.objects.get(user=request.user)
            delivery_boy.is_available = not delivery_boy.is_available
            delivery_boy.save()
            
            status = 'available' if delivery_boy.is_available else 'offline'
            messages.success(request, f'You are now {status}')
            
            return redirect('delivery_dashboard')
        except DeliveryBoy.DoesNotExist:
            messages.error(request, 'You are not authorized to perform this action.')
            return redirect('home')
    return redirect('delivery_dashboard')

@login_required
def delivery_login(request):
    if request.user.is_authenticated:
        try:
            delivery_boy = DeliveryBoy.objects.get(user=request.user)
            if not delivery_boy.is_approved:
                messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
                logout(request)
            else:
                return redirect('delivery_dashboard')
        except DeliveryBoy.DoesNotExist:
            messages.error(request, 'This login is only for delivery personnel.')
            logout(request)
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            try:
                delivery_boy = DeliveryBoy.objects.get(user=user)
                if not delivery_boy.is_approved:
                    messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
                else:
                    login(request, user)
                    return redirect('delivery_dashboard')
            except DeliveryBoy.DoesNotExist:
                messages.error(request, 'This login is only for delivery personnel.')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/delivery/login.html')

@login_required
def delivery_dashboard(request):
    try:
        delivery_boy = DeliveryBoy.objects.get(user=request.user)
        delivery_assignments = DeliveryAssignment.objects.filter(delivery_boy=delivery_boy)
        
        # Get counts for dashboard
        pending_count = delivery_assignments.filter(status='assigned').count()
        active_count = delivery_assignments.filter(status__in=['picked_up', 'in_transit']).count()
        completed_count = delivery_assignments.filter(status='delivered').count()
        
        # Get unread message count
        unread_messages = DeliveryChat.objects.filter(
            delivery_boy=delivery_boy,
            is_read=False,
            is_from_customer=True  # Only count messages from customers
        ).count()
        
        context = {
            'delivery_boy': delivery_boy,
            'delivery_assignments': delivery_assignments.order_by('-assigned_at')[:5],  # Show last 5 assignments
            'pending_count': pending_count,
            'active_count': active_count,
            'completed_count': completed_count,
            'unread_messages': unread_messages,
        }
        return render(request, 'store/delivery/dashboard.html', context)
    except DeliveryBoy.DoesNotExist:
        messages.error(request, 'You are not authorized to access this page.')
        return redirect('home')

@login_required
def update_delivery_status(request, order_id):
    if not hasattr(request.user, 'deliveryboy'):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid method'}, status=405)
    
    delivery_boy = request.user.deliveryboy
    assignment = get_object_or_404(
        DeliveryAssignment,
        order_id=order_id,
        delivery_boy=delivery_boy
    )
    
    status = request.POST.get('status')
    if status not in ['pending', 'in_progress', 'delivered', 'failed']:
        return JsonResponse({'error': 'Invalid status'}, status=400)
    
    assignment.status = status
    assignment.save()
    
    # If delivered, update order status and create a chat message
    if status == 'delivered':
        assignment.order.status = 'delivered'
        assignment.order.save()
        
        # Create system message for delivery confirmation
        DeliveryChat.objects.create(
            order=assignment.order,
            customer=assignment.order.user,
            delivery_boy=delivery_boy,
            message="Order has been delivered successfully!",
            is_from_customer=False,
            is_system_message=True
        )
    
    return JsonResponse({
        'status': 'success',
        'new_status': assignment.get_status_display()
    })

@login_required
def delivery_chat(request, order_id):
    # Get the order and verify permissions
    if hasattr(request.user, 'deliveryboy'):
        # Delivery boy accessing the chat
        delivery_boy = request.user.deliveryboy
        order = get_object_or_404(Order, delivery_assignment__delivery_boy=delivery_boy, id=order_id)
        is_delivery_boy = True
    else:
        # Customer accessing the chat
        order = get_object_or_404(Order, user=request.user, id=order_id)
        is_delivery_boy = False

    if not order.delivery_assignment:
        return HttpResponseForbidden("Chat is only available after delivery assignment")

    # Handle message submission
    if request.method == 'POST':
        message = request.POST.get('message')
        is_quick_message = request.POST.get('is_quick_message') == 'true'
        
        if message:
            DeliveryChat.objects.create(
                order=order,
                customer=order.user,
                delivery_boy=order.delivery_assignment.delivery_boy,
                message=message,
                is_from_customer=not is_delivery_boy,
                is_quick_message=is_quick_message
            )

    # Get messages and mark them as read
    messages = DeliveryChat.objects.filter(order=order).order_by('created_at')
    
    # Mark messages as read based on who's viewing
    if is_delivery_boy:
        # Mark customer messages as read when delivery boy views them
        messages.filter(is_from_customer=True, is_read=False).update(is_read=True)
    else:
        # Mark delivery boy messages as read when customer views them
        messages.filter(is_from_customer=False, is_read=False).update(is_read=True)

    # Get appropriate quick messages based on user type
    quick_messages = QuickMessage.objects.filter(is_for_customer=not is_delivery_boy)

    # For HTMX requests, only return the messages partial
    if request.headers.get('HX-Request'):
        return render(request, 'store/partials/chat_messages.html', {
            'messages': messages,
            'is_delivery_boy': is_delivery_boy
        })

    return render(request, 'store/delivery_chat.html', {
        'order': order,
        'messages': messages,
        'quick_messages': quick_messages,
        'is_delivery_boy': is_delivery_boy
    })

@login_required
@user_passes_test(is_admin)
def admin_monthly_sales_report(request):
    if not request.user.is_staff:
        return redirect('home')
    
    # Get the current date and first day of the month
    today = timezone.now()
    first_day = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Get all orders for the current month
    monthly_orders = Order.objects.filter(
        created_at__gte=first_day,
        created_at__lte=today,
        status='delivered'  # Only count delivered orders
    )
    
    # Calculate total sales
    total_sales = monthly_orders.aggregate(
        total_amount=Sum('total_amount'),
        total_orders=Count('id')
    )
    
    # Get sales by category
    category_sales = OrderItem.objects.filter(
        order__in=monthly_orders
    ).values(
        'product__category__name'
    ).annotate(
        total_sales=Sum(F('quantity') * F('price')),
        items_sold=Sum('quantity')
    ).order_by('-total_sales')
    
    # Get top selling products
    top_products = OrderItem.objects.filter(
        order__in=monthly_orders
    ).values(
        'product__name'
    ).annotate(
        total_sales=Sum(F('quantity') * F('price')),
        items_sold=Sum('quantity')
    ).order_by('-items_sold')[:5]
    
    context = {
        'total_sales': total_sales,
        'category_sales': category_sales,
        'top_products': top_products,
        'month': today.strftime('%B %Y')
    }
    
    return render(request, 'store/admin/monthly_sales_report.html', context)

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

@login_required
@user_passes_test(is_admin)
def download_monthly_sales_report(request):
    # Get the current date and first day of the month
    today = timezone.now()
    first_day = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Get all orders for the current month
    monthly_orders = Order.objects.filter(
        created_at__gte=first_day,
        created_at__lte=today,
        status='delivered'
    )
    
    # Calculate total sales
    total_sales = monthly_orders.aggregate(
        total_amount=Sum('total_amount'),
        total_orders=Count('id')
    )
    
    # Get sales by category
    category_sales = OrderItem.objects.filter(
        order__in=monthly_orders
    ).values(
        'product__category__name'
    ).annotate(
        total_sales=Sum(F('quantity') * F('price')),
        items_sold=Sum('quantity')
    ).order_by('-total_sales')
    
    # Get top selling products
    top_products = OrderItem.objects.filter(
        order__in=monthly_orders
    ).values(
        'product__name'
    ).annotate(
        total_sales=Sum(F('quantity') * F('price')),
        items_sold=Sum('quantity')
    ).order_by('-items_sold')[:5]
    
    # Create the PDF
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="monthly_sales_report_{today.strftime("%B_%Y")}.pdf"'
    
    # Create the PDF document
    doc = SimpleDocTemplate(response, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30
    )
    elements.append(Paragraph(f'Monthly Sales Report - {today.strftime("%B %Y")}', title_style))
    elements.append(Spacer(1, 20))
    
    # Summary Statistics
    elements.append(Paragraph('Summary Statistics', styles['Heading2']))
    elements.append(Spacer(1, 12))
    summary_data = [
        ['Total Sales', f'₹{total_sales["total_amount"] or 0:,.2f}'],
        ['Total Orders', str(total_sales["total_orders"] or 0)]
    ]
    summary_table = Table(summary_data, colWidths=[2*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))
    
    # Category Sales
    elements.append(Paragraph('Sales by Category', styles['Heading2']))
    elements.append(Spacer(1, 12))
    category_data = [['Category', 'Items Sold', 'Total Sales']]
    for category in category_sales:
        category_data.append([
            category['product__category__name'],
            str(category['items_sold']),
            f'₹{category["total_sales"]:,.2f}'
        ])
    category_table = Table(category_data, colWidths=[2.5*inch, 2*inch, 2*inch])
    category_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT')
    ]))
    elements.append(category_table)
    elements.append(Spacer(1, 20))
    
    # Top Products
    elements.append(Paragraph('Top Selling Products', styles['Heading2']))
    elements.append(Spacer(1, 12))
    products_data = [['Product', 'Items Sold', 'Total Sales']]
    for product in top_products:
        products_data.append([
            product['product__name'],
            str(product['items_sold']),
            f'₹{product["total_sales"]:,.2f}'
        ])
    products_table = Table(products_data, colWidths=[2.5*inch, 2*inch, 2*inch])
    products_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT')
    ]))
    elements.append(products_table)
    
    # Generate PDF
    doc.build(elements)
    return response

@login_required
@user_passes_test(is_admin)
def admin_messages(request):
    # Get all suppliers with messages
    messages = SupplierMessage.objects.all().order_by('created_at')
    
    # Group messages by supplier
    supplier_messages = {}
    for message in messages:
        if message.supplier not in supplier_messages:
            supplier_messages[message.supplier] = []
        supplier_messages[message.supplier].append(message)
    
    # Mark all messages as read
    messages.filter(read=False, is_from_admin=False).update(read=True)
    
    return render(request, 'store/admin/messages.html', {
        'supplier_messages': supplier_messages,
        'messages': messages,
        'section': 'messages'
    })

@login_required
@user_passes_test(is_supplier)
def supplier_messages(request):
    supplier = request.user.supplier
    message_list = SupplierMessage.objects.filter(supplier=supplier).order_by('created_at')
    
    if request.method == 'POST':
        content = request.POST.get('message')
        if content:
            # Create supplier's reply
            SupplierMessage.objects.create(
                supplier=supplier,
                content=content,
                is_from_admin=False
            )
            messages.success(request, 'Message sent successfully')
            return redirect('supplier_messages')
    
    # Mark all unread messages as read
    message_list.filter(read=False).update(read=True)
    
    return render(request, 'store/supplier/messages.html', {
        'messages': message_list
    })

def search(request):
    query = request.GET.get('q', '')
    if query:
        products = Product.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query)
        ).distinct()
    else:
        products = Product.objects.none()
    
    context = {
        'query': query,
        'products': products,
    }
    return render(request, 'store/search_results.html', context)

def supplier_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Check if the user is a supplier
            try:
                supplier = Supplier.objects.get(user=user)
                if not supplier.is_approved:
                    messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
                    return render(request, 'store/supplier/login.html')
                login(request, user)
                return redirect('supplier_dashboard')
            except Supplier.DoesNotExist:
                messages.error(request, 'This login is only for suppliers.')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/supplier/login.html')

def supplier_register(request):
    if request.method == 'POST':
        form = SupplierRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            supplier = Supplier.objects.create(
                user=user,
                name=form.cleaned_data['company_name'],
                address=form.cleaned_data['address'],
                phone=form.cleaned_data['phone']
            )
            messages.success(request, 'Registration successful! Please wait for admin approval.')
            return redirect('supplier_login')
    else:
        form = SupplierRegistrationForm()
    
    return render(request, 'store/supplier/register.html', {'form': form})

def search(request):
    query = request.GET.get('q', '')
    if query:
        products = Product.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query)
        ).distinct()
    else:
        products = Product.objects.none()
    
    context = {
        'query': query,
        'products': products,
    }
    return render(request, 'store/search_results.html', context)

def supplier_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Check if the user is a supplier
            try:
                supplier = Supplier.objects.get(user=user)
                if not supplier.is_approved:
                    messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
                    return render(request, 'store/supplier/login.html')
                login(request, user)
                return redirect('supplier_dashboard')
            except Supplier.DoesNotExist:
                messages.error(request, 'This login is only for suppliers.')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/supplier/login.html')

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, 'Welcome back!')
            
            # Check user type and redirect accordingly
            try:
                if hasattr(user, 'supplier'):
                    return redirect('supplier_dashboard')
                elif hasattr(user, 'deliveryboy'):
                    return redirect('delivery_dashboard')
                else:
                    return redirect('home')
            except:
                return redirect('home')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/login.html')

def supplier_register(request):
    if request.method == 'POST':
        form = SupplierRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            supplier = Supplier.objects.create(
                user=user,
                name=form.cleaned_data['company_name'],
                address=form.cleaned_data['address'],
                phone=form.cleaned_data['phone']
            )
            messages.success(request, 'Registration successful! Please wait for admin approval.')
            return redirect('supplier_login')
    else:
        form = SupplierRegistrationForm()
    
    return render(request, 'store/supplier/register.html', {'form': form})

def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('home')

def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Use get_or_create instead of create
            UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'phone': form.cleaned_data.get('phone', ''),
                    'address': form.cleaned_data.get('address', '')
                }
            )
            messages.success(request, 'Registration successful! Please login.')
            return redirect('login')
    else:
        form = UserRegistrationForm()
    
    return render(request, 'store/register.html', {'form': form})
    
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, 'Welcome back!')
            
            # Check user type and redirect accordingly
            try:
                if hasattr(user, 'supplier'):
                    return redirect('supplier_dashboard')
                elif hasattr(user, 'deliveryboy'):
                    return redirect('delivery_dashboard')
                else:
                    return redirect('home')
            except:
                return redirect('home')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/login.html')

def delivery_register(request):
    if request.method == 'POST':
        form = DeliveryBoyRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            delivery_boy = DeliveryBoy.objects.create(
                user=user,
                phone=form.cleaned_data['phone'],
                address=form.cleaned_data['address'],
                vehicle_number=form.cleaned_data.get('vehicle_number', '')
            )
            messages.success(request, 'Registration successful! Please wait for admin approval.')
            return redirect('delivery_login')
    else:
        form = DeliveryBoyRegistrationForm()
    
    return render(request, 'store/delivery/register.html', {'form': form})

def delivery_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None and hasattr(user, 'deliveryboy'):
            login(request, user)
            return redirect('delivery_dashboard')
        else:
            messages.error(request, 'Invalid credentials or not a delivery person.')
    
    return render(request, 'store/delivery/login.html')

@login_required
def delivery_dashboard(request):
    try:
        delivery_boy = DeliveryBoy.objects.get(user=request.user)
        delivery_assignments = DeliveryAssignment.objects.filter(delivery_boy=delivery_boy)
        
        # Get counts for different statuses
        pending_count = delivery_assignments.filter(status='assigned').count()
        active_count = delivery_assignments.filter(status__in=['picked_up', 'in_transit']).count()
        completed_count = delivery_assignments.filter(status='delivered').count()
        
        # Get unread message count
        unread_messages = DeliveryChat.objects.filter(
            delivery_boy=delivery_boy,
            is_read=False,
            is_from_customer=True  # Only count messages from customers
        ).count()
        
        context = {
            'delivery_boy': delivery_boy,
            'delivery_assignments': delivery_assignments.order_by('-assigned_at')[:5],  # Show last 5 assignments
            'pending_count': pending_count,
            'active_count': active_count,
            'completed_count': completed_count,
            'unread_messages': unread_messages,
        }
        return render(request, 'store/delivery/dashboard.html', context)
    except DeliveryBoy.DoesNotExist:
        messages.error(request, 'You are not authorized to access this page.')
        return redirect('home')

@login_required
def delivery_orders(request):
    try:
        delivery_boy = DeliveryBoy.objects.get(user=request.user)
        delivery_assignments = DeliveryAssignment.objects.filter(delivery_boy=delivery_boy)
        
        # Filter assignments by status if provided
        status = request.GET.get('status')
        if status:
            delivery_assignments = delivery_assignments.filter(status=status)
        
        context = {
            'delivery_boy': delivery_boy,
            'delivery_assignments': delivery_assignments.order_by('-assigned_at'),
            'current_status': status
        }
        return render(request, 'store/delivery/orders.html', context)
    except DeliveryBoy.DoesNotExist:
        messages.error(request, 'You are not authorized to access this page.')
        return redirect('home')

@login_required
def toggle_delivery_availability(request):
    if request.method == 'POST':
        try:
            delivery_boy = DeliveryBoy.objects.get(user=request.user)
            delivery_boy.is_available = not delivery_boy.is_available
            delivery_boy.save()
            
            status = 'available' if delivery_boy.is_available else 'offline'
            messages.success(request, f'You are now {status}')
            
            return redirect('delivery_dashboard')
        except DeliveryBoy.DoesNotExist:
            messages.error(request, 'You are not authorized to perform this action.')
            return redirect('home')
    return redirect('delivery_dashboard')

@login_required
def delivery_login(request):
    if request.user.is_authenticated:
        try:
            delivery_boy = DeliveryBoy.objects.get(user=request.user)
            if not delivery_boy.is_approved:
                messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
                logout(request)
            else:
                return redirect('delivery_dashboard')
        except DeliveryBoy.DoesNotExist:
            messages.error(request, 'This login is only for delivery personnel.')
            logout(request)
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            try:
                delivery_boy = DeliveryBoy.objects.get(user=user)
                if not delivery_boy.is_approved:
                    messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
                else:
                    login(request, user)
                    return redirect('delivery_dashboard')
            except DeliveryBoy.DoesNotExist:
                messages.error(request, 'This login is only for delivery personnel.')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/delivery/login.html')

@login_required
def delivery_dashboard(request):
    try:
        delivery_boy = DeliveryBoy.objects.get(user=request.user)
        delivery_assignments = DeliveryAssignment.objects.filter(delivery_boy=delivery_boy)
        
        # Get counts for dashboard
        pending_count = delivery_assignments.filter(status='assigned').count()
        active_count = delivery_assignments.filter(status__in=['picked_up', 'in_transit']).count()
        completed_count = delivery_assignments.filter(status='delivered').count()
        
        # Get unread message count
        unread_messages = DeliveryChat.objects.filter(
            delivery_boy=delivery_boy,
            is_read=False,
            is_from_customer=True  # Only count messages from customers
        ).count()
        
        context = {
            'delivery_boy': delivery_boy,
            'delivery_assignments': delivery_assignments.order_by('-assigned_at')[:5],  # Show last 5 assignments
            'pending_count': pending_count,
            'active_count': active_count,
            'completed_count': completed_count,
            'unread_messages': unread_messages,
        }
        return render(request, 'store/delivery/dashboard.html', context)
    except DeliveryBoy.DoesNotExist:
        messages.error(request, 'You are not authorized to access this page.')
        return redirect('home')

@login_required
def update_delivery_status(request, assignment_id):
    if not hasattr(request.user, 'deliveryboy'):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    assignment = get_object_or_404(DeliveryAssignment, id=assignment_id, delivery_boy=request.user.deliveryboy)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        notes = request.POST.get('notes', '')
        
        if new_status in dict(DeliveryAssignment.STATUS_CHOICES):
            old_status = assignment.status
            assignment.status = new_status
            
            # Status-specific updates
            if new_status == 'picked_up':
                assignment.picked_up_at = timezone.now()
                customer_msg = f'Your order #{assignment.order.id} has been picked up by {assignment.delivery_boy.name}'
                admin_msg = f'Order #{assignment.order.id} picked up by {assignment.delivery_boy.name}'
            
            elif new_status == 'in_transit':
                customer_msg = f'Your order #{assignment.order.id} is on the way!'
                admin_msg = f'Order #{assignment.order.id} is in transit'
                
            elif new_status == 'delivered':
                assignment.delivered_at = timezone.now()
                assignment.delivery_boy.total_deliveries += 1
                assignment.delivery_boy.save()
                
                # Update order status
                assignment.order.status = 'delivered'
                assignment.order.save()
                
                # Update daily report
                report, _ = DeliveryBoyReport.objects.get_or_create(
                    delivery_boy=assignment.delivery_boy,
                    date=timezone.now().date()
                )
                report.orders_delivered += 1
                report.save()
                
                customer_msg = f'Your order #{assignment.order.id} has been delivered!'
                admin_msg = f'Order #{assignment.order.id} delivered by {assignment.delivery_boy.name}'
            
            else:
                customer_msg = f'Your order #{assignment.order.id} status has been updated to {new_status}'
                admin_msg = f'Order #{assignment.order.id} status updated to {new_status}'
            
            # Add notes if provided
            if notes:
                customer_msg += f'\nNote: {notes}'
                admin_msg += f'\nNote: {notes}'
            
            # Create notifications
            # For customer
            Notification.objects.create(
                recipient=assignment.order.user,
                type='order_status',
                title=f'Order #{assignment.order.id} Update',
                message=customer_msg
            )
            
            # For admin
            admin_users = User.objects.filter(is_superuser=True)
            for admin in admin_users:
                Notification.objects.create(
                    recipient=admin,
                    type='delivery_status',
                    title=f'Delivery Status Update',
                    message=admin_msg
                )
            
            assignment.save()
            
            return JsonResponse({
                'success': True,
                'message': f'Status updated to {new_status}',
                'customerNotified': True,
                'adminNotified': True
            })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def order_detail(request, order_id):
    try:
        if hasattr(request.user, 'deliveryboy'):
            order = Order.objects.get(
                id=order_id,
                delivery_assignment__delivery_boy=request.user.deliveryboy
            )
        else:
            order = Order.objects.get(id=order_id, user=request.user)
            
        return render(request, 'store/order_detail.html', {'order': order})
    except Order.DoesNotExist:
        messages.error(request, 'Order not found.')
        return redirect('home')

def delivery_login(request):
    if request.user.is_authenticated:
        if hasattr(request.user, 'deliveryboy'):
            return redirect('delivery_dashboard')
        logout(request)  # Logout if not a delivery boy
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            try:
                delivery_boy = DeliveryBoy.objects.get(user=user)
                if not delivery_boy.is_approved:
                    messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
                else:
                    login(request, user)
                    return redirect('delivery_dashboard')
            except DeliveryBoy.DoesNotExist:
                messages.error(request, 'This login is only for delivery personnel.')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'store/delivery_login.html')
