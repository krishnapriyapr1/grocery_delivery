import stripe
import json
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, reverse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Cart, Order, OrderItem
from .utils import send_order_confirmation

stripe.api_key = settings.STRIPE_SECRET_KEY

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
                
                # Get shipping details from session
                shipping_details = request.session.get('shipping_details', {})
                
                # Create order with shipping details
                order = Order.objects.create(
                    user=request.user,
                    name=shipping_details.get('name', request.user.get_full_name() or request.user.username),
                    email=shipping_details.get('email', request.user.email),
                    phone=shipping_details.get('phone', request.user.userprofile.phone if hasattr(request.user, 'userprofile') else ''),
                    address=shipping_details.get('address', ''),
                    city=shipping_details.get('city', ''),
                    postal_code=shipping_details.get('postal_code', ''),
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
                
                # Clear the cart and shipping details after successful order
                cart.delete()
                if 'shipping_details' in request.session:
                    del request.session['shipping_details']
                
                # Send confirmation email
                send_order_confirmation(order)
                
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
